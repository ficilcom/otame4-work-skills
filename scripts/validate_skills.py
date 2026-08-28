#!/usr/bin/env python3
"""Validate repository-level invariants for Otame4 Agent Skills."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATEGORIES = {
    "career",
    "documents",
    "interview",
    "research",
    "offer",
}
FIELD_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s*(.*))?$")
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b", re.IGNORECASE)
ALLOWED_LICENSES = {"Proprietary"}

# 実在する個人の応募書類をサンプルとして取り込んでしまう事故を止めるための最低限の検査。
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"\b0\d{1,4}-\d{1,4}-\d{3,4}\b")
MYNUMBER_PATTERN = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}\b")

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
MARKETPLACE_FILE = ROOT / ".claude-plugin" / "marketplace.json"
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
        problems.append("license must be Proprietary or omitted for this repository")

    return [f"{relative}: {problem}" for problem in problems]


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
