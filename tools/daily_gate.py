#!/usr/bin/env python3
"""daily_gate.py — 「JST 当日 1 回」に処理を収束させる共通ヘルパー（Issue #940）

【背景】
`tools/check_cloudflare_cost.py` と `tools/commit_cost_telemetry.py` は、どちらも
「Stop hook から毎セッション呼ばれても JST 当日 1 回に収束させる」ためのマーカーファイル
ゲートを独立に実装していた（`project_dir()` / `marker_path()` / `already_ran_today()` /
`stamp_today()` という同名の関数が 2 本に分裂）。PR #937 では両者の `project_dir()` の
フォールバック（`os.getcwd()` に統一）だけを揃え、共通モジュール化は本 Issue へ持ち越していた。

【設計】
本モジュールは「マーカーファイル 1 個で JST 当日 1 回に収束させる」という **最小の共通部分**
だけを持つ（`project_dir` / `today_jst` / `already_ran_today` / `stamp_marker`）。
マーカーの相対パス（`MARKER_REL` 相当の定数）と、判定結果そのものをキャッシュする追加ロジック
（`check_cloudflare_cost.py` の `load_cached_result` / `stamp_today(payload, exit_code)` のように、
「超過だった日は stamp しない」等の呼び出し側固有の分岐）は各スクリプト側に残す。これらは
「JST 当日 1 回」という共通の骨格の上に乗る、エンドポイントごとに違う業務ルールだから。

【`already_ran_today` が fail-closed でない理由】
マーカーが読めない（未作成・破損・権限エラー等）場合は「実行済みでない」（= 今日はまだ実行して
いない）として扱う。ここを fail-closed（読めない = 実行済みとみなしてスキップ）にすると、
何らかの理由でマーカーが壊れた日に日次処理が永久にスキップされる（逆方向の危険）。

使い方:
    python3 tools/daily_gate.py --self-test    # ネットワーク・ファイルシステム副作用は
                                                # 一時ディレクトリ内で完結する
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))


def project_dir() -> Path:
    """マーカーファイルを置くベースディレクトリ。

    `CLAUDE_PROJECT_DIR` があればそれを、無ければ `os.getcwd()` を使う。
    **フォールバックは `os.getcwd()` に統一する**（`REPO_ROOT` 固定にすると、実行時の
    カレントディレクトリ次第でマーカーが別ディレクトリへ書かれ、呼び出し元ごとに
    ゲートが分裂しうる・PR #937 レビュー）。
    """
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def today_jst() -> str:
    """表示・記録用の「今日」（JST・`YYYY-MM-DD`）。マーカーの内容とそのまま文字列比較する。"""
    return datetime.now(JST).strftime("%Y-%m-%d")


def marker_path(marker_rel: str, *, base: Path | None = None) -> Path:
    """マーカーファイルの絶対パスを組み立てる。

    `base` を省略すると `project_dir()` を使う（self-test では一時ディレクトリを注入する）。
    """
    return (base if base is not None else project_dir()) / marker_rel


def already_ran_today(marker_path_: Path) -> bool:
    """`marker_path_` の中身が「今日（JST）」の日付と一致するか。

    読み取れない（未作成・破損・権限エラー等）場合は **実行済みでない** として扱う
    （fail-closed に倒すと、マーカーが壊れた日に日次処理が永久にスキップされてしまうため、
    ここは逆に「疑わしきは実行する」側へ倒す。移設元 2 スクリプトの元実装と同じ挙動）。
    """
    try:
        return marker_path_.read_text(encoding="utf-8").strip() == today_jst()
    except OSError:
        return False


def stamp_marker(marker_path_: Path) -> bool:
    """`marker_path_` へ今日の日付を書き込む。

    失敗しても例外にしない（呼び出し側は「同日中に再試行できる」設計に任せる。
    移設元 2 スクリプトはいずれも書き込み失敗を握りつぶして次回に委ねていた）。

    戻り値: 書き込みに成功したら True・失敗したら False（呼び出し側が結果を見たい場合用。
    移設元は戻り値を使わず握りつぶしていたので、既存呼び出しへの互換上は無視してもよい）。
    """
    try:
        marker_path_.parent.mkdir(parents=True, exist_ok=True)
        marker_path_.write_text(today_jst() + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_project_dir() -> list[str]:
    failures: list[str] = []
    original = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        if project_dir() != Path(os.getcwd()):
            failures.append("CLAUDE_PROJECT_DIR 未設定時は os.getcwd() を使うべき")
        os.environ["CLAUDE_PROJECT_DIR"] = "/tmp/example-project-dir"
        if project_dir() != Path("/tmp/example-project-dir"):
            failures.append("CLAUDE_PROJECT_DIR が優先されていない")
        # 空文字は「未設定」と同じ扱い（`or os.getcwd()` の分岐を固定する）
        os.environ["CLAUDE_PROJECT_DIR"] = ""
        if project_dir() != Path(os.getcwd()):
            failures.append("CLAUDE_PROJECT_DIR が空文字のとき os.getcwd() へフォールバックしていない")
    finally:
        if original is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = original
    return failures


def _self_test_today_jst() -> list[str]:
    failures: list[str] = []
    value = today_jst()
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        failures.append(f"today_jst() の形式が YYYY-MM-DD でない: {value!r}")
    # JST は UTC+9 なので、UTC の「今日」と 9 時間ずれることがある（決定論的な単体比較はしない。
    # ここでは形式のみ固定し、実測でのタイムゾーンずれは _self_test_marker_lifecycle 側で見る）。
    return failures


def _self_test_marker_lifecycle() -> list[str]:
    """`marker_path` / `already_ran_today` / `stamp_marker` の一連のライフサイクル。"""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        mp = marker_path("state/.example_gate_date", base=base)

        # 1) マーカー未作成 -> 実行済みでない
        if already_ran_today(mp):
            failures.append("マーカー未作成なのに already_ran_today() が True")

        # 2) stamp -> 直後は実行済み扱い
        if not stamp_marker(mp):
            failures.append("stamp_marker() が失敗した（正常系のはず）")
        if not mp.exists():
            failures.append("stamp_marker() 後にファイルが作成されていない")
        if not already_ran_today(mp):
            failures.append("stamp 直後に already_ran_today() が False")
        content = mp.read_text(encoding="utf-8")
        if content != today_jst() + "\n":
            failures.append(f"マーカーの中身が想定外（末尾改行含む）: {content!r}")

        # 3) 日付がずれたマーカーは「実行済みでない」（前日のスタンプ等）
        mp.write_text("2000-01-01\n", encoding="utf-8")
        if already_ran_today(mp):
            failures.append("過去日のマーカーなのに already_ran_today() が True")

        # 4) 空白のトリム（末尾改行・空白混入への耐性）
        mp.write_text(f"  {today_jst()}  \n", encoding="utf-8")
        if not already_ran_today(mp):
            failures.append("前後の空白をトリムせず already_ran_today() が False になった")

    return failures


def _self_test_already_ran_today_unreadable() -> list[str]:
    """読み取れないマーカー（未作成・親ディレクトリ自体が無い）は fail-open（実行済みでない）。"""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # 親ディレクトリごと存在しないパス（read_text が OSError を送出する）
        mp = marker_path("nonexistent-nested/.marker", base=base)
        if already_ran_today(mp):
            failures.append("読み取り不能なマーカーなのに already_ran_today() が True")

        # ディレクトリをマーカーパスとして渡す（IsADirectoryError も OSError のサブクラス）
        dir_as_marker = base / "a-directory"
        dir_as_marker.mkdir()
        if already_ran_today(dir_as_marker):
            failures.append("ディレクトリを渡したのに already_ran_today() が True")
        # stamp_marker() も同様に例外を外へ漏らさず False を返す
        if stamp_marker(dir_as_marker):
            failures.append("ディレクトリへの書き込みが失敗しない（stamp_marker が例外を握りつぶしていない）")
    return failures


def _self_test_marker_path_default_base() -> list[str]:
    """`base` 省略時は `project_dir()` を使う（差し替え可能性の配線を固定する）。"""
    failures: list[str] = []
    original = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = "/tmp/example-daily-gate"
        got = marker_path("rel/path.txt")
        if got != Path("/tmp/example-daily-gate/rel/path.txt"):
            failures.append(f"base 省略時に project_dir() が使われていない: {got}")
    finally:
        if original is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = original
    return failures


def run_self_test() -> int:
    groups = [
        ("project_dir の CLAUDE_PROJECT_DIR / os.getcwd() フォールバック", _self_test_project_dir),
        ("today_jst の形式", _self_test_today_jst),
        ("marker_path/already_ran_today/stamp_marker のライフサイクル", _self_test_marker_lifecycle),
        ("読み取り不能なマーカーは fail-open（実行済みでない）", _self_test_already_ran_today_unreadable),
        ("marker_path の base 省略時は project_dir()", _self_test_marker_path_default_base),
    ]
    failed_groups = 0
    total = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed_groups += 1
            total += len(failures)
            for failure in failures:
                print(f"FAIL[{name}]: {failure}")
    if total:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed_groups} グループ失敗（{total} 件の不一致）")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="「JST 当日 1 回」に処理を収束させる共通ヘルパー（単独 CLI としては --self-test 専用）。"
    )
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテスト")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
