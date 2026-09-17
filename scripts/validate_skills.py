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
    VENDORED_COMMON_NAME,
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

# スキルの粒度を、既存スキルの模倣ではなく検証で保つ。並びと役割は AGENTS.md の
# 「執筆」に書いてある。中身の深さは機械で測れないので、ここで見るのは置き場所だけ。
REQUIRED_SECTIONS = ("## 進め方", "## 判断上の制約", BOUNDARY_HEADING)

# 冒頭の段落は、何をするかに続けて、このスキルが行わないことで締める。
# 「合否の予測、経験の創作、応募の代行は行わない。」のような一文を求める。
INTRO_CLOSER_PATTERN = re.compile(r"(?:行わない|出さない)。(?:\*\*)?\s*\Z")

# 段階を束ねたスキルは、依頼と参照の対応表を `## 進め方` に持つ。その場合は
# 段階ごとの references が各自の成果物仕様を持つため、report-format.md を求めない。
# 表なら何でも免除にすると、普通のスキルが入力例の表を置くだけで出力形式の規則を
# 外せてしまう。行が references/ へ振り分けていること、振り分け先が2つ以上あることを
# 確かめ、段階を束ねた形になっているものだけを免除する。
ROUTING_ROW_PATTERN = re.compile(r"^\|.*\]\((references/[^)]+\.md)\).*\|\s*$", re.M)
ROUTING_TABLE_MIN_ROWS = 2
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

    text = path.read_text(encoding="utf-8")
    problems.extend(check_boundary_section(text))
    problems.extend(check_structure(path, text))

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


def routes_to_stages(procedure: str) -> bool:
    """`## 進め方` が、依頼を段階ごとの参照へ振り分ける表になっているか調べる。"""
    destinations = set(ROUTING_ROW_PATTERN.findall(procedure))
    return len(destinations) >= ROUTING_TABLE_MIN_ROWS


def check_structure(path: Path, text: str) -> list[str]:
    """節の並びと、冒頭の非対象宣言、出力雛形とスクリプトの置き場所を確かめる。"""
    problems: list[str] = []
    body = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)

    headings = tuple(f"## {name.strip()}" for name in re.findall(r"^## (.+)$", body, re.M))
    if headings != REQUIRED_SECTIONS:
        expected = " / ".join(REQUIRED_SECTIONS)
        problems.append(
            f"body must have exactly these sections in order: {expected} "
            f"(found: {' / '.join(headings) if headings else 'none'})"
        )

    intro_match = re.search(r"^# .+?\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    intro = intro_match.group(1).strip() if intro_match else ""
    if not intro:
        problems.append("body must open with a paragraph between the title and the first section")
    elif not INTRO_CLOSER_PATTERN.search(intro):
        problems.append(
            "opening paragraph must close by naming what the skill does not do "
            "(a sentence ending in 行わない。 or 出さない。)"
        )

    procedure_match = re.search(r"^## 進め方\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    procedure = procedure_match.group(1) if procedure_match else ""

    # 出力の雛形は references/report-format.md に置く。段階を束ねたスキルだけ免除する。
    report_format = path.parent / "references" / "report-format.md"
    if not report_format.exists() and not routes_to_stages(procedure):
        problems.append(
            f"references/report-format.md is required unless 進め方 routes requests to "
            f"{ROUTING_TABLE_MIN_ROWS} or more per-stage references with a table"
        )

    # 同梱スクリプトは専用の節ではなく、それを使う工程として案内する。
    scripts_dir = path.parent / "scripts"
    for script in sorted(scripts_dir.glob("*.py")) if scripts_dir.is_dir() else []:
        if script.name != VENDORED_COMMON_NAME and script.name not in procedure:
            problems.append(f"scripts/{script.name} must be introduced from within 進め方")

    return problems


def scan_personal_data(path: Path) -> list[str]:
    """実在しそうな連絡先・番号がスキル資材に混入していないか調べる。

    一致した文字列そのものは報告に載せない。検証の出力は端末とCIのログに残り、
    このリポジトリは公開されているため、値を書けば混入の範囲を広げてしまう。
    直す側に必要なのは種類と場所なので、行番号までを示す。
    """
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
            line = text.count("\n", 0, match.start()) + 1
            problems.append(
                f"{relative}:{line}: possible personal data committed ({label}); "
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


def _readme_skill_entries() -> tuple[set[tuple[str, str]], str | None]:
    """READMEの「収録スキル」表が指しているスキルを (カテゴリ, 名前) で返す。

    名前だけに落とすと、スキルを別カテゴリへ移したときにリンク切れを見逃す。
    READMEはリンク先にカテゴリを含むので、そこまで突き合わせる。
    """
    text = README_FILE.read_text(encoding="utf-8")
    match = re.search(r"^## 収録スキル\n(.*?)(?=^## )", text, re.S | re.M)
    if not match:
        return set(), "README.md: 「## 収録スキル」の節が見つからない"
    links = re.findall(r"\]\(skills/([a-z0-9-]+)/([a-z0-9-]+)/\)", match.group(1))
    return set(links), None


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
    on_disk = {(path.parent.parent.name, path.parent.name) for path in skill_files}
    on_disk_names = {name for _, name in on_disk}
    problems: list[str] = []

    label = "README.md の収録スキル表"
    entries, error = _readme_skill_entries()
    if error:
        problems.append(error)
    else:
        listed_names = {name for _, name in entries}
        for category, name in sorted(on_disk - entries):
            if name in listed_names:
                problems.append(
                    f"{label}: {name} のリンク先が実体（skills/{category}/{name}/）と一致しない"
                )
            else:
                problems.append(f"{label}: {name} が載っていない")
        for _, name in sorted(entries - on_disk):
            # リンク先のカテゴリ違いは上で報告済みなので、ここでは実体がないものだけ。
            if name not in on_disk_names:
                problems.append(f"{label}: {name} は存在しないスキルを指している")

    label = "skills.sh.json の表示グループ"
    # skills.sh.json は名前しか持たないため、カテゴリでは突き合わせられない。
    listed, error = _skills_sh_names()
    if error:
        problems.append(error)
    else:
        for name in sorted(on_disk_names - listed):
            problems.append(f"{label}: {name} が載っていない")
        for name in sorted(listed - on_disk_names):
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
