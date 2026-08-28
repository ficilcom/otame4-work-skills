#!/usr/bin/env python3
"""Grade collected company facts by source tier, freshness, coverage, and conflict.

このスクリプトは、集めた主張が「どの強さの出典に支えられているか」だけを機械的に
整理する。企業の良し悪し、応募すべきかどうか、情報の内容の正しさは判定しない。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


# 出典の強さ。日本の求人・企業調査で実際に当たれる情報源に対応させている。
TIER_RANKS = {
    "primary_filing": 4,     # 有価証券報告書、決算公告、登記、法人番号公表サイト
    "company_official": 3,   # 会社HP、IR資料、採用ページ、自社プレスリリース
    "regulated_public": 3,   # 行政が公開する職場情報、公共職業安定所の求人、法令違反の公表
    "journalism": 2,         # 報道機関の記事
    "user_provided": 2,      # 利用者が提示した資料（選考で受け取った書面など）
    "unverified": 1,         # 口コミサイト、まとめ記事、SNS、匿名の書き込み
}

EVIDENCE_BY_RANK = {4: "confirmed", 3: "confirmed", 2: "reported", 1: "unverified"}

# 出典の種類ごとに「いつまでなら最新として扱えるか」の既定値（日数）。
MAX_AGE_DAYS = {
    "primary_filing": 730,
    "company_official": 365,
    "regulated_public": 365,
    "journalism": 365,
    "user_provided": 365,
    "unverified": 180,
}

DEFAULT_TOPICS = (
    "legal_entity",
    "business_model",
    "financials",
    "organization",
    "role_context",
    "working_conditions",
    "risks",
    "recent_events",
)

URL_PATTERN = re.compile(r"^https?://\S+$")


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


def _require_date(value: object, path: str) -> date:
    text = _require_text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date (YYYY-MM-DD): {error}") from None


def _optional_date(value: object, path: str) -> date | None:
    return None if value is None else _require_date(value, path)


def parse_source(raw: object, path: str, as_of: date) -> dict[str, Any]:
    source = _require_object(raw, path)
    tier = _require_text(source.get("tier"), f"{path}.tier")
    if tier not in TIER_RANKS:
        raise ValueError(f"{path}.tier must be one of {sorted(TIER_RANKS)}")

    url = source.get("url")
    if url is not None:
        url = _require_text(url, f"{path}.url")
        if not URL_PATTERN.match(url):
            raise ValueError(f"{path}.url must be an http(s) URL")
    elif tier != "user_provided":
        raise ValueError(f"{path}.url is required unless the tier is user_provided")

    retrieved_on = _require_date(source.get("retrieved_on"), f"{path}.retrieved_on")
    if retrieved_on > as_of:
        raise ValueError(f"{path}.retrieved_on must not be later than as_of")

    published_on = _optional_date(source.get("published_on"), f"{path}.published_on")
    if published_on is not None and published_on > as_of:
        raise ValueError(f"{path}.published_on must not be later than as_of")

    if published_on is None:
        age_days: int | None = None
        stale = False
    else:
        age_days = (as_of - published_on).days
        stale = age_days > MAX_AGE_DAYS[tier]

    return {
        "url": url,
        "publisher": source.get("publisher"),
        "tier": tier,
        "rank": TIER_RANKS[tier],
        "retrieved_on": retrieved_on.isoformat(),
        "published_on": published_on.isoformat() if published_on else None,
        "age_days": age_days,
        "stale": stale,
    }


def parse_claim(raw: object, index: int, as_of: date, topics: tuple[str, ...]) -> dict[str, Any]:
    claim = _require_object(raw, f"claims[{index}]")
    identifier = _require_text(claim.get("id"), f"claims[{index}].id")
    statement = _require_text(claim.get("statement"), f"claims[{index}].statement")

    topic = _require_text(claim.get("topic"), f"claims[{index}].topic")
    if topic not in topics:
        raise ValueError(f"claims[{index}].topic must be one of {sorted(topics)}")

    sources = [
        parse_source(source, f"claims[{index}].sources[{position}]", as_of)
        for position, source in enumerate(_require_list(claim.get("sources", []), f"claims[{index}].sources"))
    ]

    conflicts = [
        _require_text(other, f"claims[{index}].conflicts_with[{position}]")
        for position, other in enumerate(
            _require_list(claim.get("conflicts_with", []), f"claims[{index}].conflicts_with")
        )
    ]

    if sources:
        best_rank = max(source["rank"] for source in sources)
        evidence = EVIDENCE_BY_RANK[best_rank]
        fresh_sources = [source for source in sources if not source["stale"]]
        undated = [source for source in sources if source["published_on"] is None]
    else:
        best_rank = 0
        evidence = "unknown"
        fresh_sources = []
        undated = []

    return {
        "id": identifier,
        "topic": topic,
        "statement": statement,
        "sources": sources,
        "best_tier_rank": best_rank,
        "evidence": evidence,
        "all_sources_stale": bool(sources) and not fresh_sources,
        "undated_source_count": len(undated),
        "conflicts_with": conflicts,
        "contested": False,
    }


def analyze(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "input")
    company = _require_text(data.get("company"), "company")
    as_of = _require_date(data.get("as_of"), "as_of")

    raw_topics = data.get("topics")
    if raw_topics is None:
        topics = DEFAULT_TOPICS
    else:
        listed = _require_list(raw_topics, "topics")
        if not listed:
            raise ValueError("topics must not be empty")
        topics = tuple(
            _require_text(topic, f"topics[{index}]") for index, topic in enumerate(listed)
        )

    raw_claims = _require_list(data.get("claims"), "claims")
    if not raw_claims:
        raise ValueError("claims must contain at least one entry")

    claims = [parse_claim(claim, index, as_of, topics) for index, claim in enumerate(raw_claims)]

    by_id: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if claim["id"] in by_id:
            raise ValueError(f"duplicate claim id: {claim['id']!r}")
        by_id[claim["id"]] = claim

    conflict_pairs: list[list[str]] = []
    for claim in claims:
        for other_id in claim["conflicts_with"]:
            if other_id not in by_id:
                raise ValueError(f"claim {claim['id']!r} conflicts with unknown id {other_id!r}")
            if other_id == claim["id"]:
                raise ValueError(f"claim {claim['id']!r} cannot conflict with itself")
            claim["contested"] = True
            by_id[other_id]["contested"] = True
            pair = sorted([claim["id"], other_id])
            if pair not in conflict_pairs:
                conflict_pairs.append(pair)

    evidence_counts = {level: 0 for level in ("confirmed", "reported", "unverified", "unknown")}
    for claim in claims:
        evidence_counts[claim["evidence"]] += 1

    topic_coverage = []
    coverage_gaps = []
    for topic in topics:
        matching = [claim for claim in claims if claim["topic"] == topic]
        if not matching:
            status, best = "missing", None
        elif any(claim["evidence"] == "confirmed" for claim in matching):
            status, best = "covered", "confirmed"
        elif any(claim["evidence"] == "reported" for claim in matching):
            status, best = "weak", "reported"
        else:
            status, best = "weak", "unverified"
        topic_coverage.append(
            {
                "topic": topic,
                "claim_count": len(matching),
                "best_evidence": best,
                "status": status,
            }
        )
        if status != "covered":
            coverage_gaps.append(topic)

    notes: list[str] = []
    if evidence_counts["unverified"]:
        notes.append(
            "口コミ・まとめ記事・SNSのみに基づく主張がある。事実として書かず、"
            "面接で確認する論点として扱う"
        )
    if any(claim["all_sources_stale"] for claim in claims):
        notes.append("出典がすべて鮮度切れの主張がある。現時点の状況として扱わない")
    if any(claim["undated_source_count"] for claim in claims):
        notes.append("公開日が不明な出典がある。時点不明のまま最新として扱わない")
    if conflict_pairs:
        notes.append("出典間で矛盾する主張がある。どちらが新しく、どちらが強い出典かで整理する")

    return {
        "company": company,
        "as_of": as_of.isoformat(),
        "claim_count": len(claims),
        "evidence_counts": evidence_counts,
        "claims": claims,
        "topic_coverage": topic_coverage,
        "coverage_gaps": coverage_gaps,
        "conflict_pairs": conflict_pairs,
        "contested_claim_ids": [claim["id"] for claim in claims if claim["contested"]],
        "stale_claim_ids": [claim["id"] for claim in claims if claim["all_sources_stale"]],
        "must_not_state_as_fact": [
            claim["id"] for claim in claims if claim["evidence"] in ("unverified", "unknown")
        ],
        "notes": notes,
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
