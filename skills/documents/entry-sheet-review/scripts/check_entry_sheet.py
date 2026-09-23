#!/usr/bin/env python3
"""Measure entry-sheet answers against length limits and surface revision candidates.

このスクリプトは文字数と表層的な文章特徴だけを機械的に測る。内容の良し悪し、
通過可能性、事実の真偽は判定しない。判断はスキル本文の手順で人が行う。
"""

from __future__ import annotations

import re
from typing import Any

from _common import (
    optional_choice,
    optional_positive_int,
    require_list,
    require_object,
    require_raw_text,
    run_cli,
)


COUNT_RULES = ("with_whitespace", "without_whitespace")
DEFAULT_MIN_RATIO = 0.8
LONG_SENTENCE_CHARS = 80

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?])\s*")
NEWLINE_PATTERN = re.compile(r"\r\n|\r|\n")
WHITESPACE_PATTERN = re.compile(r"[\s　]")
NUMERIC_PATTERN = re.compile(r"[0-9０-９]+")

# 削れば密度が上がりやすい定型表現。誤りではないので候補として提示するだけ。
REDUNDANT_PHRASES = (
    "と思います",
    "と考えております",
    "させていただ",
    "することができ",
    "することが出来",
    "非常に",
    "とても",
    "様々な",
    "さまざまな",
    "いろいろな",
    "という点",
    "ということ",
    "しっかりと",
)

# 本文に混ざった個人情報を見つけるための検査。scripts/validate_skills.py の
# リポジトリ側ガードと同じ規則を使う。片方だけ増えると検出漏れになるため、
# 追加するときは両方を揃える。
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\d)0\d{1,4}-\d{1,4}-\d{3,4}(?!\d)")
MYNUMBER_PATTERN = re.compile(r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)")

PERSONAL_DATA_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("email", "メールアドレス", EMAIL_PATTERN),
    ("phone", "電話番号", PHONE_PATTERN),
    ("my_number", "マイナンバーらしき12桁の数字", MYNUMBER_PATTERN),
)


def count_characters(answer: str) -> dict[str, int]:
    without_newlines = NEWLINE_PATTERN.sub("", answer)
    return {
        "with_whitespace": len(without_newlines),
        "without_whitespace": len(WHITESPACE_PATTERN.sub("", answer)),
    }


def split_sentences(answer: str) -> list[str]:
    pieces: list[str] = []
    for line in NEWLINE_PATTERN.split(answer):
        for piece in SENTENCE_SPLIT_PATTERN.split(line):
            stripped = piece.strip()
            if stripped:
                pieces.append(stripped)
    return pieces


def count_paragraphs(answer: str) -> int:
    blocks = [block for block in re.split(r"(?:\r\n|\r|\n)\s*(?:\r\n|\r|\n)", answer) if block.strip()]
    if blocks:
        return len(blocks)
    return 1 if answer.strip() else 0


def find_redundant_phrases(answer: str) -> list[dict[str, Any]]:
    found = []
    for phrase in REDUNDANT_PHRASES:
        occurrences = answer.count(phrase)
        if occurrences:
            found.append({"phrase": phrase, "count": occurrences})
    return found


def find_personal_data(answer: str) -> list[dict[str, Any]]:
    """本文に混ざった個人情報を種類と件数で返す。

    一致した文字列そのものは返さない。削除を促すのに必要なのは「何が何件あるか」
    であって値ではなく、報告に載せると個人情報を出力しない方針に反する。
    """
    found: list[dict[str, Any]] = []
    for kind, label, pattern in PERSONAL_DATA_PATTERNS:
        count = len(pattern.findall(answer))
        if count:
            found.append({"kind": kind, "label": label, "count": count})
    return found


def analyze_document(raw: object, index: int, count_rule: str) -> dict[str, Any]:
    document = require_object(raw, f"documents[{index}]")
    identifier = str(document.get("id") or f"documents[{index}]")
    question = require_raw_text(document.get("question"), f"documents[{index}].question")
    answer = document.get("answer")
    if not isinstance(answer, str):
        raise ValueError(f"documents[{index}].answer must be a string")

    limit_chars = optional_positive_int(
        document.get("limit_chars"), f"documents[{index}].limit_chars"
    )
    min_chars = optional_positive_int(document.get("min_chars"), f"documents[{index}].min_chars")
    if min_chars is None and limit_chars is not None:
        min_chars = int(limit_chars * DEFAULT_MIN_RATIO)
    if limit_chars is not None and min_chars is not None and min_chars > limit_chars:
        raise ValueError(f"documents[{index}].min_chars must not exceed limit_chars")

    counts = count_characters(answer)
    counted = counts[count_rule]

    if limit_chars is None:
        length_status = "unknown"
        remaining = None
    elif counted > limit_chars:
        length_status = "over_limit"
        remaining = limit_chars - counted
    elif min_chars is not None and counted < min_chars:
        length_status = "under_target"
        remaining = limit_chars - counted
    else:
        length_status = "ok"
        remaining = limit_chars - counted

    sentences = split_sentences(answer)
    sentence_lengths = [len(WHITESPACE_PATTERN.sub("", sentence)) for sentence in sentences]
    long_sentences = [
        {"index": position, "chars": length, "text": sentences[position]}
        for position, length in enumerate(sentence_lengths)
        if length > LONG_SENTENCE_CHARS
    ]

    numeric_tokens = NUMERIC_PATTERN.findall(answer)
    personal_data = find_personal_data(answer)

    review_points: list[str] = []
    if length_status == "over_limit":
        review_points.append(f"文字数超過: {counted}/{limit_chars}字（{-remaining}字削る）")
    elif length_status == "under_target":
        review_points.append(
            f"分量不足の可能性: {counted}字（目安 {min_chars}〜{limit_chars}字）"
        )
    elif length_status == "unknown":
        review_points.append("文字数制限が未確定。募集要項で確認するまで長さは判定できない")
    if long_sentences:
        review_points.append(f"{LONG_SENTENCE_CHARS}字超の文が{len(long_sentences)}件ある")
    if not numeric_tokens:
        review_points.append("数値による裏づけがない。規模・期間・成果を数で示せるか確認する")
    if personal_data:
        labels = "、".join(item["label"] for item in personal_data)
        review_points.append(
            f"本文に個人情報が含まれている（{labels}）。設問が求めていなければ削除する"
        )
    if any(item["kind"] == "my_number" for item in personal_data):
        review_points.append(
            "マイナンバーらしき数字がある。応募書類に書く場面はほぼない。"
            "提出前に必ず削除し、誤って送っていないかも確認する"
        )

    return {
        "id": identifier,
        "question": question,
        "limit_chars": limit_chars,
        "min_chars": min_chars,
        "counts": counts,
        "counted_chars": counted,
        "remaining_chars": remaining,
        "length_status": length_status,
        "sentences": {
            "count": len(sentences),
            "longest_chars": max(sentence_lengths) if sentence_lengths else 0,
            "long_sentences": long_sentences,
        },
        "paragraph_count": count_paragraphs(answer),
        "numeric_token_count": len(numeric_tokens),
        "redundant_phrase_candidates": find_redundant_phrases(answer),
        "personal_data_in_body": personal_data,
        "review_points": review_points,
    }


def analyze(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    count_rule = optional_choice(data.get("count_rule"), "count_rule", COUNT_RULES, "with_whitespace")
    count_rule_confirmed = bool(data.get("count_rule_confirmed", False))

    documents = require_list(data.get("documents"), "documents")
    if not documents:
        raise ValueError("documents must contain at least one entry")

    results = [
        analyze_document(document, index, count_rule)
        for index, document in enumerate(documents)
    ]

    notes: list[str] = []
    if not count_rule_confirmed:
        notes.append(
            "文字数の数え方（空白・句読点の扱い）が未確認。企業の指定を確認するまで "
            "上限ぎりぎりの調整は避ける"
        )

    return {
        "count_rule": count_rule,
        "count_rule_confirmed": count_rule_confirmed,
        "document_count": len(results),
        "over_limit_count": sum(1 for item in results if item["length_status"] == "over_limit"),
        "under_target_count": sum(1 for item in results if item["length_status"] == "under_target"),
        "unknown_limit_count": sum(1 for item in results if item["length_status"] == "unknown"),
        "documents": results,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(analyze, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
