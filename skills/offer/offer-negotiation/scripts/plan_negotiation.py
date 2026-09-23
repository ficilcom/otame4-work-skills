#!/usr/bin/env python3
"""Lay out the requests a user wants to make about an offer before accepting it.

内定条件について会社に依頼したい項目ごとに、提示と希望の差額（年額換算を含む）、
求人票の提示範囲との位置、根拠の有無、優先の付け方、断られた場合の扱いが
決まっているかを並べ、承諾期限までに回答が返る日程かを機械的に確認する。
交渉が通るかは予測しない。相場からの要求額も作らない。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from _common import (
    flag_collector,
    optional_amount,
    optional_bool,
    optional_choice,
    optional_date,
    optional_int,
    optional_text,
    require_list,
    require_object,
    require_text,
    run_cli,
)


CATEGORIES = ("pay", "start_date", "work_style", "location", "title", "probation", "other")
PRIORITIES = ("must", "want", "nice")
IF_DECLINED = ("accept_anyway", "decline_offer", "undecided")
CHANNELS = ("direct", "agent", "unknown")
AMOUNT_UNITS = ("monthly", "annual")
BASIS_KINDS = (
    "written_offer",
    "posting",
    "interview",
    "own_record",
    "public_source",
    "other_offer",
)
MONTHS_PER_YEAR = 12
# 回答から承諾期限までがこれより短いと、改訂された書面を確かめる時間が取りにくい。
MIN_DAYS_AFTER_ANSWER = 2


def parse_basis(raw: object, path: str) -> dict[str, Any]:
    basis = require_object(raw, path)
    if basis.get("kind") is None:
        raise ValueError(f"{path}.kind is required")
    kind = optional_choice(basis.get("kind"), f"{path}.kind", BASIS_KINDS, "own_record")
    return {
        "kind": kind,
        "note": optional_text(basis.get("note"), f"{path}.note"),
        "as_of": _iso(optional_date(basis.get("as_of"), f"{path}.as_of")),
    }


def parse_range(raw: object, path: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    posted = require_object(raw, path)
    low = optional_amount(posted.get("min"), f"{path}.min")
    high = optional_amount(posted.get("max"), f"{path}.max")
    if low is not None and high is not None and low > high:
        raise ValueError(f"{path}.min must not exceed {path}.max")
    unit = optional_choice(posted.get("unit"), f"{path}.unit", AMOUNT_UNITS, "monthly")
    components_match = optional_bool(posted.get("components_match"), f"{path}.components_match")
    return {"min": low, "max": high, "unit": unit, "components_match": components_match}


def parse_request(raw: object, index: int, seen: set[str]) -> dict[str, Any]:
    path = f"requests[{index}]"
    entry = require_object(raw, path)
    request_id = require_text(entry.get("id"), f"{path}.id")
    if request_id in seen:
        raise ValueError(f"{path}.id is duplicated: {request_id!r}")
    seen.add(request_id)

    category = optional_choice(entry.get("category"), f"{path}.category", CATEGORIES, "other")
    bases = [
        parse_basis(item, f"{path}.bases[{position}]")
        for position, item in enumerate(require_list(entry.get("bases", []), f"{path}.bases"))
    ]
    return {
        "id": request_id,
        "topic": require_text(entry.get("topic"), f"{path}.topic"),
        "category": category,
        "priority": optional_choice(entry.get("priority"), f"{path}.priority", PRIORITIES, "unset"),
        "priority_given": entry.get("priority") is not None,
        "current_text": optional_text(entry.get("current_text"), f"{path}.current_text"),
        "ask_text": require_text(entry.get("ask_text"), f"{path}.ask_text"),
        "current_amount": optional_amount(entry.get("current_amount"), f"{path}.current_amount"),
        "ask_amount": optional_amount(entry.get("ask_amount"), f"{path}.ask_amount"),
        "amount_unit": optional_choice(
            entry.get("amount_unit"), f"{path}.amount_unit", AMOUNT_UNITS, "monthly"
        ),
        "posted_range": parse_range(entry.get("posted_range"), f"{path}.posted_range"),
        "current_date": optional_date(entry.get("current_date"), f"{path}.current_date"),
        "ask_date": optional_date(entry.get("ask_date"), f"{path}.ask_date"),
        "if_declined": optional_choice(
            entry.get("if_declined"), f"{path}.if_declined", IF_DECLINED, "undecided"
        ),
        "fallback": optional_text(entry.get("fallback"), f"{path}.fallback"),
        "bases": bases,
    }


def annualize(amount: int, unit: str) -> int:
    return amount * MONTHS_PER_YEAR if unit == "monthly" else amount


def range_position(ask: int, unit: str, posted: dict[str, Any] | None) -> str:
    """希望額が求人票の提示範囲のどこにあるか。単位が違えば比べない。"""
    if posted is None:
        return "no_range"
    if posted["components_match"] is False:
        return "components_mismatch"
    if posted["unit"] != unit:
        return "unit_mismatch"
    if posted["max"] is not None and ask > posted["max"]:
        return "above_max"
    if posted["min"] is not None and ask < posted["min"]:
        return "below_min"
    if posted["max"] is None and posted["min"] is None:
        return "no_range"
    return "within"


def evaluate_request(request: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": request["id"],
        "topic": request["topic"],
        "category": request["category"],
        "priority": request["priority"],
        "current_text": request["current_text"],
        "ask_text": request["ask_text"],
        "if_declined": request["if_declined"],
        "fallback": request["fallback"],
        "basis_kinds": sorted({basis["kind"] for basis in request["bases"]}),
        "bases": request["bases"],
        "amount": None,
        "date_shift_days": None,
    }

    current, ask, unit = request["current_amount"], request["ask_amount"], request["amount_unit"]
    if current is not None and ask is not None:
        difference = ask - current
        result["amount"] = {
            "unit": unit,
            "current": current,
            "ask": ask,
            "difference": difference,
            "difference_percent": (
                round(difference / current * 100, 1) if current > 0 else None
            ),
            "annual_difference": annualize(difference, unit),
            "posted_range_position": range_position(ask, unit, request["posted_range"]),
        }
    elif ask is not None:
        result["amount"] = {
            "unit": unit,
            "current": None,
            "ask": ask,
            "difference": None,
            "difference_percent": None,
            "annual_difference": None,
            "posted_range_position": range_position(ask, unit, request["posted_range"]),
        }

    if request["current_date"] is not None and request["ask_date"] is not None:
        result["date_shift_days"] = (request["ask_date"] - request["current_date"]).days
        result["current_date"] = request["current_date"].isoformat()
        result["ask_date"] = request["ask_date"].isoformat()
    return result


def build_schedule(
    as_of: date | None,
    deadline: date | None,
    request_date: date | None,
    wait_days: int | None,
) -> dict[str, Any]:
    # 回答を待つ日数が不明なときは、期限との関係を判定しない。既定値で埋めない。
    expected = request_date + timedelta(days=wait_days) if request_date and wait_days is not None else None
    if deadline is None or expected is None:
        answer_before_deadline: bool | None = None
    else:
        answer_before_deadline = expected <= deadline
    return {
        "as_of": _iso(as_of),
        "acceptance_deadline": _iso(deadline),
        "days_to_deadline": (deadline - as_of).days if as_of and deadline else None,
        "request_date": _iso(request_date),
        "response_wait_days": wait_days,
        "expected_answer_by": _iso(expected),
        "answer_before_deadline": answer_before_deadline,
        "days_left_after_answer": (deadline - expected).days if deadline and expected else None,
        "deadline_on_weekend": deadline.weekday() >= 5 if deadline else None,
        "request_after_deadline": (
            request_date > deadline if request_date and deadline else None
        ),
    }


def collect_flags(
    written_terms: bool | None,
    channel: str,
    requests: list[dict[str, Any]],
    raw_requests: list[dict[str, Any]],
    schedule: dict[str, Any],
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if written_terms is False:
        add(
            "no_written_terms",
            "条件を書面でまだ受け取っていない。依頼の前に書面の提示を求めると、何が変わったかを後で確かめられる",
        )
    elif written_terms is None:
        add("written_terms_unknown", "条件を書面で受け取っているかが未確認。先に確かめる")

    no_current = [item["id"] for item in requests if item["current_text"] is None]
    if no_current:
        add(
            "current_term_unconfirmed",
            "現在の提示が入っていない依頼がある。書面に何と書かれているか（記載がないのか）を先に確かめる",
            no_current,
        )

    if channel == "unknown":
        add("channel_unknown", "企業に直接伝えるか、エージェント経由かが決まっていない。宛先と書き方が変わる")

    # 書面の記載は「何を変えてほしいか」を特定するもので、希望の根拠にはならない。
    no_basis = [
        item["id"] for item in requests if not set(item["basis_kinds"]) - {"written_offer"}
    ]
    if no_basis:
        add(
            "request_without_basis",
            "根拠のない依頼がある。根拠を探すか、根拠なしの希望として伝えるかを利用者が選ぶ",
            no_basis,
        )

    interview_only = [item["id"] for item in requests if item["basis_kinds"] == ["interview"]]
    if interview_only:
        add(
            "basis_is_verbal_only",
            "根拠が面接での説明だけの依頼がある。いつ誰が何と言ったかを記録と照らしてから使う",
            interview_only,
        )

    other_offer = [item["id"] for item in requests if "other_offer" in item["basis_kinds"]]
    if other_offer:
        add(
            "discloses_other_offer",
            "他社の選考・提示を根拠にしている。伝えるかどうか、社名と金額をどこまで書くかは利用者が決める。事実と違う形で書かない",
            other_offer,
        )

    public_undated = [
        item["id"]
        for item in requests
        if any(basis["kind"] == "public_source" and basis["as_of"] is None for basis in item["bases"])
    ]
    if public_undated:
        add(
            "public_source_undated",
            "公開資料を根拠にしているが時点が入っていない。出典と時点を確かめてから使う",
            public_undated,
        )

    above = [
        item["id"]
        for item in requests
        if item["amount"] and item["amount"]["posted_range_position"] == "above_max"
    ]
    if above:
        add(
            "ask_above_posted_range",
            "希望額が求人票の提示範囲の上限を超えている。事実として示すだけで、通るかどうかの判断ではない",
            above,
        )

    components = [
        item["id"]
        for item in requests
        if item["amount"] and item["amount"]["posted_range_position"] == "components_mismatch"
    ]
    if components:
        add(
            "posted_range_components_mismatch",
            "求人票の提示範囲と希望額で、含む要素（固定残業代など）が違うため比べていない。比べるなら同じ内訳に揃えた額を入れる",
            components,
        )

    mismatch = [
        item["id"]
        for item in requests
        if item["amount"] and item["amount"]["posted_range_position"] == "unit_mismatch"
    ]
    if mismatch:
        add(
            "posted_range_unit_mismatch",
            "希望額と求人票の提示範囲の単位（月額・年額）が違うため比べていない",
            mismatch,
        )

    pay_without_amount = [
        item["id"]
        for item in requests
        if item["category"] == "pay" and (item["amount"] is None or item["amount"]["difference"] is None)
    ]
    if pay_without_amount:
        add(
            "pay_amount_incomplete",
            "給与の依頼で、現在の提示額か希望額が数値で入っていない。差額を出せない",
            pay_without_amount,
        )

    not_lower = [
        item["id"]
        for item in requests
        if item["amount"] and item["amount"]["difference"] is not None and item["amount"]["difference"] <= 0
    ]
    if not_lower:
        add(
            "ask_not_above_current",
            "希望額が現在の提示額以下になっている。減らす依頼（固定残業代の時間数など）でなければ、入力の取り違えを確かめる",
            not_lower,
        )

    undecided = [
        item["id"]
        for item in requests
        if item["priority"] == "must" and item["if_declined"] == "undecided"
    ]
    if undecided:
        add(
            "must_without_decision",
            "必須とした依頼で、断られた場合にどうするかが決まっていない。決めるのは利用者で、こちらでは埋めない",
            undecided,
        )

    unset_priority = [raw["id"] for raw in raw_requests if not raw["priority_given"]]
    if len(requests) >= 2 and unset_priority:
        add(
            "priority_unset",
            "優先度が付いていない依頼がある。一部だけ通ったときに受けるかを判断できない",
            unset_priority,
        )
    elif len(requests) >= 2 and len({item["priority"] for item in requests}) == 1:
        add(
            "priority_flat",
            "すべての依頼が同じ優先度になっている。一部だけ通ったときに受けるかを判断できない",
        )

    if schedule["days_to_deadline"] is not None and schedule["days_to_deadline"] < 0:
        add("deadline_passed", "承諾期限を過ぎている。期限の扱いを先に確かめる")
    if schedule["deadline_on_weekend"]:
        add(
            "deadline_on_weekend",
            "承諾期限が土日にあたる。先方の営業日で数えると実際の期限が前にずれることがあるので確かめる",
        )
    if schedule["acceptance_deadline"] is None:
        add("deadline_unknown", "承諾期限が分かっていない。回答が間に合うかを判定できない")
    if schedule["request_date"] is None:
        add("request_date_unset", "依頼を送る日が決まっていない")
    elif schedule["request_after_deadline"]:
        add("request_after_deadline", "依頼を送る予定日が承諾期限より後になっている")
    if schedule["answer_before_deadline"] is False:
        add(
            "answer_after_deadline",
            "想定する回答日が承諾期限より後になる。期限の延長を同時に依頼するかを利用者が決める",
        )
    elif (
        schedule["days_left_after_answer"] is not None
        and schedule["days_left_after_answer"] < MIN_DAYS_AFTER_ANSWER
    ):
        add(
            "little_time_after_answer",
            f"回答から承諾期限までが{schedule['days_left_after_answer']}日で、改訂された書面を確かめる時間が取りにくい",
        )

    return flags


def plan(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    employer = require_text(data.get("employer"), "employer")
    as_of = optional_date(data.get("as_of"), "as_of")
    written_terms = optional_bool(data.get("written_terms"), "written_terms")
    channel = optional_choice(data.get("channel"), "channel", CHANNELS, "unknown")

    offer = require_object(data.get("offer", {}), "offer")
    deadline = optional_date(offer.get("acceptance_deadline"), "offer.acceptance_deadline")

    timing = require_object(data.get("plan", {}), "plan")
    request_date = optional_date(timing.get("request_date"), "plan.request_date")
    wait_days = optional_int(timing.get("response_wait_days"), "plan.response_wait_days")

    raw_entries = require_list(data.get("requests"), "requests")
    if not raw_entries:
        raise ValueError("requests must contain at least one request")
    seen: set[str] = set()
    raw_requests = [parse_request(entry, index, seen) for index, entry in enumerate(raw_entries)]
    requests = [evaluate_request(request) for request in raw_requests]

    schedule = build_schedule(as_of, deadline, request_date, wait_days)

    annual_differences = [
        item["amount"]["annual_difference"]
        for item in requests
        if item["amount"] and item["amount"]["annual_difference"] is not None
    ]
    summary = {
        "requests": len(requests),
        "by_priority": {
            priority: [item["id"] for item in requests if item["priority"] == priority]
            for priority in (*PRIORITIES, "unset")
        },
        "pay_annual_difference_total": sum(annual_differences) if annual_differences else None,
        "without_basis": sum(
            1 for item in requests if not set(item["basis_kinds"]) - {"written_offer"}
        ),
    }

    return {
        "employer": employer,
        "written_terms": written_terms,
        "channel": channel,
        "schedule": schedule,
        "summary": summary,
        "requests": requests,
        "flags": collect_flags(written_terms, channel, requests, raw_requests, schedule),
        "notes": [
            "差額は提示と希望の差を数えたものであり、交渉が通るかの見込みではない",
            "月額の差を年額にした値は×12の単純計算で、賞与や手当の連動分を含まない",
            "条件が変わった場合も、改訂された書面を受け取るまで確定として扱わない",
        ],
    }


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def main(argv: list[str] | None = None) -> int:
    return run_cli(plan, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
