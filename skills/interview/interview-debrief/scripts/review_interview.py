#!/usr/bin/env python3
"""Sort out what actually happened in an interview that has just finished.

聞かれた質問と答えられた度合い、逆質問の結果、企業側が口頭で述べた条件、次の
連絡の予定を整理する。準備していたのに答えられなかったものと、準備していなかった
ものを分ける。合否の見込みは推定しない。手応えを評価しない。
"""

from __future__ import annotations

from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_choice,
    optional_date,
    optional_text,
    require_list,
    require_object,
    require_text,
    run_cli,
)


STAGES = ("casual", "first", "second", "final", "unknown")
ANSWER_LEVELS = ("full", "partial", "none")
REVERSE_RESULTS = ("answered", "partial", "deferred", "unanswered")
# 記憶が薄れる前に書き出す。これを超えて日が経った記録は、精度が落ちている前提で扱う。
FRESH_RECORD_DAYS = 3


def parse_questions(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "questions")
    questions = []
    for index, entry in enumerate(entries):
        item = require_object(entry, f"questions[{index}]")
        answered = optional_choice(
            item.get("answered"), f"questions[{index}].answered", ANSWER_LEVELS, "none"
        )
        questions.append(
            {
                "text": require_text(item.get("text"), f"questions[{index}].text"),
                "answered": answered,
                "prepared": optional_bool(item.get("prepared"), f"questions[{index}].prepared"),
                "from_documents": bool(item.get("from_documents", False)),
                "note": optional_text(item.get("note"), f"questions[{index}].note"),
            }
        )
    return questions


def parse_reverse_questions(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "questions_asked")
    asked = []
    for index, entry in enumerate(entries):
        item = require_object(entry, f"questions_asked[{index}]")
        result = optional_choice(
            item.get("result"), f"questions_asked[{index}].result", REVERSE_RESULTS, "unanswered"
        )
        asked.append(
            {
                "text": require_text(item.get("text"), f"questions_asked[{index}].text"),
                "result": result,
                "note": optional_text(item.get("note"), f"questions_asked[{index}].note"),
            }
        )
    return asked


def parse_statements(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "employer_statements")
    statements = []
    for index, entry in enumerate(entries):
        item = require_object(entry, f"employer_statements[{index}]")
        statements.append(
            {
                "topic": require_text(item.get("topic"), f"employer_statements[{index}].topic"),
                "statement": require_text(
                    item.get("statement"), f"employer_statements[{index}].statement"
                ),
                "said_by": optional_text(item.get("said_by"), f"employer_statements[{index}].said_by"),
                "in_writing": bool(item.get("in_writing", False)),
                "conflicts_with_posting": optional_bool(
                    item.get("conflicts_with_posting"),
                    f"employer_statements[{index}].conflicts_with_posting",
                ),
                "affects_conditions": bool(item.get("affects_conditions", False)),
            }
        )
    return statements


def parse_next_steps(raw: object) -> dict[str, Any]:
    steps = require_object(raw if raw is not None else {}, "next_steps")
    next_stage = optional_choice(steps.get("next_stage"), "next_steps.next_stage", STAGES, "unknown")
    return {
        "next_stage": next_stage,
        "result_promised_by": optional_date(
            steps.get("result_promised_by"), "next_steps.result_promised_by"
        ),
        "who_contacts": optional_text(steps.get("who_contacts"), "next_steps.who_contacts"),
    }


def collect_flags(
    questions: list[dict[str, Any]],
    asked: list[dict[str, Any]],
    statements: list[dict[str, Any]],
    next_steps: dict[str, Any],
    days_since: int | None,
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if not questions:
        add("questions_not_captured", "聞かれた質問が記録されていない。振り返りの材料がない")

    prepared_but_missed = [
        item["text"] for item in questions if item["prepared"] is True and item["answered"] != "full"
    ]
    if prepared_but_missed:
        add(
            "prepared_but_not_answered",
            "準備していたのに答えきれなかった質問がある。素材ではなく、話す順序や具体性の問題として見る",
            prepared_but_missed,
        )

    unprepared = [
        item["text"] for item in questions if item["prepared"] is False and item["answered"] != "full"
    ]
    if unprepared:
        add(
            "not_prepared",
            "準備していなかった質問で答えきれなかったものがある。次の面接までに素材を用意する",
            unprepared,
        )

    from_documents = [
        item["text"] for item in questions if item["from_documents"] and item["answered"] != "full"
    ]
    if from_documents:
        add(
            "documents_not_defensible",
            "提出書類の記述を聞かれて答えきれなかったものがある。書類の表現と事実のずれを先に直す",
            from_documents,
        )

    unresolved = [item["text"] for item in asked if item["result"] in ("unanswered", "deferred", "partial")]
    if unresolved:
        add(
            "reverse_questions_unresolved",
            "逆質問のうち、答えが得られなかったものがある。次の段階か、条件提示のときに持ち越す",
            unresolved,
        )
    if not asked:
        add("no_reverse_questions_asked", "逆質問をしていない。確認したい論点が残っていないかを見る")

    verbal_conditions = [
        item["topic"]
        for item in statements
        if item["affects_conditions"] and not item["in_writing"]
    ]
    if verbal_conditions:
        add(
            "conditions_stated_verbally",
            "労働条件に関わる説明を口頭で受けている。書面で確認するまで確定した条件として扱わない",
            verbal_conditions,
        )

    conflicts = [item["topic"] for item in statements if item["conflicts_with_posting"] is True]
    if conflicts:
        add(
            "conflicts_with_posting",
            "求人票の記載と食い違う説明を受けている。どちらが適用されるかを確認する",
            conflicts,
        )

    if next_steps["result_promised_by"] is None:
        add("result_timing_unknown", "結果の連絡時期を確認していない。いつまで待つかが決まらない")
    if next_steps["who_contacts"] is None:
        add("contact_unknown", "誰から連絡が来るかを確認していない")

    if days_since is not None and days_since > FRESH_RECORD_DAYS:
        add(
            "recorded_late",
            f"面接から{days_since}日経ってからの記録である。細部の再現度が落ちている前提で扱う",
        )
    return flags


def review(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    company = require_text(data.get("company"), "company")

    stage = optional_choice(data.get("stage"), "stage", STAGES, "unknown")

    interview_date = optional_date(data.get("date"), "date")
    as_of = optional_date(data.get("as_of"), "as_of")
    if interview_date and as_of and as_of < interview_date:
        raise ValueError("as_of must not precede date")
    days_since = (as_of - interview_date).days if interview_date and as_of else None

    questions = parse_questions(data.get("questions"))
    asked = parse_reverse_questions(data.get("questions_asked"))
    statements = parse_statements(data.get("employer_statements"))
    next_steps = parse_next_steps(data.get("next_steps"))

    result_overdue = None
    if next_steps["result_promised_by"] and as_of:
        result_overdue = as_of > next_steps["result_promised_by"]

    return {
        "company": company,
        "stage": stage,
        "date": interview_date.isoformat() if interview_date else None,
        "as_of": as_of.isoformat() if as_of else None,
        "days_since_interview": days_since,
        "summary": {
            "questions": len(questions),
            "answered_fully": sum(1 for item in questions if item["answered"] == "full"),
            "answered_partially": sum(1 for item in questions if item["answered"] == "partial"),
            "not_answered": sum(1 for item in questions if item["answered"] == "none"),
            "from_documents": sum(1 for item in questions if item["from_documents"]),
            "reverse_questions": len(asked),
            "reverse_questions_resolved": sum(1 for item in asked if item["result"] == "answered"),
            "employer_statements": len(statements),
            "conditions_only_verbal": sum(
                1 for item in statements if item["affects_conditions"] and not item["in_writing"]
            ),
        },
        "questions": questions,
        "questions_asked": asked,
        "employer_statements": statements,
        "next_steps": {
            "next_stage": next_steps["next_stage"],
            "result_promised_by": (
                next_steps["result_promised_by"].isoformat()
                if next_steps["result_promised_by"]
                else None
            ),
            "who_contacts": next_steps["who_contacts"],
            "result_overdue": result_overdue,
        },
        "carry_forward": {
            "to_next_interview": [
                item["text"] for item in questions if item["answered"] != "full"
            ]
            + [item["text"] for item in asked if item["result"] in ("unanswered", "deferred", "partial")],
            "to_document_review": [
                item["text"] for item in questions if item["from_documents"] and item["answered"] != "full"
            ],
            "to_terms_check": [
                item["topic"]
                for item in statements
                if item["affects_conditions"] and not item["in_writing"]
            ],
        },
        "flags": collect_flags(questions, asked, statements, next_steps, days_since),
        "notes": [
            "この出力は面接で起きたことの整理であり、手応えの評価でも合否の見込みでもない",
            "口頭で受けた説明は、書面で確認するまで確定した労働条件ではない",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(review, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
