#!/usr/bin/env python3
"""Check whether the criteria someone is selecting employers on can actually be used.

応募先を選ぶ基準について、何を見れば確認できるかが決まっているか、何に基づいて
そう思っているか、避けたい条件が挙がっているか、両立しにくい基準を同時に必須に
していないかを機械的に確認する。基準の良し悪しは判定しない。候補の優劣も出さない。
"""

from __future__ import annotations

from typing import Any

from _common import (
    flag_collector,
    optional_choice,
    optional_text,
    require_list,
    require_object,
    require_text,
    run_cli,
)


TRACKS = ("shinsotsu", "chuto")
# 基準の重み。must が多いほど候補は減るが、多いことを誤りとしては扱わない。
KINDS = ("must", "want", "avoid")
# その基準をなぜそう思うのか。確認の重みが変わる。
BASES = ("experience", "observed", "assumption", "unknown")
BASIS_STRENGTH = {
    "experience": "firsthand",
    "observed": "secondhand",
    "assumption": "untested",
    "unknown": "unstated",
}
ASSESSMENTS = ("met", "unmet", "unknown")
# 候補に対して未確認の基準がこの割合を超えると、まだ比較できる状態にないとみなす。
UNKNOWN_RATIO_THRESHOLD = 0.5


def parse_criteria(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "criteria")
    criteria = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"criteria[{index}]"
        item = require_object(entry, path)
        criterion_id = require_text(item.get("id"), f"{path}.id")
        if criterion_id in seen:
            raise ValueError(f"{path}.id is duplicated: {criterion_id!r}")
        seen.add(criterion_id)

        kind = optional_choice(item.get("kind"), f"{path}.kind", KINDS, "want")
        basis = optional_choice(item.get("basis"), f"{path}.basis", BASES, "unknown")

        observable = [
            require_text(way, f"{path}.observable[{position}]")
            for position, way in enumerate(require_list(item.get("observable", []), f"{path}.observable"))
        ]
        criteria.append(
            {
                "id": criterion_id,
                "text": require_text(item.get("text"), f"{path}.text"),
                "kind": kind,
                "basis": basis,
                "basis_strength": BASIS_STRENGTH[basis],
                "observable": observable,
                "note": optional_text(item.get("note"), f"{path}.note"),
            }
        )
    return criteria


def parse_tradeoffs(raw: object, criterion_ids: set[str]) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "tradeoffs")
    tradeoffs = []
    for index, entry in enumerate(entries):
        path = f"tradeoffs[{index}]"
        item = require_object(entry, path)
        pair = require_list(item.get("pair"), f"{path}.pair")
        if len(pair) != 2:
            raise ValueError(f"{path}.pair must hold exactly two criterion ids")
        for position, value in enumerate(pair):
            if value not in criterion_ids:
                raise ValueError(f"{path}.pair[{position}] is not a known criterion id: {value!r}")
        if pair[0] == pair[1]:
            raise ValueError(f"{path}.pair must name two different criteria")
        tradeoffs.append(
            {
                "pair": [str(pair[0]), str(pair[1])],
                "note": optional_text(item.get("note"), f"{path}.note"),
            }
        )
    return tradeoffs


def parse_candidates(raw: object, criterion_ids: set[str]) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "candidates")
    candidates = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"candidates[{index}]"
        item = require_object(entry, path)
        label = require_text(item.get("label"), f"{path}.label")
        if label in seen:
            raise ValueError(f"{path}.label is duplicated: {label!r}")
        seen.add(label)

        assessment: dict[str, str] = {}
        for position, record in enumerate(
            require_list(item.get("assessment", []), f"{path}.assessment")
        ):
            block = require_object(record, f"{path}.assessment[{position}]")
            criterion = block.get("criterion")
            if criterion not in criterion_ids:
                raise ValueError(
                    f"{path}.assessment[{position}].criterion is not a known criterion id: {criterion!r}"
                )
            if criterion in assessment:
                raise ValueError(
                    f"{path}.assessment[{position}].criterion is duplicated: {criterion!r}"
                )
            status = optional_choice(
                block.get("status"), f"{path}.assessment[{position}].status", ASSESSMENTS, "unknown"
            )
            assessment[str(criterion)] = status
        candidates.append({"label": label, "assessment": assessment})
    return candidates


def describe_candidate(
    candidate: dict[str, Any], criteria: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = []
    for criterion in criteria:
        rows.append(
            {
                "criterion": criterion["id"],
                "kind": criterion["kind"],
                "status": candidate["assessment"].get(criterion["id"], "unknown"),
            }
        )
    unknown = [row["criterion"] for row in rows if row["status"] == "unknown"]
    unmet_must = [
        row["criterion"] for row in rows if row["kind"] == "must" and row["status"] == "unmet"
    ]
    hit_avoid = [
        row["criterion"] for row in rows if row["kind"] == "avoid" and row["status"] == "met"
    ]
    return {
        "label": candidate["label"],
        "assessment": rows,
        "unknown_criteria": unknown,
        "unmet_must": unmet_must,
        "matches_avoid": hit_avoid,
        "unknown_ratio": round(len(unknown) / len(rows), 2) if rows else None,
    }


def collect_flags(
    criteria: list[dict[str, Any]],
    tradeoffs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if not criteria:
        add("criteria_not_captured", "選ぶ基準が取り込まれていない。突き合わせるものがない")
        return flags

    unobservable = [item["id"] for item in criteria if not item["observable"]]
    if unobservable:
        add(
            "no_way_to_check",
            "何を見れば確認できるかが決まっていない基準がある。確認できない基準では候補を選べない",
            unobservable,
        )

    untested = [item["id"] for item in criteria if item["basis"] == "assumption"]
    if untested:
        add(
            "based_on_assumption",
            "実際に経験しておらず、想像で置いている基準がある。捨てる必要はないが、先に確かめる",
            untested,
        )
    unstated = [item["id"] for item in criteria if item["basis"] == "unknown"]
    if unstated:
        add(
            "basis_unstated",
            "なぜそう思うのかを確認していない基準がある",
            unstated,
        )

    if not any(item["kind"] == "avoid" for item in criteria):
        add(
            "no_avoid_criteria",
            "避けたい条件が1つも挙がっていない。欲しいものだけでは、外すべき候補が判別できない",
        )

    musts = [item["id"] for item in criteria if item["kind"] == "must"]
    if musts and len(musts) == len(criteria):
        add(
            "everything_is_must",
            "すべての基準が必須になっている。優先順位がないため、候補が残らなかったときに何を緩めるかが決まらない",
        )

    kinds = {item["id"]: item["kind"] for item in criteria}
    conflicting = [
        pair["pair"]
        for pair in tradeoffs
        if kinds[pair["pair"][0]] == "must" and kinds[pair["pair"][1]] == "must"
    ]
    if conflicting:
        add(
            "conflicting_musts",
            "両立しにくいとした基準が、どちらも必須になっている。どちらを緩めるかを先に決める",
            [criterion_id for pair in conflicting for criterion_id in pair],
        )

    if not candidates:
        add(
            "no_candidates",
            "候補が挙がっていない。基準が実際に使えるかは、候補に当ててみるまで分からない",
        )
        return flags

    unchecked = [
        entry["label"]
        for entry in candidates
        if entry["unknown_ratio"] is not None and entry["unknown_ratio"] > UNKNOWN_RATIO_THRESHOLD
    ]
    if unchecked:
        add(
            "candidate_mostly_unchecked",
            "基準の半分以上が未確認の候補がある。調べる前に候補から外さない",
            unchecked,
        )

    hitting_avoid = [entry["label"] for entry in candidates if entry["matches_avoid"]]
    if hitting_avoid:
        add(
            "candidate_matches_avoid",
            "避けたい条件に当てはまる候補がある。外すかどうかは自分で決める",
            hitting_avoid,
        )

    return flags


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    track = optional_choice(data.get("track"), "track", TRACKS, "chuto")

    criteria = parse_criteria(data.get("criteria"))
    criterion_ids = {item["id"] for item in criteria}
    tradeoffs = parse_tradeoffs(data.get("tradeoffs"), criterion_ids)
    raw_candidates = parse_candidates(data.get("candidates"), criterion_ids)
    candidates = [describe_candidate(candidate, criteria) for candidate in raw_candidates]

    kinds: dict[str, int] = {}
    strengths: dict[str, int] = {}
    for item in criteria:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        strengths[item["basis_strength"]] = strengths.get(item["basis_strength"], 0) + 1

    return {
        "track": track,
        "summary": {
            "criteria": len(criteria),
            "kinds": kinds,
            "basis_strength": strengths,
            "with_way_to_check": sum(1 for item in criteria if item["observable"]),
            "candidates": len(candidates),
        },
        "criteria": criteria,
        "tradeoffs": tradeoffs,
        "candidates": candidates,
        "flags": collect_flags(criteria, tradeoffs, candidates),
        "notes": [
            "この出力は基準が使える形になっているかの確認であり、基準の当否の評価ではない",
            "候補の順位も適合度の点数も出さない。外すかどうかは利用者が決める",
            "未確認は不適合ではない。調べる前に候補から外さない",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(check, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
