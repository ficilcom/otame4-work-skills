#!/usr/bin/env python3
"""Shared helpers for the deterministic scripts bundled with each skill.

**このファイルが唯一の編集点である。** スキル配下の `scripts/_common.py` は
`python3 scripts/sync_common.py` が生成したコピーであり、直接編集しない。
CI は `sync_common.py --check` で差分を落とす。

なぜコピーを配るのか。スキルは `skills/<category>/<skill-name>/` を単位として
単独でインストールされ、それより上の階層は利用者の環境に届かない。
`SKILL.md` は `python3 scripts/<name>.py` と相対で呼ぶため、リポジトリ共通の
モジュールを import すると、インストール後に実行時エラーになる。
各スキルへ同一の内容を配り、CI で同期を検証するのが唯一の方法である。

方針として、ここに入れるのは入力の形を確かめる処理と CLI の定型だけにする。
何を欠落とみなすか、どの条件を注意として出すかといった判断はスキル固有であり、
各スクリプトに残す。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable


MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
YEN = Decimal("1")

# 本文に混ざった個人情報を見つけるための検査。scripts/validate_skills.py の
# リポジトリ側ガードと同じ規則を使う。
# 数字の並びは \b ではなく前後の数字だけを見て区切る。このリポジトリが扱う本文は
# 日本語で、「電話は03-1234-5678です」のように地の文へ直接続くと、\b は日本語の
# 文字も語構成文字として扱うため境界にならず、検出漏れになる。
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\d)0\d{1,4}-\d{1,4}-\d{3,4}(?!\d)")
MYNUMBER_PATTERN = re.compile(r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)")


# --- 入力の形を確かめる ------------------------------------------------------


def require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_text(value: object, path: str) -> str:
    """空でない文字列を前後の空白を落として返す。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def require_raw_text(value: object, path: str) -> str:
    """空でない文字列を原文のまま返す。

    前後の空白が意味を持つ入力だけに使う。応募書類の本文がこれにあたり、
    提出時の文字数には前後の空白も含まれるため、strip すると文字数の判定が
    実際の提出内容とずれる。迷うときは require_text を使う。
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def optional_text(value: object, path: str) -> str | None:
    return None if value is None else require_text(value, path)


def optional_choice(value: object, path: str, allowed: tuple[str, ...], default: str) -> str:
    """決められた選択肢の1つを返す。未指定と null は `default` として扱う。"""
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{path} must be one of {list(allowed)}")
    return str(value)


def optional_bool(value: object, path: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean or null")
    return value


def require_date(value: object, path: str) -> date:
    text = require_text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date (YYYY-MM-DD): {error}") from None


def optional_date(value: object, path: str) -> date | None:
    return None if value is None else require_date(value, path)


def require_month_index(value: object, path: str) -> int:
    """`YYYY-MM` を月単位の通し番号に変換する。期間の重なりや空白の計算に使う。"""
    text = require_text(value, path)
    match = MONTH_PATTERN.match(text)
    if not match:
        raise ValueError(f"{path} must look like YYYY-MM: {value!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"{path} has a month outside 1-12: {value!r}")
    return year * 12 + (month - 1)


def optional_month_index(value: object, path: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a YYYY-MM string or null")
    return require_month_index(value, path)


def optional_int(value: object, path: str) -> int | None:
    """0以上の整数、または null。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer or null")
    if value < 0:
        raise ValueError(f"{path} must not be negative")
    return value


def optional_positive_int(value: object, path: str) -> int | None:
    """1以上の整数、または null。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer or null")
    return value


def optional_amount(value: object, path: str) -> int | None:
    """0以上の金額を整数に丸めて返す。小数を受け取っても切り捨てる。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number or null")
    if value < 0:
        raise ValueError(f"{path} must not be negative")
    return int(value)


def optional_number(value: object, path: str, *, allow_zero: bool = True) -> Decimal | None:
    """金額の計算に使う数値を Decimal で返す。float の丸め誤差を持ち込まない。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number or null")
    number = Decimal(str(value))
    if number < 0:
        raise ValueError(f"{path} must not be negative")
    if number == 0 and not allow_zero:
        raise ValueError(f"{path} must be greater than zero")
    return number


# --- 出力を整える ------------------------------------------------------------


def round_yen(value: Decimal | None) -> int | None:
    """円単位に四捨五入する。銀行丸めだと表示額が入力とずれるため使わない。"""
    if value is None:
        return None
    return int(value.quantize(YEN, rounding=ROUND_HALF_UP))


def strip_whitespace(text: str) -> str:
    """空白の入れ方だけが違う記述を同じものとして比べるために正規化する。"""
    return WHITESPACE_RUN_PATTERN.sub("", text)


def flag_collector(key: str = "items") -> tuple[list[dict[str, Any]], Callable[..., None]]:
    """注意事項を集める `(flags, add)` を返す。

    `add(code, message)` で1件、対象を絞れる場合は `add(code, message, [...])`
    で対象も添える。空のリストは出力に入れない。対象の入る項目名を `items` から
    変えたいときだけ `key` を渡す。
    """
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, items: list[str] | None = None) -> None:
        flag: dict[str, Any] = {"code": code, "message": message}
        if items:
            flag[key] = items
        flags.append(flag)

    return flags, add


# --- CLI ---------------------------------------------------------------------


def run_cli(
    entry: Callable[[object], Any],
    description: str | None = None,
    argv: list[str] | None = None,
) -> int:
    """JSONを読み、`entry` にかけ、結果をJSONで書き出す。

    終了コードは 0（成功）と 2（入力が不正）だけを使う。入力の誤りは
    利用者が直せるものなので、traceback ではなく1行のメッセージで返す。
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("input", nargs="?", help="入力JSONのパス。省略した場合は標準入力から読む")
    args = parser.parse_args(argv)

    raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"input is not valid JSON: {error}", file=sys.stderr)
        return 2

    try:
        report = entry(payload)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0
