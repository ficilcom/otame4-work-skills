#!/usr/bin/env python3
"""Sort a finished otameshi trial into facts, expectations, support, and settlement.

終わったおためし業務について、事前に決めた完了基準と実施後の観察事実を突き合わせ、
後から足した期待、観察者のいない評価、職務と無関係な評価、企業の支援の遅れを分け、
実施済みの実働に対する精算を評価や採用判断とは別に数える。候補者の適性や採用の
成否は判定しない。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_number,
    optional_positive_int,
    optional_text,
    require_list,
    require_object,
    require_text,
    round_yen,
    run_cli,
)


TRIAL_KINDS = ("paid_work", "learning_visit", "unknown")
# 完了基準がどうなったか。`unverified` は確認しなかった、`not_met` は確認して届かなかった。
EXPECTATION_RESULTS = ("met", "partial", "not_met", "unverified")
# 観察の出所。`hearsay` は担当者自身が見ていない伝聞。
OBSERVATION_SOURCES = ("observed", "artifact", "hearsay", "unknown")
SUPPORT_STATUSES = ("provided", "late", "not_provided", "unknown")
COMPENSATION_BASIS = ("hourly", "fixed", "none", "unknown")
NEXT_STEPS = ("continue", "hire_offer", "more_checks", "close", "undecided")


def parse_choice(value: object, path: str, allowed: tuple[str, ...], default: str) -> str:
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{path} must be one of {list(allowed)}")
    return str(value)


def parse_expectations(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "expectations")
    parsed = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"expectations[{index}]"
        item = require_object(entry, path)
        code = require_text(item.get("code"), f"{path}.code")
        if code in seen:
            raise ValueError(f"{path}.code is duplicated: {code!r}")
        seen.add(code)
        agreed = optional_bool(item.get("agreed_before_start"), f"{path}.agreed_before_start")
        parsed.append(
            {
                "code": code,
                "label": require_text(item.get("label"), f"{path}.label"),
                # 未記載は「事前に合意していない」として扱う。後から足した期待を事前の基準に混ぜない。
                "agreed_before_start": bool(agreed),
                "result": parse_choice(item.get("result"), f"{path}.result", EXPECTATION_RESULTS, "unverified"),
                "note": optional_text(item.get("note"), f"{path}.note"),
            }
        )
    return parsed


def parse_observations(raw: object, expectation_codes: set[str]) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "observations")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"observations[{index}]"
        item = require_object(entry, path)
        expectation = optional_text(item.get("expectation"), f"{path}.expectation")
        if expectation is not None and expectation not in expectation_codes:
            raise ValueError(f"{path}.expectation does not match any expectation code: {expectation!r}")
        job_related = optional_bool(item.get("job_related"), f"{path}.job_related")
        parsed.append(
            {
                "fact": require_text(item.get("fact"), f"{path}.fact"),
                "expectation": expectation,
                "source": parse_choice(item.get("source"), f"{path}.source", OBSERVATION_SOURCES, "unknown"),
                "observer": optional_text(item.get("observer"), f"{path}.observer"),
                # 未記載は職務に関係する観察として扱う。属性や私生活に触れるものは入力側で false にする。
                "job_related": True if job_related is None else job_related,
            }
        )
    return parsed


def parse_support(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "support")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"support[{index}]"
        item = require_object(entry, path)
        parsed.append(
            {
                "item": require_text(item.get("item"), f"{path}.item"),
                "status": parse_choice(item.get("status"), f"{path}.status", SUPPORT_STATUSES, "unknown"),
                "delay_days": optional_positive_int(item.get("delay_days"), f"{path}.delay_days"),
                "affected": [
                    require_text(code, f"{path}.affected[{position}]")
                    for position, code in enumerate(require_list(item.get("affected", []) or [], f"{path}.affected"))
                ],
            }
        )
    return parsed


def parse_settlement(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "settlement")
    return {
        "basis": parse_choice(block.get("basis"), "settlement.basis", COMPENSATION_BASIS, "unknown"),
        "hourly_rate": optional_number(block.get("hourly_rate"), "settlement.hourly_rate", allow_zero=False),
        "fixed_amount": optional_number(block.get("fixed_amount"), "settlement.fixed_amount", allow_zero=False),
        "hours_worked": optional_number(block.get("hours_worked"), "settlement.hours_worked"),
        "hours_planned": optional_number(block.get("hours_planned"), "settlement.hours_planned"),
        # 検収の基準が書面にあり、それに沿って減額するか。基準がなければ減額の根拠にならない。
        "acceptance_criteria_in_writing": optional_bool(
            block.get("acceptance_criteria_in_writing"), "settlement.acceptance_criteria_in_writing"
        ),
        "proposed_reduction": optional_number(block.get("proposed_reduction"), "settlement.proposed_reduction"),
        "unpaid_rework_requested": optional_bool(
            block.get("unpaid_rework_requested"), "settlement.unpaid_rework_requested"
        ),
    }


def parse_feedback(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "feedback")
    includes = require_list(block.get("includes", []) or [], "feedback.includes")
    allowed = ("other_candidates", "internal_notes", "continuation_promise", "hire_promise", "facts", "support_gaps")
    for index, item in enumerate(includes):
        if item not in allowed:
            raise ValueError(f"feedback.includes[{index}] must be one of {list(allowed)}")
    return {
        "next_step": parse_choice(block.get("next_step"), "feedback.next_step", NEXT_STEPS, "undecided"),
        "next_step_decided": optional_bool(block.get("next_step_decided"), "feedback.next_step_decided"),
        "includes": [str(item) for item in includes],
    }


def build_expectation_view(
    expectations: list[dict[str, Any]], observations: list[dict[str, Any]], support: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    affected_by = {}
    for entry in support:
        if entry["status"] in ("late", "not_provided"):
            for code in entry["affected"]:
                affected_by.setdefault(code, []).append(entry["item"])
    view = []
    for expectation in expectations:
        linked = [obs for obs in observations if obs["expectation"] == expectation["code"]]
        view.append(
            {
                **expectation,
                "observations": len(linked),
                "first_hand": sum(1 for obs in linked if obs["source"] in ("observed", "artifact")),
                "support_gaps": affected_by.get(expectation["code"], []),
            }
        )
    return view


def build_settlement(settlement: dict[str, Any]) -> dict[str, Any]:
    worked = settlement["hours_worked"]
    due = None
    if settlement["basis"] == "hourly" and settlement["hourly_rate"] is not None and worked is not None:
        due = settlement["hourly_rate"] * worked
    elif settlement["basis"] == "fixed" and settlement["fixed_amount"] is not None:
        due = settlement["fixed_amount"]
    elif settlement["basis"] == "none":
        due = Decimal(0)
    return {
        "basis": settlement["basis"],
        "hours_worked": float(worked) if worked is not None else None,
        "hours_planned": float(settlement["hours_planned"]) if settlement["hours_planned"] is not None else None,
        "amount_for_work_done": round_yen(due),
        "acceptance_criteria_in_writing": settlement["acceptance_criteria_in_writing"],
        "proposed_reduction": round_yen(settlement["proposed_reduction"]),
        "unpaid_rework_requested": settlement["unpaid_rework_requested"],
        # 精算は評価や採用判断と別に扱う。ここに評価の結果を入れない。
        "separate_from_evaluation": True,
    }


def collect_flags(
    kind: str,
    expectations: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    support: list[dict[str, Any]],
    settlement: dict[str, Any],
    feedback: dict[str, Any],
) -> list[dict[str, Any]]:
    flags, add = flag_collector("items")

    if not expectations:
        add("no_expectations", "事前に決めた完了基準が入っていない。観察事実を何と突き合わせるかが決まらない")
    added_later = [item["code"] for item in expectations if not item["agreed_before_start"]]
    if added_later:
        add("expectations_added_later", "事前に合意していない期待がある。事前の基準と分けて書き、評価の根拠にしない", added_later)
    unverified = [item["code"] for item in expectations if item["agreed_before_start"] and item["result"] == "unverified"]
    if unverified:
        add("expectations_unverified", "事前に決めた基準のうち確認しなかったものがある。未確認を未達にしない", unverified)
    not_met_with_gap = [
        item["code"] for item in expectations if item["result"] in ("partial", "not_met") and item["support_gaps"]
    ]
    if not_met_with_gap:
        add(
            "shortfall_with_support_gap",
            "届かなかった基準に、企業の支援の遅れや未提供が関わっている。候補者だけの責任にしない",
            not_met_with_gap,
        )

    if not observations:
        add("no_observations", "観察事実が入っていない。フィードバック案の根拠がない")
    hearsay = [obs["fact"] for obs in observations if obs["source"] in ("hearsay", "unknown")]
    if hearsay:
        add("observations_second_hand", "担当者自身が見ていない、または出所不明の観察がある。誰が何を確認したかを添える", hearsay)
    no_observer = [obs["fact"] for obs in observations if obs["source"] == "observed" and obs["observer"] is None]
    if no_observer:
        add("observer_missing", "観察者が入っていない観察がある", no_observer)
    not_job = [obs["fact"] for obs in observations if not obs["job_related"]]
    if not_job:
        add("observation_not_job_related", "職務と無関係な観察がある。評価にもフィードバックにも使わない", not_job)
    unlinked = [obs["fact"] for obs in observations if obs["expectation"] is None and obs["job_related"]]
    if unlinked:
        add("observations_unlinked", "事前の基準に結びついていない観察がある。基準外の事実として分けて書く", unlinked)

    if kind == "learning_visit":
        met_like = [item["code"] for item in expectations if item["result"] in ("partial", "not_met")]
        if met_like:
            add("learning_visit_judged_on_output", "無償の見学・学習を成果で評価している。学んだこと・質問・理解の振り返りにする", met_like)

    if kind == "paid_work":
        if settlement["basis"] == "unknown":
            add("settlement_basis_unknown", "報酬の決め方が入っていない。実施済みの実働に対する精算額を出していない")
        elif settlement["amount_for_work_done"] is None:
            add("settlement_incomplete", "単価か実働が入っていない。精算額を出していない")
        if settlement["proposed_reduction"] is not None and settlement["proposed_reduction"] > 0:
            if settlement["acceptance_criteria_in_writing"] is not True:
                add(
                    "reduction_without_written_criteria",
                    "書面の検収基準がないのに減額を考えている。実施済みの実働は精算し、成果の評価と分ける",
                )
            else:
                add("reduction_proposed", "減額を考えている。書面の検収基準のどの項目に沿うかを示し、候補者に説明できる形にする")
        if settlement["unpaid_rework_requested"] is True:
            add("unpaid_rework", "無償のやり直しを求めている。合意した修正範囲を超える分は追加の発注にするか、求めない")

    if "other_candidates" in feedback["includes"]:
        add("feedback_mentions_other_candidates", "他候補者の情報をフィードバックに入れない")
    if "internal_notes" in feedback["includes"]:
        add("feedback_includes_internal_notes", "内部の評価メモをフィードバックに入れない。担当者用のメモと分ける")
    if feedback["next_step"] in ("continue", "hire_offer") and feedback["next_step_decided"] is not True:
        add(
            "next_step_not_decided",
            "継続や採用の通知にしようとしているが、企業が決めていない。決めるまで通知にしない",
        )
    if ("continuation_promise" in feedback["includes"] or "hire_promise" in feedback["includes"]) and feedback[
        "next_step_decided"
    ] is not True:
        add("promise_before_decision", "決めていない継続や採用を約束する文面になっている")

    return flags


def decide_readiness(flags: list[dict[str, Any]]) -> dict[str, Any]:
    blocking_codes = {
        "no_expectations",
        "no_observations",
        "observation_not_job_related",
        "reduction_without_written_criteria",
        "unpaid_rework",
        "feedback_mentions_other_candidates",
        "feedback_includes_internal_notes",
        "next_step_not_decided",
        "promise_before_decision",
    }
    blockers = [flag["code"] for flag in flags if flag["code"] in blocking_codes]
    return {
        "status": "needs_work" if blockers else "ready_for_owner_review",
        "blockers": blockers,
        # 送信、精算、採用の判断は利用者が行う。
        "sending_is_user_action": True,
    }


def review(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    trial = require_object(data.get("trial", {}) or {}, "trial")
    kind = parse_choice(trial.get("kind"), "trial.kind", TRIAL_KINDS, "unknown")

    expectations = parse_expectations(data.get("expectations"))
    codes = {item["code"] for item in expectations}
    observations = parse_observations(data.get("observations"), codes)
    support = parse_support(data.get("support"))
    settlement = build_settlement(parse_settlement(data.get("settlement")))
    feedback = parse_feedback(data.get("feedback"))

    expectation_view = build_expectation_view(expectations, observations, support)
    flags = collect_flags(kind, expectation_view, observations, support, settlement, feedback)

    return {
        "as_of": optional_text(data.get("as_of"), "as_of"),
        "trial": {"label": optional_text(trial.get("label"), "trial.label"), "kind": kind},
        "summary": {
            "expectations_agreed_before_start": sum(1 for item in expectation_view if item["agreed_before_start"]),
            "expectations_added_later": sum(1 for item in expectation_view if not item["agreed_before_start"]),
            "met": sum(1 for item in expectation_view if item["agreed_before_start"] and item["result"] == "met"),
            "partial": sum(1 for item in expectation_view if item["agreed_before_start"] and item["result"] == "partial"),
            "not_met": sum(1 for item in expectation_view if item["agreed_before_start"] and item["result"] == "not_met"),
            "unverified": sum(1 for item in expectation_view if item["agreed_before_start"] and item["result"] == "unverified"),
            "observations_first_hand": sum(1 for obs in observations if obs["source"] in ("observed", "artifact")),
            "support_late_or_missing": sum(1 for entry in support if entry["status"] in ("late", "not_provided")),
        },
        "expectations": expectation_view,
        "observations": observations,
        "support": support,
        "settlement": settlement,
        "feedback": feedback,
        "readiness": decide_readiness(flags),
        "flags": flags,
    }


if __name__ == "__main__":
    raise SystemExit(run_cli(review, __doc__))
