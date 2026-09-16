"""Load and run a skill's bundled script the way its CLI does.

各テストが `importlib.util.spec_from_file_location` を書き写していたが、その
読み込み方はスクリプトのディレクトリを `sys.path` に載せないため、スキルに
同梱された `_common.py` を import できない。実行時は `python3 scripts/<name>.py`
なので Python が `scripts/` を `sys.path[0]` に置き、import が通る。
ここで同じ状態を作り、テストと実行時の条件を揃える。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def script_path(relative_path: str) -> Path:
    """リポジトリルートからの相対パスでスクリプトの場所を返す。"""
    script = ROOT / relative_path
    if not script.is_file():
        raise FileNotFoundError(f"script not found: {relative_path}")
    return script


def load_script(relative_path: str) -> ModuleType:
    """スクリプトをモジュールとして読み込む。"""
    script = script_path(relative_path)

    # 同じディレクトリに置かれたモジュール（_common.py など）を、実行時と同じ
    # 経路で解決できるようにする。
    script_dir = str(script.parent)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)

    spec = importlib.util.spec_from_file_location(script.stem, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(
    script: Path,
    payload: Any = None,
    *,
    argv: tuple[str, ...] = (),
    raw: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """スクリプトを実際のCLIとして実行する。

    `payload` を渡すとJSONにして標準入力へ流す。`raw` を渡すとその文字列を
    そのまま流す（不正なJSONの扱いを確かめる用）。`argv` は引数に渡す。
    """
    if payload is not None and raw is not None:
        raise TypeError("pass either payload or raw, not both")
    stdin = raw if raw is not None else (
        json.dumps(payload, ensure_ascii=False) if payload is not None else ""
    )
    return subprocess.run(
        [sys.executable, str(script), *argv],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
