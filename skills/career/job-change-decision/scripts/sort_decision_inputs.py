#!/usr/bin/env python3
"""Sort the inputs to a stay-or-leave decision without making the decision.

現職への不満を、原因の所在、転職しても付いてくるか、現職でまだ試していないかで
分ける。行き先で得たいものと、いま持っていて失うものが両方挙がっているかを確認
し、留まる選択肢が検討されたかを数える。どちらを選ぶべきかは出さない。
"""

from __future__ import annotations

from typing import Any

from _common import (
    flag_collector,
    optional_date,
    optional_text,
    require_list,
    require_object,
    require_text,
    run_cli,
)


# 不満の原因がどこにあるか。転職で変わる範囲が原因ごとに違う。
CAUSES = ("role", "team", "company", "industry", "self", "unknown")
# 転職しても付いてくるか。
PORTABILITY = ("yes", "no", "unknown")
TRIED_INTERNALLY = ("yes", "no", "not_possible", "unknown")
SEVERITIES = ("high", "medium", "low", "unknown")
OPTION_STATUSES = ("considered", "not_considered", "ruled_out")
IMPORTANCE = ("high", "medium", "low", "unknown")

# (code, label, keeps_current_job)
OPTIONS: tuple[tuple[str, str, bool], ...] = (
    ("stay_as_is", "現職のまま、何も変えない", True),
    ("stay_and_change", "現職で改善を働きかける（担当、体制、働き方）", True),
    ("internal_transfer", "社内異動", True),
    ("role_change", "現職内での職種転換", True),
    ("leave_of_absence", "休職・療養", True),
    ("upskilling", "先に学習や資格取得を行う", False),
    ("side_work", "副業（就業規則の定めを確認する）", True),
    ("job_change", "転職", False),
    ("independent", "独立・フリーランス", False),
)
OPTION_CODES = {code for code, _, _ in OPTIONS}
STAY_OPTIONS = {code for code, _, keeps in OPTIONS if keeps}
# 原因がここにある不満は、現職の中で動かせる余地が残っていることがある。
INTERNALLY_ADDRESSABLE = ("role", "team", "self")


def parse_concerns(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "concerns")
    concerns = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"concerns[{index}]"
        item = require_object(entry, path)
        concern_id = require_text(item.get("id"), f"{path}.id")
        if concern_id in seen:
            raise ValueError(f"{path}.id is duplicated: {concern_id!r}")
        seen.add(concern_id)

        cause = item.get("cause", "unknown")
        if cause not in CAUSES:
            raise ValueError(f"{path}.cause must be one of {list(CAUSES)}")
        portable = item.get("portable", "unknown")
        if portable not in PORTABILITY:
            raise ValueError(f"{path}.portable must be one of {list(PORTABILITY)}")
        tried = item.get("tried_internally", "unknown")
        if tried not in TRIED_INTERNALLY:
            raise ValueError(f"{path}.tried_internally must be one of {list(TRIED_INTERNALLY)}")
        severity = item.get("severity", "unknown")
        if severity not in SEVERITIES:
            raise ValueError(f"{path}.severity must be one of {list(SEVERITIES)}")

        concerns.append(
            {
                "id": concern_id,
                "text": require_text(item.get("text"), f"{path}.text"),
                "cause": cause,
                "portable": portable,
                "tried_internally": tried,
                "severity": severity,
            }
        )
    return concerns


def parse_wants(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "wants")
    return [
        {
            "text": require_text(require_object(entry, f"wants[{index}]").get("text"), f"wants[{index}].text"),
            "must": bool(require_object(entry, f"wants[{index}]").get("must", False)),
        }
        for index, entry in enumerate(entries)
    ]


def parse_keeps(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "keeps")
    keeps = []
    for index, entry in enumerate(entries):
        item = require_object(entry, f"keeps[{index}]")
        importance = item.get("importance", "unknown")
        if importance not in IMPORTANCE:
            raise ValueError(f"keeps[{index}].importance must be one of {list(IMPORTANCE)}")
        keeps.append(
            {
                "text": require_text(item.get("text"), f"keeps[{index}].text"),
                "importance": importance,
            }
        )
    return keeps


def parse_options(raw: object) -> dict[str, dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "options")
    parsed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        item = require_object(entry, f"options[{index}]")
        code = item.get("code")
        if code not in OPTION_CODES:
            raise ValueError(f"options[{index}].code is not a known option: {code!r}")
        if code in parsed:
            raise ValueError(f"options[{index}].code is duplicated: {code!r}")
        status = item.get("status", "not_considered")
        if status not in OPTION_STATUSES:
            raise ValueError(f"options[{index}].status must be one of {list(OPTION_STATUSES)}")
        parsed[code] = {
            "status": status,
            "note": optional_text(item.get("note"), f"options[{index}].note"),
        }
    return parsed


def parse_constraints(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "constraints")
    return [
        {
            "text": require_text(
                require_object(entry, f"constraints[{index}]").get("text"),
                f"constraints[{index}].text",
            ),
            "date": optional_date(
                require_object(entry, f"constraints[{index}]").get("date"),
                f"constraints[{index}].date",
            ),
        }
        for index, entry in enumerate(entries)
    ]


def sort_concerns(concerns: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "follows_you": [item["id"] for item in concerns if item["portable"] == "yes"],
        "changes_with_employer": [item["id"] for item in concerns if item["portable"] == "no"],
        "portability_unknown": [item["id"] for item in concerns if item["portable"] == "unknown"],
        "untried_internally": [
            item["id"]
            for item in concerns
            if item["tried_internally"] == "no" and item["cause"] in INTERNALLY_ADDRESSABLE
        ],
        "cause_unknown": [item["id"] for item in concerns if item["cause"] == "unknown"],
        "industry_wide": [item["id"] for item in concerns if item["cause"] == "industry"],
    }


def collect_flags(
    concerns: list[dict[str, Any]],
    wants: list[dict[str, Any]],
    keeps: list[dict[str, Any]],
    options: list[dict[str, Any]],
    sorted_concerns: dict[str, list[str]],
    days_to_deadline: int | None,
    criteria_defined: bool | None,
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if not concerns:
        add("concerns_not_captured", "現状の不満は未入力。不満のない相談では、希望や今後確かめたいことから対話を続けられる")

    if sorted_concerns["follows_you"]:
        add(
            "concerns_that_follow_you",
            "転職しても残ると本人が予想した悩みがある。環境によって変わる部分と、その予想を見直す材料を確認できる",
            sorted_concerns["follows_you"],
        )
    if sorted_concerns["portability_unknown"]:
        add(
            "portability_unknown",
            "転職で変わるか未確認の悩みがある。変わる場合と変わらない場合で選択肢を比較できる",
            sorted_concerns["portability_unknown"],
        )
    if sorted_concerns["untried_internally"]:
        add(
            "not_tried_internally",
            "原因が職務・人間関係・自分の状態にあり、現職でまだ試していない不満がある",
            sorted_concerns["untried_internally"],
        )
    if sorted_concerns["cause_unknown"]:
        add(
            "cause_unknown",
            "原因の所在が特定できていない不満がある。転職で変わる範囲が決まらない",
            sorted_concerns["cause_unknown"],
        )
    if sorted_concerns["industry_wide"]:
        add(
            "industry_wide_concerns",
            "原因が業界の構造にあると本人が捉えた悩みがある。別の職場でも同じ条件かは未確認",
            sorted_concerns["industry_wide"],
        )

    if concerns and not wants:
        add(
            "no_destination_stated",
            "現職の不満は挙がっているが、次に何を得たいかが挙がっていない。比較の片側しかない",
        )
    if concerns and not keeps:
        add(
            "nothing_recorded_as_kept",
            "いま持っていて失うものが挙がっていない。移ることの代償が見えない",
        )

    not_considered = [
        entry["code"] for entry in options if entry["status"] == "not_considered"
    ]
    if not_considered:
        add("options_not_considered", "未検討の選択肢がある。相談に関係するものだけ扱い、全件の検討は求めない", not_considered)

    # 検討したうえで外したもの（ruled_out）は、検討済みとして扱う。
    stay_considered = any(
        entry["status"] in ("considered", "ruled_out")
        for entry in options
        if entry["code"] in STAY_OPTIONS
    )
    if not stay_considered:
        add(
            "staying_not_considered",
            "現職に留まる選択肢の検討は記録されていない。未記録と未検討を区別し、本人の意向と状況に応じて確認する",
        )

    if criteria_defined is not True:
        add(
            "decision_criteria_undefined",
            "判断基準は未確認。結論を急がず、次に確かめることや見直す時期を相談できる",
        )
    if days_to_deadline is not None and days_to_deadline < 0:
        add("decision_deadline_passed", "自分で決めた判断期限を過ぎている")

    return flags


def sort_inputs(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    as_of = optional_date(data.get("as_of"), "as_of")

    concerns = parse_concerns(data.get("concerns"))
    wants = parse_wants(data.get("wants"))
    keeps = parse_keeps(data.get("keeps"))
    provided = parse_options(data.get("options"))
    constraints = parse_constraints(data.get("constraints"))

    decision = require_object(data.get("decision", {}), "decision")
    deadline = optional_date(decision.get("deadline"), "decision.deadline")
    criteria_defined = decision.get("criteria_defined")
    if criteria_defined is not None and not isinstance(criteria_defined, bool):
        raise ValueError("decision.criteria_defined must be a boolean or null")
    days_to_deadline = (deadline - as_of).days if deadline and as_of else None

    options = [
        {
            "code": code,
            "label": label,
            "keeps_current_job": keeps_current,
            "status": provided[code]["status"] if code in provided else "not_considered",
            "note": provided[code]["note"] if code in provided else None,
        }
        for code, label, keeps_current in OPTIONS
    ]

    sorted_concerns = sort_concerns(concerns)

    return {
        "as_of": data.get("as_of"),
        "summary": {
            "concerns": len(concerns),
            "follows_you": len(sorted_concerns["follows_you"]),
            "changes_with_employer": len(sorted_concerns["changes_with_employer"]),
            "portability_unknown": len(sorted_concerns["portability_unknown"]),
            "untried_internally": len(sorted_concerns["untried_internally"]),
            "wants": len(wants),
            "keeps": len(keeps),
            "options_considered": sum(1 for entry in options if entry["status"] == "considered"),
            "options_total": len(options),
        },
        "concerns": concerns,
        "sorted_concerns": sorted_concerns,
        "wants": wants,
        "keeps": keeps,
        "options": options,
        "constraints": [
            {"text": item["text"], "date": item["date"].isoformat() if item["date"] else None}
            for item in constraints
        ],
        "decision": {
            "deadline": deadline.isoformat() if deadline else None,
            "days_to_deadline": days_to_deadline,
            "criteria_defined": criteria_defined,
        },
        "flags": collect_flags(
            concerns, wants, keeps, options, sorted_concerns, days_to_deadline, criteria_defined
        ),
        "notes": [
            "この出力は判断の材料を分けたものであり、転職すべきかどうかの結論ではない",
            "portable と tried_internally は利用者自身の判断であって、こちらの評価ではない",
            "severity は利用者の申告であり、優先順位の決定ではない",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(sort_inputs, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
