#!/usr/bin/env python3
"""Measure how completely a work history has been inventoried.

棚卸しした経験について、事実の分解が埋まっているか、裏づけが何に基づくか、在籍
期間のどこが手つかずかを機械的に確認する。経験の価値、強み、適性は判定しない。
書かれていない経験を推測で補わない。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TRACKS = ("shinsotsu", "chuto")
ROLE_STATEMENTS = ("owner", "member", "team", "unstated")
# 裏づけが何に基づくか。company-research の出典階層と同じ考え方で、強さを分けて扱う。
EVIDENCE_LEVELS = ("public", "record", "third_party", "memory", "unknown")
EVIDENCE_STRENGTH = {
    "public": "strong",
    "record": "strong",
    "third_party": "medium",
    "memory": "weak",
    "unknown": "unconfirmed",
}
EXPERIENCE_KINDS = (
    "build",
    "improvement",
    "operation",
    "people",
    "sales",
    "research",
    "other",
)
# 事実として分解できているかを見る項目。文章の巧拙は見ない。
NARRATIVE_FIELDS = ("situation", "actions", "outcome")

MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
# 在籍期間のうち、これだけ連続して棚卸しが空いていると、抜けとして報告する。
UNCOVERED_STRETCH_MONTHS = 6
# 種類の偏りを見るのは、経験がこの件数以上あるときだけにする。
CONCENTRATION_MINIMUM = 3


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


def _month_index(value: object, path: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a YYYY-MM string or null")
    match = MONTH_PATTERN.match(value.strip())
    if not match:
        raise ValueError(f"{path} must look like YYYY-MM: {value!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"{path} has a month outside 1-12: {value!r}")
    return year * 12 + (month - 1)


def parse_timeline(raw: object, as_of: int | None) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "timeline")
    timeline = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"timeline[{index}]")
        label = _require_text(item.get("label"), f"timeline[{index}].label")
        if label in seen:
            raise ValueError(f"timeline[{index}].label is duplicated: {label!r}")
        seen.add(label)

        start = _month_index(item.get("start"), f"timeline[{index}].start")
        if start is None:
            raise ValueError(f"timeline[{index}].start is required")
        end = _month_index(item.get("end"), f"timeline[{index}].end")
        if end is None:
            if as_of is None:
                raise ValueError(
                    f"timeline[{index}].end is open, so as_of (YYYY-MM) is required"
                )
            end = as_of
        if end < start:
            raise ValueError(f"timeline[{index}].end must not precede start")
        timeline.append(
            {
                "label": label,
                "start": start,
                "end": end,
                "start_text": item.get("start"),
                "end_text": item.get("end"),
                "open": item.get("end") is None,
            }
        )
    return sorted(timeline, key=lambda entry: entry["start"])


def parse_metrics(raw: object, path: str) -> list[dict[str, Any]]:
    metrics = []
    for index, entry in enumerate(_require_list(raw if raw is not None else [], path)):
        item = _require_object(entry, f"{path}[{index}]")
        evidence = item.get("evidence", "unknown")
        if evidence not in EVIDENCE_LEVELS:
            raise ValueError(f"{path}[{index}].evidence must be one of {list(EVIDENCE_LEVELS)}")
        metrics.append(
            {
                "text": _require_text(item.get("text"), f"{path}[{index}].text"),
                "evidence": evidence,
                "strength": EVIDENCE_STRENGTH[evidence],
            }
        )
    return metrics


def parse_experiences(raw: object, labels: set[str]) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "experiences")
    experiences = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"experiences[{index}]"
        item = _require_object(entry, path)
        experience_id = _require_text(item.get("id"), f"{path}.id")
        if experience_id in seen:
            raise ValueError(f"{path}.id is duplicated: {experience_id!r}")
        seen.add(experience_id)

        label = _optional_text(item.get("timeline_label"), f"{path}.timeline_label")
        if label is not None and label not in labels:
            raise ValueError(f"{path}.timeline_label is not in the timeline: {label!r}")

        kind = item.get("kind", "other")
        if kind not in EXPERIENCE_KINDS:
            raise ValueError(f"{path}.kind must be one of {list(EXPERIENCE_KINDS)}")
        role = item.get("role", "unstated")
        if role not in ROLE_STATEMENTS:
            raise ValueError(f"{path}.role must be one of {list(ROLE_STATEMENTS)}")
        evidence = item.get("evidence", "unknown")
        if evidence not in EVIDENCE_LEVELS:
            raise ValueError(f"{path}.evidence must be one of {list(EVIDENCE_LEVELS)}")

        period = item.get("period")
        start = end = None
        if period is not None:
            block = _require_object(period, f"{path}.period")
            start = _month_index(block.get("start"), f"{path}.period.start")
            end = _month_index(block.get("end"), f"{path}.period.end")
            if start is None:
                raise ValueError(f"{path}.period.start is required when period is given")
            if end is not None and end < start:
                raise ValueError(f"{path}.period.end must not precede start")

        actions = [
            _require_text(action, f"{path}.actions[{position}]")
            for position, action in enumerate(_require_list(item.get("actions", []), f"{path}.actions"))
        ]

        experiences.append(
            {
                "id": experience_id,
                "title": _require_text(item.get("title"), f"{path}.title"),
                "timeline_label": label,
                "kind": kind,
                "role": role,
                "evidence": evidence,
                "evidence_strength": EVIDENCE_STRENGTH[evidence],
                "situation": _optional_text(item.get("situation"), f"{path}.situation"),
                "actions": actions,
                "outcome": _optional_text(item.get("outcome"), f"{path}.outcome"),
                "metrics": parse_metrics(item.get("metrics"), f"{path}.metrics"),
                "confidential_risk": bool(item.get("confidential_risk", False)),
                "start": start,
                "end": end,
            }
        )
    return experiences


def describe_experience(experience: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if not experience["situation"]:
        missing.append("situation")
    if not experience["actions"]:
        missing.append("actions")
    if not experience["outcome"]:
        missing.append("outcome")
    if experience["role"] == "unstated":
        missing.append("role")
    if experience["start"] is None:
        missing.append("period")

    return {
        "id": experience["id"],
        "title": experience["title"],
        "timeline_label": experience["timeline_label"],
        "kind": experience["kind"],
        "role": experience["role"],
        "evidence": experience["evidence"],
        "evidence_strength": experience["evidence_strength"],
        "metric_count": len(experience["metrics"]),
        "metrics_backed_by_memory_only": bool(experience["metrics"])
        and all(metric["strength"] == "weak" for metric in experience["metrics"]),
        "missing_fields": missing,
        "complete": not missing,
        "confidential_risk": experience["confidential_risk"],
    }


def longest_uncovered_stretch(covered: set[int], start: int, end: int) -> int:
    longest = current = 0
    for month in range(start, end + 1):
        if month in covered:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def build_coverage(
    timeline: list[dict[str, Any]], experiences: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    coverage = []
    for entry in timeline:
        covered: set[int] = set()
        assigned = 0
        for experience in experiences:
            if experience["timeline_label"] != entry["label"] or experience["start"] is None:
                continue
            assigned += 1
            finish = experience["end"] if experience["end"] is not None else experience["start"]
            for month in range(max(experience["start"], entry["start"]), min(finish, entry["end"]) + 1):
                covered.add(month)

        total_months = entry["end"] - entry["start"] + 1
        coverage.append(
            {
                "label": entry["label"],
                "start": entry["start_text"],
                "end": entry["end_text"],
                "open": entry["open"],
                "total_months": total_months,
                "covered_months": len(covered),
                "experience_count": assigned,
                "longest_uncovered_stretch": longest_uncovered_stretch(
                    covered, entry["start"], entry["end"]
                ),
            }
        )
    return coverage


def collect_flags(
    track: str,
    described: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    kinds: dict[str, int],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, items: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if items:
            flag["items"] = items
        flags.append(flag)

    if not described:
        add("experiences_not_captured", "経験が取り込まれていない。棚卸しがまだ始まっていない")
        return flags

    incomplete = [entry["id"] for entry in described if not entry["complete"]]
    if incomplete:
        add(
            "experience_incomplete",
            "状況・行動・結果・役割・時期のどれかが埋まっていない経験がある。書類に使う前に埋める",
            incomplete,
        )

    unstated_role = [entry["id"] for entry in described if entry["role"] == "unstated"]
    if unstated_role:
        add(
            "role_unstated",
            "自分の担当範囲が決まっていない経験がある。書類でも面接でも最初に聞かれる",
            unstated_role,
        )

    weak = [entry["id"] for entry in described if entry["evidence_strength"] == "weak"]
    if weak:
        add(
            "evidence_from_memory_only",
            "裏づけが記憶だけの経験がある。資料で確認できるか、当時を知る人がいるかを確かめる",
            weak,
        )
    unconfirmed = [entry["id"] for entry in described if entry["evidence_strength"] == "unconfirmed"]
    if unconfirmed:
        add(
            "evidence_unconfirmed",
            "裏づけを確認していない経験がある。記憶だけの経験と区別して扱う",
            unconfirmed,
        )

    memory_metrics = [entry["id"] for entry in described if entry["metrics_backed_by_memory_only"]]
    if memory_metrics:
        add(
            "metrics_from_memory_only",
            "数値の根拠が記憶だけの経験がある。書類に数値を書く前に、出所を確認する",
            memory_metrics,
        )
    if not any(entry["metric_count"] for entry in described):
        add(
            "no_metrics_captured",
            "数値のある経験が1件もない。中途の書類では担当範囲と成果の大きさが読み取れない",
        )

    confidential = [entry["id"] for entry in described if entry["confidential_risk"]]
    if confidential:
        add(
            "confidential_content",
            "現職・前職の非公開情報を含む経験がある。書類と面接で話す範囲を先に決める",
            confidential,
        )

    uncovered = [
        entry["label"]
        for entry in coverage
        if entry["longest_uncovered_stretch"] >= UNCOVERED_STRETCH_MONTHS
    ]
    if uncovered:
        add(
            "period_not_inventoried",
            f"在籍期間のうち{UNCOVERED_STRETCH_MONTHS}か月以上、棚卸しできていない期間がある",
            uncovered,
        )

    unassigned = [entry["id"] for entry in described if entry["timeline_label"] is None]
    if unassigned:
        add(
            "experience_not_placed",
            "どの在籍期間の経験かが決まっていないものがある。時期が特定できないと職務経歴書に置けない",
            unassigned,
        )

    if track == "chuto" and coverage:
        latest = coverage[-1]
        if latest["experience_count"] == 0:
            add(
                "recent_period_empty",
                f"直近の在籍先（{latest['label']}）の経験が1件も棚卸しされていない。中途では直近が最も見られる",
            )

    if len(described) >= CONCENTRATION_MINIMUM and len(kinds) == 1:
        only = next(iter(kinds))
        add(
            "kind_concentration",
            f"棚卸しした経験がすべて同じ種類（{only}）に寄っている。他の種類の経験が漏れていないかを見る",
        )

    return flags


def analyze(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    track = data.get("track", "chuto")
    if track not in TRACKS:
        raise ValueError(f"track must be one of {list(TRACKS)}")

    as_of = _month_index(data.get("as_of"), "as_of")
    timeline = parse_timeline(data.get("timeline"), as_of)
    experiences = parse_experiences(data.get("experiences"), {entry["label"] for entry in timeline})

    described = [describe_experience(experience) for experience in experiences]
    coverage = build_coverage(timeline, experiences)

    kinds: dict[str, int] = {}
    for entry in described:
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1

    strengths: dict[str, int] = {}
    for entry in described:
        strengths[entry["evidence_strength"]] = strengths.get(entry["evidence_strength"], 0) + 1

    return {
        "track": track,
        "as_of": data.get("as_of"),
        "summary": {
            "experiences": len(described),
            "complete": sum(1 for entry in described if entry["complete"]),
            "with_metrics": sum(1 for entry in described if entry["metric_count"]),
            "evidence_strength": strengths,
            "kinds": kinds,
            "months_in_timeline": sum(entry["total_months"] for entry in coverage),
            "months_inventoried": sum(entry["covered_months"] for entry in coverage),
        },
        "experiences": described,
        "coverage": coverage,
        "flags": collect_flags(track, described, coverage, kinds),
        "notes": [
            "この出力は棚卸しの網羅と裏づけを数えたものであり、経験の価値や本人の適性の評価ではない",
            "埋まっていない項目は、利用者に確認して埋める。推測で補わない",
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
        report = analyze(payload)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
