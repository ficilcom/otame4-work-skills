#!/usr/bin/env python3
"""Match an application against the listed requirements, and check the reply.

募集の要件と応募内容を突き合わせ、要件ごとに応募者が示したこと・一部示したこと・
示していないこと・未確認を数え、確認質問にする項目を出す。返信の目的（招待、
質問、保留、辞退）に対して、確認前の辞退、推測に基づく判断、職務と無関係な属性、
他候補者や内部メモの混入、未合意の提案を合意済みに見せる書き方を注意として返す。
応募者の適性も、採用の成否も判定しない。
"""

from __future__ import annotations

from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_number,
    optional_text,
    require_list,
    require_object,
    require_text,
    run_cli,
)


EVIDENCE_STATUSES = ("shown", "partial", "not_shown", "unknown")
# 根拠の出所。`assumed` は応募者が述べていない推測で、根拠として数えない。
EVIDENCE_SOURCES = ("application", "profile", "portfolio", "chat", "interview", "assumed", "unknown")
STATED_BY_CANDIDATE = ("application", "profile", "portfolio", "chat", "interview")
REPLY_PURPOSES = ("invite", "ask", "hold", "decline", "unknown")
# 返信案に入れようとしているもの。混ぜてはいけないものを見つけるための語彙。
REPLY_CONTENTS = (
    "questions",
    "next_step",
    "conditions",
    "other_candidates",
    "internal_notes",
    "new_work",
    "new_dates",
    "reason_for_decline",
)
PRESENTATIONS = ("proposal", "agreed", "unknown")
# 確認していない、または一部しか示されていない要件を「開いている」と呼ぶ。
OPEN_STATUSES = ("partial", "unknown")


def parse_choice(value: object, path: str, allowed: tuple[str, ...], default: str) -> str:
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{path} must be one of {list(allowed)}")
    return str(value)


def parse_requirements(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw, "requirements")
    if not entries:
        raise ValueError("requirements must contain at least one requirement")
    parsed = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"requirements[{index}]"
        item = require_object(entry, path)
        code = require_text(item.get("code"), f"{path}.code")
        if code in seen:
            raise ValueError(f"{path}.code is duplicated: {code!r}")
        seen.add(code)
        required = optional_bool(item.get("required"), f"{path}.required")
        job_related = optional_bool(item.get("job_related"), f"{path}.job_related")
        parsed.append(
            {
                "code": code,
                "label": require_text(item.get("label"), f"{path}.label"),
                # 未記載は必須として扱う。歓迎要件と決めつけて確認を落とさない。
                "required": True if required is None else required,
                # 未記載は職務に関係する要件として扱う。属性の疑いは入力側で false にする。
                "job_related": True if job_related is None else job_related,
            }
        )
    return parsed


def parse_evidence(raw: object, codes: set[str]) -> dict[str, dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "evidence")
    parsed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        path = f"evidence[{index}]"
        item = require_object(entry, path)
        code = require_text(item.get("requirement"), f"{path}.requirement")
        if code not in codes:
            raise ValueError(f"{path}.requirement does not match any requirement code: {code!r}")
        if code in parsed:
            raise ValueError(f"{path}.requirement is duplicated: {code!r}")
        parsed[code] = {
            "status": parse_choice(item.get("status"), f"{path}.status", EVIDENCE_STATUSES, "unknown"),
            "source": parse_choice(item.get("source"), f"{path}.source", EVIDENCE_SOURCES, "unknown"),
            "note": optional_text(item.get("note"), f"{path}.note"),
        }
    return parsed


def parse_reply(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "reply")
    includes = require_list(block.get("includes", []) or [], "reply.includes")
    for index, item in enumerate(includes):
        if item not in REPLY_CONTENTS:
            raise ValueError(f"reply.includes[{index}] must be one of {list(REPLY_CONTENTS)}")
    return {
        "purpose": parse_choice(block.get("purpose"), "reply.purpose", REPLY_PURPOSES, "unknown"),
        "includes": [str(item) for item in includes],
    }


def parse_proposals(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "proposals")
    parsed = []
    for index, entry in enumerate(entries):
        path = f"proposals[{index}]"
        item = require_object(entry, path)
        parsed.append(
            {
                "topic": require_text(item.get("topic"), f"{path}.topic"),
                "agreed": optional_bool(item.get("agreed"), f"{path}.agreed"),
                "presented_as": parse_choice(
                    item.get("presented_as"), f"{path}.presented_as", PRESENTATIONS, "unknown"
                ),
            }
        )
    return parsed


def parse_availability(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    block = require_object(raw, "availability")
    return {
        "candidate_weekly_hours": optional_number(
            block.get("candidate_weekly_hours"), "availability.candidate_weekly_hours"
        ),
        "required_weekly_hours": optional_number(
            block.get("required_weekly_hours"), "availability.required_weekly_hours"
        ),
    }


def build_coverage(
    requirements: list[dict[str, Any]], evidence: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    coverage = []
    for requirement in requirements:
        entry = evidence.get(requirement["code"])
        status = entry["status"] if entry else "unknown"
        source = entry["source"] if entry else None
        # 推測は根拠にならない。示されたことにせず、未確認へ戻す。
        assumed = source == "assumed"
        effective = "unknown" if assumed and status in ("shown", "partial") else status
        coverage.append(
            {
                **requirement,
                "status": effective,
                "source": source,
                "stated_by_candidate": source in STATED_BY_CANDIDATE,
                "assumed": assumed,
                "note": entry["note"] if entry else None,
            }
        )
    return coverage


def build_questions(coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """確認質問にする要件を返す。職務と無関係な要件は質問にしない。"""
    questions = []
    for item in coverage:
        if not item["job_related"]:
            continue
        if item["status"] in OPEN_STATUSES:
            questions.append(
                {
                    "requirement": item["code"],
                    "label": item["label"],
                    "required": item["required"],
                    "why": "一部しか示されていない" if item["status"] == "partial" else "応募内容から確認できていない",
                }
            )
        elif item["status"] == "not_shown" and item["required"]:
            questions.append(
                {
                    "requirement": item["code"],
                    "label": item["label"],
                    "required": True,
                    "why": "応募内容に書かれていない。書いていないだけか、経験がないかを確かめる",
                }
            )
    return questions


def build_summary(coverage: list[dict[str, Any]]) -> dict[str, Any]:
    required = [item for item in coverage if item["required"] and item["job_related"]]
    return {
        "required_total": len(required),
        "required_shown": sum(1 for item in required if item["status"] == "shown"),
        "required_partial": sum(1 for item in required if item["status"] == "partial"),
        "required_not_shown": sum(1 for item in required if item["status"] == "not_shown"),
        "required_unknown": sum(1 for item in required if item["status"] == "unknown"),
        "preferred_shown": sum(
            1 for item in coverage if not item["required"] and item["job_related"] and item["status"] == "shown"
        ),
    }


def collect_flags(
    coverage: list[dict[str, Any]],
    reply: dict[str, Any],
    proposals: list[dict[str, Any]],
    availability: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    flags, add = flag_collector("items")

    assumed = [item["code"] for item in coverage if item["assumed"]]
    if assumed:
        add("assumed_evidence", "応募者が述べていない推測を根拠にしている。未確認に戻し、確認質問にする", assumed)

    not_job_related = [item["code"] for item in coverage if not item["job_related"]]
    if not_job_related:
        add(
            "requirement_not_job_related",
            "職務と無関係な要件がある。照合と返信の判断に使わず、募集文からも外す",
            not_job_related,
        )

    open_required = [
        item["code"]
        for item in coverage
        if item["required"] and item["job_related"] and item["status"] in OPEN_STATUSES
    ]
    not_shown_required = [
        item["code"]
        for item in coverage
        if item["required"] and item["job_related"] and item["status"] == "not_shown"
    ]

    purpose = reply["purpose"]
    if purpose == "decline":
        if open_required:
            add(
                "decline_before_confirming",
                "確認していない必須要件があるのに辞退の返信にしている。先に確認質問を送るか、"
                "確認済みの理由だけで判断する",
                open_required,
            )
        if not_job_related:
            add("decline_reason_not_job_related", "辞退の理由に職務と無関係な属性を含めない")
        if "reason_for_decline" not in reply["includes"]:
            add(
                "decline_without_reason",
                "辞退の返信に理由が入っていない。書くかどうかは利用者が決め、書くなら募集の要件に照らした事実だけにする",
            )
    elif purpose == "invite":
        if open_required or not_shown_required:
            add(
                "invite_with_open_requirements",
                "招待の返信だが、確認していない必須要件がある。初回の面談か開始前に確かめる質問として添える",
                open_required + not_shown_required,
            )
    elif purpose == "unknown":
        add("reply_purpose_unknown", "返信の目的（招待、質問、保留、辞退）が決まっていない")

    if "other_candidates" in reply["includes"]:
        add("reply_mentions_other_candidates", "他の応募者の情報を返信に入れない")
    if "internal_notes" in reply["includes"]:
        add("reply_includes_internal_notes", "内部の評価メモを返信に入れない。候補者に伝える事実と分ける")
    if "new_work" in reply["includes"] or "new_dates" in reply["includes"]:
        add(
            "new_terms_in_reply",
            "募集文にない業務や日程を返信で出している。提案として書き、本人が同意した扱いにしない",
        )

    presented_as_agreed = [
        item["topic"] for item in proposals if item["presented_as"] == "agreed" and item["agreed"] is not True
    ]
    if presented_as_agreed:
        add("proposal_presented_as_agreed", "合意していない提案を合意済みとして書いている", presented_as_agreed)

    if availability is not None:
        needed = availability["required_weekly_hours"]
        offered = availability["candidate_weekly_hours"]
        if needed is not None and offered is not None and offered < needed:
            add(
                "availability_short",
                "応募者の週の稼働が計画の週の実働より少ない。範囲を減らすか期間を延ばす案を返信に添え、"
                "稼働だけを理由に辞退にしない",
            )

    return flags


def decide_readiness(reply: dict[str, Any], flags: list[dict[str, Any]]) -> dict[str, Any]:
    blocking_codes = {
        "assumed_evidence",
        "decline_before_confirming",
        "decline_reason_not_job_related",
        "reply_mentions_other_candidates",
        "reply_includes_internal_notes",
        "proposal_presented_as_agreed",
        "reply_purpose_unknown",
    }
    blockers = [flag["code"] for flag in flags if flag["code"] in blocking_codes]
    return {
        "purpose": reply["purpose"],
        "status": "needs_work" if blockers else "ready_for_owner_review",
        "blockers": blockers,
        # 送信は利用者が行う。ここでは下書きの点検までを返す。
        "sending_is_user_action": True,
    }


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    requirements = parse_requirements(data.get("requirements"))
    codes = {requirement["code"] for requirement in requirements}
    evidence = parse_evidence(data.get("evidence"), codes)
    reply = parse_reply(data.get("reply"))
    proposals = parse_proposals(data.get("proposals"))
    availability = parse_availability(data.get("availability"))

    coverage = build_coverage(requirements, evidence)
    questions = build_questions(coverage)
    summary = build_summary(coverage)
    flags = collect_flags(coverage, reply, proposals, availability)
    readiness = decide_readiness(reply, flags)

    return {
        "as_of": optional_text(data.get("as_of"), "as_of"),
        "summary": summary,
        "coverage": coverage,
        "questions": questions,
        "proposals": proposals,
        "readiness": readiness,
        "flags": flags,
    }


if __name__ == "__main__":
    raise SystemExit(run_cli(check, __doc__))
