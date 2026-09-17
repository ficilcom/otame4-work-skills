#!/usr/bin/env python3
"""Cost an otameshi trial plan: workload, schedule, and what it comes to.

作業別の見積もりから、候補者の実働と企業担当者の工数を別々に合計し、実施期間に
配置したときの週あたりの実働を出し、予定費用を予算と突き合わせる。単価や相場を
補わず、予算に合わせて実働を削らない。採用の成否も候補者の適性も判定しない。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_date,
    optional_number,
    optional_int,
    optional_text,
    require_list,
    require_object,
    require_text,
    round_yen,
    run_cli,
)


# 作業の種類。`company_work` は企業の実務であり、経験にかかわらず有償枠で設計する。
TASK_KINDS = ("learning", "mock", "company_work", "unknown")
COMPANY_WORK = "company_work"

# 報酬の決め方。`unknown` のまま予定費用を出さない。
COMPENSATION_BASIS = ("hourly", "fixed", "unknown")

# 条件がどの段階にあるか。企業の内部案を提示済み・合意済みとして扱わない。
AGREEMENT_STATES = ("internal_draft", "offered", "candidate_request", "mutual", "unconfirmed")
INTERNAL_ONLY = ("internal_draft", "unconfirmed")

DAYS_PER_WEEK = Decimal(7)
HOUR = Decimal("0.01")


def as_hours(value: Decimal | None) -> float | None:
    """時間を0.01単位に丸めて返す。None は None のままにする。"""
    if value is None:
        return None
    return float(value.quantize(HOUR))


def parse_task(raw: object, index: int) -> dict[str, Any]:
    path = f"tasks[{index}]"
    task = require_object(raw, path)

    kind = task.get("kind", "unknown")
    if kind not in TASK_KINDS:
        raise ValueError(f"{path}.kind must be one of {list(TASK_KINDS)}")

    low = optional_number(task.get("candidate_hours"), f"{path}.candidate_hours")
    high = optional_number(task.get("candidate_hours_max"), f"{path}.candidate_hours_max")
    if high is not None and low is None:
        raise ValueError(f"{path}.candidate_hours_max needs {path}.candidate_hours")
    if high is not None and high < low:
        raise ValueError(f"{path}.candidate_hours_max must not be below {path}.candidate_hours")

    return {
        "label": require_text(task.get("label"), f"{path}.label"),
        "kind": kind,
        # 支払い対象かどうか。未記載は「不明」であり、無償と決めつけない。
        "paid": optional_bool(task.get("paid"), f"{path}.paid"),
        "candidate_hours": low,
        "candidate_hours_max": high,
        # 企業担当者の工数。候補者の実働には足さない。合同作業は双方に入れる。
        "company_hours": optional_number(task.get("company_hours"), f"{path}.company_hours"),
    }


def sum_hours(
    tasks: list[dict[str, Any]], key: str, max_key: str | None = None
) -> tuple[Decimal | None, Decimal | None]:
    """入力済みの見積もりだけを合計し、(最小, 最大) を返す。未記入を0で埋めない。"""
    known = [task for task in tasks if task[key] is not None]
    if not known:
        return None, None
    low = sum((task[key] for task in known), Decimal(0))
    if max_key is None:
        return low, low
    high = sum(((task[max_key] or task[key]) for task in known), Decimal(0))
    return low, high


def unestimated(tasks: list[dict[str, Any]]) -> list[str]:
    """どちらの時間も入っていない作業を返す。

    企業単独の作業は `company_hours` だけを持つのが正しい形なので、
    `candidate_hours` が空でも見積もり漏れとして扱わない。
    """
    return [
        task["label"]
        for task in tasks
        if task["candidate_hours"] is None and task["company_hours"] is None
    ]


def parse_period(raw: object) -> dict[str, Any]:
    block = require_object(raw or {}, "plan.period")
    start = optional_date(block.get("start"), "plan.period.start")
    end = optional_date(block.get("end"), "plan.period.end")
    if start is not None and end is not None and end < start:
        raise ValueError("plan.period.end must not be before plan.period.start")

    days = weeks = None
    if start is not None and end is not None:
        days = Decimal((end - start).days + 1)
        weeks = days / DAYS_PER_WEEK

    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "checkpoint": optional_text(block.get("checkpoint"), "plan.period.checkpoint"),
        "calendar_days": int(days) if days is not None else None,
        "weeks": as_hours(weeks),
    }


def parse_compensation(raw: object) -> dict[str, Any]:
    block = require_object(raw or {}, "compensation")
    basis = block.get("basis", "unknown")
    if basis not in COMPENSATION_BASIS:
        raise ValueError(f"compensation.basis must be one of {list(COMPENSATION_BASIS)}")
    return {
        "basis": basis,
        "hourly_rate": optional_number(block.get("hourly_rate"), "compensation.hourly_rate", allow_zero=False),
        "fixed_amount": optional_number(block.get("fixed_amount"), "compensation.fixed_amount", allow_zero=False),
        "expenses_included": optional_bool(block.get("expenses_included"), "compensation.expenses_included"),
        "tax_treatment": optional_text(block.get("tax_treatment"), "compensation.tax_treatment"),
        "payment_date": optional_text(block.get("payment_date"), "compensation.payment_date"),
    }


def parse_conditions(raw: object) -> list[dict[str, Any]]:
    conditions = []
    for index, entry in enumerate(require_list(raw or [], "conditions")):
        path = f"conditions[{index}]"
        item = require_object(entry, path)
        agreement = item.get("agreement", "unconfirmed")
        if agreement not in AGREEMENT_STATES:
            raise ValueError(f"{path}.agreement must be one of {list(AGREEMENT_STATES)}")
        conditions.append(
            {
                "topic": require_text(item.get("topic"), f"{path}.topic"),
                "value": optional_text(item.get("value"), f"{path}.value"),
                "agreement": agreement,
                "basis": optional_text(item.get("basis"), f"{path}.basis"),
            }
        )
    return conditions


def per_hour_range(
    cost_low: Decimal | None,
    cost_high: Decimal | None,
    hours_low: Decimal | None,
    hours_high: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    """予定費用を実働で割り、(下限, 上限) を返す。

    見積もりの下限どうし・上限どうしを組にして割り、小さい方を下限にする。
    固定額の時間換算は比較のための割り算であり、時間単価の契約を意味しない。
    """
    if cost_low is None or hours_low is None or hours_low <= 0:
        return None, None
    at_low = cost_low / hours_low
    at_high = (cost_high or cost_low) / (hours_high if hours_high and hours_high > 0 else hours_low)
    return (at_low, at_high) if at_low <= at_high else (at_high, at_low)


def derive_cost(
    compensation: dict[str, Any],
    paid_low: Decimal | None,
    paid_high: Decimal | None,
    all_low: Decimal | None,
    all_high: Decimal | None,
) -> dict[str, Any]:
    """予定費用と時間換算を出す。基準か実働が欠けていれば None のままにする。

    予定費用は有償と決めた作業だけで出す。時間換算は2通り出す。有償時間で割った
    ものと、**無償の作業も含めた候補者の全実働で割ったもの**である。説明や会議を
    無償枠へ移すほど後者は下がるので、帳尻合わせが数字に表れる。
    """
    basis = compensation["basis"]
    rate = compensation["hourly_rate"]
    fixed = compensation["fixed_amount"]

    cost_low = cost_high = None
    if basis == "hourly" and rate is not None and paid_low is not None:
        cost_low = rate * paid_low
        cost_high = rate * (paid_high if paid_high is not None else paid_low)
    elif basis == "fixed" and fixed is not None:
        cost_low = cost_high = fixed

    paid_hourly_low, paid_hourly_high = per_hour_range(cost_low, cost_high, paid_low, paid_high)
    all_hourly_low, all_hourly_high = per_hour_range(cost_low, cost_high, all_low, all_high)

    return {
        "basis": basis,
        "hourly_rate": round_yen(rate),
        "fixed_amount": round_yen(fixed),
        "planned_cost_min": round_yen(cost_low),
        "planned_cost_max": round_yen(cost_high),
        "effective_hourly_paid_min": round_yen(paid_hourly_low),
        "effective_hourly_paid_max": round_yen(paid_hourly_high),
        "effective_hourly_all_min": round_yen(all_hourly_low),
        "effective_hourly_all_max": round_yen(all_hourly_high),
        "expenses_included": compensation["expenses_included"],
        "tax_treatment": compensation["tax_treatment"],
        "payment_date": compensation["payment_date"],
    }


def collect_flags(
    tasks: list[dict[str, Any]],
    workload: dict[str, Any],
    schedule: dict[str, Any],
    cost: dict[str, Any],
    budget: dict[str, Any] | None,
    revisions: dict[str, Any],
    conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags, add = flag_collector("items")

    unpaid = [task["label"] for task in tasks if task["kind"] == COMPANY_WORK and task["paid"] is False]
    if unpaid:
        add(
            "company_work_unpaid",
            "企業の実務を無償の枠に置いている。未経験を理由に実務を無償化しない",
            unpaid,
        )

    pay_unknown = [task["label"] for task in tasks if task["kind"] == COMPANY_WORK and task["paid"] is None]
    if pay_unknown:
        add("company_work_pay_unknown", "企業の実務だが、有償枠かどうかを決めていない", pay_unknown)

    if workload["unpaid_hours"] is not None and workload["paid_hours_min"] is not None:
        add(
            "unpaid_hours_in_paid_trial",
            f"有償の計画に無償の作業が{workload['unpaid_hours']}時間ある。"
            "説明や必要な会議を無償枠に移して予算を合わせていないかを確認する",
        )

    if workload["candidate_hours_missing"]:
        add(
            "candidate_hours_missing",
            "時間の見積もりが入っていない作業がある。合計は入力済みの作業だけの値である",
            workload["candidate_hours_missing"],
        )

    if workload["company_hours_total"] is None:
        add(
            "company_hours_missing",
            "企業担当者の工数がどの作業にも入っていない。説明・レビュー・振り返りの"
            "時間を確保できるかを別に見積もる",
        )

    if cost["basis"] == "unknown":
        add("compensation_basis_unknown", "報酬の決め方が未定である。予定費用を出していない")
    elif cost["basis"] == "hourly" and cost["hourly_rate"] is None:
        add("hourly_rate_missing", "時間単価が未定である。相場を創作せず、必要時間と単価の確認にする")
    elif cost["basis"] == "fixed" and cost["fixed_amount"] is None:
        add("fixed_amount_missing", "固定額が未定である")

    if cost["expenses_included"] is None or cost["tax_treatment"] is None:
        add("expenses_or_tax_unclear", "経費・税の含み方が未定である。総費用が確定したように見せない")

    if budget is None:
        add("budget_not_set", "予算が入っていない。範囲と費用の突き合わせができない")
    elif budget["decidable"] is False:
        add(
            "budget_undecidable",
            "見積もりか報酬の基準が欠けているため、予算に収まるかを判定していない",
        )
    elif budget["over"] is True:
        add(
            "over_budget",
            "予定費用が予算を超える。範囲を減らす案、予算を増やす案、期間を変える案を並べて"
            "比べる。期間だけ延ばしても総実働と総額は減らない",
        )

    if schedule["weeks"] is None:
        add("period_missing", "実施期間が入っていない。週あたりの実働を出せない")
    elif schedule["fits_candidate_availability"] is False:
        add(
            "weekly_hours_exceed_candidate",
            "期間に配置すると、週あたりの実働が候補者の稼働可能時間を超える。"
            "合意していない残業や追加作業を前提にしない",
        )
    elif schedule["candidate_weekly_hours"] is None:
        add("candidate_availability_unknown", "候補者の週の稼働可能時間が入っていない。配置を確認できない")
    elif schedule["fits_candidate_availability"] is None:
        add(
            "weekly_fit_undecidable",
            "見積もりの欠けた作業があるため、週あたりの実働が収まるかを判定していない",
        )

    if schedule["checkpoint"] is None:
        add("checkpoint_missing", "途中確認日を決めていない")

    if revisions["rounds"] is None or revisions["hours"] is None:
        add(
            "revision_scope_open_ended",
            "修正の回数または時間の範囲が決まっていない。「納得するまで」を、確認できる品質と"
            "有限の修正範囲に具体化する",
        )

    internal = [item["topic"] for item in conditions if item["agreement"] in INTERNAL_ONLY]
    if internal:
        add(
            "conditions_internal_only",
            "候補者に提示していない条件がある。内部案だけから承諾済みの募集文・返信文を作らない",
            internal,
        )

    return flags


def plan(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    header = require_object(data.get("plan", {}), "plan")

    raw_tasks = require_list(data.get("tasks"), "tasks")
    if not raw_tasks:
        raise ValueError("tasks must contain at least one task")
    tasks = [parse_task(raw, index) for index, raw in enumerate(raw_tasks)]

    low, high = sum_hours(tasks, "candidate_hours", "candidate_hours_max")
    company_low, _ = sum_hours(tasks, "company_hours")
    missing = unestimated(tasks)

    # 費用は有償と決めた作業だけで出す。無償と未確定の時間は別に見せ、どちらにも寄せない。
    paid_low, paid_high = sum_hours(
        [task for task in tasks if task["paid"] is True], "candidate_hours", "candidate_hours_max"
    )
    unpaid_low, _ = sum_hours([task for task in tasks if task["paid"] is False], "candidate_hours")
    undecided_low, _ = sum_hours([task for task in tasks if task["paid"] is None], "candidate_hours")

    workload = {
        "candidate_hours_min": as_hours(low),
        "candidate_hours_max": as_hours(high),
        "candidate_hours_missing": missing,
        "paid_hours_min": as_hours(paid_low),
        "paid_hours_max": as_hours(paid_high),
        "unpaid_hours": as_hours(unpaid_low),
        "pay_status_unknown_hours": as_hours(undecided_low),
        # 企業担当者の工数は、候補者の実働とは別の数字として持つ。合計しない。
        "company_hours_total": as_hours(company_low),
        "tasks": [
            {
                "label": task["label"],
                "kind": task["kind"],
                "paid": task["paid"],
                "candidate_hours": as_hours(task["candidate_hours"]),
                "candidate_hours_max": as_hours(task["candidate_hours_max"]),
                "company_hours": as_hours(task["company_hours"]),
            }
            for task in tasks
        ],
    }

    period = parse_period(header.get("period"))
    available = optional_number(
        header.get("candidate_weekly_hours"), "plan.candidate_weekly_hours", allow_zero=False
    )
    weeks = Decimal(str(period["weeks"])) if period["weeks"] is not None else None
    weekly_low = weekly_high = None
    if weeks is not None and weeks > 0:
        if low is not None:
            weekly_low = low / weeks
        if high is not None:
            weekly_high = high / weeks
    # 見積もりの欠けた作業があるうちは、上限が確定しない。収まるとも超えるとも言わない。
    estimated = not missing
    fits = (
        None
        if available is None or weekly_high is None or not estimated
        else weekly_high <= available
    )
    schedule = {
        **period,
        "candidate_weekly_hours": as_hours(available),
        "required_weekly_hours_min": as_hours(weekly_low),
        "required_weekly_hours_max": as_hours(weekly_high),
        "fits_candidate_availability": fits,
    }

    compensation = parse_compensation(data.get("compensation"))
    cost = derive_cost(compensation, paid_low, paid_high, low, high)

    budget = None
    raw_budget = data.get("budget")
    if raw_budget is not None:
        block = require_object(raw_budget, "budget")
        amount = optional_number(block.get("amount"), "budget.amount", allow_zero=False)
        if amount is None:
            raise ValueError("budget.amount is required when budget is given")
        # 見積もりの欠けた作業があるうちは予定費用の上限が確定しないので、
        # 予算に収まるかを出さない。未確定を「収まる」に置き換えない。
        highest = cost["planned_cost_max"] if estimated else None
        budget = {
            "amount": round_yen(amount),
            "includes_expenses": optional_bool(block.get("includes_expenses"), "budget.includes_expenses"),
            "difference_at_max": None if highest is None else round_yen(amount - Decimal(highest)),
            "over": None if highest is None else Decimal(highest) > amount,
            "decidable": estimated and cost["planned_cost_max"] is not None,
        }

    raw_revisions = require_object(data.get("revisions", {}), "revisions")
    # 0 は「修正なしで合意した」であり、省略（未確認）とは別物なので受け取る。
    revisions = {
        "rounds": optional_int(raw_revisions.get("rounds"), "revisions.rounds"),
        "hours": optional_number(raw_revisions.get("hours"), "revisions.hours"),
    }

    conditions = parse_conditions(data.get("conditions"))

    return {
        "as_of": data.get("as_of"),
        "label": optional_text(header.get("label"), "plan.label"),
        "workload": workload,
        "schedule": schedule,
        "cost": cost,
        "budget": budget,
        "revisions": {"rounds": revisions["rounds"], "hours": as_hours(revisions["hours"])},
        "conditions": conditions,
        "not_offered_yet": [item["topic"] for item in conditions if item["agreement"] in INTERNAL_ONLY],
        "flags": collect_flags(tasks, workload, schedule, cost, budget, revisions, conditions),
        "notes": [
            "この出力は計画を数字に直しただけで、採用の成否も候補者の適性も判定していない",
            "候補者の実働と企業担当者の工数は別々に数えている。合計して1つの数字にしない",
            "固定額の時間換算は比較のための割り算であり、時間単価の契約や適法性を意味しない",
            "予定費用は経費・税の扱いが確定するまで総費用ではない",
            "期間を延ばしても総実働と予定費用は変わらない。範囲を変えたときだけ変わる",
            "最低賃金や契約形態の判断が必要なら一次情報を確認し、専門家への質問を用意する",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(plan, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
