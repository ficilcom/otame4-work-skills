#!/usr/bin/env python3
"""Put a proposed otameshi trial on one basis: hours, schedule, and pay.

提示された有償おためし業務について、作業別の実働を合計し、実施期間に配置した
ときの週あたりの実働を出し、報酬を予定額と換算時給に揃える。求職者の実働と
企業担当者の工数は別々に数え、足し合わせない。単価や相場を補わず、欠けている
条件は欠けたまま返す。応募すべきか、条件が妥当かは判定しない。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_date,
    optional_number,
    optional_positive_int,
    optional_text,
    require_list,
    require_object,
    require_text,
    round_yen,
    run_cli,
)


# 作業の種類。`company_work` は企業の実務であり、経験にかかわらず有償枠で扱う。
TASK_KINDS = ("learning", "mock", "company_work", "unknown")
COMPANY_WORK = "company_work"

# 報酬の決め方。`unknown` のまま予定額を出さない。
COMPENSATION_BASIS = ("hourly", "fixed", "unknown")

# 条件がどの段階にあるか。`mutual` 以外を合意済みとして扱わない。
AGREEMENT_STATES = ("company_offer", "candidate_request", "proposal", "mutual", "unconfirmed")

# 契約の型。名称だけで法的な扱いを決めないため、確認状況としてのみ持つ。
ENGAGEMENT_TYPES = ("employment", "contract", "unknown")

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
        # 企業担当者の工数。求職者の実働とは別に数える。合同作業は双方に入れる。
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
    block = require_object(raw or {}, "trial.period")
    start = optional_date(block.get("start"), "trial.period.start")
    end = optional_date(block.get("end"), "trial.period.end")
    if start is not None and end is not None and end < start:
        raise ValueError("trial.period.end must not be before trial.period.start")

    days = weeks = None
    if start is not None and end is not None:
        days = Decimal((end - start).days + 1)
        weeks = days / DAYS_PER_WEEK

    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "checkpoint": optional_text(block.get("checkpoint"), "trial.period.checkpoint"),
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
        "payer": optional_text(block.get("payer"), "compensation.payer"),
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
                "source": optional_text(item.get("source"), f"{path}.source"),
            }
        )
    return conditions


def derive_money(compensation: dict[str, Any], low: Decimal | None, high: Decimal | None) -> dict[str, Any]:
    """予定額と換算時給を出す。基準か実働が欠けていれば None のままにする。"""
    basis = compensation["basis"]
    rate = compensation["hourly_rate"]
    fixed = compensation["fixed_amount"]

    planned_low = planned_high = None
    if basis == "hourly" and rate is not None and low is not None:
        planned_low, planned_high = rate * low, rate * (high if high is not None else low)
    elif basis == "fixed" and fixed is not None:
        planned_low = planned_high = fixed

    # 固定額の時間換算は比較のための割り算であり、時間単価の契約を意味しない。
    effective_low = effective_high = None
    if planned_low is not None and low is not None and low > 0:
        effective_high = planned_low / low
        effective_low = (planned_high or planned_low) / (high if high and high > 0 else low)
        if effective_low > effective_high:
            effective_low, effective_high = effective_high, effective_low

    return {
        "basis": basis,
        "hourly_rate": round_yen(rate),
        "fixed_amount": round_yen(fixed),
        "planned_total_min": round_yen(planned_low),
        "planned_total_max": round_yen(planned_high),
        "effective_hourly_min": round_yen(effective_low),
        "effective_hourly_max": round_yen(effective_high),
        "expenses_included": compensation["expenses_included"],
        "tax_treatment": compensation["tax_treatment"],
        "payment_date": compensation["payment_date"],
        "payer": compensation["payer"],
    }


def collect_flags(
    tasks: list[dict[str, Any]],
    workload: dict[str, Any],
    schedule: dict[str, Any],
    money: dict[str, Any],
    minimum_wage: dict[str, Any] | None,
    revisions: dict[str, Any],
    engagement_type: str,
    conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags, add = flag_collector("items")

    unpaid = [task["label"] for task in tasks if task["kind"] == COMPANY_WORK and task["paid"] is False]
    if unpaid:
        add(
            "company_work_unpaid",
            "企業の実務が無償の枠に入っている。経験の有無にかかわらず有償枠として確認する",
            unpaid,
        )

    pay_unknown = [task["label"] for task in tasks if task["kind"] == COMPANY_WORK and task["paid"] is None]
    if pay_unknown:
        add("company_work_pay_unknown", "企業の実務だが、支払い対象かどうかが入力されていない", pay_unknown)

    if workload["candidate_hours_missing"]:
        add(
            "candidate_hours_missing",
            "時間の見積もりが入っていない作業がある。合計は入力済みの作業だけの値である",
            workload["candidate_hours_missing"],
        )

    if workload["unpaid_hours"] is not None and workload["paid_hours_min"] is not None:
        add(
            "unpaid_hours_in_paid_trial",
            f"有償の話に無償の作業が{workload['unpaid_hours']}時間含まれる。"
            "予定額はこの時間を除いた額であり、無償で埋め合わせる前提になっていないか確認する",
        )

    if money["basis"] == "unknown":
        add("compensation_basis_unknown", "報酬の決め方が未確認である。予定額を出していない")
    elif money["basis"] == "hourly" and money["hourly_rate"] is None:
        add("hourly_rate_missing", "時間単価が提示されていない。相場で補わず、単価の確認質問にする")
    elif money["basis"] == "fixed" and money["fixed_amount"] is None:
        add("fixed_amount_missing", "固定額が提示されていない")

    if money["expenses_included"] is None or money["tax_treatment"] is None:
        add("expenses_or_tax_unclear", "経費・税の含み方が未確認である。予定額を手取りとして扱わない")

    if money["payment_date"] is None or money["payer"] is None:
        add("payment_terms_unconfirmed", "支払日または支払主体が未確認である")

    if schedule["weeks"] is None:
        add("period_missing", "実施期間が入っていない。週あたりの実働を出せない")
    elif schedule["fits_weekly_availability"] is False:
        add(
            "weekly_hours_exceed_availability",
            "期間に配置すると、週あたりの実働が本人の提供できる時間を超える。"
            "範囲を減らすか期間を延ばすかを確認する",
        )
    elif schedule["weekly_available_hours"] is None:
        add("weekly_availability_unknown", "本人が提供できる週の時間が入っていない。無理のない配置か判定できない")

    if revisions["rounds"] is None or revisions["hours"] is None:
        add(
            "revision_scope_open_ended",
            "修正の回数または時間の範囲が未確認である。有限の範囲に具体化する確認事項にする",
        )

    if engagement_type == "unknown":
        add("engagement_type_unknown", "契約形態が未確認である。名称だけで支払い・検収の扱いを決めない")

    if minimum_wage is None:
        add(
            "minimum_wage_not_supplied",
            "最低賃金を入力していない。判断に関わるなら一次情報で地域と時点を確認して入れ直す",
        )
    elif minimum_wage["below"] is True:
        add(
            "below_supplied_minimum_wage",
            "換算時給が、入力された最低賃金を下回る。地域と時点、雇用か業務委託かを"
            "一次情報で確認し、適法性の判断は専門家への質問にする",
        )

    unconfirmed = [item["topic"] for item in conditions if item["agreement"] == "unconfirmed"]
    if unconfirmed:
        add("conditions_unconfirmed", "未確認のままの条件がある。合意済みとして返信に含めない", unconfirmed)

    return flags


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    trial = require_object(data.get("trial", {}), "trial")

    engagement_type = trial.get("engagement_type", "unknown")
    if engagement_type not in ENGAGEMENT_TYPES:
        raise ValueError(f"trial.engagement_type must be one of {list(ENGAGEMENT_TYPES)}")

    raw_tasks = require_list(data.get("tasks"), "tasks")
    if not raw_tasks:
        raise ValueError("tasks must contain at least one task")
    tasks = [parse_task(raw, index) for index, raw in enumerate(raw_tasks)]

    low, high = sum_hours(tasks, "candidate_hours", "candidate_hours_max")
    company_low, _ = sum_hours(tasks, "company_hours")
    missing = unestimated(tasks)
    # 予定額は有償と確認できた作業だけで出す。無償と未確定の時間はどちらにも寄せない。
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
        # 企業担当者の工数は、求職者の実働とは別の数字として持つ。合計しない。
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

    period = parse_period(trial.get("period"))
    available = optional_number(
        trial.get("weekly_available_hours"), "trial.weekly_available_hours", allow_zero=False
    )
    weeks = Decimal(str(period["weeks"])) if period["weeks"] is not None else None
    weekly_low = weekly_high = None
    if weeks is not None and weeks > 0:
        if low is not None:
            weekly_low = low / weeks
        if high is not None:
            weekly_high = high / weeks
    fits = None if available is None or weekly_high is None else weekly_high <= available
    schedule = {
        **period,
        "weekly_available_hours": as_hours(available),
        "required_weekly_hours_min": as_hours(weekly_low),
        "required_weekly_hours_max": as_hours(weekly_high),
        "fits_weekly_availability": fits,
    }

    compensation = parse_compensation(data.get("compensation"))
    money = derive_money(compensation, paid_low, paid_high)

    minimum_wage = None
    raw_wage = data.get("minimum_wage")
    if raw_wage is not None:
        block = require_object(raw_wage, "minimum_wage")
        hourly = optional_number(block.get("hourly"), "minimum_wage.hourly", allow_zero=False)
        if hourly is None:
            raise ValueError("minimum_wage.hourly is required when minimum_wage is given")
        lowest = money["effective_hourly_min"]
        minimum_wage = {
            "hourly": round_yen(hourly),
            "source": optional_text(block.get("source"), "minimum_wage.source"),
            "as_of": optional_text(block.get("as_of"), "minimum_wage.as_of"),
            "below": None if lowest is None else Decimal(lowest) < hourly,
        }

    raw_revisions = require_object(data.get("revisions", {}), "revisions")
    revisions = {
        "rounds": optional_positive_int(raw_revisions.get("rounds"), "revisions.rounds"),
        "hours": optional_number(raw_revisions.get("hours"), "revisions.hours", allow_zero=False),
    }

    conditions = parse_conditions(data.get("conditions"))

    return {
        "as_of": data.get("as_of"),
        "label": optional_text(trial.get("label"), "trial.label"),
        "engagement_type": engagement_type,
        "workload": workload,
        "schedule": schedule,
        "compensation": money,
        "minimum_wage": minimum_wage,
        "revisions": {"rounds": revisions["rounds"], "hours": as_hours(revisions["hours"])},
        "conditions": conditions,
        "unconfirmed_conditions": [item["topic"] for item in conditions if item["agreement"] == "unconfirmed"],
        "flags": collect_flags(
            tasks, workload, schedule, money, minimum_wage, revisions, engagement_type, conditions
        ),
        "notes": [
            "この出力は提示条件を同じ基準に並べただけで、応募の可否も条件の妥当性も判定していない",
            "求職者の実働と企業担当者の工数は別々に数えている。合計して1つの数字にしない",
            "固定額の時間換算は比較のための割り算であり、時間単価の契約や適法性を意味しない",
            "予定額は経費・税の扱いが確定するまで手取りではない",
            "最低賃金は入力された値との比較であり、地域と時点は一次情報で確認する",
            "期間を延ばしても総実働と予定額は変わらない。範囲を変えたときだけ変わる",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(check, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
