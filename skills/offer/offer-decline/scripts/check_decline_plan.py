#!/usr/bin/env python3
"""Check the order and the loose ends before declining offers or withdrawing from selections.

受ける側が確定しているか、辞退がどの段階のものか、経路ごとに誰へ伝えるか、期限が
残っているか、精算や返却が残っていないかを機械的に確認する。辞退すべきかどうかは
判定しない。承諾後の辞退について法的な結論も出さない。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


# 辞退の段階。実務上も重みも別物なので、まとめて扱わない。
DECLINE_STAGES = ("in_selection", "offered_not_accepted", "offered_accepted", "unknown")
# 応募の経路。誰に伝えるか、誰に影響するかが変わる。
ROUTES = ("direct", "agent", "school_recommendation", "referral", "platform", "unknown")
# 経路ごとに、本人以外へ連絡や確認が要るもの。
ROUTE_EXTRA_CONTACT = {
    "agent": "担当のエージェントを通して伝える。企業へ直接連絡すると経路が二重になる",
    "school_recommendation": "学校の就職課にも連絡する。推薦枠は後続の応募者に影響しうる",
    "referral": "紹介してくれた人にも自分から伝える。企業からの連絡で知る形にしない",
}
# 期限までがこれ以下なら、伝える準備の時間が取れないものとして注記する。
DEADLINE_SOON_DAYS = 2


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


def _optional_date(value: object, path: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date string (YYYY-MM-DD) or null")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} is not an ISO date (YYYY-MM-DD): {error}") from error


def parse_accepting(raw: object) -> dict[str, Any]:
    if raw is None:
        return {"company": None, "accepted": None, "terms_in_writing": None, "start_date": None}
    accepting = _require_object(raw, "accepting")
    return {
        "company": _optional_text(accepting.get("company"), "accepting.company"),
        "accepted": _optional_bool(accepting.get("accepted"), "accepting.accepted"),
        "terms_in_writing": _optional_bool(
            accepting.get("terms_in_writing"), "accepting.terms_in_writing"
        ),
        "start_date": _optional_date(accepting.get("start_date"), "accepting.start_date"),
    }


def parse_declining(raw: object) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "declining")
    declining = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"declining[{index}]"
        item = _require_object(entry, path)
        decline_id = _require_text(item.get("id"), f"{path}.id")
        if decline_id in seen:
            raise ValueError(f"{path}.id is duplicated: {decline_id!r}")
        seen.add(decline_id)

        stage = item.get("stage", "unknown")
        if stage not in DECLINE_STAGES:
            raise ValueError(f"{path}.stage must be one of {list(DECLINE_STAGES)}")
        route = item.get("route", "unknown")
        if route not in ROUTES:
            raise ValueError(f"{path}.route must be one of {list(ROUTES)}")

        loose = _require_object(item.get("loose_ends", {}), f"{path}.loose_ends")
        for key in loose:
            if key not in ("documents_held", "expenses_unsettled", "items_borrowed"):
                raise ValueError(f"{path}.loose_ends has an unknown field: {key!r}")

        declining.append(
            {
                "id": decline_id,
                "company": _require_text(item.get("company"), f"{path}.company"),
                "stage": stage,
                "route": route,
                "deadline": _optional_date(item.get("deadline"), f"{path}.deadline"),
                "notice_sent": bool(item.get("notice_sent", False)),
                "contacted_person": _optional_text(
                    item.get("contacted_person"), f"{path}.contacted_person"
                ),
                "loose_ends": {
                    "documents_held": bool(loose.get("documents_held", False)),
                    "expenses_unsettled": bool(loose.get("expenses_unsettled", False)),
                    "items_borrowed": bool(loose.get("items_borrowed", False)),
                },
                "pressured_to_decline_others": bool(item.get("pressured_to_decline_others", False)),
            }
        )
    return declining


def describe(entry: dict[str, Any], as_of: date | None) -> dict[str, Any]:
    days_to_deadline = (entry["deadline"] - as_of).days if entry["deadline"] and as_of else None
    loose = [key for key, value in entry["loose_ends"].items() if value]
    return {
        "id": entry["id"],
        "company": entry["company"],
        "stage": entry["stage"],
        "route": entry["route"],
        "extra_contact": ROUTE_EXTRA_CONTACT.get(entry["route"]),
        "deadline": entry["deadline"].isoformat() if entry["deadline"] else None,
        "days_to_deadline": days_to_deadline,
        "notice_sent": entry["notice_sent"],
        "contacted_person": entry["contacted_person"],
        "loose_ends": loose,
    }


def collect_flags(
    accepting: dict[str, Any],
    declining: list[dict[str, Any]],
    described: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, items: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if items:
            flag["items"] = items
        flags.append(flag)

    if not declining:
        add("nothing_to_decline", "辞退の対象が取り込まれていない")
        return flags

    # 受ける側が固まる前に辞退すると、どこにも行き先がない状態になりうる。
    keeping_an_offer = any(entry["stage"] != "in_selection" for entry in declining)
    if keeping_an_offer:
        if accepting["accepted"] is not True:
            add(
                "not_accepted_elsewhere",
                "受ける側の承諾が確認できていない。先に辞退すると、どこにも行き先がない状態になりうる",
            )
        elif accepting["terms_in_writing"] is not True:
            add(
                "accepting_terms_not_in_writing",
                "受ける側の労働条件が書面で確認できていない。辞退の前に offer-terms-check で確定させる",
            )

    accepted_declines = [entry["id"] for entry in declining if entry["stage"] == "offered_accepted"]
    if accepted_declines:
        add(
            "declining_after_acceptance",
            "承諾したあとの辞退が含まれる。承諾前の辞退とは実務上の扱いが違う。"
            "先方の準備が進んでいる前提で、早く直接伝える",
            accepted_declines,
        )

    unknown_stage = [entry["id"] for entry in declining if entry["stage"] == "unknown"]
    if unknown_stage:
        add(
            "stage_unknown",
            "選考途中か、内定後か、承諾後かが確定していない。伝え方と急ぎ方が決まらない",
            unknown_stage,
        )

    for route, message in ROUTE_EXTRA_CONTACT.items():
        matching = [entry["id"] for entry in declining if entry["route"] == route]
        if matching:
            add(f"route_{route}", message, matching)

    unknown_route = [entry["id"] for entry in declining if entry["route"] == "unknown"]
    if unknown_route:
        add("route_unknown", "応募の経路が確定していない。誰に伝えるかが決まらない", unknown_route)

    pending = [entry["id"] for entry in declining if not entry["notice_sent"]]
    if pending:
        add("notice_not_sent", "まだ辞退を伝えていない先がある", pending)

    for code, label in (
        ("documents_held", "預けた書類の返却"),
        ("expenses_unsettled", "交通費など精算が残っているもの"),
        ("items_borrowed", "借りている物の返却"),
    ):
        matching = [entry["id"] for entry in declining if entry["loose_ends"][code]]
        if matching:
            add(f"loose_end_{code}", f"{label}が残っている先がある", matching)

    passed = [
        entry["id"]
        for entry in described
        if entry["days_to_deadline"] is not None and entry["days_to_deadline"] < 0
    ]
    if passed:
        add("deadline_passed", "返答の期限を過ぎている先がある。まず連絡する", passed)

    soon = [
        entry["id"]
        for entry in described
        if entry["days_to_deadline"] is not None and 0 <= entry["days_to_deadline"] <= DEADLINE_SOON_DAYS
    ]
    if soon:
        add("deadline_soon", "返答の期限が迫っている先がある", soon)

    pressured = [entry["id"] for entry in declining if entry["pressured_to_decline_others"]]
    if pressured:
        add(
            "pressured_to_decline_others",
            "他社の辞退を求められたと記録されている先がある。応じる義務はない。"
            "求められた内容と時期を事実として記録し、応じるかどうかは自分で決める",
            pressured,
        )

    return flags


def check(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    as_of = _optional_date(data.get("as_of"), "as_of")
    accepting = parse_accepting(data.get("accepting"))
    declining = parse_declining(data.get("declining"))
    described = [describe(entry, as_of) for entry in declining]

    return {
        "as_of": data.get("as_of"),
        "accepting": {
            "company": accepting["company"],
            "accepted": accepting["accepted"],
            "terms_in_writing": accepting["terms_in_writing"],
            "start_date": accepting["start_date"].isoformat() if accepting["start_date"] else None,
        },
        "summary": {
            "declining": len(described),
            "notice_sent": sum(1 for entry in described if entry["notice_sent"]),
            "in_selection": sum(1 for entry in described if entry["stage"] == "in_selection"),
            "offered_not_accepted": sum(
                1 for entry in described if entry["stage"] == "offered_not_accepted"
            ),
            "offered_accepted": sum(
                1 for entry in described if entry["stage"] == "offered_accepted"
            ),
            "with_loose_ends": sum(1 for entry in described if entry["loose_ends"]),
        },
        "declining": described,
        "flags": collect_flags(accepting, declining, described),
        "notes": [
            "この出力は順序と連絡先の確認であり、辞退すべきかどうかの判断ではない",
            "承諾後の辞退の法的な扱いは事案による。ここでは結論を出さない",
            "辞退の理由を詳しく述べる義務はない。伝えるかどうかは自分で決める",
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
