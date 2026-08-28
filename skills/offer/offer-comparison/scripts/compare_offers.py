#!/usr/bin/env python3
"""Put several job offers on one basis so they can be read side by side.

提示年収を、固定残業代・賞与・固定手当に分解し、変動しない年額と、みなし残業を
含めた想定労働時間での時給に揃える。項目が欠けている内定があれば、その項目は
比較不能として落とす。どの内定が良いかは判定せず、順位も総合点も出さない。
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


# 提示条件の出所。書面以外は比較に使う前に確認する必要がある。
COMPENSATION_BASIS = (
    "written_notice",
    "offer_letter",
    "verbal",
    "posting",
    "estimated",
    "unknown",
)
WRITTEN_BASIS = ("written_notice", "offer_letter")

# 労働基準法36条の特別条項なしの上限（月45時間）。これを超える設定は注記する。
MONTHLY_OVERTIME_REFERENCE_HOURS = Decimal(45)
# 提示年収と内訳の合計がこれ以上ずれる場合、内訳が提示額を説明できていないとみなす。
RECONCILE_TOLERANCE_RATIO = Decimal("0.01")
RECONCILE_TOLERANCE_FLOOR = Decimal(10000)
YEN = Decimal("1")
MONTHS = Decimal(12)

# (key, label, note)
MONEY_METRICS: tuple[tuple[str, str, str], ...] = (
    ("stated_annual", "提示年収（記載どおり）", "内訳が違えば同じ意味にならない"),
    ("base_annual", "基本給＋固定手当の年額", "固定残業代と賞与を除いた部分"),
    ("fixed_overtime_annual", "固定残業代の年額", "対応する時間数と合わせて読む"),
    ("bonus_annual", "賞与の年額", "保証されているかを併記する"),
    ("guaranteed_annual", "変動しない年額", "業績連動の賞与を除いた合計"),
    ("total_annual_all_components", "内訳をすべて足した年額", "賞与が想定どおり出た場合の合計"),
    ("housing_support_annual", "住宅補助の年額", "課税の扱いで手取りへの効き方が変わる"),
)
HOUR_METRICS: tuple[tuple[str, str, str], ...] = (
    ("assumed_annual_hours", "想定年間労働時間", "所定労働時間＋みなし残業時間"),
)
HOURLY_METRICS: tuple[tuple[str, str, str], ...] = (
    ("hourly_stated", "提示年収の時給換算", "上の想定労働時間で割ったもの"),
    ("hourly_guaranteed", "変動しない年額の時給換算", "賞与の変動を除いたもの"),
)


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, path)


def _optional_bool(value: object, path: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean or null")
    return value


def _optional_number(value: object, path: str, *, allow_zero: bool = True) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number or null")
    number = Decimal(str(value))
    if number < 0:
        raise ValueError(f"{path} must not be negative")
    if number == 0 and not allow_zero:
        raise ValueError(f"{path} must be greater than zero")
    return number


def _round_yen(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int(value.quantize(YEN, rounding=ROUND_HALF_UP))


def parse_fixed_overtime(raw: object, path: str) -> dict[str, Any]:
    if raw is None:
        return {"disclosed": False, "monthly_amount": None, "hours": None, "included_in_annual": None}
    block = _require_object(raw, path)
    return {
        "disclosed": True,
        "monthly_amount": _optional_number(block.get("monthly_amount"), f"{path}.monthly_amount"),
        "hours": _optional_number(block.get("hours"), f"{path}.hours"),
        "included_in_annual": _optional_bool(
            block.get("included_in_annual"), f"{path}.included_in_annual"
        ),
    }


def parse_bonus(raw: object, path: str) -> dict[str, Any]:
    if raw is None:
        return {"disclosed": False, "annual_amount": None, "guaranteed": None, "included_in_annual": None}
    block = _require_object(raw, path)
    return {
        "disclosed": True,
        "annual_amount": _optional_number(block.get("annual_amount"), f"{path}.annual_amount"),
        "guaranteed": _optional_bool(block.get("guaranteed"), f"{path}.guaranteed"),
        "included_in_annual": _optional_bool(
            block.get("included_in_annual"), f"{path}.included_in_annual"
        ),
    }


def parse_offer(raw: object, index: int) -> dict[str, Any]:
    path = f"offers[{index}]"
    offer = _require_object(raw, path)
    label = _require_text(offer.get("label"), f"{path}.label")

    compensation = _require_object(offer.get("compensation", {}), f"{path}.compensation")
    basis = compensation.get("basis", "unknown")
    if basis not in COMPENSATION_BASIS:
        raise ValueError(f"{path}.compensation.basis must be one of {list(COMPENSATION_BASIS)}")

    components = _require_object(compensation.get("components", {}), f"{path}.compensation.components")
    working = _require_object(offer.get("working_hours", {}), f"{path}.working_hours")
    other = _require_object(offer.get("other", {}), f"{path}.other")

    monthly_scheduled = _optional_number(
        working.get("monthly_scheduled_hours"), f"{path}.working_hours.monthly_scheduled_hours", allow_zero=False
    )
    if monthly_scheduled is None:
        daily = _optional_number(
            working.get("daily_scheduled_hours"), f"{path}.working_hours.daily_scheduled_hours", allow_zero=False
        )
        days = _optional_number(
            working.get("monthly_working_days"), f"{path}.working_hours.monthly_working_days", allow_zero=False
        )
        monthly_scheduled = daily * days if daily is not None and days is not None else None

    non_monetary = []
    for position, entry in enumerate(_require_list(offer.get("non_monetary", []), f"{path}.non_monetary")):
        item = _require_object(entry, f"{path}.non_monetary[{position}]")
        non_monetary.append(
            {
                "topic": _require_text(item.get("topic"), f"{path}.non_monetary[{position}].topic"),
                "value": _require_text(item.get("value"), f"{path}.non_monetary[{position}].value"),
            }
        )

    return {
        "label": label,
        "employment_type": _optional_text(offer.get("employment_type"), f"{path}.employment_type"),
        "basis": basis,
        "stated_annual": _optional_number(
            compensation.get("annual_total"), f"{path}.compensation.annual_total", allow_zero=False
        ),
        "monthly_base": _optional_number(
            components.get("monthly_base"), f"{path}.compensation.components.monthly_base", allow_zero=False
        ),
        "fixed_allowances_monthly": _optional_number(
            components.get("fixed_allowances_monthly"),
            f"{path}.compensation.components.fixed_allowances_monthly",
        ),
        "fixed_overtime": parse_fixed_overtime(
            components.get("fixed_overtime"), f"{path}.compensation.components.fixed_overtime"
        ),
        "bonus": parse_bonus(components.get("bonus"), f"{path}.compensation.components.bonus"),
        "monthly_scheduled_hours": monthly_scheduled,
        "commute_allowance_monthly": _optional_number(
            other.get("commute_allowance_monthly"), f"{path}.other.commute_allowance_monthly"
        ),
        "housing_support_monthly": _optional_number(
            other.get("housing_support_monthly"), f"{path}.other.housing_support_monthly"
        ),
        "retirement_plan": _optional_text(other.get("retirement_plan"), f"{path}.other.retirement_plan"),
        "non_monetary": non_monetary,
    }


def derive(offer: dict[str, Any]) -> dict[str, Any]:
    """内訳から、同じ基準で並べられる数値を作る。欠けている項目は None のままにする。"""
    fixed_overtime = offer["fixed_overtime"]
    bonus = offer["bonus"]

    monthly_base = offer["monthly_base"]
    allowances = offer["fixed_allowances_monthly"]
    base_monthly = None
    if monthly_base is not None:
        base_monthly = monthly_base + (allowances if allowances is not None else Decimal(0))
    base_annual = base_monthly * MONTHS if base_monthly is not None else None

    fixed_overtime_annual = (
        fixed_overtime["monthly_amount"] * MONTHS if fixed_overtime["monthly_amount"] is not None else None
    )
    bonus_annual = bonus["annual_amount"]

    parts = (base_annual, fixed_overtime_annual, bonus_annual)
    total_all = sum(parts, Decimal(0)) if all(part is not None for part in parts) else None

    guaranteed_annual = None
    if base_annual is not None and fixed_overtime_annual is not None:
        guaranteed_annual = base_annual + fixed_overtime_annual
        if bonus["guaranteed"] is True and bonus_annual is not None:
            guaranteed_annual += bonus_annual
        elif bonus["guaranteed"] is None:
            guaranteed_annual = None

    scheduled = offer["monthly_scheduled_hours"]
    overtime_hours = fixed_overtime["hours"]
    if scheduled is None:
        annual_hours = None
    elif fixed_overtime["disclosed"] and overtime_hours is None:
        annual_hours = None
    else:
        annual_hours = (scheduled + (overtime_hours or Decimal(0))) * MONTHS

    def per_hour(amount: Decimal | None) -> Decimal | None:
        if amount is None or annual_hours is None or annual_hours == 0:
            return None
        return amount / annual_hours

    housing = offer["housing_support_monthly"]
    housing_annual = housing * MONTHS if housing is not None else None
    commute = offer["commute_allowance_monthly"]

    computed_annual = None
    if base_annual is not None:
        computed_annual = base_annual
        if fixed_overtime["included_in_annual"] is True and fixed_overtime_annual is not None:
            computed_annual += fixed_overtime_annual
        elif fixed_overtime["included_in_annual"] is None and fixed_overtime["disclosed"]:
            computed_annual = None
        if computed_annual is not None and bonus["disclosed"]:
            if bonus["included_in_annual"] is True and bonus_annual is not None:
                computed_annual += bonus_annual
            elif bonus["included_in_annual"] is None:
                computed_annual = None

    reconcile = None
    stated = offer["stated_annual"]
    if stated is not None and computed_annual is not None:
        difference = computed_annual - stated
        tolerance = max(stated * RECONCILE_TOLERANCE_RATIO, RECONCILE_TOLERANCE_FLOOR)
        reconcile = {
            "computed_annual": _round_yen(computed_annual),
            "difference": _round_yen(difference),
            "within_tolerance": abs(difference) <= tolerance,
        }

    return {
        "stated_annual": stated,
        "base_annual": base_annual,
        "fixed_overtime_annual": fixed_overtime_annual,
        "fixed_overtime_hours": overtime_hours,
        "bonus_annual": bonus_annual,
        "bonus_guaranteed": bonus["guaranteed"],
        "guaranteed_annual": guaranteed_annual,
        "total_annual_all_components": total_all,
        "housing_support_annual": housing_annual,
        "commute_allowance_monthly": commute,
        "assumed_annual_hours": annual_hours,
        "hourly_stated": per_hour(stated),
        "hourly_guaranteed": per_hour(guaranteed_annual),
        "reconcile": reconcile,
    }


def build_metric(key: str, label: str, note: str, rows: list[dict[str, Any]], *, money: bool) -> dict[str, Any]:
    values: dict[str, Any] = {}
    missing: list[str] = []
    for row in rows:
        value = row["figures"][key]
        if value is None:
            missing.append(row["label"])
        else:
            values[row["label"]] = _round_yen(value) if money else float(value)

    metric: dict[str, Any] = {
        "key": key,
        "label": label,
        "note": note,
        "values": values,
        "missing": missing,
        "comparable": not missing and len(values) >= 2,
    }
    if metric["comparable"]:
        numbers = [Decimal(str(value)) for value in values.values()]
        low, high = min(numbers), max(numbers)
        metric["min"] = _round_yen(low) if money else float(low)
        metric["max"] = _round_yen(high) if money else float(high)
        metric["spread"] = _round_yen(high - low) if money else float(high - low)
        metric["spread_ratio"] = float((high / low).quantize(Decimal("0.01"))) if low > 0 else None
    return metric


def collect_flags(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, offers: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if offers:
            flag["offers"] = offers
        flags.append(flag)

    if len(rows) < 2:
        add("single_offer", "内定が1件しかない。比較ではなく、その1件の分解として読む")

    weak = [row["label"] for row in rows if row["basis"] not in WRITTEN_BASIS]
    if weak:
        add(
            "basis_not_written",
            "書面以外の情報で条件を入力している内定がある。比較に使う前に書面で確認する",
            weak,
        )

    undisclosed = [row["label"] for row in rows if not row["fixed_overtime"]["disclosed"]]
    if undisclosed:
        add(
            "fixed_overtime_undisclosed",
            "固定残業代の有無が入力されていない内定がある。基本給を分離できない",
            undisclosed,
        )

    hours_unknown = [row["label"] for row in rows if row["figures"]["assumed_annual_hours"] is None]
    if hours_unknown:
        add(
            "working_hours_unknown",
            "想定労働時間が出せない内定がある。時給での比較ができない",
            hours_unknown,
        )

    long_overtime = [
        row["label"]
        for row in rows
        if row["fixed_overtime"]["hours"] is not None
        and row["fixed_overtime"]["hours"] > MONTHLY_OVERTIME_REFERENCE_HOURS
    ]
    if long_overtime:
        add(
            "fixed_overtime_hours_high",
            f"みなし残業が月{MONTHLY_OVERTIME_REFERENCE_HOURS}時間を超える前提の内定がある",
            long_overtime,
        )

    performance_bonus = [
        row["label"]
        for row in rows
        if row["bonus"]["guaranteed"] is False and row["bonus"]["included_in_annual"] is True
    ]
    if performance_bonus:
        add(
            "performance_bonus_in_stated_annual",
            "提示年収に、保証されていない賞与が含まれる内定がある。提示額どうしを並べない",
            performance_bonus,
        )

    bonus_unknown = [
        row["label"] for row in rows if row["bonus"]["disclosed"] and row["bonus"]["guaranteed"] is None
    ]
    if bonus_unknown:
        add(
            "bonus_guarantee_unknown",
            "賞与が保証されているかが不明な内定がある。変動しない年額を出せない",
            bonus_unknown,
        )

    mismatched = [
        row["label"]
        for row in rows
        if row["figures"]["reconcile"] is not None and not row["figures"]["reconcile"]["within_tolerance"]
    ]
    if mismatched:
        add(
            "stated_annual_does_not_reconcile",
            "内訳の合計が提示年収と一致しない内定がある。何が提示額に含まれるかを確認する",
            mismatched,
        )

    types = {row["employment_type"] for row in rows if row["employment_type"]}
    if len(types) > 1:
        add(
            "employment_types_differ",
            f"雇用形態が揃っていない（{'、'.join(sorted(types))}）。金額だけを並べても同じ条件の比較にならない",
        )

    return flags


def compare(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    raw_offers = _require_list(data.get("offers"), "offers")
    if not raw_offers:
        raise ValueError("offers must contain at least one offer")

    rows = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_offers):
        offer = parse_offer(raw, index)
        if offer["label"] in seen:
            raise ValueError(f"offers[{index}].label is duplicated: {offer['label']!r}")
        seen.add(offer["label"])
        offer["figures"] = derive(offer)
        rows.append(offer)

    metrics = (
        [build_metric(key, label, note, rows, money=True) for key, label, note in MONEY_METRICS]
        + [build_metric(key, label, note, rows, money=False) for key, label, note in HOUR_METRICS]
        + [build_metric(key, label, note, rows, money=True) for key, label, note in HOURLY_METRICS]
    )

    offers_out = []
    for row in rows:
        figures = row["figures"]
        offers_out.append(
            {
                "label": row["label"],
                "employment_type": row["employment_type"],
                "basis": row["basis"],
                "basis_is_written": row["basis"] in WRITTEN_BASIS,
                "figures": {
                    key: _round_yen(figures[key])
                    for key, _, _ in MONEY_METRICS
                },
                "fixed_overtime_hours": (
                    float(figures["fixed_overtime_hours"])
                    if figures["fixed_overtime_hours"] is not None
                    else None
                ),
                "bonus_guaranteed": figures["bonus_guaranteed"],
                "assumed_annual_hours": (
                    float(figures["assumed_annual_hours"])
                    if figures["assumed_annual_hours"] is not None
                    else None
                ),
                "hourly_stated": _round_yen(figures["hourly_stated"]),
                "hourly_guaranteed": _round_yen(figures["hourly_guaranteed"]),
                "commute_allowance_monthly": _round_yen(figures["commute_allowance_monthly"]),
                "retirement_plan": row["retirement_plan"],
                "reconcile": figures["reconcile"],
                "non_monetary": row["non_monetary"],
            }
        )

    return {
        "as_of": data.get("as_of"),
        "offers": offers_out,
        "metrics": metrics,
        "not_comparable": [
            {"key": metric["key"], "label": metric["label"], "missing": metric["missing"]}
            for metric in metrics
            if not metric["comparable"]
        ],
        "flags": collect_flags(rows),
        "notes": [
            "この出力は提示条件を同じ基準に並べ替えただけで、順位も総合点も含まない",
            "通勤手当は実費の補填であり、比較の金額に含めていない",
            "退職金・企業年金・持株会は年額に換算していない。記載のまま別に読む",
            "手取りは扶養、住所地、社会保険、住宅補助の課税扱いで変わる。額面の比較を手取りの比較として扱わない",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="入力JSONのパス。省略した場合は標準入力から読む")
    args = parser.parse_args(argv)

    raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"input is not valid JSON: {error}", file=sys.stderr)
        return 2

    try:
        report = compare(payload)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
