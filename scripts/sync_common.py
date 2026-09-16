#!/usr/bin/env python3
"""Copy scripts/_common_source.py into every skill that ships deterministic scripts.

スキルは `skills/<category>/<skill-name>/` を単位として単独でインストールされ、
それより上の階層は利用者の環境に届かない。共通処理はリポジトリ共通のモジュールに
まとめられないため、同一の内容を各スキルへ配り、ここで同期を検証する。

    python3 scripts/sync_common.py            # 配布する
    python3 scripts/sync_common.py --check    # 差分があれば終了コード1（CI用）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "_common_source.py"
SKILLS_DIR = ROOT / "skills"
VENDORED_NAME = "_common.py"

BANNER = """# ---------------------------------------------------------------------------
# 生成物。直接編集しない。
# 編集するのは scripts/_common_source.py で、`python3 scripts/sync_common.py`
# で各スキルへ配り直す。CI は `--check` で差分を落とす。
# ---------------------------------------------------------------------------
"""


def render() -> str:
    """配布する内容を組み立てる。shebang の直後に生成物である旨を入れる。"""
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("#!"):
        return lines[0] + BANNER + "".join(lines[1:])
    return BANNER + text


def target_dirs() -> list[Path]:
    """決定的スクリプトを同梱しているスキルの scripts/ を返す。"""
    found = []
    for script_dir in sorted(SKILLS_DIR.glob("*/*/scripts")):
        if not script_dir.is_dir():
            continue
        if any(p.name != VENDORED_NAME for p in script_dir.glob("*.py")):
            found.append(script_dir)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="書き込まずに差分だけを報告する",
    )
    args = parser.parse_args(argv)

    if not SOURCE.exists():
        print(f"missing source: {SOURCE.relative_to(ROOT)}", file=sys.stderr)
        return 2

    expected = render()
    targets = target_dirs()
    stale: list[Path] = []
    written: list[Path] = []

    for script_dir in targets:
        destination = script_dir / VENDORED_NAME
        current = destination.read_text(encoding="utf-8") if destination.exists() else None
        if current == expected:
            continue
        if args.check:
            stale.append(destination.relative_to(ROOT))
            continue
        destination.write_text(expected, encoding="utf-8")
        written.append(destination.relative_to(ROOT))

    # 配布先でなくなったスキルに残ったコピーも落とす。
    for leftover in sorted(SKILLS_DIR.glob(f"*/*/scripts/{VENDORED_NAME}")):
        if leftover.parent in targets:
            continue
        if args.check:
            stale.append(leftover.relative_to(ROOT))
        else:
            leftover.unlink()
            print(f"Removed {leftover.relative_to(ROOT)}")

    if args.check:
        if stale:
            print("Vendored _common.py is out of sync:", file=sys.stderr)
            for path in stale:
                print(f"- {path}", file=sys.stderr)
            print(
                "Run `python3 scripts/sync_common.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"Vendored _common.py is in sync across {len(targets)} skill(s).")
        return 0

    for path in written:
        print(f"Wrote {path}")
    print(f"Synced {len(targets)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
