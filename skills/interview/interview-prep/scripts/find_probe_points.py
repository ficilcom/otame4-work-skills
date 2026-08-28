#!/usr/bin/env python3
"""Find where an interviewer is likely to dig into the documents already submitted.

提出済みの応募書類の各主張と職歴、求人の必須要件を突き合わせ、裏づけを説明でき
ない主張、担当範囲が曖昧な記述、職歴の空白、書類が触れていない必須要件を機械的に
洗い出す。想定質問は定型の問い方を組み立てるだけで、回答は作らない。合否は予測
しない。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TRACKS = ("shinsotsu", "chuto")
STAGES = ("casual", "first", "second", "final", "unknown")
DOCUMENT_SOURCES = ("es", "rirekisho", "shokumu", "portfolio", "scout_reply", "unknown")
ROLE_STATEMENTS = ("owner", "member", "team", "unstated")
REQUIREMENT_KINDS = ("must", "want")
PREPARED_STATUSES = ("drafted", "outlined", "none")
PRIORITIES = ("high", "medium", "low")

MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
# 在籍のない月がこれ以上続くと、理由を聞かれる前提で準備する。
GAP_MONTHS_THRESHOLD = 3
# 在籍期間がこれ未満だと、退職理由を掘られる前提で準備する。
SHORT_TENURE_MONTHS = 12

# (topic, label, tracks)
PREPARED_TOPICS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("self_introduction", "自己紹介・これまでの経歴の要約", ("shinsotsu", "chuto")),
    ("motivation_for_company", "志望動機（なぜこの会社か）", ("shinsotsu", "chuto")),
    ("career_change_reason", "転職理由（なぜ辞めるか、なぜ今か）", ("chuto",)),
    ("job_hunting_axis", "就職活動の軸", ("shinsotsu",)),
    ("student_experience", "学生時代に力を入れたこと", ("shinsotsu",)),
    ("strengths", "強みと、この職種でどう活きるか", ("shinsotsu", "chuto")),
    ("failure", "うまくいかなかった経験と、その後どうしたか", ("shinsotsu", "chuto")),
    ("career_plan", "今後のキャリアの見通し", ("shinsotsu", "chuto")),
    ("conditions", "希望条件（年収、勤務地、入社時期）", ("shinsotsu", "chuto")),
    ("reverse_questions", "逆質問", ("shinsotsu", "chuto")),
)

# (code, priority, 問い方の型)
PROBE_TEMPLATES: dict[str, tuple[str, str]] = {
    "unverifiable_claim": ("high", "「{topic}」について、実際に何をしたのかを具体的に教えてください"),
    "role_unclear": ("high", "「{topic}」で、あなた自身が担当した範囲はどこまでですか"),
    "uncovered_must_requirement": ("high", "求人が挙げている「{topic}」について教えてください"),
    "confidential_content": ("high", "「{topic}」の具体的な数字や取引先について教えてください"),
    "unquantified_outcome": ("medium", "「{topic}」の成果は、何がどれだけ変わったのですか"),
    "repeatability_unstated": ("medium", "「{topic}」と同じことを、当社の環境でどう再現しますか"),
    "employment_gap": ("medium", "{topic}の期間は何をされていましたか"),
    "overlapping_employment": ("medium", "{topic}の期間が重なっていますが、どういう状況ですか"),
    "short_tenure": ("medium", "{topic}を短期間で離れた理由を教えてください"),
}
PROBE_REASONS: dict[str, str] = {
    "unverifiable_claim": "書類に書いてあるが、根拠を自分で説明できないと申告している",
    "role_unclear": "主語がチームのままで、担当範囲が読み取れない",
    "uncovered_must_requirement": "必須要件に対応する記述が書類にない",
    "confidential_content": "現職・前職の非公開情報に踏み込む可能性がある",
    "unquantified_outcome": "成果を主張しているが、測った数値がない",
    "repeatability_unstated": "成果は書かれているが、再現の条件が書かれていない",
    "employment_gap": "職歴に空白がある",
    "overlapping_employment": "在籍期間が重なっている",
    "short_tenure": "在籍期間が短い",
}


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


def _optional_bool(value: object, path: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean or null")
    return value


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


def parse_claims(raw: object) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "claims")
    claims = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"claims[{index}]")
        claim_id = _require_text(item.get("id"), f"claims[{index}].id")
        if claim_id in seen:
            raise ValueError(f"claims[{index}].id is duplicated: {claim_id!r}")
        seen.add(claim_id)

        source = item.get("source", "unknown")
        if source not in DOCUMENT_SOURCES:
            raise ValueError(f"claims[{index}].source must be one of {list(DOCUMENT_SOURCES)}")
        role = item.get("role_stated", "unstated")
        if role not in ROLE_STATEMENTS:
            raise ValueError(f"claims[{index}].role_stated must be one of {list(ROLE_STATEMENTS)}")

        metrics = [
            _require_text(metric, f"claims[{index}].metrics[{position}]")
            for position, metric in enumerate(_require_list(item.get("metrics", []), f"claims[{index}].metrics"))
        ]
        claims.append(
            {
                "id": claim_id,
                "topic": _require_text(item.get("topic"), f"claims[{index}].topic"),
                "source": source,
                "role_stated": role,
                "metrics": metrics,
                "claims_outcome": bool(item.get("claims_outcome", False)),
                "verifiable_by_user": _optional_bool(
                    item.get("verifiable_by_user"), f"claims[{index}].verifiable_by_user"
                ),
                "repeatable_stated": bool(item.get("repeatable_stated", False)),
                "confidential_risk": bool(item.get("confidential_risk", False)),
            }
        )
    return claims


def parse_timeline(raw: object) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "timeline")
    timeline = []
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"timeline[{index}]")
        start = _month_index(item.get("start"), f"timeline[{index}].start")
        end = _month_index(item.get("end"), f"timeline[{index}].end")
        if start is None:
            raise ValueError(f"timeline[{index}].start is required")
        if end is not None and end < start:
            raise ValueError(f"timeline[{index}].end must not precede start")
        timeline.append(
            {
                "label": _require_text(item.get("label"), f"timeline[{index}].label"),
                "start": start,
                "end": end,
                "start_text": item.get("start"),
                "end_text": item.get("end"),
            }
        )
    return sorted(timeline, key=lambda entry: entry["start"])


def parse_requirements(raw: object, claim_ids: set[str]) -> list[dict[str, Any]]:
    entries = _require_list(raw if raw is not None else [], "requirements")
    requirements = []
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"requirements[{index}]")
        kind = item.get("kind", "must")
        if kind not in REQUIREMENT_KINDS:
            raise ValueError(f"requirements[{index}].kind must be one of {list(REQUIREMENT_KINDS)}")
        covered_by = [
            _require_text(value, f"requirements[{index}].covered_by[{position}]")
            for position, value in enumerate(
                _require_list(item.get("covered_by", []), f"requirements[{index}].covered_by")
            )
        ]
        for claim_id in covered_by:
            if claim_id not in claim_ids:
                raise ValueError(
                    f"requirements[{index}].covered_by refers to an unknown claim id: {claim_id!r}"
                )
        requirements.append(
            {
                "text": _require_text(item.get("text"), f"requirements[{index}].text"),
                "kind": kind,
                "covered_by": covered_by,
            }
        )
    return requirements


def parse_prepared(raw: object) -> dict[str, str]:
    entries = _require_list(raw if raw is not None else [], "prepared")
    prepared: dict[str, str] = {}
    known = {topic for topic, _, _ in PREPARED_TOPICS}
    for index, entry in enumerate(entries):
        item = _require_object(entry, f"prepared[{index}]")
        topic = _require_text(item.get("topic"), f"prepared[{index}].topic")
        if topic not in known:
            raise ValueError(f"prepared[{index}].topic is not a known topic: {topic!r}")
        status = item.get("status", "none")
        if status not in PREPARED_STATUSES:
            raise ValueError(f"prepared[{index}].status must be one of {list(PREPARED_STATUSES)}")
        prepared[topic] = status
    return prepared


def make_probe(code: str, topic: str, detail: str, refers_to: str | None = None) -> dict[str, Any]:
    priority, template = PROBE_TEMPLATES[code]
    probe: dict[str, Any] = {
        "code": code,
        "priority": priority,
        "topic": topic,
        "reason": PROBE_REASONS[code],
        "likely_question": template.format(topic=topic),
        "prepare": detail,
    }
    if refers_to:
        probe["refers_to"] = refers_to
    return probe


def probe_claims(claims: list[dict[str, Any]], track: str) -> list[dict[str, Any]]:
    probes = []
    for claim in claims:
        if claim["verifiable_by_user"] is not True:
            probes.append(
                make_probe(
                    "unverifiable_claim",
                    claim["topic"],
                    "この主張の根拠を説明できるかを利用者に確認する。説明できないなら、書類の表現を事実に合わせて直す",
                    claim["id"],
                )
            )
        if claim["confidential_risk"]:
            probes.append(
                make_probe(
                    "confidential_content",
                    claim["topic"],
                    "どこまで話すかの線引きを先に決める。未公開の数値、顧客名、社内資料の内容は話さない",
                    claim["id"],
                )
            )
        if claim["role_stated"] in ("team", "unstated"):
            probes.append(
                make_probe(
                    "role_unclear",
                    claim["topic"],
                    "自分が決めたこと、自分が手を動かしたこと、他者がやったことを分けて言えるようにする",
                    claim["id"],
                )
            )
        if claim["claims_outcome"] and not claim["metrics"]:
            probes.append(
                make_probe(
                    "unquantified_outcome",
                    claim["topic"],
                    "測った指標、変化の幅、期間を確認する。数値が出せないなら、何をもって成果と判断したかを言えるようにする",
                    claim["id"],
                )
            )
        if track == "chuto" and claim["metrics"] and not claim["repeatable_stated"]:
            probes.append(
                make_probe(
                    "repeatability_unstated",
                    claim["topic"],
                    "成果が出た条件（体制、権限、期間）と、応募先で同じ条件が揃うかを整理する",
                    claim["id"],
                )
            )
    return probes


def probe_timeline(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    probes = []
    for entry in timeline:
        end = entry["end"]
        if end is not None and (end - entry["start"]) < SHORT_TENURE_MONTHS:
            probes.append(
                make_probe(
                    "short_tenure",
                    entry["label"],
                    "退職理由を、前職の批判ではなく、次に何を求めたかで言えるようにする",
                )
            )

    for previous, following in zip(timeline, timeline[1:]):
        if previous["end"] is None:
            probes.append(
                make_probe(
                    "overlapping_employment",
                    f"{previous['label']}と{following['label']}",
                    "在籍が続いたまま次の期間が始まっている。副業・兼業・出向のどれかを説明できるようにする",
                )
            )
            continue
        if following["start"] <= previous["end"]:
            probes.append(
                make_probe(
                    "overlapping_employment",
                    f"{previous['label']}と{following['label']}",
                    "在籍期間が重なっている。副業・兼業・出向のどれかを説明できるようにする",
                )
            )
            continue
        gap = following["start"] - previous["end"] - 1
        if gap >= GAP_MONTHS_THRESHOLD:
            probes.append(
                make_probe(
                    "employment_gap",
                    f"{previous['end_text']}から{following['start_text']}",
                    f"{gap}か月の空白について、何をしていたかを事実で説明できるようにする",
                )
            )
    return probes


def probe_requirements(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        make_probe(
            "uncovered_must_requirement",
            requirement["text"],
            "書類のどの経験で答えるかを決める。該当する経験がないなら、近い経験と、埋め方を用意する",
        )
        for requirement in requirements
        if requirement["kind"] == "must" and not requirement["covered_by"]
    ]


def build_preparation(track: str, prepared: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "topic": topic,
            "label": label,
            "status": prepared.get(topic, "none"),
        }
        for topic, label, tracks in PREPARED_TOPICS
        if track in tracks
    ]


def collect_flags(
    claims: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    preparation: list[dict[str, Any]],
    questions_to_ask: list[str],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, items: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if items:
            flag["items"] = items
        flags.append(flag)

    if not claims:
        add("claims_not_captured", "提出書類の主張が取り込まれていない。書類を見ずに想定質問を作らない")
    unverifiable = [claim["id"] for claim in claims if claim["verifiable_by_user"] is False]
    if unverifiable:
        add(
            "unverifiable_claims_in_documents",
            "根拠を説明できない主張が提出書類に残っている。面接より先に、書類の表現を事実に合わせる必要がある",
            unverifiable,
        )
    unknown_support = [claim["id"] for claim in claims if claim["verifiable_by_user"] is None]
    if unknown_support:
        add(
            "claim_support_unconfirmed",
            "根拠を説明できるかを確認していない主張がある",
            unknown_support,
        )

    if not timeline:
        add("timeline_not_captured", "職歴が取り込まれていない。空白や重複の確認ができない")
    if not requirements:
        add("requirements_not_captured", "求人の要件が取り込まれていない。必須要件の抜けを確認できない")

    unprepared = [entry["topic"] for entry in preparation if entry["status"] == "none"]
    if unprepared:
        add("topics_not_prepared", "まだ準備していない定番の論点がある", unprepared)

    if not questions_to_ask:
        add(
            "no_questions_to_ask",
            "逆質問が用意されていない。企業研究で残った未確認の論点をここに回す",
        )
    return flags


def analyze(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    role = _require_text(data.get("role"), "role")

    track = data.get("track", "chuto")
    if track not in TRACKS:
        raise ValueError(f"track must be one of {list(TRACKS)}")
    stage = data.get("stage", "unknown")
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {list(STAGES)}")

    claims = parse_claims(data.get("claims"))
    timeline = parse_timeline(data.get("timeline"))
    requirements = parse_requirements(data.get("requirements"), {claim["id"] for claim in claims})
    prepared = parse_prepared(data.get("prepared"))
    preparation = build_preparation(track, prepared)
    questions_to_ask = [
        _require_text(question, f"questions_to_ask[{index}]")
        for index, question in enumerate(
            _require_list(data.get("questions_to_ask", []), "questions_to_ask")
        )
    ]

    probes = probe_claims(claims, track) + probe_timeline(timeline) + probe_requirements(requirements)
    order = {priority: position for position, priority in enumerate(PRIORITIES)}
    probes.sort(key=lambda probe: (order[probe["priority"]], probe["code"]))

    return {
        "role": role,
        "track": track,
        "stage": stage,
        "summary": {
            "claims": len(claims),
            "probe_points": len(probes),
            "high_priority": sum(1 for probe in probes if probe["priority"] == "high"),
            "must_requirements": sum(1 for item in requirements if item["kind"] == "must"),
            "uncovered_must_requirements": sum(
                1 for item in requirements if item["kind"] == "must" and not item["covered_by"]
            ),
            "topics_prepared": sum(1 for entry in preparation if entry["status"] == "drafted"),
            "topics_total": len(preparation),
            "questions_to_ask": len(questions_to_ask),
        },
        "probe_points": probes,
        "preparation": preparation,
        "questions_to_ask": questions_to_ask,
        "flags": collect_flags(claims, timeline, requirements, preparation, questions_to_ask),
        "notes": [
            "priority は準備の順序であって、評価でも合否の見込みでもない",
            "likely_question は定型の問い方であり、実際の質問文でも模範解答でもない",
            "回答は利用者の事実から作る。書類にない経験を補わない",
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
