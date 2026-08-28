#!/usr/bin/env python3
"""Check an offer's stated working conditions item by item.

内定時に提示された労働条件について、明示事項が書面（電子交付を含む）で示されて
いるかを項目ごとに数え、求人票・面接での説明との食い違いと、承諾期限までに書面が
揃うかを機械的に洗い出す。適法性は判定しない。明示事項の範囲は改正で変わるため、
`references/required-items.md` の出典から一次情報を確認して使う。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


ITEM_STATUSES = ("stated", "missing", "unclear", "unknown")
SOURCES = (
    "notice",
    "contract",
    "offer_letter",
    "verbal",
    "posting",
    "interview",
    "agent",
    "unknown",
)
WRITTEN_SOURCES = ("notice", "contract", "offer_letter")
DOCUMENT_KINDS = (
    "working_conditions_notice",
    "employment_contract",
    "offer_letter",
    "none",
    "unknown",
)
DOCUMENT_FORMS = ("written", "electronic", "verbal", "none", "unknown")
WRITTEN_FORMS = ("written", "electronic")
CONTRACT_TYPES = ("indefinite", "fixed_term", "unknown")

# 承諾期限までの日数がこれを下回る場合、書面確認の時間が取れないものとして注記する。
SHORT_ACCEPTANCE_WINDOW_DAYS = 7

# (code, label, group, applies_to)
# group は明示の強さの区分であり、法的な当否の判定ではない。
#   required_written  … 書面等での明示が求められる事項
#   required          … 明示事項だが書面交付の対象外
#   part_time_document … 短時間・有期雇用の労働者に文書で明示される事項
#   conditional       … 定めがある場合に明示される事項
#   practical         … 法定の区分ではないが、入社前に確定させたい確認項目
CHECKLIST: tuple[tuple[str, str, str, str], ...] = (
    ("contract_period", "労働契約の期間", "required_written", "all"),
    ("renewal_criteria", "有期契約を更新する場合の基準", "required_written", "fixed_term"),
    ("renewal_limit", "更新上限の有無と内容", "required_written", "fixed_term"),
    ("workplace", "就業の場所", "required_written", "all"),
    ("workplace_change_scope", "就業の場所の変更の範囲", "required_written", "all"),
    ("duties", "従事すべき業務の内容", "required_written", "all"),
    ("duties_change_scope", "業務の内容の変更の範囲", "required_written", "all"),
    ("start_end_time", "始業・終業の時刻", "required_written", "all"),
    ("overtime_presence", "所定労働時間を超える労働の有無", "required_written", "all"),
    ("breaks_holidays_leave", "休憩時間・休日・休暇", "required_written", "all"),
    ("shift_rotation", "交替制勤務の就業時転換", "required_written", "shift"),
    ("wage_determination", "賃金の決定・計算・支払の方法", "required_written", "all"),
    ("wage_closing_payment", "賃金の締切・支払の時期", "required_written", "all"),
    ("resignation", "退職に関する事項（解雇の事由を含む）", "required_written", "all"),
    (
        "conversion_opportunity",
        "無期転換申込みの機会",
        "required_written",
        "fixed_term_conversion",
    ),
    (
        "conversion_conditions",
        "無期転換後の労働条件",
        "required_written",
        "fixed_term_conversion",
    ),
    ("pay_raise", "昇給に関する事項", "required", "all"),
    ("bonus_presence", "賞与の有無", "part_time_document", "part_time_or_fixed_term"),
    (
        "retirement_allowance_presence",
        "退職手当の有無",
        "part_time_document",
        "part_time_or_fixed_term",
    ),
    ("consultation_contact", "相談窓口", "part_time_document", "part_time_or_fixed_term"),
    ("retirement_allowance", "退職手当の定め", "conditional", "if_provided"),
    ("bonus", "賞与・臨時の賃金の定め", "conditional", "if_provided"),
    ("cost_burden", "労働者に負担させる食費・作業用品", "conditional", "if_provided"),
    ("safety_health", "安全衛生", "conditional", "if_provided"),
    ("training", "職業訓練", "conditional", "if_provided"),
    ("accident_compensation", "災害補償・業務外の傷病扶助", "conditional", "if_provided"),
    ("awards_sanctions", "表彰・制裁", "conditional", "if_provided"),
    ("leave_of_absence", "休職", "conditional", "if_provided"),
    (
        "fixed_overtime_detail",
        "固定残業代の時間数・金額・超過分の取扱い",
        "practical",
        "if_provided",
    ),
    ("social_insurance", "社会保険・雇用保険の加入", "practical", "all"),
    ("probation_conditions", "試用期間中の労働条件", "practical", "if_provided"),
    ("commute_allowance", "通勤手当", "practical", "if_provided"),
)
CHECKLIST_CODES = {code for code, _, _, _ in CHECKLIST}


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


def _optional_amount(value: object, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number or null")
    if value < 0:
        raise ValueError(f"{path} must not be negative")
    return int(value)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def parse_document(raw: object) -> dict[str, Any]:
    document = _require_object(raw if raw is not None else {}, "document")
    kind = document.get("kind", "unknown")
    if kind not in DOCUMENT_KINDS:
        raise ValueError(f"document.kind must be one of {list(DOCUMENT_KINDS)}")
    form = document.get("form", "unknown")
    if form not in DOCUMENT_FORMS:
        raise ValueError(f"document.form must be one of {list(DOCUMENT_FORMS)}")
    received = _optional_date(document.get("received_date"), "document.received_date")
    return {
        "kind": kind,
        "form": form,
        "received_date": received,
        "is_written": kind != "none" and form in WRITTEN_FORMS,
    }


def parse_contract(raw: object) -> dict[str, Any]:
    contract = _require_object(raw if raw is not None else {}, "contract")
    contract_type = contract.get("type", "unknown")
    if contract_type not in CONTRACT_TYPES:
        raise ValueError(f"contract.type must be one of {list(CONTRACT_TYPES)}")
    return {
        "type": contract_type,
        "shift_work": _optional_bool(contract.get("shift_work"), "contract.shift_work"),
        "part_time_or_fixed_term": _optional_bool(
            contract.get("part_time_or_fixed_term"), "contract.part_time_or_fixed_term"
        ),
        "conversion_applicable": _optional_bool(
            contract.get("conversion_applicable"), "contract.conversion_applicable"
        ),
    }


def parse_offer(raw: object) -> dict[str, Any]:
    offer = _require_object(raw if raw is not None else {}, "offer")
    offer_date = _optional_date(offer.get("offer_date"), "offer.offer_date")
    deadline = _optional_date(offer.get("acceptance_deadline"), "offer.acceptance_deadline")
    if offer_date is not None and deadline is not None and deadline < offer_date:
        raise ValueError("offer.acceptance_deadline must not precede offer.offer_date")
    return {"offer_date": offer_date, "acceptance_deadline": deadline}


def parse_items(raw: object) -> dict[str, dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "items")
    parsed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"items[{index}]")
        code = _require_text(item.get("code"), f"items[{index}].code")
        if code not in CHECKLIST_CODES:
            raise ValueError(f"items[{index}].code is not a known checklist code: {code!r}")
        if code in parsed:
            raise ValueError(f"items[{index}].code is duplicated: {code!r}")
        status = item.get("status", "unknown")
        if status not in ITEM_STATUSES:
            raise ValueError(f"items[{index}].status must be one of {list(ITEM_STATUSES)}")
        source = item.get("source", "unknown")
        if source not in SOURCES:
            raise ValueError(f"items[{index}].source must be one of {list(SOURCES)}")
        note = item.get("note")
        if note is not None and not isinstance(note, str):
            raise ValueError(f"items[{index}].note must be a string or null")
        parsed[code] = {
            "status": status,
            "source": source,
            "applicable": _optional_bool(item.get("applicable"), f"items[{index}].applicable"),
            "note": note.strip() if isinstance(note, str) else None,
        }
    return parsed


def resolve_requirement(applies_to: str, contract: dict[str, Any], applicable: bool | None) -> str:
    """その項目が確認対象かを yes / no / depends で返す。"""
    if applies_to == "all":
        return "yes"
    if applies_to == "fixed_term":
        if contract["type"] == "fixed_term":
            return "yes"
        return "no" if contract["type"] == "indefinite" else "depends"
    if applies_to == "fixed_term_conversion":
        if contract["type"] == "indefinite":
            return "no"
        if contract["conversion_applicable"] is True:
            return "yes"
        if contract["conversion_applicable"] is False:
            return "no"
        return "depends"
    if applies_to == "shift":
        if contract["shift_work"] is True:
            return "yes"
        return "no" if contract["shift_work"] is False else "depends"
    if applies_to == "part_time_or_fixed_term":
        if contract["part_time_or_fixed_term"] is True or contract["type"] == "fixed_term":
            return "yes"
        if contract["part_time_or_fixed_term"] is False and contract["type"] == "indefinite":
            return "no"
        return "depends"
    if applies_to == "if_provided":
        if applicable is True:
            return "yes"
        return "no" if applicable is False else "depends"
    raise ValueError(f"unknown applies_to: {applies_to!r}")


def build_items(contract: dict[str, Any], provided: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for code, label, group, applies_to in CHECKLIST:
        entry = provided.get(code)
        applicable = entry["applicable"] if entry else None
        required = resolve_requirement(applies_to, contract, applicable)
        status = entry["status"] if entry else "unknown"
        source = entry["source"] if entry else "unknown"
        items.append(
            {
                "code": code,
                "label": label,
                "group": group,
                "required": required,
                "status": status,
                "source": source,
                "in_writing": status == "stated" and source in WRITTEN_SOURCES,
                "checked": entry is not None,
                "note": entry["note"] if entry else None,
            }
        )
    return items


def parse_comparisons(raw: object) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "comparisons")
    parsed = []
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"comparisons[{index}]")
        topic = _require_text(item.get("topic"), f"comparisons[{index}].topic")
        values_raw = _require_object(item.get("values", {}), f"comparisons[{index}].values")
        values: dict[str, str] = {}
        for source, value in values_raw.items():
            if source not in SOURCES:
                raise ValueError(
                    f"comparisons[{index}].values has an unknown source {source!r}"
                )
            values[source] = _require_text(value, f"comparisons[{index}].values.{source}")
        amounts_raw = _require_object(item.get("amounts", {}), f"comparisons[{index}].amounts")
        amounts: dict[str, int] = {}
        for source, value in amounts_raw.items():
            if source not in SOURCES:
                raise ValueError(
                    f"comparisons[{index}].amounts has an unknown source {source!r}"
                )
            amount = _optional_amount(value, f"comparisons[{index}].amounts.{source}")
            if amount is not None:
                amounts[source] = amount
        parsed.append(evaluate_comparison(topic, values, amounts))
    return parsed


def evaluate_comparison(
    topic: str, values: dict[str, str], amounts: dict[str, int]
) -> dict[str, Any]:
    written = {source: text for source, text in values.items() if source in WRITTEN_SOURCES}
    other = {source: text for source, text in values.items() if source not in WRITTEN_SOURCES}

    if len(values) < 2:
        verdict = "insufficient"
    elif len({_normalize(text) for text in values.values()}) > 1:
        verdict = "different"
    else:
        verdict = "consistent"
    if not written and other:
        verdict = "not_in_written_document"

    amount_gap = None
    written_amounts = [amount for source, amount in amounts.items() if source in WRITTEN_SOURCES]
    other_amounts = [amount for source, amount in amounts.items() if source not in WRITTEN_SOURCES]
    if written_amounts and other_amounts:
        written_amount = min(written_amounts)
        other_max = max(other_amounts)
        amount_gap = {
            "written": written_amount,
            "other_source_max": other_max,
            "difference": written_amount - other_max,
        }

    return {
        "topic": topic,
        "verdict": verdict,
        "values": values,
        "amount_gap": amount_gap,
    }


def build_acceptance(document: dict[str, Any], offer: dict[str, Any]) -> dict[str, Any]:
    deadline = offer["acceptance_deadline"]
    offer_date = offer["offer_date"]
    window_days = (deadline - offer_date).days if deadline and offer_date else None

    received = document["received_date"]
    if deadline is None:
        written_before_deadline: bool | None = None
    elif document["is_written"] and received is not None:
        written_before_deadline = received <= deadline
    elif document["is_written"] and received is None:
        written_before_deadline = None
    else:
        written_before_deadline = False

    return {
        "offer_date": offer_date.isoformat() if offer_date else None,
        "acceptance_deadline": deadline.isoformat() if deadline else None,
        "written_terms_received_date": received.isoformat() if received else None,
        "window_days": window_days,
        "written_terms_before_deadline": written_before_deadline,
    }


def collect_flags(
    document: dict[str, Any],
    contract: dict[str, Any],
    items: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    acceptance: dict[str, Any],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, codes: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if codes:
            flag["items"] = codes
        flags.append(flag)

    if not document["is_written"]:
        add(
            "no_written_terms",
            "労働条件が書面（電子交付を含む）で受け取れていない。口頭・求人票の記載は入社後の条件を確定しない",
        )

    required = [item for item in items if item["required"] == "yes"]

    missing = [item["code"] for item in required if item["status"] == "missing"]
    if missing:
        add("required_item_missing", "確認対象の項目に記載がない", missing)

    unclear = [item["code"] for item in required if item["status"] == "unclear"]
    if unclear:
        add("required_item_unclear", "記載はあるが範囲や条件が読み取れない項目がある", unclear)

    unchecked = [item["code"] for item in required if item["status"] == "unknown"]
    if unchecked:
        add("required_item_unchecked", "まだ確認していない項目がある。未確認を「記載あり」と扱わない", unchecked)

    outside = [
        item["code"]
        for item in required
        if item["group"] in ("required_written", "part_time_document")
        and item["status"] == "stated"
        and item["source"] not in WRITTEN_SOURCES
    ]
    if outside:
        add(
            "stated_outside_written_document",
            "書面ではなく口頭・求人票・エージェント経由でしか確認できていない項目がある",
            outside,
        )

    change_scope = [
        item["code"]
        for item in items
        if item["code"] in ("workplace_change_scope", "duties_change_scope")
        and item["status"] in ("missing", "unclear", "unknown")
    ]
    if change_scope:
        add(
            "change_scope_unconfirmed",
            "就業場所・業務の「変更の範囲」が確認できていない。転勤や職種変更がどこまで及ぶかを書面で確認する",
            change_scope,
        )

    if contract["type"] == "fixed_term":
        renewal = [
            item["code"]
            for item in items
            if item["code"] in ("renewal_criteria", "renewal_limit")
            and item["status"] != "stated"
        ]
        if renewal:
            add(
                "fixed_term_renewal_unconfirmed",
                "有期契約だが、更新の基準または更新上限が確認できていない",
                renewal,
            )
    if contract["type"] == "unknown":
        add("contract_type_unknown", "有期か無期かが確定していない。確認すべき項目が決まらない")

    depends = [item["code"] for item in items if item["required"] == "depends"]
    if depends:
        add(
            "applicability_unknown",
            "該当するかどうかが未確定の項目がある。制度の有無を先に確認する",
            depends,
        )

    conflicts = [item["topic"] for item in comparisons if item["verdict"] == "different"]
    if conflicts:
        add("source_conflict", f"出典間で記載が食い違う条件がある: {'、'.join(conflicts)}")

    not_written = [
        item["topic"] for item in comparisons if item["verdict"] == "not_in_written_document"
    ]
    if not_written:
        add(
            "terms_not_in_written_document",
            f"求人票・面接で示されたが書面にない条件がある: {'、'.join(not_written)}",
        )

    lower = [
        item["topic"]
        for item in comparisons
        if item["amount_gap"] is not None and item["amount_gap"]["difference"] < 0
    ]
    if lower:
        add(
            "amount_lower_in_written_document",
            f"書面の金額が他の出典より低い条件がある: {'、'.join(lower)}",
        )

    if acceptance["written_terms_before_deadline"] is False:
        add(
            "deadline_before_written_terms",
            "書面で条件を受け取る前に承諾期限が来る。期限の延長か、書面の先行提示を求めるかを検討する",
        )
    window = acceptance["window_days"]
    if window is not None and window < SHORT_ACCEPTANCE_WINDOW_DAYS:
        add(
            "short_acceptance_window",
            f"承諾期限までが{window}日で、書面の確認と比較の時間が取りにくい",
        )

    return flags


def check(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    employer = _require_text(data.get("employer"), "employer")

    document = parse_document(data.get("document"))
    contract = parse_contract(data.get("contract"))
    offer = parse_offer(data.get("offer"))
    items = build_items(contract, parse_items(data.get("items")))
    comparisons = parse_comparisons(data.get("comparisons"))
    acceptance = build_acceptance(document, offer)

    required = [item for item in items if item["required"] == "yes"]
    summary = {
        "required_total": len(required),
        "stated_in_writing": sum(1 for item in required if item["in_writing"]),
        "stated_outside_writing": sum(
            1 for item in required if item["status"] == "stated" and not item["in_writing"]
        ),
        "missing": sum(1 for item in required if item["status"] == "missing"),
        "unclear": sum(1 for item in required if item["status"] == "unclear"),
        "unchecked": sum(1 for item in required if item["status"] == "unknown"),
        "applicability_unknown": sum(1 for item in items if item["required"] == "depends"),
    }

    open_questions = [
        _require_text(question, f"open_questions[{index}]")
        for index, question in enumerate(
            _require_list(data.get("open_questions", []), "open_questions")
        )
    ]

    return {
        "employer": employer,
        "document": {
            "kind": document["kind"],
            "form": document["form"],
            "is_written": document["is_written"],
        },
        "contract": contract,
        "acceptance": acceptance,
        "summary": summary,
        "items": items,
        "comparisons": comparisons,
        "flags": collect_flags(document, contract, items, comparisons, acceptance),
        "open_questions": open_questions,
        "notes": [
            "この出力は記載の有無と出典の食い違いを数えたものであり、労働条件の適法性の判定ではない",
            "明示事項の範囲は改正で変わる。判断に使う前に厚生労働省の公表資料で現在の内容を確認する",
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
