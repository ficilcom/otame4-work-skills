#!/usr/bin/env python3
"""Repository-level constants shared by the tools under scripts/.

ここはリポジトリの道具だけが読む。スキルには配布されないため、
`_common_source.py` と違って通常のモジュールとして import してよい。
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# カテゴリはここだけで定義する。追加したら skills/<category>/ を作り、
# README とプラグイン定義にも反映する（検証スクリプトが不一致を落とす）。
CATEGORIES: tuple[str, ...] = (
    "career",
    "documents",
    "interview",
    "research",
    "offer",
    "trial",
    "employer",
    "sidework",
)

SKILLS_DIR = ROOT / "skills"

# スキル名の規則。雛形の作成と検証の両方がここを読む。
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX_LENGTH = 64


def is_valid_skill_name(name: str) -> bool:
    return len(name) <= SKILL_NAME_MAX_LENGTH and SKILL_NAME_PATTERN.fullmatch(name) is not None

# 各スキルへ配る共通モジュールのファイル名。スキル同梱のスクリプトを数えるとき、
# この生成物は「そのスキルが持つスクリプト」に含めない。
VENDORED_COMMON_NAME = "_common.py"
MARKETPLACE_FILE = ROOT / ".claude-plugin" / "marketplace.json"
README_FILE = ROOT / "README.md"
SKILLS_SH_FILE = ROOT / "skills.sh.json"
