#!/usr/bin/env python3
"""Sort incoming scout messages by what they actually disclose.

受け取ったスカウトやエージェント経由の求人について、企業名の明示、条件の記載、
個別化の有無、返信期限、同一企業の重複を機械的に確認し、次に何をする段階かに
振り分ける。求人の良し悪しは判定しない。書かれていない条件を推測しない。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


SENDERS = ("company", "agent", "platform", "unknown")
PAY_CLAIM_TYPES = ("range", "maximum", "possible", "none")
INTEREST_LEVELS = ("yes", "maybe", "no", "unknown")
# 条件として最低限そろっていないと、求人票の読み解きに渡せない項目。
CONDITION_FIELDS = ("pay", "location", "employment_type", "duties")
# 返信期限までがこれ以下なら、判断の時間が取れないものとして注記する。
DEADLINE_SOON_DAYS = 3


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


def _optional_date(value: object, path: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date string (YYYY-MM-DD) or null")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} is not an ISO date (YYYY-MM-DD): {error}") from error


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def parse_scout(raw: object, index: int) -> dict[str, Any]:
    path = f"scouts[{index}]"
    item = _require_object(raw, path)

    sender = item.get("from", "unknown")
    if sender not in SENDERS:
        raise ValueError(f"{path}.from must be one of {list(SENDERS)}")
    pay_claim = item.get("pay_claim_type", "none")
    if pay_claim not in PAY_CLAIM_TYPES:
        raise ValueError(f"{path}.pay_claim_type must be one of {list(PAY_CLAIM_TYPES)}")
    interest = item.get("user_interest", "unknown")
    if interest not in INTEREST_LEVELS:
        raise ValueError(f"{path}.user_interest must be one of {list(INTEREST_LEVELS)}")

    conditions_raw = _require_object(item.get("conditions", {}), f"{path}.conditions")
    conditions = {}
    for field in CONDITION_FIELDS:
        value = conditions_raw.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{path}.conditions.{field} must be a boolean or null")
        conditions[field] = bool(value)
    for key in conditions_raw:
        if key not in CONDITION_FIELDS:
            raise ValueError(f"{path}.conditions has an unknown field: {key!r}")

    personalized = [
        _require_text(reason, f"{path}.personalized[{position}]")
        for position, reason in enumerate(
            _require_list(item.get("personalized", []), f"{path}.personalized")
        )
    ]

    return {
        "id": _require_text(item.get("id"), f"{path}.id"),
        "from": sender,
        "company": _optional_text(item.get("company"), f"{path}.company"),
        "role": _optional_text(item.get("role"), f"{path}.role"),
        "received": _optional_date(item.get("received"), f"{path}.received"),
        "reply_deadline": _optional_date(item.get("reply_deadline"), f"{path}.reply_deadline"),
        "conditions": conditions,
        "personalized": personalized,
        "pay_claim_type": pay_claim,
        "requires_registration": bool(item.get("requires_registration", False)),
        "user_interest": interest,
    }


def route(scout: dict[str, Any], missing: list[str]) -> str:
    """次に何をする段階かを、記載の状態から機械的に決める。良し悪しの判定ではない。"""
    if scout["user_interest"] == "no":
        return "declined"
    if scout["company"] is None:
        return "needs_company_name"
    if missing:
        return "needs_conditions"
    if scout["user_interest"] == "yes":
        return "ready_for_posting_analysis"
    return "user_decision_pending"


def describe(scout: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in CONDITION_FIELDS if not scout["conditions"][field]]
    return {
        "id": scout["id"],
        "from": scout["from"],
        "company": scout["company"],
        "role": scout["role"],
        "company_named": scout["company"] is not None,
        "missing_conditions": missing,
        "personalized": bool(scout["personalized"]),
        "personalization_reasons": scout["personalized"],
        "pay_claim_type": scout["pay_claim_type"],
        "requires_registration": scout["requires_registration"],
        "user_interest": scout["user_interest"],
        "routing": route(scout, missing),
    }


def collect_flags(
    scouts: list[dict[str, Any]], described: list[dict[str, Any]], as_of: date | None
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, items: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if items:
            flag["items"] = items
        flags.append(flag)

    if not scouts:
        add("scouts_not_captured", "スカウトが取り込まれていない")
        return flags

    template = [entry["id"] for entry in described if not entry["personalized"]]
    if template:
        add(
            "no_personalization",
            "経歴に触れた記述がないスカウトがある。一斉送信の可能性を前提に、条件の記載だけで判断する",
            template,
        )

    unnamed = [entry["id"] for entry in described if not entry["company_named"]]
    if unnamed:
        add(
            "company_not_named",
            "企業名が明かされていないスカウトがある。企業研究も求人票の読み解きもできない",
            unnamed,
        )

    incomplete = [entry["id"] for entry in described if entry["missing_conditions"]]
    if incomplete:
        add(
            "conditions_incomplete",
            "給与・勤務地・雇用形態・業務内容のいずれかが書かれていないスカウトがある",
            incomplete,
        )

    soft_pay = [
        entry["id"] for entry in described if entry["pay_claim_type"] in ("maximum", "possible")
    ]
    if soft_pay:
        add(
            "pay_claim_not_an_offer",
            "「最大」「可能」といった書き方の年収が示されているスカウトがある。提示された条件ではない",
            soft_pay,
        )

    registration = [entry["id"] for entry in described if entry["requires_registration"]]
    if registration:
        add(
            "registration_required_before_details",
            "詳細を見るのに登録や面談が必要なスカウトがある。経歴を渡す前に、渡す範囲を決める",
            registration,
        )

    seen: dict[str, list[str]] = {}
    for scout in scouts:
        if scout["company"] is None:
            continue
        seen.setdefault(_normalize(scout["company"]), []).append(scout["id"])
    duplicates = [ids for ids in seen.values() if len(ids) > 1]
    if duplicates:
        add(
            "same_company_multiple_routes",
            "同じ企業のスカウトを複数の経路から受けている。経路が重なると応募が重複しうるため、"
            "どの経路で進めるかを先に決める",
            [scout_id for ids in duplicates for scout_id in ids],
        )

    if as_of is not None:
        passed = [
            scout["id"]
            for scout in scouts
            if scout["reply_deadline"] is not None and scout["reply_deadline"] < as_of
        ]
        if passed:
            add("reply_deadline_passed", "返信期限を過ぎたスカウトがある", passed)
        soon = [
            scout["id"]
            for scout in scouts
            if scout["reply_deadline"] is not None
            and 0 <= (scout["reply_deadline"] - as_of).days <= DEADLINE_SOON_DAYS
        ]
        if soon:
            add(
                "reply_deadline_soon",
                f"返信期限まで{DEADLINE_SOON_DAYS}日以内のスカウトがある。急がされること自体は条件の良さではない",
                soon,
            )

    undecided = [entry["id"] for entry in described if entry["user_interest"] == "unknown"]
    if undecided:
        add("interest_unknown", "関心の有無を確認していないスカウトがある", undecided)

    return flags


def triage(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    as_of = _optional_date(data.get("as_of"), "as_of")

    raw_scouts = _require_list(data.get("scouts", []), "scouts")
    scouts = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_scouts):
        scout = parse_scout(raw, index)
        if scout["id"] in seen:
            raise ValueError(f"scouts[{index}].id is duplicated: {scout['id']!r}")
        seen.add(scout["id"])
        scouts.append(scout)

    described = [describe(scout) for scout in scouts]
    routing: dict[str, list[str]] = {}
    for entry in described:
        routing.setdefault(entry["routing"], []).append(entry["id"])

    return {
        "as_of": data.get("as_of"),
        "summary": {
            "scouts": len(described),
            "company_named": sum(1 for entry in described if entry["company_named"]),
            "personalized": sum(1 for entry in described if entry["personalized"]),
            "conditions_complete": sum(
                1 for entry in described if not entry["missing_conditions"]
            ),
            "routing": {key: len(value) for key, value in sorted(routing.items())},
        },
        "scouts": described,
        "routing": routing,
        "flags": collect_flags(scouts, described, as_of),
        "notes": [
            "この出力は記載の有無と重複を数えたものであり、求人や企業の評価ではない",
            "routing は次に何をする段階かであって、応募すべきかどうかではない",
            "企業名が分かったものだけが company-research と job-posting-analysis に渡せる",
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
        report = triage(payload)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
