#!/usr/bin/env python3
"""Put a side-work assignment's stated terms, hours, and fee on one basis.

業務委託の案件について、取引条件が書面で明示されているかを項目ごとに数え、
打合せ・修正・無償の作業を含めた総稼働を合計し、報酬を予定額と換算時給に揃え、
受領から支払期日までの日数を数える。単価や慣行を補わず、欠けている条件は欠けた
まま返す。条件が妥当か、受けるべきかは判定しない。
"""

from __future__ import annotations

from datetime import date
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


ENGAGEMENTS = ("contract_work", "employment", "unknown")
# 条件の出所。`none` は提示そのものがまだ来ていない状態。
OFFER_FORMS = (
    "contract",
    "purchase_order",
    "email",
    "proposal",
    "chat",
    "verbal",
    "listing",
    "none",
    "unknown",
)
TERM_SOURCES = tuple(form for form in OFFER_FORMS if form != "none")
# 書面、または書面に準じるものとして数える出所。チャットと口頭は含めない。
WRITTEN_SOURCES = ("contract", "purchase_order", "email", "proposal")
ITEM_STATUSES = ("stated", "missing", "unclear", "unknown")
COMPENSATION_BASIS = ("fixed", "hourly", "per_deliverable", "unknown")
TAX_TREATMENTS = ("included", "excluded", "unknown")

# (code, label, group, conditional, start_required)
# conditional は、案件によって対象外になりうる項目。対象外にするときは入力の
# `applicable` を false にする。start_required は、着手前に確定させる項目。
CHECKLIST: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("parties", "発注者と受注者の名称", "transaction", False, False),
    ("order_date", "業務を委託した日", "transaction", False, False),
    ("deliverable", "給付の内容", "transaction", False, True),
    ("delivery_date", "給付を受領する期日", "transaction", False, True),
    ("delivery_place", "給付を受領する場所・方法", "transaction", False, False),
    ("inspection", "検査を行う場合の検査完了日", "transaction", True, False),
    ("payment_amount", "報酬の額と算定方法", "transaction", False, True),
    ("payment_due", "支払期日", "transaction", False, True),
    ("payment_method", "支払方法と振込手数料の負担", "money", False, False),
    ("scope_out", "範囲外とみなす作業", "scope", False, True),
    ("revision_limit", "修正の回数と1回あたりの範囲", "scope", True, True),
    ("estimated_hours", "想定される稼働時間", "scope", False, False),
    ("response_expectation", "連絡手段と応答を求められる時間帯", "scope", False, False),
    ("materials", "提供される資料、アカウント、機材", "scope", False, False),
    ("expenses", "経費の負担", "money", False, False),
    ("withholding", "源泉徴収の有無", "money", False, False),
    ("consumption_tax", "消費税の扱いとインボイスの求め", "money", False, False),
    ("ip_ownership", "成果物の権利の帰属と移転の時期", "rights", True, True),
    ("secondary_use", "二次利用・改変・転売の範囲", "rights", True, False),
    ("credit_disclosure", "実績として公開できる範囲", "rights", False, False),
    ("confidentiality", "秘密保持の対象と期間", "rights", False, True),
    ("competition_restriction", "競業・専属の制限", "rights", True, False),
    ("subcontracting", "再委託の可否", "practical", False, False),
    ("late_or_defect", "遅延・不備があったときの取扱い", "exit", False, False),
    ("liability", "損害賠償の範囲と上限", "exit", False, False),
    ("termination", "中途解除・中止のときの報酬と予告", "exit", False, True),
)
CHECKLIST_CODES = {code for code, _, _, _, _ in CHECKLIST}

HOUR = Decimal("0.01")


def as_hours(value: Decimal | None) -> float | None:
    """時間を0.01単位に丸めて返す。None は None のままにする。"""
    if value is None:
        return None
    return float(value.quantize(HOUR))


def parse_choice(value: object, path: str, allowed: tuple[str, ...], default: str) -> str:
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{path} must be one of {list(allowed)}")
    return str(value)


def parse_offer(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "offer")
    form = parse_choice(block.get("form"), "offer.form", OFFER_FORMS, "unknown")
    return {
        "form": form,
        "in_writing": form in WRITTEN_SOURCES,
        "received_date": optional_date(block.get("received_date"), "offer.received_date"),
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
        source = item.get("source")
        if source is not None and source not in TERM_SOURCES:
            raise ValueError(f"{path}.source must be one of {list(TERM_SOURCES)}")
        parsed[str(code)] = {
            "status": parse_choice(item.get("status"), f"{path}.status", ITEM_STATUSES, "unknown"),
            "source": source,
            "applicable": optional_bool(item.get("applicable"), f"{path}.applicable"),
            "note": optional_text(item.get("note"), f"{path}.note"),
        }
    return parsed


def parse_work(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "work")
    tasks = []
    for index, entry in enumerate(entries):
        path = f"work[{index}]"
        item = require_object(entry, path)
        low = optional_number(item.get("hours"), f"{path}.hours")
        high = optional_number(item.get("hours_max"), f"{path}.hours_max")
        if high is not None and low is None:
            raise ValueError(f"{path}.hours_max needs {path}.hours")
        if high is not None and high < low:
            raise ValueError(f"{path}.hours_max must not be below {path}.hours")
        tasks.append(
            {
                "label": require_text(item.get("label"), f"{path}.label"),
                "hours": low,
                "hours_max": high,
                # 支払いの対象かどうか。未記載は「不明」であり、無償と決めつけない。
                "paid": optional_bool(item.get("paid"), f"{path}.paid"),
            }
        )
    return tasks


def parse_compensation(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "compensation")
    return {
        "basis": parse_choice(
            block.get("basis"), "compensation.basis", COMPENSATION_BASIS, "unknown"
        ),
        "fixed_amount": optional_number(
            block.get("fixed_amount"), "compensation.fixed_amount", allow_zero=False
        ),
        "hourly_rate": optional_number(
            block.get("hourly_rate"), "compensation.hourly_rate", allow_zero=False
        ),
        "unit_amount": optional_number(
            block.get("unit_amount"), "compensation.unit_amount", allow_zero=False
        ),
        "units": optional_positive_int(block.get("units"), "compensation.units"),
        "expenses_borne_by_worker": optional_number(
            block.get("expenses_borne_by_worker"), "compensation.expenses_borne_by_worker"
        ),
        "withholding": optional_bool(block.get("withholding"), "compensation.withholding"),
        "consumption_tax": parse_choice(
            block.get("consumption_tax"),
            "compensation.consumption_tax",
            TAX_TREATMENTS,
            "unknown",
        ),
    }


def parse_payment(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "payment")
    delivery = optional_date(block.get("delivery_date"), "payment.delivery_date")
    acceptance = optional_date(block.get("acceptance_date"), "payment.acceptance_date")
    if delivery is not None and acceptance is not None and acceptance < delivery:
        raise ValueError("payment.acceptance_date must not precede payment.delivery_date")
    return {
        "delivery_date": delivery,
        "acceptance_date": acceptance,
        "due_date": optional_date(block.get("due_date"), "payment.due_date"),
        "reference_term_days": optional_positive_int(
            block.get("reference_term_days"), "payment.reference_term_days"
        ),
    }


def parse_availability(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "availability")
    return {
        "weekly_hours": optional_number(
            block.get("weekly_hours"), "availability.weekly_hours", allow_zero=False
        ),
        "weeks": optional_number(block.get("weeks"), "availability.weeks", allow_zero=False),
    }


def parse_revisions(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "revisions")
    return {
        "rounds": optional_positive_int(block.get("rounds"), "revisions.rounds"),
        "hours": optional_number(block.get("hours"), "revisions.hours", allow_zero=False),
    }


def sum_hours(tasks: list[dict[str, Any]]) -> tuple[Decimal | None, Decimal | None]:
    """入力済みの見積もりだけを合計し、(最小, 最大) を返す。未記入を0で埋めない。"""
    known = [task for task in tasks if task["hours"] is not None]
    if not known:
        return None, None
    low = sum((task["hours"] for task in known), Decimal(0))
    high = sum(((task["hours_max"] or task["hours"]) for task in known), Decimal(0))
    return low, high


def build_checklist(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checklist = []
    for code, label, group, conditional, start_required in CHECKLIST:
        entry = items.get(code)
        applicable = entry["applicable"] if entry else None
        if applicable is None:
            # 条件付きの項目は、対象かどうかが入力されるまで判定しない。
            applicable = None if conditional else True
        checklist.append(
            {
                "code": code,
                "label": label,
                "group": group,
                "conditional": conditional,
                "start_required": start_required,
                "applicable": applicable,
                "status": entry["status"] if entry else "unknown",
                "source": entry["source"] if entry else None,
                "in_writing": bool(entry and entry["source"] in WRITTEN_SOURCES),
                "note": entry["note"] if entry else None,
            }
        )
    return checklist


def build_hours(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    total_low, total_high = sum_hours(tasks)
    paid_low, paid_high = sum_hours([task for task in tasks if task["paid"] is True])
    unpaid_low, unpaid_high = sum_hours([task for task in tasks if task["paid"] is False])
    return {
        "total_min": as_hours(total_low),
        "total_max": as_hours(total_high),
        "paid_min": as_hours(paid_low),
        "paid_max": as_hours(paid_high),
        "unpaid_min": as_hours(unpaid_low),
        "unpaid_max": as_hours(unpaid_high),
        "unestimated": [task["label"] for task in tasks if task["hours"] is None],
        "payment_status_unknown": [
            task["label"] for task in tasks if task["paid"] is None and task["hours"] is not None
        ],
        "_total": (total_low, total_high),
        "_paid": (paid_low, paid_high),
    }


def per_hour_range(
    amount_low: Decimal | None,
    amount_high: Decimal | None,
    hours_low: Decimal | None,
    hours_high: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    """予定額を稼働で割り、(下限, 上限) を返す。

    金額の下限を時間の上限で、金額の上限を時間の下限で割り、小さい方を下限にする。
    固定額の時間換算は比較のための割り算であり、時間単価の契約を意味しない。
    """
    if amount_low is None or hours_low is None or hours_low <= 0:
        return None, None
    high_hours = hours_high if hours_high and hours_high > 0 else hours_low
    at_low = amount_low / high_hours
    at_high = (amount_high if amount_high is not None else amount_low) / hours_low
    return (at_low, at_high) if at_low <= at_high else (at_high, at_low)


def build_money(compensation: dict[str, Any], hours: dict[str, Any]) -> dict[str, Any]:
    """予定額と換算時給を出す。基準か稼働が欠けていれば None のままにする。

    換算時給は2通り出す。支払いの対象になる時間で割ったものと、**無償の作業も
    含めた総稼働で割ったもの**である。無償の作業が多いほど後者は下がる。
    """
    basis = compensation["basis"]
    paid_low, paid_high = hours["_paid"]
    total_low, total_high = hours["_total"]

    planned_low = planned_high = None
    if basis == "fixed" and compensation["fixed_amount"] is not None:
        planned_low = planned_high = compensation["fixed_amount"]
    elif basis == "hourly" and compensation["hourly_rate"] is not None and paid_low is not None:
        planned_low = compensation["hourly_rate"] * paid_low
        planned_high = compensation["hourly_rate"] * (paid_high if paid_high is not None else paid_low)
    elif (
        basis == "per_deliverable"
        and compensation["unit_amount"] is not None
        and compensation["units"] is not None
    ):
        planned_low = planned_high = compensation["unit_amount"] * compensation["units"]

    expenses = compensation["expenses_borne_by_worker"]
    after_low = after_high = None
    if planned_low is not None and expenses is not None:
        after_low = planned_low - expenses
        after_high = (planned_high if planned_high is not None else planned_low) - expenses

    paid_hourly = per_hour_range(planned_low, planned_high, paid_low, paid_high)
    all_hourly = per_hour_range(planned_low, planned_high, total_low, total_high)
    after_hourly = per_hour_range(after_low, after_high, total_low, total_high)

    return {
        "basis": basis,
        "planned_total_min": round_yen(planned_low),
        "planned_total_max": round_yen(planned_high),
        "expenses_borne_by_worker": round_yen(expenses),
        "after_expenses_min": round_yen(after_low),
        "after_expenses_max": round_yen(after_high),
        "effective_hourly_paid_min": round_yen(paid_hourly[0]),
        "effective_hourly_paid_max": round_yen(paid_hourly[1]),
        "effective_hourly_all_min": round_yen(all_hourly[0]),
        "effective_hourly_all_max": round_yen(all_hourly[1]),
        "effective_hourly_after_expenses_min": round_yen(after_hourly[0]),
        "effective_hourly_after_expenses_max": round_yen(after_hourly[1]),
        "withholding": compensation["withholding"],
        "consumption_tax": compensation["consumption_tax"],
        "net_amount_calculated": False,
    }


def days_between(start: date | None, end: date | None) -> int | None:
    return None if start is None or end is None else (end - start).days


def build_payment(payment: dict[str, Any]) -> dict[str, Any]:
    from_delivery = days_between(payment["delivery_date"], payment["due_date"])
    from_acceptance = days_between(payment["acceptance_date"], payment["due_date"])
    reference = payment["reference_term_days"]
    exceeds = None
    if reference is not None and from_delivery is not None:
        exceeds = from_delivery > reference
    return {
        "delivery_date": payment["delivery_date"].isoformat() if payment["delivery_date"] else None,
        "acceptance_date": (
            payment["acceptance_date"].isoformat() if payment["acceptance_date"] else None
        ),
        "due_date": payment["due_date"].isoformat() if payment["due_date"] else None,
        "days_from_delivery": from_delivery,
        "days_from_acceptance": from_acceptance,
        "reference_term_days": reference,
        "exceeds_reference": exceeds,
    }


def build_schedule(availability: dict[str, Any], hours: dict[str, Any]) -> dict[str, Any]:
    total_low, total_high = hours["_total"]
    weeks = availability["weeks"]
    available = availability["weekly_hours"]

    weekly_low = weekly_high = None
    if weeks is not None and total_low is not None:
        weekly_low = total_low / weeks
        weekly_high = (total_high if total_high is not None else total_low) / weeks

    fits = None
    if available is not None and weekly_high is not None and not hours["unestimated"]:
        fits = weekly_high <= available

    return {
        "weeks": as_hours(weeks),
        "weekly_available_hours": as_hours(available),
        "weekly_needed_min": as_hours(weekly_low),
        "weekly_needed_max": as_hours(weekly_high),
        "fits_weekly_availability": fits,
    }


def collect_flags(
    engagement: str,
    offer: dict[str, Any],
    checklist: list[dict[str, Any]],
    hours: dict[str, Any],
    money: dict[str, Any],
    payment: dict[str, Any],
    schedule: dict[str, Any],
    revisions: dict[str, Any],
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if engagement == "employment":
        add(
            "engagement_is_employment",
            "雇用として働く副業である。労働条件の明示が論点になるため、"
            "この確認表ではなく offer-terms-check を使う",
        )
    elif engagement == "unknown":
        add(
            "engagement_unknown",
            "契約の型が未確認である。名称だけで決めず、指揮命令と時間の拘束の実態を聞き取る",
        )

    if offer["form"] == "none":
        add(
            "no_offer_received",
            "条件を書いたものをまだ受け取っていない。この時点ではすべての条件が未確定である",
        )
    elif not offer["in_writing"]:
        add(
            "terms_not_in_writing",
            "条件がチャット・口頭・募集文どまりで、書面や条件を書いたメールになっていない。"
            "確認済みとして扱わない",
        )

    in_scope = [entry for entry in checklist if entry["applicable"] is not False]

    blockers = [
        entry["code"]
        for entry in in_scope
        if entry["start_required"] and not (entry["status"] == "stated" and entry["in_writing"])
    ]
    if blockers:
        add(
            "start_blockers",
            "着手前に確定させる項目のうち、書面で確認できていないものがある",
            blockers,
        )

    unconfirmed = [entry["code"] for entry in in_scope if entry["status"] == "unknown"]
    if unconfirmed:
        add("terms_unconfirmed", "確認していない項目がある", unconfirmed)

    unclear = [entry["code"] for entry in in_scope if entry["status"] == "unclear"]
    if unclear:
        add("terms_unclear", "記載はあるが読み取れない項目がある。質問に変える", unclear)

    undecidable = [entry["code"] for entry in checklist if entry["applicable"] is None]
    if undecidable:
        add(
            "applicability_undecidable",
            "対象になるかどうかを入力していない項目がある。対象外として数えていない",
            undecidable,
        )

    if hours["unestimated"]:
        add(
            "hours_unestimated",
            "時間の見積もりが入っていない作業がある。合計は入力済みの作業だけの値である",
            hours["unestimated"],
        )
    if hours["payment_status_unknown"]:
        add(
            "payment_status_unknown",
            "支払いの対象かどうかが入力されていない作業がある。無償と決めつけない",
            hours["payment_status_unknown"],
        )
    if hours["unpaid_min"]:
        add(
            "unpaid_hours_included",
            f"支払いの対象でない作業が{hours['unpaid_min']}時間含まれる。"
            "換算時給はこの時間を含めて下がる。実績になるという説明を報酬として数えない",
        )

    if money["basis"] == "unknown":
        add("compensation_basis_unknown", "報酬の決め方が未確認である。予定額を出していない")
    elif money["planned_total_min"] is None:
        add(
            "planned_total_unavailable",
            "報酬の決め方に必要な数値が揃っていない。相場で補わず、確認質問にする",
        )

    if money["expenses_borne_by_worker"] is None:
        add("expenses_unknown", "自分が負担する経費が入っていない。予定額を手取りとして扱わない")
    elif money["after_expenses_min"] is not None and money["after_expenses_min"] <= 0:
        add(
            "expenses_exceed_fee",
            "自分が負担する経費が予定額に届いている。経費の負担を先に確認する",
        )

    if money["withholding"] is None or money["consumption_tax"] == "unknown":
        add(
            "tax_treatment_unclear",
            "源泉徴収の有無または消費税の扱いが未確認である。提示額と入金額が変わる。"
            "手取りは計算していない",
        )

    if payment["due_date"] is None:
        add("payment_due_missing", "支払期日が確定していない。着手前の確認事項の先頭に置く")
    elif payment["days_from_delivery"] is None:
        add("delivery_date_missing", "納品日が入っていない。支払までの日数を出せない")
    elif payment["exceeds_reference"] is True:
        add(
            "payment_term_exceeds_reference",
            f"納品日から支払期日まで{payment['days_from_delivery']}日で、"
            f"入力した参照値{payment['reference_term_days']}日を超える。"
            "起点と根拠を確認し、判断は一次情報と専門家に残す",
        )
    elif payment["reference_term_days"] is None:
        add(
            "payment_term_reference_not_supplied",
            "支払期日の参照値を入力していない。日数だけを出している。"
            "判断に関わるなら一次情報で確認して入れ直す",
        )

    revision_item = next(entry for entry in checklist if entry["code"] == "revision_limit")
    if revision_item["applicable"] is not False and (
        revisions["rounds"] is None or revisions["hours"] is None
    ):
        add(
            "revision_scope_open_ended",
            "修正の回数または時間の上限が未確認である。有限の範囲に具体化する確認事項にする",
        )

    if schedule["fits_weekly_availability"] is False:
        add(
            "weekly_hours_exceed_availability",
            f"週あたり{schedule['weekly_needed_max']}時間が必要で、出せる"
            f"{schedule['weekly_available_hours']}時間を超える。範囲を減らすか期間を延ばすかを確認する",
        )
    elif schedule["weekly_available_hours"] is None or schedule["weeks"] is None:
        add("availability_unknown", "出せる週の時間または使える週数が入っていない")
    elif schedule["fits_weekly_availability"] is None:
        add(
            "weekly_fit_undecidable",
            "見積もりの欠けた作業があるため、週あたりの稼働が収まるかを判定していない",
        )

    return flags


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    engagement = parse_choice(data.get("engagement"), "engagement", ENGAGEMENTS, "unknown")
    offer = parse_offer(data.get("offer"))
    items = parse_items(data.get("items"))
    tasks = parse_work(data.get("work"))
    compensation = parse_compensation(data.get("compensation"))
    payment_input = parse_payment(data.get("payment"))
    availability = parse_availability(data.get("availability"))
    revisions = parse_revisions(data.get("revisions"))

    checklist = build_checklist(items)
    hours = build_hours(tasks)
    money = build_money(compensation, hours)
    payment = build_payment(payment_input)
    schedule = build_schedule(availability, hours)
    flags = collect_flags(
        engagement, offer, checklist, hours, money, payment, schedule, revisions
    )

    in_scope = [entry for entry in checklist if entry["applicable"] is not False]
    hours_public = {key: value for key, value in hours.items() if not key.startswith("_")}

    return {
        "as_of": data.get("as_of"),
        "engagement": engagement,
        "offer": {
            "form": offer["form"],
            "in_writing": offer["in_writing"],
            "received_date": offer["received_date"].isoformat() if offer["received_date"] else None,
        },
        "checklist": checklist,
        "hours": hours_public,
        "money": money,
        "payment": payment,
        "schedule": schedule,
        "revisions": {"rounds": revisions["rounds"], "hours": as_hours(revisions["hours"])},
        "summary": {
            "items_in_scope": len(in_scope),
            "items_in_writing": sum(
                1 for entry in in_scope if entry["status"] == "stated" and entry["in_writing"]
            ),
            "items_unknown": sum(1 for entry in in_scope if entry["status"] == "unknown"),
            "start_required_total": sum(1 for entry in in_scope if entry["start_required"]),
            "start_required_in_writing": sum(
                1
                for entry in in_scope
                if entry["start_required"] and entry["status"] == "stated" and entry["in_writing"]
            ),
        },
        "flags": flags,
        "notes": [
            "この出力は明示の状況と数え上げであって、条件の妥当性も適法性も判定していない",
            "換算時給は比較のための割り算であり、時間単価の契約を意味しない",
            "源泉徴収、消費税、経費の扱いは確定していないため、手取りは計算していない",
            "取引条件の明示や支払期日に関する定めは時点で変わる。一次情報で確認する",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(check, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
