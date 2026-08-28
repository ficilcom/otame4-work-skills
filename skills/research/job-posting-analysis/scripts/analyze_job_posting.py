#!/usr/bin/env python3
"""Decompose a Japanese job posting's stated pay and requirements.

固定残業代を年収から分離し、想定労働時間で時給に換算し、要件の充足状況を数える。
採用可能性、企業の良し悪し、応募すべきかどうかは判定しない。求人票に書かれて
いないことは推定せず `unknown` のまま残す。
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


REQUIREMENT_KINDS = ("must", "want")
USER_STATUSES = ("met", "partial", "unmet", "unknown")
WORKING_TIME_SYSTEMS = ("standard", "flex", "discretionary", "fixed_shift", "unknown")
PAY_BASIS = ("posted", "user_provided", "estimated", "unknown")

# 労働基準法36条の特別条項なしの上限（月45時間）。これを超えるみなし残業は注記する。
MONTHLY_OVERTIME_REFERENCE_HOURS = 45
# レンジの上下が開きすぎている求人は、提示条件が実質未確定として扱う。
WIDE_RANGE_RATIO = Decimal("1.5")
YEN = Decimal("1")


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


def _optional_number(value: object, path: str, *, allow_zero: bool = True) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number or null")
    number = Decimal(str(value))
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{path} must be a positive number")
    return number


def _round_yen(value: Decimal) -> int:
    return int(value.quantize(YEN, rounding=ROUND_HALF_UP))


def parse_compensation(raw: object) -> dict[str, Any]:
    compensation = _require_object(raw, "compensation")

    basis = compensation.get("basis", "unknown")
    if basis not in PAY_BASIS:
        raise ValueError(f"compensation.basis must be one of {list(PAY_BASIS)}")

    annual_min = _optional_number(compensation.get("annual_min"), "compensation.annual_min", allow_zero=False)
    annual_max = _optional_number(compensation.get("annual_max"), "compensation.annual_max", allow_zero=False)
    if annual_min is not None and annual_max is not None and annual_min > annual_max:
        raise ValueError("compensation.annual_min must not exceed compensation.annual_max")

    raw_fixed = compensation.get("fixed_overtime")
    if raw_fixed is None:
        fixed = {"disclosed": False, "included_in_range": None, "hours": None, "annual_amount": None}
    else:
        block = _require_object(raw_fixed, "compensation.fixed_overtime")
        included = block.get("included_in_range")
        if included is not None and not isinstance(included, bool):
            raise ValueError("compensation.fixed_overtime.included_in_range must be a boolean or null")
        hours = _optional_number(block.get("hours"), "compensation.fixed_overtime.hours")
        amount = _optional_number(block.get("annual_amount"), "compensation.fixed_overtime.annual_amount")
        fixed = {
            "disclosed": True,
            "included_in_range": included,
            "hours": hours,
            "annual_amount": amount,
        }

    bonus_included = compensation.get("bonus_included_in_range")
    if bonus_included is not None and not isinstance(bonus_included, bool):
        raise ValueError("compensation.bonus_included_in_range must be a boolean or null")

    return {
        "basis": basis,
        "annual_min": annual_min,
        "annual_max": annual_max,
        "fixed_overtime": fixed,
        "bonus_included_in_range": bonus_included,
    }


def parse_working_hours(raw: object) -> dict[str, Any]:
    if raw is None:
        return {"system": "unknown", "monthly_scheduled_hours": None}
    hours = _require_object(raw, "working_hours")
    system = hours.get("system", "unknown")
    if system not in WORKING_TIME_SYSTEMS:
        raise ValueError(f"working_hours.system must be one of {list(WORKING_TIME_SYSTEMS)}")

    monthly = _optional_number(hours.get("monthly_scheduled_hours"), "working_hours.monthly_scheduled_hours", allow_zero=False)
    if monthly is None:
        daily = _optional_number(hours.get("daily_scheduled_hours"), "working_hours.daily_scheduled_hours", allow_zero=False)
        days = _optional_number(hours.get("monthly_working_days"), "working_hours.monthly_working_days", allow_zero=False)
        monthly = daily * days if daily is not None and days is not None else None

    return {"system": system, "monthly_scheduled_hours": monthly}


def parse_requirements(raw: object) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "requirements")
    parsed = []
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"requirements[{index}]")
        kind = item.get("kind", "must")
        if kind not in REQUIREMENT_KINDS:
            raise ValueError(f"requirements[{index}].kind must be one of {list(REQUIREMENT_KINDS)}")
        status = item.get("user_status", "unknown")
        if status not in USER_STATUSES:
            raise ValueError(f"requirements[{index}].user_status must be one of {list(USER_STATUSES)}")
        parsed.append(
            {
                "text": _require_text(item.get("text"), f"requirements[{index}].text"),
                "kind": kind,
                "user_status": status,
                "measurable": bool(item.get("measurable", False)),
            }
        )
    return parsed


def build_pay_breakdown(compensation: dict[str, Any], working: dict[str, Any]) -> dict[str, Any]:
    fixed = compensation["fixed_overtime"]
    annual_min = compensation["annual_min"]
    annual_max = compensation["annual_max"]
    fixed_amount = fixed["annual_amount"]
    fixed_hours = fixed["hours"]
    included = fixed["included_in_range"]

    def base(annual: Decimal | None) -> int | None:
        if annual is None:
            return None
        if not fixed["disclosed"] or fixed_amount is None or included is None:
            return None
        return _round_yen(annual - fixed_amount if included else annual)

    base_min = base(annual_min)
    base_max = base(annual_max)

    monthly_scheduled = working["monthly_scheduled_hours"]
    if monthly_scheduled is None or fixed_hours is None:
        annual_hours = None
    else:
        annual_hours = (monthly_scheduled + fixed_hours) * Decimal(12)

    def hourly(annual: Decimal | None) -> int | None:
        if annual is None or annual_hours is None or annual_hours == 0:
            return None
        return _round_yen(annual / annual_hours)

    range_ratio = None
    if annual_min is not None and annual_max is not None and annual_min > 0:
        range_ratio = float((annual_max / annual_min).quantize(Decimal("0.01")))

    return {
        "stated_annual_min": _round_yen(annual_min) if annual_min is not None else None,
        "stated_annual_max": _round_yen(annual_max) if annual_max is not None else None,
        "base_annual_min_excluding_fixed_overtime": base_min,
        "base_annual_max_excluding_fixed_overtime": base_max,
        "assumed_annual_hours": float(annual_hours) if annual_hours is not None else None,
        "hourly_min": hourly(annual_min),
        "hourly_max": hourly(annual_max),
        "range_ratio": range_ratio,
    }


def collect_flags(
    compensation: dict[str, Any],
    working: dict[str, Any],
    pay: dict[str, Any],
    requirements: list[dict[str, Any]],
) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        flags.append({"code": code, "message": message})

    if compensation["basis"] in ("estimated", "unknown"):
        add("pay_basis_unconfirmed", "提示年収の出所が未確認。求人票の原文で確認するまで比較に使わない")
    if compensation["annual_min"] is None or compensation["annual_max"] is None:
        add("pay_range_incomplete", "年収レンジが不完全。下限か上限が不明のまま比較しない")

    fixed = compensation["fixed_overtime"]
    if not fixed["disclosed"]:
        add("fixed_overtime_undisclosed", "固定残業代の有無が不明。基本給が実際いくらかを確認する")
    else:
        if fixed["included_in_range"] is None:
            add("fixed_overtime_inclusion_unknown", "固定残業代が提示年収に含まれるか不明。応募前に確認する")
        if fixed["hours"] is None:
            add("fixed_overtime_hours_unknown", "みなし残業時間数が不明。時給換算ができない")
        elif fixed["hours"] > MONTHLY_OVERTIME_REFERENCE_HOURS:
            add(
                "fixed_overtime_hours_high",
                f"みなし残業が月{fixed['hours']}時間で、特別条項なしの上限"
                f"{MONTHLY_OVERTIME_REFERENCE_HOURS}時間を超える前提になっている",
            )
        if fixed["annual_amount"] is None:
            add("fixed_overtime_amount_unknown", "固定残業代の金額が不明。基本給を分離できない")
        if fixed["hours"] is not None and fixed["hours"] > 0 and working["system"] == "discretionary":
            add(
                "discretionary_with_fixed_overtime",
                "裁量労働制と固定残業時間が併記されている。制度の適用範囲を確認する",
            )

    if compensation["bonus_included_in_range"] is None:
        add("bonus_treatment_unknown", "賞与が提示年収に含まれるか不明。含む前提で比較しない")

    if working["monthly_scheduled_hours"] is None:
        add("scheduled_hours_unknown", "所定労働時間が不明。時給換算ができない")

    if pay["range_ratio"] is not None and Decimal(str(pay["range_ratio"])) >= WIDE_RANGE_RATIO:
        add(
            "pay_range_wide",
            f"年収レンジの上下が{pay['range_ratio']}倍開いている。どの条件で下限・上限になるかを確認する",
        )

    if not requirements:
        add("requirements_not_captured", "要件が取り込まれていない。必須と歓迎の区別ができない")
    elif not any(item["measurable"] for item in requirements):
        add(
            "requirements_not_measurable",
            "要件がすべて抽象的で、経験年数や具体的な成果物で確認できない",
        )
    return flags


def analyze(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    title = _require_text(data.get("title"), "title")

    compensation = parse_compensation(data.get("compensation", {}))
    working = parse_working_hours(data.get("working_hours"))
    requirements = parse_requirements(data.get("requirements"))
    pay = build_pay_breakdown(compensation, working)

    counts = {kind: {status: 0 for status in USER_STATUSES} for kind in REQUIREMENT_KINDS}
    for item in requirements:
        counts[item["kind"]][item["user_status"]] += 1

    open_questions = [
        _require_text(question, f"open_questions[{index}]")
        for index, question in enumerate(_require_list(data.get("open_questions", []), "open_questions"))
    ]

    return {
        "title": title,
        "employment_type": data.get("employment_type"),
        "working_time_system": working["system"],
        "pay": pay,
        "requirement_counts": counts,
        "requirements": requirements,
        "unmet_must_requirements": [
            item["text"] for item in requirements if item["kind"] == "must" and item["user_status"] == "unmet"
        ],
        "unknown_requirement_count": sum(
            1 for item in requirements if item["user_status"] == "unknown"
        ),
        "flags": collect_flags(compensation, working, pay, requirements),
        "open_questions": open_questions,
        "notes": [
            "この出力は求人票の記載を分解しただけで、採用可能性も企業評価も含まない",
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
        report = analyze(payload)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
