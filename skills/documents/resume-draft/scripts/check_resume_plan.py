#!/usr/bin/env python3
"""Check the plan behind a shokumu-keirekisho before it is written out.

棚卸しした経験のうち職務経歴書に載せるものについて、求人の要件ごとの対応、
裏づけと役割、確認できていない数値、抽象化していない守秘情報、在籍期間の
空白と重なりを数え、選んだ形式での並び順を組み立てる。文章の良し悪しも、
書類選考の通過も判定しない。
"""

from __future__ import annotations

from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_choice,
    optional_month_index,
    optional_text,
    require_list,
    require_month_index,
    require_object,
    require_text,
    run_cli,
)


TRACKS = ("chuto", "shinsotsu")
FORMATS = ("reverse_chronological", "chronological", "functional", "unknown")
LEVELS = ("must", "want")
ROLES = ("owner", "member", "team", "unstated")
EVIDENCE = ("public", "record", "third_party", "memory", "unknown")
KINDS = ("build", "improvement", "operation", "people", "sales", "research", "other")
# 断定形で数値を書いてよいのは、公開情報か手元の資料で確かめられたものだけ。
CONFIRMED_EVIDENCE = ("public", "record")


def format_month(index: int | None) -> str | None:
    if index is None:
        return None
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def parse_requirements(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "target.requirements")
    seen: set[str] = set()
    parsed = []
    for index, entry in enumerate(entries):
        path = f"target.requirements[{index}]"
        item = require_object(entry, path)
        requirement_id = require_text(item.get("id"), f"{path}.id")
        if requirement_id in seen:
            raise ValueError(f"{path}.id is duplicated: {requirement_id!r}")
        seen.add(requirement_id)
        parsed.append(
            {
                "id": requirement_id,
                "text": require_text(item.get("text"), f"{path}.text"),
                "level": optional_choice(item.get("level"), f"{path}.level", LEVELS, "must"),
            }
        )
    return parsed


def parse_timeline(raw: object, as_of: int | None) -> list[dict[str, Any]]:
    entries = require_list(raw, "timeline")
    if not entries:
        raise ValueError("timeline must contain at least one period")
    seen: set[str] = set()
    parsed = []
    for index, entry in enumerate(entries):
        path = f"timeline[{index}]"
        item = require_object(entry, path)
        label = require_text(item.get("label"), f"{path}.label")
        if label in seen:
            raise ValueError(f"{path}.label is duplicated: {label!r}")
        seen.add(label)
        start = require_month_index(item.get("start"), f"{path}.start")
        end = optional_month_index(item.get("end"), f"{path}.end")
        if end is None:
            if as_of is None:
                raise ValueError(f"{path}.end is null (current); set as_of to the current month")
            end_for_math = as_of
        else:
            end_for_math = end
        if end_for_math < start:
            raise ValueError(f"{path} ends before it starts")
        parsed.append(
            {
                "label": label,
                "start": start,
                "end": end,
                "end_for_math": end_for_math,
                "current": end is None,
            }
        )
    return parsed


def parse_experiences(
    raw: object, labels: set[str], requirement_ids: set[str]
) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "experiences")
    seen: set[str] = set()
    parsed = []
    for index, entry in enumerate(entries):
        path = f"experiences[{index}]"
        item = require_object(entry, path)
        experience_id = require_text(item.get("id"), f"{path}.id")
        if experience_id in seen:
            raise ValueError(f"{path}.id is duplicated: {experience_id!r}")
        seen.add(experience_id)

        label = optional_text(item.get("timeline_label"), f"{path}.timeline_label")
        if label is not None and label not in labels:
            raise ValueError(f"{path}.timeline_label does not match any timeline label: {label!r}")

        supports = [
            require_text(value, f"{path}.supports[{position}]")
            for position, value in enumerate(require_list(item.get("supports", []), f"{path}.supports"))
        ]
        unknown = [value for value in supports if value not in requirement_ids]
        if unknown:
            raise ValueError(f"{path}.supports names unknown requirement ids: {unknown}")

        metrics = []
        for position, metric in enumerate(require_list(item.get("metrics", []), f"{path}.metrics")):
            metric_path = f"{path}.metrics[{position}]"
            metric_item = require_object(metric, metric_path)
            metrics.append(
                {
                    "text": require_text(metric_item.get("text"), f"{metric_path}.text"),
                    "evidence": optional_choice(
                        metric_item.get("evidence"), f"{metric_path}.evidence", EVIDENCE, "unknown"
                    ),
                }
            )

        parsed.append(
            {
                "id": experience_id,
                "title": require_text(item.get("title"), f"{path}.title"),
                "timeline_label": label,
                "kind": optional_choice(item.get("kind"), f"{path}.kind", KINDS, "other"),
                "role": optional_choice(item.get("role"), f"{path}.role", ROLES, "unstated"),
                "evidence": optional_choice(item.get("evidence"), f"{path}.evidence", EVIDENCE, "unknown"),
                "metrics": metrics,
                "confidential_risk": optional_bool(
                    item.get("confidential_risk"), f"{path}.confidential_risk"
                ),
                "abstracted": optional_bool(item.get("abstracted"), f"{path}.abstracted"),
                "include": optional_bool(item.get("include"), f"{path}.include"),
                "supports": supports,
            }
        )
    return parsed


def build_requirements(
    requirements: list[dict[str, Any]], included: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for requirement in requirements:
        supporters = [item["id"] for item in included if requirement["id"] in item["supports"]]
        confirmed = [
            item["id"]
            for item in included
            if requirement["id"] in item["supports"] and item["evidence"] in CONFIRMED_EVIDENCE
        ]
        result.append(
            {
                **requirement,
                "supported_by": supporters,
                "supported_by_confirmed": confirmed,
            }
        )
    return result


def build_gaps(timeline: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(timeline, key=lambda period: period["start"])
    gaps, overlaps = [], []
    for previous, current in zip(ordered, ordered[1:]):
        distance = current["start"] - previous["end_for_math"] - 1
        if distance > 0:
            gaps.append(
                {
                    "after": previous["label"],
                    "before": current["label"],
                    "from": format_month(previous["end_for_math"] + 1),
                    "to": format_month(current["start"] - 1),
                    "months": distance,
                }
            )
        elif current["start"] <= previous["end_for_math"]:
            overlaps.append(
                {
                    "labels": [previous["label"], current["label"]],
                    "months": previous["end_for_math"] - current["start"] + 1,
                }
            )
    return gaps, overlaps


def build_outline(
    fmt: str, timeline: list[dict[str, Any]], included: list[dict[str, Any]]
) -> dict[str, Any]:
    """選んだ形式で、載せる経験の並び順を組み立てる。文章は作らない。"""
    if fmt == "functional":
        groups = []
        for kind in KINDS:
            members = [item["id"] for item in included if item["kind"] == kind]
            if members:
                groups.append({"kind": kind, "experiences": members})
        periods = sorted(timeline, key=lambda period: period["start"], reverse=True)
        return {
            "format": fmt,
            "groups": groups,
            "employment_list": [period["label"] for period in periods],
        }

    newest_first = fmt != "chronological"
    periods = sorted(timeline, key=lambda period: period["start"], reverse=newest_first)
    sections = []
    for period in periods:
        sections.append(
            {
                "label": period["label"],
                "start": format_month(period["start"]),
                "end": format_month(period["end"]) if period["end"] is not None else "現在",
                "experiences": [
                    item["id"] for item in included if item["timeline_label"] == period["label"]
                ],
            }
        )
    unassigned = [item["id"] for item in included if item["timeline_label"] is None]
    return {"format": fmt, "sections": sections, "unassigned": unassigned}


def collect_flags(
    track: str,
    fmt: str,
    has_target: bool,
    requirements: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    experiences: list[dict[str, Any]],
    included: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if track == "shinsotsu":
        add(
            "shinsotsu_track",
            "新卒の応募では職務経歴書を求められないことが多い。応募先の指定を確かめる",
        )
    if fmt == "unknown":
        add("format_undecided", "形式が決まっていない。並び順を決められない")
    if not has_target:
        add("no_target", "応募先の要件が入っていない。汎用版として作り、その旨を明記する")

    undecided = [item["id"] for item in experiences if item["include"] is None]
    if undecided:
        add("include_undecided", "載せるかどうかが決まっていない経験がある", undecided)
    if not included:
        add("nothing_included", "載せる経験が1つも決まっていない")

    must_unsupported = [
        item["id"] for item in requirements if item["level"] == "must" and not item["supported_by"]
    ]
    if must_unsupported:
        add(
            "must_requirement_unsupported",
            "必須要件のうち、対応する経験がないものがある。言い換えで埋めず、近い経験があるかを確かめるか、載せずに面接で説明するかを利用者が決める",
            must_unsupported,
        )
    memory_only = [
        item["id"]
        for item in requirements
        if item["supported_by"] and not item["supported_by_confirmed"]
    ]
    if memory_only:
        add(
            "requirement_supported_without_record",
            "要件を示す経験がすべて資料で確かめられていない。書けるが、数値や規模を断定しない",
            memory_only,
        )

    unstated = [item["id"] for item in included if item["role"] == "unstated"]
    if unstated:
        add(
            "role_unstated",
            "担当範囲が決まっていない経験を載せている。書類でも面接でも最初に聞かれる。役割を確かめてから書く",
            unstated,
        )
    team = [item["id"] for item in included if item["role"] == "team"]
    if team:
        add(
            "team_outcome",
            "チームの成果として載せる経験がある。成果の主語をチームにし、自分の担当部分を分けて書く",
            team,
        )

    unconfirmed_metrics = [
        item["id"]
        for item in included
        if any(metric["evidence"] not in CONFIRMED_EVIDENCE for metric in item["metrics"])
    ]
    if unconfirmed_metrics:
        add(
            "metric_not_confirmed",
            "資料で確かめていない数値を含む経験がある。断定形で書かないか、数値を使わない表現にする",
            unconfirmed_metrics,
        )
    unknown_evidence = [item["id"] for item in included if item["evidence"] == "unknown"]
    if unknown_evidence:
        add("evidence_unknown", "裏づけを確かめていない経験を載せている", unknown_evidence)

    confidential = [
        item["id"]
        for item in included
        if item["confidential_risk"] is True and item["abstracted"] is not True
    ]
    if confidential:
        add(
            "confidential_not_abstracted",
            "守秘情報を含む経験を、抽象化を決めないまま載せている。特定できない形にできなければ載せない",
            confidential,
        )
    confidential_unknown = [item["id"] for item in included if item["confidential_risk"] is None]
    if confidential_unknown:
        add(
            "confidential_unchecked",
            "守秘情報を含むかを確かめていない経験を載せている",
            confidential_unknown,
        )

    unassigned = [item["id"] for item in included if item["timeline_label"] is None]
    if unassigned and fmt != "functional":
        add(
            "experience_without_period",
            "どの在籍期間の経験かが決まっていない。推測で割り当てない",
            unassigned,
        )

    if track == "chuto":
        empty = [
            period["label"]
            for period in timeline
            if not any(item["timeline_label"] == period["label"] for item in included)
        ]
        if empty:
            add(
                "period_without_content",
                "載せる経験がない在籍期間がある。社名と期間だけ載せるか、担当業務を短く書くかを決める。在籍を省かない",
                empty,
            )
        latest = max(timeline, key=lambda period: period["start"])
        latest_count = sum(1 for item in included if item["timeline_label"] == latest["label"])
        older_count = sum(
            1
            for item in included
            if item["timeline_label"] is not None and item["timeline_label"] != latest["label"]
        )
        if latest_count == 0 and older_count > 0:
            add(
                "latest_period_thin",
                "直近の在籍期間に載せる経験がなく、古い期間の経験だけが並んでいる。直近の仕事が最もよく読まれる",
                [latest["label"]],
            )

    if gaps:
        add(
            "timeline_gap",
            "在籍期間の間に空白がある。期間をずらさず、書き方と面接での説明を決める",
            [f"{gap['from']}〜{gap['to']}（{gap['months']}か月）" for gap in gaps],
        )
    if overlaps:
        add(
            "timeline_overlap",
            "在籍期間が重なっている。兼務・副業・入力の誤りのどれかを確かめる",
            ["・".join(overlap["labels"]) for overlap in overlaps],
        )

    return flags


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    track = optional_choice(data.get("track"), "track", TRACKS, "chuto")
    fmt = optional_choice(data.get("format"), "format", FORMATS, "unknown")
    as_of = optional_month_index(data.get("as_of"), "as_of")

    target = require_object(data.get("target") or {}, "target")
    requirements = parse_requirements(target.get("requirements"))
    timeline = parse_timeline(data.get("timeline"), as_of)
    experiences = parse_experiences(
        data.get("experiences"),
        {period["label"] for period in timeline},
        {item["id"] for item in requirements},
    )
    included = [item for item in experiences if item["include"] is True]

    requirement_rows = build_requirements(requirements, included)
    gaps, overlaps = build_gaps(timeline)

    return {
        "track": track,
        "format": fmt,
        "target": optional_text(target.get("label"), "target.label"),
        "summary": {
            "experiences": len(experiences),
            "included": len(included),
            "must_requirements": sum(1 for item in requirements if item["level"] == "must"),
            "must_supported": sum(
                1 for item in requirement_rows if item["level"] == "must" and item["supported_by"]
            ),
            "want_requirements": sum(1 for item in requirements if item["level"] == "want"),
            "want_supported": sum(
                1 for item in requirement_rows if item["level"] == "want" and item["supported_by"]
            ),
        },
        "requirements": requirement_rows,
        "included": [
            {
                "id": item["id"],
                "title": item["title"],
                "timeline_label": item["timeline_label"],
                "role": item["role"],
                "evidence": item["evidence"],
                "supports": item["supports"],
                "metrics": item["metrics"],
            }
            for item in included
        ],
        "not_supporting_any_requirement": [
            item["id"] for item in included if requirements and not item["supports"]
        ],
        "outline": build_outline(fmt, timeline, included),
        "gaps": gaps,
        "overlaps": overlaps,
        "flags": collect_flags(
            track,
            fmt,
            bool(requirements),
            requirement_rows,
            timeline,
            experiences,
            included,
            gaps,
            overlaps,
        ),
        "notes": [
            "要件との対応は利用者が付けた対応を数えたもので、経験が要件を満たすかの判定ではない",
            "並び順は選んだ形式に沿った骨組みであり、文章の良し悪しや通過の見込みは判定しない",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(check, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
