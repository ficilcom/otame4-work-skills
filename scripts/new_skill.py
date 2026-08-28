#!/usr/bin/env python3
"""Create a minimal Agent Skill scaffold under skills/."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATEGORIES = (
    "career",
    "documents",
    "interview",
    "research",
    "offer",
)
ROOT = Path(__file__).resolve().parents[1]

TEMPLATE = """---
name: {name}
description: "PLACEHOLDER: what this skill does, and when an agent should use it."
license: MIT
metadata:
  author: ficilcom
---

# {title}

PLACEHOLDER: 成果物、進め方、判断上の制約を書く。

## 進め方

PLACEHOLDER

## 判断上の制約

PLACEHOLDER

## 個人情報と権限境界

このスキルは下書き・分析・助言のみを行う。利用者本人の明示的な承認なしに、
応募の送信、企業や採用担当者への連絡、求人サイトやATSへの登録・更新を実行しない。
氏名、連絡先、生年月日、学籍番号、在籍企業の非公開情報は、作業に必要な範囲を超えて
収集・保存・出力しない。
"""


def title_from_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", choices=CATEGORIES, help="skill category")
    parser.add_argument("name", help="lowercase, hyphenated skill name")
    args = parser.parse_args()
    name = args.name

    if len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        parser.error(
            "name must be at most 64 characters and contain only lowercase "
            "letters, digits, and single hyphens"
        )

    skill_dir = ROOT / "skills" / args.category / name
    skill_file = skill_dir / "SKILL.md"
    if skill_dir.exists():
        parser.error(f"skill already exists: {skill_dir.relative_to(ROOT)}")

    skill_dir.mkdir(parents=True)
    skill_file.write_text(
        TEMPLATE.format(name=name, title=title_from_name(name)), encoding="utf-8"
    )
    keep_file = skill_dir.parent / ".gitkeep"
    if keep_file.exists():
        keep_file.unlink()
        print(f"Removed {keep_file.relative_to(ROOT)}")
    print(f"Created {skill_file.relative_to(ROOT)}")
    print("Replace every PLACEHOLDER, then add the skill to .claude-plugin/marketplace.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
