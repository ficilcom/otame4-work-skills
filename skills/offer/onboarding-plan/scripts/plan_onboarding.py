#!/usr/bin/env python3
"""Lay out the expectations, probation dates, and checkpoints around a new job.

入社後の最初の数か月について、面接・内定・交渉で示された期待と約束を出典ごとに
並べ、書面にないもの、測り方が決まっていないもの、出典間で食い違うものを出す。
試用期間の終わりの日付を計算し、確かめる場が決まっていない項目と、期限を過ぎた
入社前の手続きを機械的に洗い出す。試用期間の評価も適法性も判定しない。
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_choice,
    optional_date,
    optional_positive_int,
    optional_text,
    require_list,
    require_object,
    require_text,
    run_cli,
    strip_whitespace,
)


SOURCES = (
    "notice",
    "offer_letter",
    "job_description",
    "posting",
    "interview",
    "agent",
    "negotiation",
    "unknown",
)
# 労働条件通知書・雇用契約書、内定通知書、職務記述書として受け取ったものだけを書面とみなす。
# 求人票は募集の条件であり、入社後の条件を確定しない。
WRITTEN_SOURCES = ("notice", "offer_letter", "job_description")
CONFIRM_WITH = ("recruiter", "manager", "hr", "agent", "undecided")
TASK_STATUSES = ("done", "planned", "not_started")

PROBATION_CONDITIONS = ("pay", "employment_type", "work_style")

# 試用期間の終わりのこれだけ前までに、本採用の判断基準を上長と確かめる場を置く。
PROBATION_REVIEW_LEAD_DAYS = 30


def add_months(start: date, months: int) -> date:
    """月数を足す。行き先の月に同じ日がなければ月末に寄せる。"""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_weekday(day: date) -> date:
    """土日なら次の月曜に寄せる。祝日と会社の休日は考慮しない。"""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def previous_weekday(day: date) -> date:
    """土日なら前の金曜に寄せる。祝日と会社の休日は考慮しない。"""
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def parse_probation(raw: object, start: date | None) -> dict[str, Any]:
    probation = require_object(raw if raw is not None else {}, "probation")
    exists = optional_bool(probation.get("exists"), "probation.exists")
    months = optional_positive_int(probation.get("months"), "probation.months")
    end_date = optional_date(probation.get("end_date"), "probation.end_date")

    computed_end = None
    if end_date is not None:
        computed_end = end_date
    elif months is not None and start is not None:
        computed_end = add_months(start, months) - timedelta(days=1)
    if computed_end is not None and start is not None and computed_end < start:
        raise ValueError("probation ends before the start date")

    return {
        "exists": exists,
        "months": months,
        "end_date": computed_end,
        "end_date_given": end_date is not None,
        "criteria_known": optional_bool(probation.get("criteria_known"), "probation.criteria_known"),
        "conditions_same": parse_conditions_same(probation.get("conditions_same")),
    }


def parse_conditions_same(raw: object) -> dict[str, bool | None]:
    """試用期間中の条件が本採用後と同じかを、給与・雇用形態・勤務形態ごとに受け取る。"""
    conditions = require_object(raw if raw is not None else {}, "probation.conditions_same")
    unknown = sorted(set(conditions) - set(PROBATION_CONDITIONS))
    if unknown:
        raise ValueError(f"probation.conditions_same has unknown keys: {unknown}")
    return {
        key: optional_bool(conditions.get(key), f"probation.conditions_same.{key}")
        for key in PROBATION_CONDITIONS
    }


def parse_expectations(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "expectations")
    seen: set[str] = set()
    parsed = []
    for index, entry in enumerate(entries):
        path = f"expectations[{index}]"
        item = require_object(entry, path)
        expectation_id = require_text(item.get("id"), f"{path}.id")
        if expectation_id in seen:
            raise ValueError(f"{path}.id is duplicated: {expectation_id!r}")
        seen.add(expectation_id)
        source = optional_choice(item.get("source"), f"{path}.source", SOURCES, "unknown")
        parsed.append(
            {
                "id": expectation_id,
                "topic": require_text(item.get("topic"), f"{path}.topic"),
                "content": require_text(item.get("content"), f"{path}.content"),
                "source": source,
                "in_writing": source in WRITTEN_SOURCES,
                "said_by": optional_text(item.get("said_by"), f"{path}.said_by"),
                "said_on": optional_date(item.get("said_on"), f"{path}.said_on"),
                "measurable": optional_bool(item.get("measurable"), f"{path}.measurable"),
                "due": optional_date(item.get("due"), f"{path}.due"),
                "confirm_with": optional_choice(
                    item.get("confirm_with"), f"{path}.confirm_with", CONFIRM_WITH, "undecided"
                ),
                "confirmed": optional_bool(item.get("confirmed"), f"{path}.confirmed"),
                "before_start": optional_bool(item.get("before_start"), f"{path}.before_start"),
            }
        )
    return parsed


def parse_tasks(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "pre_start_tasks")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"pre_start_tasks[{index}]"
        item = require_object(entry, path)
        parsed.append(
            {
                "label": require_text(item.get("label"), f"{path}.label"),
                "due": optional_date(item.get("due"), f"{path}.due"),
                "status": optional_choice(
                    item.get("status"), f"{path}.status", TASK_STATUSES, "not_started"
                ),
            }
        )
    return parsed


def parse_checkpoints(raw: object, expectation_ids: set[str]) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "checkpoints")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"checkpoints[{index}]"
        item = require_object(entry, path)
        topics = [
            require_text(value, f"{path}.topics[{position}]")
            for position, value in enumerate(require_list(item.get("topics", []), f"{path}.topics"))
        ]
        unknown = [topic for topic in topics if topic not in expectation_ids]
        if unknown:
            raise ValueError(f"{path}.topics names unknown expectation ids: {unknown}")
        parsed.append(
            {
                "label": require_text(item.get("label"), f"{path}.label"),
                "date": optional_date(item.get("date"), f"{path}.date"),
                "with": optional_choice(item.get("with"), f"{path}.with", CONFIRM_WITH, "undecided"),
                "topics": topics,
            }
        )
    return parsed


def suggest_checkpoints(start: date, probation_end: date | None) -> list[dict[str, Any]]:
    """確かめる場が1つも入っていないときに出す目安。利用者が決め直す前提で出す。"""
    suggestions = [
        {"label": "入社初週の上長との面談", "date": next_weekday(start + timedelta(days=1)), "with": "manager"},
        {"label": "入社1か月の振り返り", "date": next_weekday(add_months(start, 1)), "with": "manager"},
    ]
    if probation_end is not None:
        review = previous_weekday(probation_end - timedelta(days=PROBATION_REVIEW_LEAD_DAYS))
        if review > suggestions[-1]["date"]:
            suggestions.append(
                {"label": "試用期間の基準の確認", "date": review, "with": "manager"}
            )
    return [
        {**item, "date": item["date"].isoformat(), "topics": [], "suggested": True}
        for item in suggestions
    ]


def find_conflicts(expectations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for item in expectations:
        by_topic.setdefault(strip_whitespace(item["topic"]), []).append(item)
    conflicts = []
    for items in by_topic.values():
        contents = {strip_whitespace(item["content"]) for item in items}
        if len(items) >= 2 and len(contents) > 1:
            conflicts.append(
                {
                    "topic": items[0]["topic"],
                    "values": [
                        {"id": item["id"], "source": item["source"], "content": item["content"]}
                        for item in items
                    ],
                }
            )
    return conflicts


def collect_flags(
    as_of: date | None,
    start: date | None,
    written_terms: bool | None,
    probation: dict[str, Any],
    expectations: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    checkpoints: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if start is None:
        add("start_date_unknown", "入社日が確定していない。段取りの日付を決められない")
    if written_terms is False:
        add(
            "no_written_terms",
            "労働条件を書面でまだ受け取っていない。入社前の段取りより先に書面を求める",
        )
    elif written_terms is None:
        add("written_terms_unknown", "労働条件を書面で受け取っているかが未確認")

    verbal = [
        item["id"]
        for item in expectations
        if not item["in_writing"] and item["confirmed"] is not True
    ]
    if verbal:
        add(
            "verbal_only",
            "書面になく、まだ確かめていない期待・約束がある。確定した条件として扱わない",
            verbal,
        )
    unmeasured = [item["id"] for item in expectations if item["measurable"] is False]
    if unmeasured:
        add(
            "no_agreed_measure",
            "何ができたら達成かが決まっていない期待がある。上長と測り方を確かめる",
            unmeasured,
        )
    no_owner = [item["id"] for item in expectations if item["confirm_with"] == "undecided"]
    if no_owner:
        add("confirm_with_undecided", "誰に確かめるかが決まっていない項目がある", no_owner)
    if conflicts:
        add(
            "expectation_conflict",
            "出典によって内容が食い違う項目がある。どちらが正しいかを推測せず、確かめる",
            [item["topic"] for item in conflicts],
        )
    before_start = [
        item["id"]
        for item in expectations
        if item["before_start"] is True
        or (start is not None and item["due"] is not None and item["due"] < start)
    ]
    if before_start:
        add(
            "pre_start_work",
            "入社前の作業を求められている。賃金の扱い、参加の要否、期限と範囲を確かめる",
            before_start,
        )

    if probation["exists"] is None:
        add("probation_unknown", "試用期間があるかが確かめられていない")
    elif probation["exists"]:
        if probation["end_date"] is None:
            add("probation_length_unknown", "試用期間の長さか終わりの日付が分からない")
        if probation["criteria_known"] is not True:
            add(
                "probation_criteria_unknown",
                "本採用の判断基準が示されていない。入社後の早い時期に上長と確かめる",
            )
        unknown_conditions = [
            key for key, same in probation["conditions_same"].items() if same is None
        ]
        if unknown_conditions:
            add(
                "probation_conditions_unknown",
                "試用期間中の条件が本採用後と同じかを確かめていない項目がある",
                unknown_conditions,
            )
        differ = [key for key, same in probation["conditions_same"].items() if same is False]
        if differ:
            add(
                "probation_conditions_differ",
                "試用期間中は本採用後と条件が違う項目がある。違いの中身と、本採用後に切り替わる日を確かめる",
                differ,
            )

    scheduled = {topic for checkpoint in checkpoints for topic in checkpoint["topics"]}
    unscheduled = [
        item["id"]
        for item in expectations
        if item["id"] not in scheduled and item["confirmed"] is not True
    ]
    if checkpoints and unscheduled:
        add(
            "not_scheduled",
            "確かめる場が決まっていない項目がある",
            unscheduled,
        )
    if not checkpoints:
        add("no_checkpoints", "確かめる場が1つも決まっていない。目安を出すので、利用者が日付と相手を決める")

    if start is not None:
        before_start = [
            checkpoint["label"]
            for checkpoint in checkpoints
            if checkpoint["date"] is not None and checkpoint["date"] < start
            and checkpoint["with"] == "manager"
        ]
        if before_start:
            add(
                "manager_checkpoint_before_start",
                "入社前に上長との場が入っている。入社前の面談の扱い（業務か、任意か）を確かめる",
                before_start,
            )

    if probation["exists"] and probation["end_date"] is not None and checkpoints:
        review_by = probation["end_date"] - timedelta(days=PROBATION_REVIEW_LEAD_DAYS)
        early = [
            checkpoint
            for checkpoint in checkpoints
            if checkpoint["date"] is not None and checkpoint["date"] <= review_by
        ]
        if not early:
            add(
                "no_checkpoint_before_probation_review",
                f"試用期間の終わりの{PROBATION_REVIEW_LEAD_DAYS}日前（{review_by.isoformat()}）までに確かめる場がない",
            )

    if as_of is not None:
        overdue = [
            task["label"]
            for task in tasks
            if task["due"] is not None and task["due"] < as_of and task["status"] != "done"
        ]
        if overdue:
            add("pre_start_task_overdue", "期限を過ぎた入社前の手続きがある", overdue)
    undated = [task["label"] for task in tasks if task["due"] is None and task["status"] != "done"]
    if undated:
        add("pre_start_task_undated", "期限が分からない入社前の手続き・準備がある。会社の案内で確かめる", undated)

    return flags


def plan(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    employer = require_text(data.get("employer"), "employer")
    as_of = optional_date(data.get("as_of"), "as_of")
    start = optional_date(data.get("start_date"), "start_date")
    written_terms = optional_bool(data.get("written_terms"), "written_terms")

    probation = parse_probation(data.get("probation"), start)
    expectations = parse_expectations(data.get("expectations"))
    tasks = parse_tasks(data.get("pre_start_tasks"))
    checkpoints = parse_checkpoints(data.get("checkpoints"), {item["id"] for item in expectations})
    conflicts = find_conflicts(expectations)

    return {
        "employer": employer,
        "dates": {
            "as_of": as_of.isoformat() if as_of else None,
            "start_date": start.isoformat() if start else None,
            "days_to_start": (start - as_of).days if start and as_of else None,
            "probation_end": probation["end_date"].isoformat() if probation["end_date"] else None,
            "probation_end_computed": probation["end_date"] is not None and not probation["end_date_given"],
        },
        "probation": {
            "exists": probation["exists"],
            "months": probation["months"],
            "criteria_known": probation["criteria_known"],
            "conditions_same": probation["conditions_same"],
        },
        "summary": {
            "expectations": len(expectations),
            "in_writing": sum(1 for item in expectations if item["in_writing"]),
            "verbal_unconfirmed": sum(
                1 for item in expectations if not item["in_writing"] and item["confirmed"] is not True
            ),
            "without_measure": sum(1 for item in expectations if item["measurable"] is False),
        },
        "expectations": [
            {
                **item,
                "said_on": item["said_on"].isoformat() if item["said_on"] else None,
                "due": item["due"].isoformat() if item["due"] else None,
            }
            for item in expectations
        ],
        "conflicts": conflicts,
        "checkpoints": [
            {**checkpoint, "date": checkpoint["date"].isoformat() if checkpoint["date"] else None}
            for checkpoint in checkpoints
        ],
        "suggested_checkpoints": (
            suggest_checkpoints(start, probation["end_date"] if probation["exists"] else None)
            if not checkpoints and start is not None
            else []
        ),
        "pre_start_tasks": [
            {**task, "due": task["due"].isoformat() if task["due"] else None} for task in tasks
        ],
        "flags": collect_flags(
            as_of, start, written_terms, probation, expectations, tasks, checkpoints, conflicts
        ),
        "notes": [
            "試用期間の終わりは入社日と月数から計算した日付で、会社の定めで確かめる",
            "確かめる場の目安は日付の例であり、土日は避けているが祝日と会社の休日は考慮していない。日付と相手は利用者と会社が決める",
            "この出力は期待の整理であり、試用期間の評価や職場への適応の見込みではない",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(plan, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
