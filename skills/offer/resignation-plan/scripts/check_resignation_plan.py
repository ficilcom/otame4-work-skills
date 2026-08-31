#!/usr/bin/env python3
"""Check the dates and the checklist behind a planned resignation.

退職の申出日、退職日、入社日の関係を日数で確認し、申出期限、在籍の重なり、空白
期間、有給の消化可能日数、受け取る書類と返す物の確認状況を機械的に洗い出す。
退職できるかどうかの法的判断はしない。制度は時点で変わるため一次情報で確認する。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


CONTRACT_TYPES = ("indefinite", "fixed_term", "unknown")
RULE_SOURCES = ("employment_rules", "contract", "unknown")
TASK_STATUSES = ("done", "planned", "none")
ITEM_STATUSES = ("confirmed", "pending", "not_applicable", "unknown")

# 内定承諾より前に退職を申し出ると、内定が流れたときに戻れなくなる。
# (code, label, group)
CHECKLIST: tuple[tuple[str, str, str], ...] = (
    ("confirm_rules", "就業規則の退職に関する定めの確認", "task"),
    ("notice_to_manager", "直属の上長への申出", "task"),
    ("resignation_letter", "退職届・退職願の提出", "task"),
    ("handover_plan", "引き継ぎ計画の作成", "task"),
    ("handover_execution", "引き継ぎの実施", "task"),
    ("paid_leave_request", "有給休暇の消化の申請", "task"),
    ("notify_outside", "社外への連絡（会社の方針に従う）", "task"),
    ("health_insurance", "健康保険の切替", "task"),
    ("pension", "年金の手続き", "task"),
    ("residual_tax", "住民税の納付方法の確認", "task"),
    ("retirement_savings", "企業年金・確定拠出年金の移換", "task"),
    ("rishokuhyo", "離職票", "receive"),
    ("employment_insurance_card", "雇用保険被保険者証", "receive"),
    ("withholding_slip", "源泉徴収票", "receive"),
    ("pension_number", "年金手帳または基礎年金番号の通知", "receive"),
    ("retirement_certificate", "退職証明書", "receive"),
    ("health_insurance_card", "健康保険証", "return"),
    ("employee_id", "社員証・入館証", "return"),
    ("company_devices", "貸与されたPC・携帯・鍵", "return"),
    ("business_cards", "名刺（自分の分と受け取った分）", "return"),
    ("work_materials", "業務資料・データ", "return"),
)
CHECKLIST_CODES = {code for code, _, _ in CHECKLIST}
TASK_CODES = {code for code, _, group in CHECKLIST if group == "task"}


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _optional_bool(value: object, path: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean or null")
    return value


def _optional_date(value: object, path: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date string (YYYY-MM-DD) or null")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} is not an ISO date (YYYY-MM-DD): {error}") from error


def _optional_int(value: object, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer or null")
    if value < 0:
        raise ValueError(f"{path} must not be negative")
    return value


def count_weekdays(start: date, end: date) -> int:
    """申出日の翌日から退職日までの平日数。祝日と会社の休日は含まない概算。"""
    if end <= start:
        return 0
    days = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


def parse_current(raw: object) -> dict[str, Any]:
    current = _require_object(raw if raw is not None else {}, "current")
    contract_type = current.get("contract_type", "unknown")
    if contract_type not in CONTRACT_TYPES:
        raise ValueError(f"current.contract_type must be one of {list(CONTRACT_TYPES)}")
    rule_source = current.get("notice_rule_source", "unknown")
    if rule_source not in RULE_SOURCES:
        raise ValueError(f"current.notice_rule_source must be one of {list(RULE_SOURCES)}")
    return {
        "contract_type": contract_type,
        "notice_rule_source": rule_source,
        "notice_days_required": _optional_int(
            current.get("notice_days_required"), "current.notice_days_required"
        ),
        "contract_end": _optional_date(current.get("contract_end"), "current.contract_end"),
    }


def parse_dates(raw: object) -> dict[str, Any]:
    dates = _require_object(raw if raw is not None else {}, "dates")
    notice = _optional_date(dates.get("intended_notice_date"), "dates.intended_notice_date")
    last_day = _optional_date(dates.get("desired_last_day"), "dates.desired_last_day")
    start_new = _optional_date(dates.get("start_date_new"), "dates.start_date_new")
    if notice is not None and last_day is not None and last_day < notice:
        raise ValueError("dates.desired_last_day must not precede dates.intended_notice_date")
    return {
        "intended_notice_date": notice,
        "desired_last_day": last_day,
        "start_date_new": start_new,
        "paid_leave_days_remaining": _optional_int(
            dates.get("paid_leave_days_remaining"), "dates.paid_leave_days_remaining"
        ),
    }


def parse_items(raw: object) -> dict[str, dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "items")
    parsed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"items[{index}]")
        code = item.get("code")
        if code not in CHECKLIST_CODES:
            raise ValueError(f"items[{index}].code is not a known checklist code: {code!r}")
        if code in parsed:
            raise ValueError(f"items[{index}].code is duplicated: {code!r}")
        statuses = TASK_STATUSES if code in TASK_CODES else ITEM_STATUSES
        status = item.get("status", "none" if code in TASK_CODES else "unknown")
        if status not in statuses:
            raise ValueError(f"items[{index}].status must be one of {list(statuses)}")
        note = item.get("note")
        if note is not None and not isinstance(note, str):
            raise ValueError(f"items[{index}].note must be a string or null")
        parsed[code] = {"status": status, "note": note.strip() if isinstance(note, str) else None}
    return parsed


def build_schedule(current: dict[str, Any], dates: dict[str, Any]) -> dict[str, Any]:
    notice = dates["intended_notice_date"]
    last_day = dates["desired_last_day"]
    start_new = dates["start_date_new"]

    notice_days = (last_day - notice).days if notice and last_day else None
    gap_days = (start_new - last_day).days - 1 if last_day and start_new else None
    weekdays = count_weekdays(notice, last_day) if notice and last_day else None

    remaining = dates["paid_leave_days_remaining"]
    leave_fits = None
    if remaining is not None and weekdays is not None:
        leave_fits = remaining <= weekdays

    return {
        "intended_notice_date": notice.isoformat() if notice else None,
        "desired_last_day": last_day.isoformat() if last_day else None,
        "start_date_new": start_new.isoformat() if start_new else None,
        "notice_to_last_day_days": notice_days,
        "notice_days_required": current["notice_days_required"],
        "weekdays_until_last_day": weekdays,
        "paid_leave_days_remaining": remaining,
        "paid_leave_fits_in_remaining_weekdays": leave_fits,
        "days_between_jobs": gap_days,
    }


def build_checklist(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checklist = []
    for code, label, group in CHECKLIST:
        entry = items.get(code)
        default = "none" if group == "task" else "unknown"
        checklist.append(
            {
                "code": code,
                "label": label,
                "group": group,
                "status": entry["status"] if entry else default,
                "note": entry["note"] if entry else None,
            }
        )
    return checklist


def collect_flags(
    current: dict[str, Any],
    schedule: dict[str, Any],
    checklist: list[dict[str, Any]],
    offer_accepted: bool | None,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, items: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if items:
            flag["items"] = items
        flags.append(flag)

    if offer_accepted is not True:
        add(
            "offer_not_confirmed",
            "転職先の内定承諾が確認できていない。承諾前に退職を申し出ると、内定が流れたときに戻れなくなる",
        )

    if current["notice_rule_source"] == "unknown" or current["notice_days_required"] is None:
        add(
            "notice_rule_unconfirmed",
            "就業規則の退職に関する定めを確認していない。申出の期限と手続きが決まらない",
        )
    else:
        actual = schedule["notice_to_last_day_days"]
        required = current["notice_days_required"]
        if actual is not None and actual < required:
            add(
                "notice_period_short",
                f"申出から退職日までが{actual}日で、就業規則の定める{required}日に届かない。日程の調整を要する",
            )

    if current["contract_type"] == "fixed_term":
        add(
            "fixed_term_contract",
            "有期契約のため、期間途中の退職は無期契約と扱いが違う。契約書と就業規則を確認する",
        )
    elif current["contract_type"] == "unknown":
        add("contract_type_unknown", "有期か無期かが確定していない。適用される手続きが決まらない")

    gap = schedule["days_between_jobs"]
    if gap is not None:
        if gap < 0:
            add(
                "overlapping_employment",
                "退職日より前に入社日が来ており、在籍が重なる。二重在籍の可否を両社に確認する",
            )
        elif gap > 0:
            add(
                "gap_between_jobs",
                f"退職日と入社日の間に{gap}日の空白がある。健康保険、年金、住民税の手続きが自分側に発生する",
            )

    if schedule["paid_leave_fits_in_remaining_weekdays"] is False:
        add(
            "paid_leave_may_not_fit",
            f"有給の残り{schedule['paid_leave_days_remaining']}日に対し、退職日までの平日は"
            f"{schedule['weekdays_until_last_day']}日しかない。引き継ぎと両立するかを先に決める",
        )
    elif schedule["paid_leave_days_remaining"] is None:
        add("paid_leave_unknown", "有給の残日数が不明。消化の計画が立てられない")

    not_started = [entry["code"] for entry in checklist if entry["group"] == "task" and entry["status"] == "none"]
    if not_started:
        add("tasks_not_started", "着手していない手続きがある", not_started)

    unconfirmed = [
        entry["code"]
        for entry in checklist
        if entry["group"] in ("receive", "return") and entry["status"] == "unknown"
    ]
    if unconfirmed:
        add(
            "documents_unconfirmed",
            "受け取る書類・返す物のうち、確認していないものがある",
            unconfirmed,
        )
    return flags


def check(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    current = parse_current(data.get("current"))
    dates = parse_dates(data.get("dates"))
    items = parse_items(data.get("items"))
    offer_accepted = _optional_bool(data.get("offer_accepted"), "offer_accepted")

    schedule = build_schedule(current, dates)
    checklist = build_checklist(items)

    return {
        "as_of": data.get("as_of"),
        "contract_type": current["contract_type"],
        "offer_accepted": offer_accepted,
        "schedule": schedule,
        "checklist": checklist,
        "summary": {
            "tasks_total": sum(1 for entry in checklist if entry["group"] == "task"),
            "tasks_done": sum(
                1 for entry in checklist if entry["group"] == "task" and entry["status"] == "done"
            ),
            "documents_to_receive_confirmed": sum(
                1
                for entry in checklist
                if entry["group"] == "receive" and entry["status"] == "confirmed"
            ),
            "items_to_return_confirmed": sum(
                1
                for entry in checklist
                if entry["group"] == "return" and entry["status"] == "confirmed"
            ),
        },
        "flags": collect_flags(current, schedule, checklist, offer_accepted),
        "notes": [
            "この出力は日程と手続きの確認であり、退職できるかどうかの法的判断ではない",
            "平日数は土日を除いた概算で、祝日と会社の休日を含まない",
            "社会保険・税・雇用保険の手続きは時点で変わる。実行前に一次情報で確認する",
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
        report = check(payload)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
