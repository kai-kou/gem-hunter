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

## 終了コード（`docs/rules/check-tool-design-rules.md` §1）

  0 … 判定が成立した（Layer 2 不要、または起動プランを出力した / --legacy 実行が成功した）
  1 … 実行系の失敗（PR 情報を取得できない / --legacy 実行が失敗した）
  2 … 判定不能（spec が不在・壊れている・最小構造を満たさない）

⚠️ **標準の 3 値からの逸脱と、その理由**: 本ツールは違反を数える検査器ではなく「Layer 2 を起動すべきか」
を判定して実行プランを出す **判定器** なので、標準の 1（= 違反あり）に対応する状態を持たない。
そこで 1 を「実行系の失敗」に割り当て、**判定そのものが成立しない状態はすべて 2 に寄せる**
（呼び出し元は「2 なら Layer 2 を実施済みとみなさない」の 1 点だけを見ればよい）。入力不足
（`--diff-lines` 等の渡し忘れ）を 1 に置くのは、それが判定材料の不在ではなく **呼び出し方の誤り**
（クラウドでは明示引数が必須）であり、引数を足した再実行で解消するためである。

🔴 **2 を 0 に丸めない**（Issue #881）。トリガー該当時に spec が使えないなら「起動せよ」と
出力してはいけない。判定器が起動を指示し実行系が起動できない状態は fail-open であり、
Layer 2 の実施率が 0% のまま緑を返し続ける原因になった（実測: PR #873 で発覚するまで
`tools/discussion_specs/code_review.json` は一度も存在しなかった）。
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
    """`gh` を安全に呼び出す。起動できなければ (127, "") を返し例外にしない（#196）。

    捕捉対象は `FileNotFoundError` だけでなく `OSError` 全般にする。`gh` が PATH 上に
    あっても実行属性が無い（`PermissionError`）・PATH のエントリがディレクトリを指す
    （`NotADirectoryError`）といった異常構成では別の `OSError` が飛び、片方だけ捕捉すると
    「gh が無い環境でも判定結果を返す」という本関数の目的が崩れるため。
    """
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
    except OSError:
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


# participant の name 規約は **実行系と同一の定義を import して再利用する**（新しいコピーを作らない）。
# 判定器だけが緩いと「判定器は起動せよと言うが実行系（run_discussion_review.py の _check_name /
# discussion_whiteboard.py の _AUTHOR_RE）が拒否する」という #881 と同型の fail-open が別経路で
# 再発する。run_discussion_review.py のトップレベルは定数定義だけで副作用が無いため import して安全。
from run_discussion_review import _NAME_RE as _PARTICIPANT_NAME_RE  # noqa: E402


def validate_spec(spec_path: Path) -> tuple[bool, str]:
    """議論 spec の実在と最小構造を検証する（Issue #881）。

    返り値は `(ok, reason)`。`ok=False` のとき呼び出し元は「起動せよ」と出力せず
    判定不能（exit 2）で終わる（fail-closed・`check-tool-design-rules.md` §1）。

    検証項目は `discussion-review` スキル Step 0 が spec を Read した直後に行うものと同じ
    （participants >= 2・name 規約）。実行系が読んで初めて落ちるのでは判定器の意味が無いため、
    判定器側で先に同じ検証をする。
    """
    if not spec_path.is_file():
        return False, f"spec が存在しません: {spec_path}"
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return False, f"spec を JSON として読めません: {spec_path}（{exc}）"
    except OSError as exc:
        return False, f"spec を読み込めません: {spec_path}（{exc}）"
    if not isinstance(spec, dict):
        return False, f"spec のトップレベルがオブジェクトではありません: {spec_path}"

    participants = spec.get("participants")
    if not isinstance(participants, list) or len(participants) < 2:
        return False, (
            f"participants が 2 名未満です: {spec_path}"
            "（議論型レビューは相互反論が成立しないと意味がない）"
        )
    for i, p in enumerate(participants):
        if not isinstance(p, dict):
            return False, f"participants[{i}] がオブジェクトではありません: {spec_path}"
        name = p.get("name")
        # 🔴 match ではなく fullmatch を使う: Python の `$` は非 MULTILINE でも
        # 「末尾の改行の直前」にマッチするため、match だと "a\n" が通ってしまう。
        if not isinstance(name, str) or not _PARTICIPANT_NAME_RE.fullmatch(name):
            return False, (
                f"participants[{i}].name が name 規約（先頭は英数字・以降は英数字と _- ・"
                f"32 字以内）に反します: {name!r}"
            )
        if not p.get("lens"):
            return False, f"participants[{i}]（{name}）に lens がありません: {spec_path}"

    synthesizer = spec.get("synthesizer")
    if not isinstance(synthesizer, dict) or not synthesizer.get("instruction"):
        return False, f"synthesizer（instruction 付き）がありません: {spec_path}"
    if not spec.get("verdict_schema"):
        return False, f"verdict_schema がありません: {spec_path}"

    return True, f"spec 検証 OK: {spec_path}（participants {len(participants)} 名）"


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
    parser.add_argument("--spec", default=None,
                        help=f"議論 spec JSON のパス（既定: {SPEC_PATH}）。下流リポジトリは自前の spec を指定する")
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

    # 🔴 spec を検証してから「起動」と言う（Issue #881・fail-closed）。
    # dry-run も含めてこの順序を崩さない（「起動する」と報告した後で実行系が spec 不在に
    # 気づく設計だと、判定器の出力を信じた呼び出し元が Layer 2 を実施済みと誤認する）。
    spec_path = Path(args.spec).expanduser() if args.spec else SPEC_PATH
    spec_ok, spec_reason = validate_spec(spec_path)
    if not spec_ok:
        print(
            f"⚠️ Layer 2 判定不能: {spec_reason}\n"
            f"（トリガー条件は満たしています: {reason}）\n"
            "spec を修復するか --spec で有効な spec を指定してください。",
            file=sys.stderr,
        )
        sys.exit(2)

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
            "spec": str(spec_path),
            "targets": existing,
            "rounds": 2,
            "reason": reason,
            "fallback_command": (
                f"python3 tools/discussion_review_trigger.py --pr {args.pr} "
                f"--diff-lines {diff_lines} --labels \"{','.join(sorted(labels))}\" "
                f"--changed-files \"{','.join(changed_files)}\" "
                f"--spec \"{spec_path}\" --legacy"
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
            "--spec", str(spec_path),
            *target_args,
            "--rounds", "2",
        ],
        cwd=str(REPO_ROOT),
    )

    if rc != 0:
        # 🔴 rc をそのまま転送しない。run_discussion_review.py は spec と無関係の理由でも 2 を返すため、
        # 転送すると本ツールの exit 2（= spec が使えない）と意味が混線し、呼び出し元が
        # 「spec を修復せよ」という見当違いの復旧に走る。
        print(
            f"⚠️ Layer 2 レビュー失敗（run_discussion_review.py exit {rc}）。"
            "Layer 1 / Layer 3 レビューで継続します。",
            file=sys.stderr,
        )
        sys.exit(1)

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

    # バリアント B: gh は PATH にあるが nameWithOwner が空文字（別種の失敗形）。
    # 🔴 戻り値が非空であることだけを見ても検証にならない: resolve_repo_slug() の既定
    # placeholder は本リポジトリでは置換済み（"__" を含まない）なので、git remote を
    # 引かずに即座に placeholder を返す。つまり「フォールバックが呼ばれたか」と
    # 「戻り値が非空か」は独立しており、後者は分岐を通らなくても真になる（PR #765 レビュー指摘）。
    # そこで resolve_repo_slug 自体を差し替え、**実際に呼ばれたこと** を確認する。
    class _FakeResult:
        returncode = 0
        stdout = "\n"

    called: list[bool] = []

    def _fake_resolve(*_a, **_kw) -> str:
        called.append(True)
        return "sentinel-owner/sentinel-repo"

    global resolve_repo_slug
    orig_resolve = resolve_repo_slug
    subprocess.run = lambda *_a, **_kw: _FakeResult()  # type: ignore[assignment]
    resolve_repo_slug = _fake_resolve  # type: ignore[assignment]
    try:
        repo2 = _get_repo()
        assert called, "gh の出力が空なら resolve_repo_slug へフォールバックするはず"
        assert repo2 == "sentinel-owner/sentinel-repo", (
            f"フォールバックの戻り値をそのまま返すはず（実際: {repo2!r}）"
        )
    finally:
        subprocess.run = orig_run  # type: ignore[assignment]
        resolve_repo_slug = orig_resolve  # type: ignore[assignment]

    # バリアント C: gh は PATH にあるが実行できない（PermissionError 等の OSError）
    def _raise_permission(*_a, **_kw):
        raise PermissionError("[Errno 13] Permission denied: 'gh'")

    subprocess.run = _raise_permission  # type: ignore[assignment]
    try:
        rc3, out3 = _run_gh(["repo", "view"])
        assert (rc3, out3) == (127, ""), "FileNotFoundError 以外の OSError も握り潰すはず"
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

    # --- 4. spec の実在・構造検証（Issue #881） ---
    # 失敗経路1: spec が存在しない → 判定不能（ok=False）
    ok, why = validate_spec(REPO_ROOT / "tools" / "discussion_specs" / "__absent__.json")
    assert ok is False and "存在しません" in why, f"spec 不在は ok=False のはず（実際: {ok} / {why}）"

    import tempfile

    # 一時ファイルは 1 つのディレクトリにまとめ、self-test の最後に一括削除する
    # （本 self-test は run_checks.sh から毎回走るため、残置すると /tmp に蓄積する）。
    _tmpdir = tempfile.TemporaryDirectory(prefix="drt_selftest_")
    _tmp_seq = [0]

    def _write_spec(obj) -> Path:
        _tmp_seq[0] += 1
        path = Path(_tmpdir.name) / f"spec_{_tmp_seq[0]}.json"
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return path

    valid_participants = [
        {"name": "a", "model": "sonnet", "lens": "x"},
        {"name": "b", "model": "sonnet", "lens": "y"},
    ]
    base = {
        "topic": "t", "brief": "b", "participants": valid_participants,
        "synthesizer": {"name": "lead", "instruction": "i"},
        "verdict_schema": {"findings": []},
    }

    # 失敗経路2: JSON としてパースできない
    bad_path = Path(_tmpdir.name) / "broken.json"
    bad_path.write_text("{ not json", encoding="utf-8")
    ok, why = validate_spec(bad_path)
    assert ok is False and "JSON" in why, f"壊れた JSON は ok=False のはず（実際: {ok} / {why}）"

    # 失敗経路3: participants が 2 名未満（discussion-review SKILL.md Step 0 の検証）
    ok, why = validate_spec(_write_spec({**base, "participants": [valid_participants[0]]}))
    assert ok is False and "participants" in why, f"participants 1 名は ok=False のはず（実際: {ok} / {why}）"

    # 失敗経路4: name 規約違反（英数字と _- 以外 / 32 字超）
    ok, _ = validate_spec(_write_spec(
        {**base, "participants": [{"name": "a b", "model": "sonnet", "lens": "x"}, valid_participants[1]]}))
    assert ok is False, "空白を含む name は ok=False のはず"
    ok, _ = validate_spec(_write_spec(
        {**base, "participants": [{"name": "a" * 33, "model": "sonnet", "lens": "x"}, valid_participants[1]]}))
    assert ok is False, "33 字の name は ok=False のはず"

    # 失敗経路5: synthesizer / verdict_schema の欠落
    for missing in ("synthesizer", "verdict_schema"):
        obj = {k: v for k, v in base.items() if k != missing}
        ok, why = validate_spec(_write_spec(obj))
        assert ok is False and missing in why, f"{missing} 欠落は ok=False のはず（実際: {ok} / {why}）"

    # 正常系: リポジトリ同梱の本物の spec が検証を通る（これ自体が #881 の回帰テスト）
    ok, why = validate_spec(SPEC_PATH)
    assert ok is True, f"同梱 spec が検証を通らない: {why}"

    # 失敗経路6: name の「境界の外側」の負ケース（#750・Layer 1 指摘）
    # 末尾改行: Python の `$` は非 MULTILINE でも末尾改行の直前にマッチするため、
    # `match` + `$` だと "a\n" が通る。fullmatch でこの抜け道を塞いでいることを固定する。
    ok, _ = validate_spec(_write_spec(
        {**base, "participants": [{"name": "a\n", "model": "sonnet", "lens": "x"}, valid_participants[1]]}))
    assert ok is False, "末尾に改行を含む name は ok=False のはず（$ ではなく fullmatch で弾く）"

    # 先頭が英数字でない name: 実行系（run_discussion_review.py / discussion_whiteboard.py）が
    # 拒否するため、判定器が通すと #881 と同型の「判定器は起動せよと言うが実行系が落ちる」になる。
    for bad_name in ("-alice", "_bob"):
        ok, _ = validate_spec(_write_spec(
            {**base, "participants": [{"name": bad_name, "model": "sonnet", "lens": "x"},
                                      valid_participants[1]]}))
        assert ok is False, f"先頭が英数字でない name（{bad_name}）は ok=False のはず"

    # 失敗経路7: participants の要素が dict でない（例外を漏らさず ok=False を返すこと）
    for bad_participant in ("alice", None, 42, ["alice"]):
        ok, _ = validate_spec(_write_spec({**base, "participants": [bad_participant, valid_participants[1]]}))
        assert ok is False, f"participants に非オブジェクト（{bad_participant!r}）があれば ok=False のはず"

    # --- 5. 本番の入口（main()）から exit code までの到達確認（#686） ---
    # 判定ロジックだけを直接呼ぶテストでは、main() が validate_spec を呼び忘れても緑になる。
    # 起動条件を満たす引数（差分 400 行）で子プロセスを起動し、spec 不在時に
    # 「起動プラン」を出さず非ゼロで終わることを本番経路で確認する。
    if os.environ.get("_DRT_SELFTEST_CHILD") != "1":
        env2 = dict(os.environ)
        env2["_DRT_SELFTEST_CHILD"] = "1"
        blocked = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--pr", "999", "--diff-lines", "400", "--labels", "type:bug",
             "--spec", str(REPO_ROOT / "tools" / "discussion_specs" / "__absent__.json")],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env2, timeout=30,
        )
        assert blocked.returncode == 2, (
            f"spec 不在は判定不能 exit 2 のはず（実際: {blocked.returncode}）\n{blocked.stderr}"
        )
        assert "run_native_discussion_review" not in blocked.stdout, (
            f"spec 不在なのに起動プランを出力している:\n{blocked.stdout}"
        )
        assert "Layer 2 レビュー起動" not in blocked.stderr, (
            f"spec 不在なのに「起動」と報告している:\n{blocked.stderr}"
        )

        # --dry-run でも同じ（「起動する」と言ってから spec 不在が判明する順序にしない）
        blocked_dry = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--pr", "999", "--diff-lines", "400", "--dry-run",
             "--spec", str(REPO_ROOT / "tools" / "discussion_specs" / "__absent__.json")],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env2, timeout=30,
        )
        assert blocked_dry.returncode == 2, (
            f"--dry-run でも spec 不在は exit 2 のはず（実際: {blocked_dry.returncode}）"
        )

        # 正常系: 同梱 spec なら起動プランを出して exit 0（検証が常に落ちる実装への変異を検知する）
        okrun = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--pr", "999", "--diff-lines", "400", "--labels", "type:bug"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env2, timeout=30,
        )
        assert okrun.returncode == 0, (
            f"同梱 spec がある正常系は exit 0 のはず（実際: {okrun.returncode}）\n{okrun.stderr}"
        )
        assert "run_native_discussion_review" in okrun.stdout, (
            f"正常系で起動プランが出ていない:\n{okrun.stdout}"
        )

        # --spec で指定した spec が fallback_command にも引き継がれること。
        # 引き継がれないと、検証・提示した spec とフォールバック実行で使う spec が食い違い、
        # 別の観点セットで「実行済み」になる（fail-open・Layer 1 指摘）。
        alt_spec = REPO_ROOT / "tools" / "discussion_specs" / "code_review.json"
        okspec = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--pr", "999", "--diff-lines", "400", "--spec", str(alt_spec)],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env2, timeout=30,
        )
        assert okspec.returncode == 0, f"--spec 指定の正常系は exit 0 のはず（実際: {okspec.returncode}）"
        plan = json.loads(okspec.stdout)
        assert plan["spec"] == str(alt_spec), f"plan.spec が --spec を反映していない: {plan['spec']}"
        assert f'--spec "{alt_spec}"' in plan["fallback_command"], (
            f"fallback_command に --spec が引き継がれていない:\n{plan['fallback_command']}"
        )

    _tmpdir.cleanup()

    print("OK: discussion_review_trigger self-test passed")


if __name__ == "__main__":
    main()
