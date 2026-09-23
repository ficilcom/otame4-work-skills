#!/usr/bin/env python3
"""Total what an otameshi trial costs the company, cash and staff time apart.

候補者への支払い、企業担当者の工数、掲載料などの周辺費用を別々に合計し、
現金で出る額と、社内工数を金額化した額を分けて示し、予算と突き合わせる。
確認していない金額や相場は補わず、欠けたまま返す。採用の成否は判定しない。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_choice,
    optional_number,
    optional_text,
    require_list,
    require_object,
    require_text,
    round_hours,
    round_yen,
    run_cli,
)


TRIAL_KINDS = ("paid_work", "learning_visit", "unknown")
PAY_BASIS = ("hourly", "fixed", "none", "unknown")
# 金額の出所。`official` は公式の料金表示や見積書、`estimate` は社内の見込み。
AMOUNT_SOURCES = ("official", "quote", "estimate", "unknown")
CONFIRMED_SOURCES = ("official", "quote")


def parse_candidate_pay(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "candidate_pay")
    low = optional_number(block.get("hours"), "candidate_pay.hours")
    high = optional_number(block.get("hours_max"), "candidate_pay.hours_max")
    if high is not None and low is None:
        raise ValueError("candidate_pay.hours_max needs candidate_pay.hours")
    if high is not None and high < low:
        raise ValueError("candidate_pay.hours_max must not be below candidate_pay.hours")
    return {
        "basis": optional_choice(block.get("basis"), "candidate_pay.basis", PAY_BASIS, "unknown"),
        "hourly_rate": optional_number(block.get("hourly_rate"), "candidate_pay.hourly_rate", allow_zero=False),
        "fixed_amount": optional_number(block.get("fixed_amount"), "candidate_pay.fixed_amount", allow_zero=False),
        "hours": low,
        "hours_max": high,
        "expenses": optional_number(block.get("expenses"), "candidate_pay.expenses"),
    }


def parse_company_hours(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "company_hours")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"company_hours[{index}]"
        item = require_object(entry, path)
        parsed.append(
            {
                "role": require_text(item.get("role"), f"{path}.role"),
                "hours": optional_number(item.get("hours"), f"{path}.hours"),
                # 社内で使っている時間あたりの原価。入っていなければ金額化しない。
                "hourly_cost": optional_number(item.get("hourly_cost"), f"{path}.hourly_cost", allow_zero=False),
            }
        )
    return parsed


def parse_other_costs(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "other_costs")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"other_costs[{index}]"
        item = require_object(entry, path)
        parsed.append(
            {
                "label": require_text(item.get("label"), f"{path}.label"),
                "amount": optional_number(item.get("amount"), f"{path}.amount"),
                "source": optional_choice(item.get("source"), f"{path}.source", AMOUNT_SOURCES, "unknown"),
                "note": optional_text(item.get("note"), f"{path}.note"),
            }
        )
    return parsed


def parse_budget(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    block = require_object(raw, "budget")
    return {
        "amount": optional_number(block.get("amount"), "budget.amount"),
        # 予算が社内工数の金額化まで含むかどうか。含まないなら現金の額と比べる。
        "includes_company_hours": optional_bool(
            block.get("includes_company_hours"), "budget.includes_company_hours"
        ),
    }


def parse_alternatives(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "alternatives")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"alternatives[{index}]"
        item = require_object(entry, path)
        parsed.append(
            {
                "label": require_text(item.get("label"), f"{path}.label"),
                "amount": optional_number(item.get("amount"), f"{path}.amount"),
                "source": optional_choice(item.get("source"), f"{path}.source", AMOUNT_SOURCES, "unknown"),
            }
        )
    return parsed


def build_candidate_pay(pay: dict[str, Any]) -> dict[str, Any]:
    low = high = None
    hours_high = pay["hours_max"] if pay["hours_max"] is not None else pay["hours"]
    if pay["basis"] == "hourly" and pay["hourly_rate"] is not None and pay["hours"] is not None:
        low = pay["hourly_rate"] * pay["hours"]
        high = pay["hourly_rate"] * hours_high
    elif pay["basis"] == "fixed" and pay["fixed_amount"] is not None:
        low = high = pay["fixed_amount"]
    elif pay["basis"] == "none":
        low = high = Decimal(0)
    return {
        "basis": pay["basis"],
        "hours_min": round_hours(pay["hours"]),
        "hours_max": round_hours(hours_high),
        "pay_min": round_yen(low),
        "pay_max": round_yen(high),
        "expenses": round_yen(pay["expenses"]),
        "_pay": (low, high),
    }


def build_company_hours(entries: list[dict[str, Any]]) -> dict[str, Any]:
    known = [entry for entry in entries if entry["hours"] is not None]
    total = sum((entry["hours"] for entry in known), Decimal(0)) if known else None
    # 金額化は、すべての役割に工数と原価が入っているときだけ行う。一部だけの金額化は
    # 社内工数を小さく見せるので、見積もりや原価が欠けた役割があれば None のままにする。
    costed = None
    if known and len(known) == len(entries) and all(entry["hourly_cost"] is not None for entry in known):
        costed = sum((entry["hours"] * entry["hourly_cost"] for entry in known), Decimal(0))
    return {
        "total_hours": round_hours(total),
        "by_role": [
            {
                "role": entry["role"],
                "hours": round_hours(entry["hours"]),
                "hourly_cost": round_yen(entry["hourly_cost"]),
                "cost": round_yen(entry["hours"] * entry["hourly_cost"])
                if entry["hours"] is not None and entry["hourly_cost"] is not None
                else None,
            }
            for entry in entries
        ],
        "unestimated_roles": [entry["role"] for entry in entries if entry["hours"] is None],
        "uncosted_roles": [
            entry["role"] for entry in entries if entry["hours"] is not None and entry["hourly_cost"] is None
        ],
        "internal_cost": round_yen(costed),
        "_internal_cost": costed,
    }


def build_other_costs(entries: list[dict[str, Any]]) -> dict[str, Any]:
    confirmed = [entry for entry in entries if entry["amount"] is not None and entry["source"] in CONFIRMED_SOURCES]
    estimated = [entry for entry in entries if entry["amount"] is not None and entry["source"] not in CONFIRMED_SOURCES]
    unknown = [entry for entry in entries if entry["amount"] is None]
    confirmed_total = sum((entry["amount"] for entry in confirmed), Decimal(0))
    estimated_total = sum((entry["amount"] for entry in estimated), Decimal(0))
    return {
        "items": [
            {
                "label": entry["label"],
                "amount": round_yen(entry["amount"]),
                "source": entry["source"],
                "confirmed": entry["source"] in CONFIRMED_SOURCES and entry["amount"] is not None,
                "note": entry["note"],
            }
            for entry in entries
        ],
        "confirmed_total": round_yen(confirmed_total),
        "estimated_total": round_yen(estimated_total),
        "unknown_amounts": [entry["label"] for entry in unknown],
        "_total": confirmed_total + estimated_total,
        "_has_unknown": bool(unknown),
    }


def build_totals(
    candidate: dict[str, Any],
    company: dict[str, Any],
    other: dict[str, Any],
    budget: dict[str, Any] | None,
) -> dict[str, Any]:
    pay_low, pay_high = candidate["_pay"]
    expenses = Decimal(candidate["expenses"]) if candidate["expenses"] is not None else Decimal(0)

    expenses_known = candidate["expenses"] is not None
    cash_low = cash_high = None
    if pay_low is not None:
        cash_low = pay_low + expenses + other["_total"]
        cash_high = pay_high + expenses + other["_total"]

    with_internal_low = with_internal_high = None
    if cash_low is not None and company["_internal_cost"] is not None:
        with_internal_low = cash_low + company["_internal_cost"]
        with_internal_high = cash_high + company["_internal_cost"]

    comparison = None
    if budget is not None and budget["amount"] is not None:
        scope = budget["includes_company_hours"]
        # 予算が社内工数まで含むかが決まるまで、どちらの額とも比べない。
        basis = None if scope is None else ("with_internal_cost" if scope else "cash")
        compared = (
            None
            if basis is None
            else (with_internal_high if basis == "with_internal_cost" else cash_high)
        )
        over = (
            None
            if compared is None or other["_has_unknown"] or not expenses_known
            else compared > budget["amount"]
        )
        comparison = {
            "budget": round_yen(budget["amount"]),
            "compared_on": basis,
            "compared_amount": round_yen(compared),
            "over": over,
            "gap": round_yen(compared - budget["amount"]) if compared is not None and over is not None else None,
            "decidable": over is not None,
        }

    return {
        "cash_min": round_yen(cash_low),
        "cash_max": round_yen(cash_high),
        "cash_is_complete": cash_low is not None and not other["_has_unknown"] and expenses_known,
        "with_internal_cost_min": round_yen(with_internal_low),
        "with_internal_cost_max": round_yen(with_internal_high),
        "budget": comparison,
    }


def collect_flags(
    kind: str,
    candidate: dict[str, Any],
    company: dict[str, Any],
    other: dict[str, Any],
    totals: dict[str, Any],
    alternatives: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags, add = flag_collector("items")

    if candidate["basis"] == "unknown":
        add("candidate_pay_unknown", "候補者への支払いの決め方が未定である。相場で埋めず、現金の総額を出していない")
    elif candidate["basis"] == "hourly" and candidate["pay_max"] is None:
        add("candidate_pay_incomplete", "時間単価か実働が入っていない。現金の総額を出していない")
    elif candidate["basis"] == "fixed" and candidate["pay_max"] is None:
        add("candidate_pay_incomplete", "固定額が入っていない。現金の総額を出していない")
    if kind == "paid_work" and candidate["basis"] == "none":
        add("paid_work_without_pay", "有償業務なのに候補者への支払いがない。実務は経験にかかわらず有償枠にする")

    if candidate["expenses"] is None and candidate["basis"] != "none":
        add("candidate_expenses_unknown", "候補者の経費（交通費など）の扱いが入っていない。負担しないなら 0 と書く")

    if company["total_hours"] is None:
        add("company_hours_missing", "企業担当者の工数が入っていない。説明・レビュー・振り返りの時間を見積もり、社内説明に入れる")
    elif company["unestimated_roles"]:
        add(
            "company_hours_incomplete",
            "工数が入っていない役割がある。合計は入力済みの役割だけの値で、金額化と予算との比較は保留にしている",
            company["unestimated_roles"],
        )
    elif company["internal_cost"] is None:
        add(
            "company_hours_not_costed",
            "社内工数を金額化していない。原価の基準が社内にあれば入れ、なければ時間のまま示す",
            company["uncosted_roles"] or None,
        )

    if other["unknown_amounts"]:
        add("other_costs_unknown", "金額が未確認の費用がある。現金の総額を確定額として示さない", other["unknown_amounts"])
    estimated = [item["label"] for item in other["items"] if item["amount"] is not None and not item["confirmed"]]
    if estimated:
        add("other_costs_estimated", "社内の見込みで置いた費用がある。公式の料金や見積書で確認してから確定額にする", estimated)

    budget = totals["budget"]
    if budget is None:
        add("budget_not_set", "予算が入っていない。既存の枠がなく申請額を決める資料なら、現金の額を申請額として示す")
    elif budget["compared_on"] is None:
        add(
            "budget_scope_unknown",
            "予算が社内工数の金額化まで含むかが入っていない。決まるまで予算に収まるかを判定していない",
        )
    elif budget["decidable"] is False:
        add("budget_undecidable", "支払い・費用に未確定があるため、予算に収まるかを判定していない")
    elif budget["over"] is True:
        add("over_budget", "総額が予算を超える。範囲を減らす案、予算を増やす案を並べる。期間だけ延ばしても総額は減らない")

    unverified = [alt["label"] for alt in alternatives if alt["amount"] is None or alt["source"] not in CONFIRMED_SOURCES]
    if unverified:
        add(
            "alternatives_unverified",
            "比較対象の費用が確認済みでない。公式の料金や見積書がない選択肢は、金額を並べずに名前だけ挙げる",
            unverified,
        )

    return flags


def summarize(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    trial = require_object(data.get("trial", {}) or {}, "trial")
    kind = optional_choice(trial.get("kind"), "trial.kind", TRIAL_KINDS, "unknown")

    candidate = build_candidate_pay(parse_candidate_pay(data.get("candidate_pay")))
    company = build_company_hours(parse_company_hours(data.get("company_hours")))
    other = build_other_costs(parse_other_costs(data.get("other_costs")))
    budget = parse_budget(data.get("budget"))
    alternatives = parse_alternatives(data.get("alternatives"))
    totals = build_totals(candidate, company, other, budget)
    flags = collect_flags(kind, candidate, company, other, totals, alternatives)

    return {
        "as_of": optional_text(data.get("as_of"), "as_of"),
        "trial": {"label": optional_text(trial.get("label"), "trial.label"), "kind": kind},
        "candidate_pay": {key: value for key, value in candidate.items() if not key.startswith("_")},
        "company_hours": {key: value for key, value in company.items() if not key.startswith("_")},
        "other_costs": {key: value for key, value in other.items() if not key.startswith("_")},
        "totals": totals,
        "alternatives": [
            {
                "label": alt["label"],
                "amount": round_yen(alt["amount"]) if alt["source"] in CONFIRMED_SOURCES else None,
                "source": alt["source"],
                "comparable": alt["amount"] is not None and alt["source"] in CONFIRMED_SOURCES,
            }
            for alt in alternatives
        ],
        "flags": flags,
    }


if __name__ == "__main__":
    raise SystemExit(run_cli(summarize, __doc__))
