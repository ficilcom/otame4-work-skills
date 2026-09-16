#!/usr/bin/env python3
"""Validate repository-level invariants for Otame4 Agent Skills."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _repo import (
    CATEGORIES,
    MARKETPLACE_FILE,
    README_FILE,
    ROOT,
    SKILLS_DIR,
    SKILLS_SH_FILE,
)


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s*(.*))?$")
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b", re.IGNORECASE)
ALLOWED_LICENSES = {"MIT"}

# どのスキルも、外部への行為を勝手に実行しないことを本文で約束する。
# 節の中身はスキルごとに違ってよい（退職なら基礎年金番号、スカウトなら経歴の
# 受け渡しと、注意すべき点が違う）。ここで確かめるのは、節があることと、
# 権限境界の約束が書かれていることだけで、文面は揃えない。
BOUNDARY_HEADING = "## 個人情報と権限境界"
BOUNDARY_PROMISE_PATTERN = re.compile(r"自動実行しない|本人が行う")

# 実在する個人の応募書類をサンプルとして公開してしまう事故を止めるための最低限の検査。
# 数字の並びは \b ではなく前後の数字だけを見て区切る。このリポジトリの本文は日本語で、
# 「電話は03-1234-5678です」のように地の文へ直接続くと、\b は日本語の文字も
# 語構成文字として扱うため境界にならず、検出漏れになる。
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\d)0\d{1,4}-\d{1,4}-\d{3,4}(?!\d)")
MYNUMBER_PATTERN = re.compile(r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)")

TEXT_SUFFIXES = {".md", ".json", ".txt", ".yaml", ".yml", ".csv"}


def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["SKILL.md must start with YAML frontmatter"]

    try:
        closing = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}, ["frontmatter is missing its closing ---"]

    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = FIELD_PATTERN.match(line)
        if not match:
            problems.append(f"invalid top-level frontmatter line: {line!r}")
            continue
        key, value = match.groups()
        raw_value = (value or "").strip()
        # The skills CLI rejects a colon followed by whitespace in a plain YAML scalar.
        # Keep this dependency-free check focused on that discovery failure.
        if (
            key == "description"
            and not raw_value.startswith(("'", '"'))
            and re.search(r":(?:\s|$)", raw_value)
        ):
            problems.append("description containing a colon followed by whitespace must be quoted for valid YAML")
        fields[key] = (value or "").strip().strip("'\"")

    body = "\n".join(lines[closing + 1 :]).strip()
    if not body:
        problems.append("Markdown body must not be empty")
    if PLACEHOLDER_PATTERN.search(text):
        problems.append("unfinished placeholder found (TODO, TBD, FIXME, or PLACEHOLDER)")
    return fields, problems


def validate_skill(path: Path) -> list[str]:
    problems: list[str] = []
    relative = path.relative_to(ROOT)
    if path.parent.parent.parent != SKILLS_DIR:
        problems.append("skill must live at skills/<category>/<skill-name>/SKILL.md")
    elif path.parent.parent.name not in CATEGORIES:
        problems.append(f"unknown skill category: {path.parent.parent.name!r}")

    fields, parse_problems = parse_frontmatter(path)
    problems.extend(parse_problems)

    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name:
        problems.append("frontmatter requires a non-empty name")
    elif len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        problems.append("name must be <=64 characters of lowercase letters, digits, and hyphens")
    elif name != path.parent.name:
        problems.append(f"name {name!r} must match parent directory {path.parent.name!r}")

    if not description:
        problems.append("frontmatter requires a non-empty description")
    elif len(description) > 1024:
        problems.append("description must be <=1024 characters")

    license_name = fields.get("license")
    if license_name is not None and license_name not in ALLOWED_LICENSES:
        problems.append("license must be MIT or omitted for this repository")

    problems.extend(check_boundary_section(path.read_text(encoding="utf-8")))

    return [f"{relative}: {problem}" for problem in problems]


def check_boundary_section(text: str) -> list[str]:
    """権限境界の節があり、外部への行為を約束していることを確かめる。"""
    match = re.search(
        rf"^{re.escape(BOUNDARY_HEADING)}\n(.*?)(?=^## |\Z)", text, re.S | re.M
    )
    if not match:
        return [f"body must contain a {BOUNDARY_HEADING!r} section"]
    body = match.group(1).strip()
    if not body:
        return [f"{BOUNDARY_HEADING!r} section must not be empty"]
    if not BOUNDARY_PROMISE_PATTERN.search(body):
        return [
            f"{BOUNDARY_HEADING!r} section must state that the skill does not act "
            "on the user's behalf (自動実行しない / 本人が行う)"
        ]
    return []


def scan_personal_data(path: Path) -> list[str]:
    """実在しそうな連絡先・番号がスキル資材に混入していないか調べる。"""
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    relative = path.relative_to(ROOT)
    problems: list[str] = []
    for label, pattern in (
        ("email address", EMAIL_PATTERN),
        ("phone number", PHONE_PATTERN),
        ("12-digit number (my number?)", MYNUMBER_PATTERN),
    ):
        for match in pattern.finditer(text):
            if "example" in match.group(0).lower():
                continue
            problems.append(
                f"{relative}: possible personal data committed ({label}: {match.group(0)!r}); "
                "use clearly fictional placeholders"
            )
            break
    return problems


def validate_marketplace(skill_files: list[Path]) -> list[str]:
    if not MARKETPLACE_FILE.exists():
        return [".claude-plugin/marketplace.json is missing"]

    try:
        marketplace = json.loads(MARKETPLACE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f".claude-plugin/marketplace.json is not valid JSON: {error}"]

    problems: list[str] = []
    declared: set[tuple[str, str]] = set()
    for plugin in marketplace.get("plugins", []):
        source = str(plugin.get("source", ""))
        category = source.removeprefix("./skills/").strip("/")
        if category not in CATEGORIES:
            problems.append(
                f".claude-plugin/marketplace.json: plugin {plugin.get('name')!r} "
                f"has an unknown source {source!r}"
            )
            continue
        for entry in plugin.get("skills", []):
            declared.add((category, str(entry).removeprefix("./").strip("/")))

    on_disk = {(path.parent.parent.name, path.parent.name) for path in skill_files}
    for category, name in sorted(on_disk - declared):
        problems.append(
            f".claude-plugin/marketplace.json: skills/{category}/{name} is not listed in any plugin"
        )
    for category, name in sorted(declared - on_disk):
        problems.append(
            f".claude-plugin/marketplace.json: lists skills/{category}/{name}, which does not exist"
        )
    return problems


def _readme_skill_names() -> tuple[set[str], str | None]:
    """READMEの「収録スキル」表に載っているスキル名を返す。"""
    text = README_FILE.read_text(encoding="utf-8")
    match = re.search(r"^## 収録スキル\n(.*?)(?=^## )", text, re.S | re.M)
    if not match:
        return set(), "README.md: 「## 収録スキル」の節が見つからない"
    links = re.findall(r"\]\(skills/([a-z0-9-]+)/([a-z0-9-]+)/\)", match.group(1))
    return {name for _, name in links}, None


def _skills_sh_names() -> tuple[set[str], str | None]:
    """skills.sh.json の表示グループに載っているスキル名を返す。"""
    try:
        config = json.loads(SKILLS_SH_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set(), "skills.sh.json is missing"
    except json.JSONDecodeError as error:
        return set(), f"skills.sh.json is not valid JSON: {error}"
    names: set[str] = set()
    for group in config.get("groupings", []):
        names.update(str(entry) for entry in group.get("skills", []))
    return names, None


def validate_registries(skill_files: list[Path]) -> list[str]:
    """スキルの一覧を手で持っている場所が、実体とズレていないか調べる。

    スキルを1つ追加するだけで marketplace.json、READMEの表、skills.sh.json の
    3箇所を更新する必要がある。marketplace.json だけが検証されていて、残りは
    黙ってズレる状態だったため、まとめてここで突き合わせる。
    """
    on_disk = {path.parent.name for path in skill_files}
    problems: list[str] = []
    for label, (listed, error) in (
        ("README.md の収録スキル表", _readme_skill_names()),
        ("skills.sh.json の表示グループ", _skills_sh_names()),
    ):
        if error:
            problems.append(error)
            continue
        for name in sorted(on_disk - listed):
            problems.append(f"{label}: {name} が載っていない")
        for name in sorted(listed - on_disk):
            problems.append(f"{label}: {name} は存在しないスキルを指している")
    return problems


def validate_vendored_common() -> list[str]:
    """各スキルに配った _common.py が scripts/_common_source.py と一致するか調べる。

    スキルは単独でインストールされ、リポジトリ共通のモジュールは利用者の環境へ
    届かない。同一の内容を配るしかないため、ズレをここで落とす。
    """
    try:
        from sync_common import VENDORED_NAME, render, target_dirs
    except ImportError as error:  # pragma: no cover - 配置が壊れているときだけ
        return [f"scripts/sync_common.py could not be imported: {error}"]

    expected = render()
    problems: list[str] = []
    for script_dir in target_dirs():
        destination = script_dir / VENDORED_NAME
        relative = destination.relative_to(ROOT)
        if not destination.exists():
            problems.append(f"{relative}: missing; run `python3 scripts/sync_common.py`")
        elif destination.read_text(encoding="utf-8") != expected:
            problems.append(
                f"{relative}: out of sync with scripts/_common_source.py; "
                "run `python3 scripts/sync_common.py` and commit the result"
            )
    return problems


def main() -> int:
    skill_files = sorted(SKILLS_DIR.glob("**/SKILL.md")) if SKILLS_DIR.exists() else []
    problems: list[str] = []

    for path in skill_files:
        problems.extend(validate_skill(path))

    for path in sorted(SKILLS_DIR.rglob("*")) if SKILLS_DIR.exists() else []:
        if path.is_file():
            problems.extend(scan_personal_data(path))

    embedded_tests = sorted(SKILLS_DIR.glob("**/test_*.py")) if SKILLS_DIR.exists() else []
    problems.extend(
        f"{path.relative_to(ROOT)}: development tests must live under tests/"
        for path in embedded_tests
    )

    for category in sorted(CATEGORIES):
        category_dir = SKILLS_DIR / category
        if not category_dir.exists():
            problems.append(f"skills/{category}: category directory is missing")
            continue
        keep_file = category_dir / ".gitkeep"
        if keep_file.exists() and any(path.name != ".gitkeep" for path in category_dir.iterdir()):
            problems.append(
                f"{keep_file.relative_to(ROOT)}: remove .gitkeep from a non-empty category"
            )

    problems.extend(validate_marketplace(skill_files))
    problems.extend(validate_registries(skill_files))
    problems.extend(validate_vendored_common())

    if problems:
        print("Skill validation failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    if not skill_files:
        print("No skills found yet; repository scaffold is valid.")
        return 0

    print(f"Validated {len(skill_files)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
