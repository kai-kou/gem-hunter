#!/usr/bin/env python3
"""discussion_review_trigger.py — Layer 2 議論型レビューの自動トリガー（判定器）。

PR の差分行数またはラベルに基づいて Layer 2 議論型レビューの要否を判定する。
pr-review-watcher スキルが PR 作成後に呼び出す（Issue #97）。

既定（ネイティブ経路・Issue #193）: トリガー該当時は「実行プラン JSON」を stdout に出力して
終了する。呼び出し元のエージェントがこのプランを使って discussion-review スキル
（ネイティブ Agent Teams）を実行する。本スクリプトはサブプロセスを起動しない。

--legacy 指定時（フォールバック）: 旧経路（run_discussion_review.py = claude -p 駆動）を
サブプロセスとして直接起動する。ネイティブ経路が成立しない場合のみ使う。

トリガー条件:
  - 差分行数（追加 + 削除）が TRIGGER_DIFF_LINES（300行）以上
  - PR ラベルに TRIGGER_LABELS（type:security / type:breaking-change）が含まれる

## クラウド環境での使い方（gh CLI 不可・MCP ツールで事前取得必須）

クラウド実行環境では gh CLI の GraphQL/REST が無効なため、エージェントが
mcp__github__pull_request_read で取得した値を引数として渡す:

  python3 tools/discussion_review_trigger.py \\
      --pr 42 \\
      --diff-lines 450 \\
      --labels "type:improvement" \\
      --changed-files "tools/foo.py,docs/bar.md"

## ローカル環境での使い方（gh CLI 有効時）

  python3 tools/discussion_review_trigger.py --pr 42
  python3 tools/discussion_review_trigger.py --pr 42 --dry-run

## gh が全く見つからない環境（Issue #196）

`gh` バイナリ自体が PATH 上に存在しない場合（クラウドで --diff-lines 等を
渡し忘れた・シムも無い等）でも `FileNotFoundError` で落ちず、判定不能を
示すメッセージと非ゼロ終了コードを返す（呼び出し元は明示引数を渡す経路へ
フォールバックできる）。リポジトリ名の解決は `gh repo view` が使えない場合
`tools/repo_slug.py`（`git remote get-url origin` ベース）にフォールバックする。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "tools" / "discussion_specs" / "code_review.json"
TRIGGER_DIFF_LINES = 300
TRIGGER_LABELS = {"type:security", "type:breaking-change"}

# tools/repo_slug.py（gh 不要の owner/repo 解決ヘルパー）を import する。
# スクリプト単体実行（`python3 tools/discussion_review_trigger.py`）でも
# 他所からの import でも解決できるよう、tools/ を明示的に sys.path へ足す。
sys.path.insert(0, str(REPO_ROOT / "tools"))
from repo_slug import resolve_repo_slug  # noqa: E402


def _run_gh(args: list[str]) -> tuple[int, str]:
    """`gh` を安全に呼び出す。バイナリ自体が無ければ (127, "") を返し例外にしない（#196）。"""
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
    except FileNotFoundError:
        return 127, ""
    return result.returncode, result.stdout.strip()


def _get_repo() -> str:
    rc, out = _run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    if rc == 0 and out:
        return out
    # gh 不在 / 失敗時は git remote ベースの解決にフォールバック（#196）
    return resolve_repo_slug()


def _gh(*args: str, repo: str = "") -> tuple[int, str]:
    repo_flag = ["-R", repo] if repo else []
    return _run_gh([*args, *repo_flag])


def get_pr_info_gh(pr_number: int, repo: str) -> dict:
    """gh CLI で PR 情報を取得する（ローカル環境用）。"""
    rc, out = _gh("pr", "view", str(pr_number),
                  "--json", "labels,additions,deletions,headRefName,number",
                  repo=repo)
    if rc != 0:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


def get_changed_files_gh(pr_number: int, repo: str) -> list[str]:
    """gh CLI で変更ファイル一覧を取得する（ローカル環境用）。"""
    rc, out = _gh("pr", "diff", str(pr_number), "--name-only", repo=repo)
    if rc != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def should_trigger(diff_lines: int, labels: set[str]) -> tuple[bool, str]:
    matched = labels & TRIGGER_LABELS
    if matched:
        return True, f"ラベル {sorted(matched)} 検出"
    if diff_lines >= TRIGGER_DIFF_LINES:
        return True, f"差分 {diff_lines} 行（閾値 {TRIGGER_DIFF_LINES} 行）"
    return False, f"差分 {diff_lines} 行・対象ラベルなし（閾値未達）"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Layer 2 議論型レビュー自動トリガー（Issue #97）",
    )
    parser.add_argument("--pr", type=int, default=None, help="PR 番号")
    parser.add_argument("--dry-run", action="store_true",
                        help="判定のみ・実際にはレビューを実行しない")
    # クラウド環境用: mcp__github__pull_request_read で取得した値を直接渡す
    parser.add_argument("--diff-lines", type=int, default=None,
                        help="差分行数（追加+削除）。省略時は gh CLI で取得を試みる")
    parser.add_argument("--labels", default="",
                        help="カンマ区切りのラベル名一覧。省略時は gh CLI で取得を試みる")
    parser.add_argument("--changed-files", default="",
                        help="カンマ区切りの変更ファイルパス一覧。省略時は gh CLI で取得を試みる")
    parser.add_argument("--legacy", action="store_true",
                        help="旧経路（run_discussion_review.py = claude -p）を直接起動する（フォールバック用）")
    parser.add_argument("--self-test", action="store_true",
                        help="判定ロジック・gh 不在時のフォールバックを検証して終了する")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    if args.pr is None:
        parser.error("--pr は必須です（--self-test を除く）")

    # 引数で直接提供された場合はそれを使う（クラウド環境）
    if args.diff_lines is not None:
        diff_lines = args.diff_lines
        labels = {la.strip() for la in args.labels.split(",") if la.strip()}
        changed_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]
    else:
        # gh CLI で取得を試みる（ローカル環境）
        repo = _get_repo()
        pr_info = get_pr_info_gh(args.pr, repo)
        if not pr_info:
            print(
                f"⚠️ PR #{args.pr} の情報を取得できませんでした。\n"
                "クラウド環境では --diff-lines / --labels / --changed-files を指定してください。",
                file=sys.stderr,
            )
            sys.exit(1)
        diff_lines = pr_info.get("additions", 0) + pr_info.get("deletions", 0)
        labels = {la["name"] for la in pr_info.get("labels", [])}
        changed_files = get_changed_files_gh(args.pr, repo)

    trigger, reason = should_trigger(diff_lines, labels)
    if not trigger:
        print(f"ℹ️ Layer 2 レビュー不要: {reason}")
        sys.exit(0)

    # 実行プラン JSON（stdout）と混ざらないよう、進捗ログは stderr へ出す
    print(f"🔍 Layer 2 レビュー起動: {reason}", file=sys.stderr)

    if args.dry_run:
        print("(dry-run: 実行しません)")
        sys.exit(0)

    # 変更ファイルのうちリポジトリに存在するものだけターゲットに含める
    existing = [f for f in changed_files if (REPO_ROOT / f).exists()]
    targets = ",".join(existing) if existing else ""

    if not args.legacy:
        # ネイティブ経路（既定・Issue #193）: 実行プランを出力し、呼び出し元エージェントが
        # discussion-review スキル（ネイティブ Agent Teams）でこのプランを実行する。
        plan = {
            "action": "run_native_discussion_review",
            "skill": "discussion-review",
            "id": f"pr-{args.pr}",
            "spec": str(SPEC_PATH),
            "targets": existing,
            "rounds": 2,
            "reason": reason,
            "fallback_command": (
                f"python3 tools/discussion_review_trigger.py --pr {args.pr} "
                f"--diff-lines {diff_lines} --labels \"{','.join(sorted(labels))}\" "
                f"--changed-files \"{','.join(changed_files)}\" --legacy"
            ),
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        print("▶ 上記プランに従い discussion-review スキル（ネイティブ）で Layer 2 を実行してください。",
              file=sys.stderr)
        sys.exit(0)

    # --legacy: 旧経路（claude -p 駆動）をサブプロセス起動（フォールバック）
    target_args = ["--targets", targets] if targets else []
    rc = subprocess.call(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "run_discussion_review.py"),
            "--id", f"pr-{args.pr}",
            "--spec", str(SPEC_PATH),
            *target_args,
            "--rounds", "2",
        ],
        cwd=str(REPO_ROOT),
    )

    if rc != 0:
        print(
            f"⚠️ Layer 2 レビュー失敗（exit {rc}）。"
            "Layer 1 / Layer 3 レビューで継続します。",
            file=sys.stderr,
        )
        sys.exit(rc)

    print("✅ Layer 2 レビュー完了")


def _self_test() -> None:
    """判定ロジックと gh 不在時のフォールバックを検証する（Issue #196）。"""

    # --- 1. should_trigger の判定ロジック（閾値・ラベル） ---
    # 失敗経路1: 閾値未満 かつ 対象ラベルなし → 起動しない
    trig, _ = should_trigger(299, set())
    assert trig is False, "diff=299・ラベルなしは起動しないはず"

    # 失敗経路2: 閾値ちょうど（境界値） → 起動する
    trig, reason = should_trigger(300, set())
    assert trig is True and "300" in reason, "diff=300（閾値ちょうど）は起動するはず"

    # 失敗経路3: 閾値超過 → 起動する
    trig, _ = should_trigger(9999, set())
    assert trig is True

    # 失敗経路4: diff=0 でも対象ラベルがあれば起動する（ラベル優先）
    trig, reason = should_trigger(0, {"type:security"})
    assert trig is True and "security" in reason

    trig, _ = should_trigger(0, {"type:breaking-change"})
    assert trig is True

    # 失敗経路5: 非対象ラベル（type:bug 等）だけでは起動しない
    trig, _ = should_trigger(10, {"type:bug", "type:improvement"})
    assert trig is False

    # --- 2. gh が全く見つからない環境での挙動（#196 の本丸） ---
    # バリアント A: subprocess.run が FileNotFoundError を送出する（PATH に gh が皆無）
    orig_run = subprocess.run

    def _raise_file_not_found(*_a, **_kw):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'gh'")

    subprocess.run = _raise_file_not_found  # type: ignore[assignment]
    try:
        rc, out = _run_gh(["repo", "view"])
        assert (rc, out) == (127, ""), "_run_gh は例外を握り潰し (127, \"\") を返すはず"

        # _get_repo() は gh 不在時に例外を投げず git remote ベースへフォールバックする
        repo = _get_repo()
        assert isinstance(repo, str) and repo, "_get_repo は gh 不在でも文字列を返すはず"

        # _gh() 経由（get_pr_info_gh / get_changed_files_gh が使う）も同様に握り潰す
        rc2, out2 = _gh("pr", "view", "42", repo="owner/repo")
        assert (rc2, out2) == (127, "")

        # get_pr_info_gh / get_changed_files_gh は例外を外に漏らさず空値を返す
        assert get_pr_info_gh(42, "owner/repo") == {}
        assert get_changed_files_gh(42, "owner/repo") == []
    finally:
        subprocess.run = orig_run  # type: ignore[assignment]

    # バリアント B: gh は PATH にあるが nameWithOwner が空文字（別種の失敗形）
    class _FakeResult:
        returncode = 0
        stdout = "\n"

    subprocess.run = lambda *_a, **_kw: _FakeResult()  # type: ignore[assignment]
    try:
        repo2 = _get_repo()
        assert isinstance(repo2, str) and repo2, "空出力時も resolve_repo_slug へフォールバックするはず"
    finally:
        subprocess.run = orig_run  # type: ignore[assignment]

    # --- 3. エントリポイントから exit code までの到達確認 ---
    # main() を実際に子プロセスとして --pr 付きで起動し、gh を PATH から完全に外しても
    # 非ゼロ例外（FileNotFoundError のトレースバック）を出さず判定結果を返すことを確認する
    # （再帰的な自己呼び出しを避けるため子プロセスは --self-test ではなく通常呼び出しにする）。
    import os

    if os.environ.get("_DRT_SELFTEST_CHILD") != "1":
        env = dict(os.environ)
        # PATH から gh を完全に除去（本物・シムの両方を排除）
        env["PATH"] = "/usr/bin:/bin"
        env["_DRT_SELFTEST_CHILD"] = "1"
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--pr", "999", "--diff-lines", "10", "--labels", "type:bug", "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env, timeout=30,
        )
        assert result.returncode == 0, (
            f"gh 不在環境での --pr 実行が非ゼロ終了: rc={result.returncode}\n{result.stderr}"
        )
        assert "FileNotFoundError" not in result.stderr, (
            f"gh 不在環境で FileNotFoundError が漏れている:\n{result.stderr}"
        )

        # 明示引数を渡さない fallback 経路（旧: _get_repo → gh pr view）も
        # FileNotFoundError を漏らさず、判定不能メッセージ + 非ゼロ終了で応答することを確認する
        result2 = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--pr", "999"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env, timeout=30,
        )
        assert result2.returncode != 0, "gh も引数もない場合は非ゼロ終了で判定不能を示すはず"
        assert "FileNotFoundError" not in result2.stderr, (
            f"引数なし fallback 経路で FileNotFoundError が漏れている:\n{result2.stderr}"
        )

    print("OK: discussion_review_trigger self-test passed")


if __name__ == "__main__":
    main()
