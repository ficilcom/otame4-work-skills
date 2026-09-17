#!/usr/bin/env python3
"""Check an otameshi listing draft for what a candidate needs before applying.

募集文の下書きについて、応募の判断に必要な項目が書かれているかを項目ごとに数え、
本文の中の範囲が閉じていない表現、無償の実務、採用の保証、職務と無関係な属性の
記載を見つけ、計画の数字（実働・期間・報酬・予算）が同時に成立するかを確かめる。
魅力や条件を補わず、欠けている項目は欠けたまま返す。応募が集まるかは判定しない。
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from _common import (
    flag_collector,
    optional_number,
    optional_text,
    require_list,
    require_object,
    require_raw_text,
    round_yen,
    run_cli,
)


LISTING_KINDS = ("paid_work", "learning_visit", "unknown")
AUDIENCES = ("experienced", "inexperienced", "any", "unknown")
# 原稿がどの段階か。判定には使わず、報告で下書きを新規案にするか修正案にするかを分けるための情報。
STAGES = ("internal_draft", "ready_to_post", "published", "unknown")
ITEM_STATUSES = ("stated", "missing", "unclear", "unknown")
COMPENSATION_BASIS = ("hourly", "fixed", "none", "unknown")
AGREEMENT_STATES = ("internal_draft", "offered", "candidate_request", "mutual", "unconfirmed")
INTERNAL_ONLY = ("internal_draft", "unconfirmed")

# (code, label, group, required_for)
# required_for は、その項目がないと候補者が応募を判断できない募集の種類。
CHECKLIST: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("work_content", "任せる作業の内容と対象（何を、いくつ）", "work", ("paid_work", "learning_visit")),
    ("deliverable", "成果物または実施内容と完了基準", "work", ("paid_work",)),
    ("out_of_scope", "対象外の作業", "work", ("paid_work",)),
    ("experience_required", "必要な経験と使う道具", "work", ("paid_work",)),
    ("support", "企業の支援（説明担当、資料、レビュー）", "support", ("paid_work", "learning_visit")),
    ("contact_role", "受け入れ担当者の役割", "support", ()),
    ("hours", "実働の見込み（合計時間）", "time", ("paid_work", "learning_visit")),
    ("schedule", "期間、週の稼働、実施する時間帯", "time", ("paid_work", "learning_visit")),
    ("location", "実施場所とリモートの可否", "time", ("paid_work", "learning_visit")),
    ("compensation", "報酬の有無と基準（時間単価・固定額・無償）", "money", ("paid_work", "learning_visit")),
    ("expenses", "交通費・経費の扱い", "money", ("learning_visit",)),
    ("contract_form", "契約形態", "money", ("paid_work",)),
    ("payment_timing", "支払時期と支払主体", "money", ("paid_work",)),
    ("selection_process", "応募後の流れと開始までの目安", "process", ()),
    ("after_trial", "体験後の扱い（採用や継続を保証しないこと）", "process", ()),
    ("confidentiality", "秘密情報の扱い", "process", ()),
)
CHECKLIST_CODES = {code for code, _, _, _ in CHECKLIST}

# 本文の表現の検査。(code, pattern, message, severity, kinds)
# severity は `block`（掲載前に直す）/ `check`（確認して残すか決める）。
# kinds は対象になる募集の種類。空なら常に見る。
TEXT_CHECKS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "open_ended_scope",
        r"納得(?:いく|する|できる)まで|応相談|随時|柔軟に対応|臨機応変|一式|その他付随|付随する業務|都度相談",
        "範囲や回数が閉じていない表現がある。候補者は仕事量を見積もれない",
        "block",
        (),
    ),
    (
        "ceiling_expression",
        r"最大|まで可能|まで支給",
        "上限の表現がある。実際に適用される条件を本文に書く",
        "check",
        (),
    ),
    (
        "unpaid_company_work",
        r"無償で実務|無償で業務|無料で実務|無給|ボランティアとして|報酬なしで(?:実務|業務|納品)",
        "企業の実務を無償で求める表現がある。実務は経験にかかわらず有償枠にする",
        "block",
        (),
    ),
    (
        "hiring_guarantee",
        r"採用(?:を)?確約|必ず採用|内定(?:を)?保証|採用保証|全員採用|体験後(?:は|に)(?:必ず)?採用|継続(?:を)?(?:確約|保証)",
        "採用や継続を保証する表現がある。体験後の判断は双方に残す",
        "block",
        (),
    ),
    (
        "personal_attribute",
        r"男性(?:限定|のみ|歓迎)|女性(?:限定|のみ|歓迎)|\d{2}歳(?:以下|以上|まで|未満)|\d0代(?:まで|以下|限定|歓迎|の方)|若い方|主婦|主夫|既婚|未婚|国籍",
        "職務と無関係な属性で応募者を絞る表現がある。募集の表現に関する公的資料を確認し、職務要件に置き換える",
        "block",
        (),
    ),
    (
        "unverifiable_claim",
        r"No\.?\s?1|ナンバーワン|日本一|業界最(?:大|高|速)|圧倒的",
        "根拠を示せない訴求がある。出典を添えるか外す",
        "check",
        (),
    ),
    (
        "learning_visit_does_company_work",
        r"納品|実案件|顧客対応|お客様対応|売上|ノルマ|実務を担当|実際の(?:注文|業務|案件)を処理",
        "無償の見学・学習の募集に企業の実務が入っている。実務にするなら有償業務として設計し直す",
        "block",
        ("learning_visit",),
    ),
    (
        "unpaid_as_prerequisite",
        r"無償(?:体験|参加|で体験)|無料(?:体験|で体験)|まずは無償|最初は無料",
        "有償業務の募集に無償の体験が入っている。企業の実務は有償で書き、無償体験を応募の前提にしない",
        "block",
        ("paid_work",),
    ),
)

HOUR = Decimal("0.01")


def as_hours(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(HOUR))


def parse_choice(value: object, path: str, allowed: tuple[str, ...], default: str) -> str:
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{path} must be one of {list(allowed)}")
    return str(value)


def parse_listing(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "listing")
    text = block.get("text")
    return {
        "kind": parse_choice(block.get("kind"), "listing.kind", LISTING_KINDS, "unknown"),
        "audience": parse_choice(block.get("audience"), "listing.audience", AUDIENCES, "unknown"),
        "stage": parse_choice(block.get("stage"), "listing.stage", STAGES, "unknown"),
        # 本文は原文のまま扱う。前後の空白も含めて掲載されるため strip しない。
        "text": None if text is None else require_raw_text(text, "listing.text"),
    }


def parse_items(raw: object) -> dict[str, dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "items")
    parsed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        path = f"items[{index}]"
        item = require_object(entry, path)
        code = item.get("code")
        if code not in CHECKLIST_CODES:
            raise ValueError(f"{path}.code is not a known checklist code: {code!r}")
        if code in parsed:
            raise ValueError(f"{path}.code is duplicated: {code!r}")
        parsed[str(code)] = {
            "status": parse_choice(item.get("status"), f"{path}.status", ITEM_STATUSES, "unknown"),
            "note": optional_text(item.get("note"), f"{path}.note"),
        }
    return parsed


def parse_plan(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    block = require_object(raw, "plan")
    low = optional_number(block.get("candidate_hours"), "plan.candidate_hours")
    high = optional_number(block.get("candidate_hours_max"), "plan.candidate_hours_max")
    if high is not None and low is None:
        raise ValueError("plan.candidate_hours_max needs plan.candidate_hours")
    if high is not None and high < low:
        raise ValueError("plan.candidate_hours_max must not be below plan.candidate_hours")
    compensation = require_object(block.get("compensation", {}) or {}, "plan.compensation")
    return {
        "candidate_hours": low,
        "candidate_hours_max": high,
        "weekly_hours": optional_number(block.get("weekly_hours"), "plan.weekly_hours", allow_zero=False),
        "period_weeks": optional_number(block.get("period_weeks"), "plan.period_weeks", allow_zero=False),
        "basis": parse_choice(
            compensation.get("basis"), "plan.compensation.basis", COMPENSATION_BASIS, "unknown"
        ),
        "hourly_rate": optional_number(
            compensation.get("hourly_rate"), "plan.compensation.hourly_rate", allow_zero=False
        ),
        "fixed_amount": optional_number(
            compensation.get("fixed_amount"), "plan.compensation.fixed_amount", allow_zero=False
        ),
        "budget": optional_number(block.get("budget"), "plan.budget"),
    }


def parse_conditions(raw: object) -> list[dict[str, Any]]:
    conditions = []
    for index, entry in enumerate(require_list(raw if raw is not None else [], "conditions")):
        path = f"conditions[{index}]"
        item = require_object(entry, path)
        conditions.append(
            {
                "topic": require_raw_text(item.get("topic"), f"{path}.topic").strip(),
                "agreement": parse_choice(
                    item.get("agreement"), f"{path}.agreement", AGREEMENT_STATES, "unconfirmed"
                ),
            }
        )
    return conditions


def build_checklist(kind: str, items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checklist = []
    for code, label, group, required_for in CHECKLIST:
        entry = items.get(code)
        # 募集の種類が未定なら、どちらかで必須の項目はすべて必須として扱う。
        required = kind in required_for if kind != "unknown" else bool(required_for)
        checklist.append(
            {
                "code": code,
                "label": label,
                "group": group,
                "required": required,
                "status": entry["status"] if entry else "unknown",
                "note": entry["note"] if entry else None,
            }
        )
    return checklist


def scan_text(text: str | None, kind: str) -> list[dict[str, Any]]:
    """本文の表現を検査する。一致した箇所は短く切って返し、本文全体は出力に載せない。"""
    if text is None:
        return []
    findings = []
    for code, pattern, message, severity, kinds in TEXT_CHECKS:
        if kinds and kind not in kinds:
            continue
        matches = [match.group(0) for match in re.finditer(pattern, text)]
        if matches:
            unique = list(dict.fromkeys(matches))
            findings.append(
                {"code": code, "severity": severity, "message": message, "matched": unique}
            )
    return findings


def build_numbers(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """計画の数字が同時に成立するかを確かめる。欠けている数字は None のままにする。"""
    if plan is None:
        return None
    low = plan["candidate_hours"]
    high = plan["candidate_hours_max"] if plan["candidate_hours_max"] is not None else low

    capacity = None
    if plan["weekly_hours"] is not None and plan["period_weeks"] is not None:
        capacity = plan["weekly_hours"] * plan["period_weeks"]
    fits_period = None
    if capacity is not None and high is not None:
        fits_period = high <= capacity

    cost_low = cost_high = None
    if plan["basis"] == "hourly" and plan["hourly_rate"] is not None and low is not None:
        cost_low = plan["hourly_rate"] * low
        cost_high = plan["hourly_rate"] * high
    elif plan["basis"] == "fixed" and plan["fixed_amount"] is not None:
        cost_low = cost_high = plan["fixed_amount"]
    elif plan["basis"] == "none":
        cost_low = cost_high = Decimal(0)

    budget = plan["budget"]
    over = None
    if budget is not None and cost_high is not None:
        over = cost_high > budget

    return {
        "candidate_hours_min": as_hours(low),
        "candidate_hours_max": as_hours(high),
        "period_capacity_hours": as_hours(capacity),
        "fits_period": fits_period,
        "basis": plan["basis"],
        "planned_cost_min": round_yen(cost_low),
        "planned_cost_max": round_yen(cost_high),
        "budget": round_yen(budget),
        "budget_gap": round_yen(cost_high - budget) if over is not None else None,
        "over_budget": over,
    }


def collect_flags(
    listing: dict[str, Any],
    checklist: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    numbers: dict[str, Any] | None,
    conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags, add = flag_collector("items")

    if listing["kind"] == "unknown":
        add("listing_kind_unknown", "有償業務か無償の見学・学習かが決まっていない。必須項目をどちらの基準でも見ている")

    if listing["text"] is None:
        add("text_missing", "本文が入っていない。表現の検査をしていない")

    missing = [item["code"] for item in checklist if item["required"] and item["status"] == "missing"]
    if missing:
        add("required_items_missing", "候補者が応募を判断するのに必要な項目が書かれていない", missing)
    unclear = [item["code"] for item in checklist if item["required"] and item["status"] == "unclear"]
    if unclear:
        add("required_items_unclear", "書いてはあるが読み取れない必須項目がある。具体的な数字や範囲に直す", unclear)
    unknown = [item["code"] for item in checklist if item["required"] and item["status"] == "unknown"]
    if unknown:
        add("required_items_unchecked", "確認していない必須項目がある。未確認を「記載なし」にも「記載あり」にも丸めない", unknown)

    blocking = [finding["code"] for finding in findings if finding["severity"] == "block"]
    if blocking:
        add("text_needs_rewrite", "掲載前に直す表現がある", blocking)

    if listing["kind"] == "paid_work":
        after_trial = next(item for item in checklist if item["code"] == "after_trial")
        if after_trial["status"] != "stated":
            add(
                "after_trial_unstated",
                "体験後の扱い（採用や継続を保証しないこと）が書かれていないか未確認である。応募後に必ず聞かれるので本文に書く",
            )

    if listing["audience"] == "inexperienced" and listing["kind"] == "paid_work":
        add(
            "inexperienced_paid_work",
            "未経験者に企業の実務を任せる募集である。有償枠のままにし、支援と説明の時間を本文に書く",
        )

    if numbers is not None:
        if numbers["fits_period"] is False:
            add(
                "hours_exceed_period",
                "実働の合計が、週の稼働×期間に収まらない。範囲を減らすか期間を延ばす。"
                "本文に両方の数字を書くなら同時に成立させる",
            )
        if numbers["over_budget"] is True:
            add(
                "over_budget",
                "予定費用が予算を超える。実働・単価・予算のどれかを変えるまで、3つを同時に本文に書かない",
            )
        if numbers["basis"] == "unknown":
            add("compensation_basis_unknown", "報酬の決め方が未定である。相場で埋めず、確認してから本文に書く")
        if listing["kind"] == "paid_work" and numbers["basis"] == "none":
            add("paid_work_without_pay", "有償業務の募集なのに報酬なしになっている")

    internal = [item["topic"] for item in conditions if item["agreement"] in INTERNAL_ONLY]
    if internal:
        add(
            "conditions_internal_only",
            "社内案・未確認のままの条件がある。確定した条件として本文に書かない",
            internal,
        )

    return flags


def decide_readiness(listing: dict[str, Any], flags: list[dict[str, Any]]) -> dict[str, Any]:
    """掲載前の点検としてどこまで進められるかを返す。掲載の可否そのものは決めない。"""
    blocking_codes = {
        "required_items_missing",
        "required_items_unclear",
        "required_items_unchecked",
        "text_needs_rewrite",
        "hours_exceed_period",
        "over_budget",
        "compensation_basis_unknown",
        "paid_work_without_pay",
        "conditions_internal_only",
        "listing_kind_unknown",
        "text_missing",
    }
    blockers = [flag["code"] for flag in flags if flag["code"] in blocking_codes]
    status = "needs_work" if blockers else "ready_for_owner_review"
    return {
        "stage": listing["stage"],
        "status": status,
        "blockers": blockers,
        # 掲載の操作は利用者が行う。ここでは点検の結果までを返す。
        "posting_is_user_action": True,
    }


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    listing = parse_listing(data.get("listing"))
    items = parse_items(data.get("items"))
    plan = parse_plan(data.get("plan"))
    conditions = parse_conditions(data.get("conditions"))

    checklist = build_checklist(listing["kind"], items)
    findings = scan_text(listing["text"], listing["kind"])
    numbers = build_numbers(plan)
    flags = collect_flags(listing, checklist, findings, numbers, conditions)
    readiness = decide_readiness(listing, flags)

    return {
        "as_of": optional_text(data.get("as_of"), "as_of"),
        "listing": {
            "kind": listing["kind"],
            "audience": listing["audience"],
            "stage": listing["stage"],
            "text_length": len(listing["text"]) if listing["text"] is not None else None,
        },
        "checklist": checklist,
        "text_findings": findings,
        "numbers": numbers,
        "readiness": readiness,
        "flags": flags,
    }


if __name__ == "__main__":
    raise SystemExit(run_cli(check, __doc__))
