#!/usr/bin/env python3
"""check_lp_publish_drift.py — `main` の `site/` と `gh-pages` ブランチのルートのドリフトを機械検知する
（読み取り専用・fail-closed）。

【背景】Issue #996（#372 の分割 1/4）。`site/README.md` の手順により `main` の `site/` ツリーは
`gh-pages` ブランチのルートへそのままコピーして push する運用だが、それが行われたかを確認する
検査が存在しなかった（`tools/` に `gh-pages` を見るスクリプトが無く、`check_publish_drift.py` /
`check_prod_drift.py` も LP を対象にしない）。同期漏れが起きても現状は沈黙する。

【比較方法】
`main`（既定は `origin/main`）の `site/` ディレクトリの git tree オブジェクトハッシュと、
`gh-pages` ブランチのルート tree オブジェクトハッシュを突き合わせる。`site/README.md` の同期手順
（`git rev-parse HEAD:site` をそのまま `git commit-tree` の tree として使い `gh-pages` へ push する）
と同じ単位で比較するため、**tree ハッシュが完全一致すれば内容が完全に一致している**（コミット履歴・
コミットメッセージの違いは無視してよい。ここが `check_prod_drift.py` の SHA タグ比較と違う点で、
LP は「デプロイ」という別の概念を経由せず git オブジェクトとして直接コピーされるため、コミットの
同一性ではなく tree の同一性で判定できる）。

【終了コード（fail-closed・tools/check_prod_drift.py の規約を踏襲・docs/rules/check-tool-design-rules.md §1）】
  0 = 乖離なし（tree ハッシュが完全一致）
  1 = 乖離あり（tree ハッシュが不一致）
  2 = 判定不能（`origin/main` / `gh-pages` の fetch 失敗・`site/` パス解決失敗・
      `gh-pages` ブランチ自体が存在しない 等）。呼び出し側はこの場合「乖離なし」として
      扱ってはならない（フェイルオープン禁止）

【呼び出し元（本判定・`--self-test` とも配線・Issue #996）】
  🔴 本判定は `tools/run_checks.sh` に配線する（区分 (a)・`check-tool-design-rules.md` §5.1）。
  `main` ブランチと同一 origin への `git fetch` は、セッションが日常的に push/PR 作成で使う
  経路であり `check_prod_drift.py`（Cloudflare API 認証が要る）とは事情が異なるため、
  本番疎通系検査と同列に self-test だけへ限定する理由が無い。

  ただし fetch 失敗（オフライン環境・権限不足等）は exit 2（判定不能）で fail-closed に倒すため、
  ネットワーク不通の環境で PR が赤くなった場合はその旨を `run_checks.sh` の出力から読み取れる。

【禁止事項】本スクリプトは読み取り専用の git コマンドのみを実行する。`git push` は一切呼ばない。

日時の扱い: `docs/rules/datetime-rules.md` の SSOT に従い、表示・記録用の `checked_at` は JST。
git の内部比較（tree ハッシュ文字列比較）はタイムゾーンに依存しない。

使い方:
    python3 tools/check_lp_publish_drift.py
    python3 tools/check_lp_publish_drift.py --json
    python3 tools/check_lp_publish_drift.py --ref origin/main   # main 側の比較対象 ref（既定値）
    python3 tools/check_lp_publish_drift.py --self-test         # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_secrets import mask_text  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))

SITE_SUBPATH = "site"
GH_PAGES_REMOTE_REF = "refs/remotes/origin/gh-pages"
MAIN_REMOTE_REF_NAME = "main"

# 既存モジュール確認（agent-team-summary.md #474 項目0）:
# - tools/repo_slug.py — GitHub REST を呼ばないため不使用（該当なし）
# - tools/github_rest.py — 本ツールは GitHub REST を一切呼ばない（git コマンドのみ）ため不使用
# - tools/mask_secrets.py — 使用する（下記 import）。エラーメッセージの秘匿値マスクに利用
# - tools/git_diff_utils.py — `run_git_or_raise()` を検討したが、(a) 同関数の docstring が
#   「check_agent_diff_claim.py 専用の性質」と明記し例外送出方式であること、(b) 本ツールは
#   check_prod_drift.py と同じ「tuple(ok, out) を返し fail-closed の exit 2 へ倒す」設計に
#   揃える必要があること、の 2 点から不採用。ただしパス正規化系（normalize_*）は本ツールの
#   スコープ（tree ハッシュの単純突合）に該当しないため使わない。


# ──────────────────────────────────────────────
# runner 型（実 subprocess.run 互換。self-test で差し替え可能にする・#710）
# ──────────────────────────────────────────────

GitRunner = Callable[..., subprocess.CompletedProcess]


def _default_runner(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """実 git を呼ぶ既定 runner。self-test では FakeGitRunner に差し替える。"""
    return subprocess.run(args, **kwargs)


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械比較には使わない（datetime-rules.md）。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


# ──────────────────────────────────────────────
# git 実行ラッパー（読み取り専用コマンドのみ）
# ──────────────────────────────────────────────


def run_git(args: list[str], *, runner: GitRunner = _default_runner, timeout: int = 60) -> tuple[bool, str]:
    """`git <args...>` を実行し (成功したか, stdout または理由文字列) を返す。

    失敗時の理由は Issue / PR コメントへ転記されうるため mask_text() で秘匿値を落としてから返す。
    """
    cmd = ["git", *args]
    try:
        result = runner(cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT)
    except subprocess.TimeoutExpired:
        return False, f"コマンドがタイムアウトしました（{timeout}秒）: {' '.join(cmd)}"
    except OSError as e:
        # FileNotFoundError（git 不在）も PermissionError も OSError のサブクラス。
        # ここで捕まえ損ねると exit 2（fail-closed）を経由せず Python 既定の非 0 終了で
        # 落ちる（check_prod_drift.py と同じ理由）。
        return False, f"コマンドを実行できません（{type(e).__name__}: {e}）: {' '.join(cmd)}"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return False, mask_text(err) or f"コマンド実行失敗（exit {result.returncode}）: {' '.join(cmd)}"
    return True, result.stdout


# ──────────────────────────────────────────────
# 取得系（実 I/O。純関数の decide() からは分離する — check_prod_drift.py と同じ理由で
# self-test から実 I/O を排除しつつ、判定ロジックだけを検証できるようにする）
# ──────────────────────────────────────────────


def fetch_refs(
    *, main_ref_name: str = MAIN_REMOTE_REF_NAME, runner: GitRunner = _default_runner,
) -> tuple[bool, str | None]:
    """`origin` から `main` と `gh-pages` の両方を明示 refspec で取得する（G-1: session-safety-rules.md）。

    1 コマンドにまとめる（2 回に分けると片方だけ成功した状態を扱う必要が増え、判定不能への
    倒し方が複雑になるため）。失敗経路: 認証エラー・ネットワーク不通・`gh-pages` ブランチが
    そもそも存在しない（この場合も git fetch 自体は該当 refspec だけ解決できず非ゼロを返す）。
    """
    ok, out = run_git(
        [
            "fetch", "origin",
            f"+{main_ref_name}:refs/remotes/origin/{main_ref_name}",
            "+gh-pages:refs/remotes/origin/gh-pages",
        ],
        runner=runner,
    )
    if not ok:
        return False, out
    return True, None


def resolve_main_site_tree(ref: str, *, runner: GitRunner = _default_runner) -> tuple[str | None, str | None]:
    """`{ref}:site` の tree オブジェクトハッシュを解決する。`site/` が存在しない場合も失敗として返す。"""
    ok, out = run_git(["rev-parse", f"{ref}:{SITE_SUBPATH}"], runner=runner)
    if not ok:
        return None, f"main 側の site/ tree 解決に失敗しました（{out}）"
    sha = out.strip()
    if not sha:
        return None, "main 側の site/ tree 解決結果が空でした"
    return sha, None


def resolve_gh_pages_tree(*, runner: GitRunner = _default_runner) -> tuple[str | None, str | None]:
    """`gh-pages` ブランチのルート tree オブジェクトハッシュを解決する。"""
    ok, out = run_git(["rev-parse", f"{GH_PAGES_REMOTE_REF}^{{tree}}"], runner=runner)
    if not ok:
        return None, f"gh-pages 側の root tree 解決に失敗しました（{out}）"
    sha = out.strip()
    if not sha:
        return None, "gh-pages 側の root tree 解決結果が空でした"
    return sha, None


# ──────────────────────────────────────────────
# 判定ロジック（純関数・subprocess 非依存 = --self-test の対象）
# ──────────────────────────────────────────────


def decide(main_tree: str, gh_pages_tree: str) -> dict:
    """1 回分の判定を行う純関数。tree ハッシュの完全一致だけで判定する（単純な文字列比較）。"""
    a = main_tree.strip().lower()
    b = gh_pages_tree.strip().lower()
    drifted = a != b
    if drifted:
        reason = "main の site/ tree ハッシュと gh-pages のルート tree ハッシュが一致しません"
    else:
        reason = "main の site/ tree ハッシュと gh-pages のルート tree ハッシュが完全一致しています"
    return {"drifted": drifted, "reason": reason, "main_site_tree": a, "gh_pages_tree": b}


def exit_code_for(drifted: bool | None) -> int:
    """判定結果を終了コードへ写像する唯一の関数（0/1/2 のマッピングを一元化）。

    drifted=None は「判定不能」を表し fail-closed で 2 を返す（0 を既定値にしない）。
    """
    if drifted is None:
        return 2
    return 1 if drifted else 0


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


class FakeGitRunner:
    """`git <args>` の呼び出しを記録し、あらかじめ登録した応答を返す fake runner（#710）。

    登録は `register(prefix_tuple, returncode, stdout, stderr)` で行い、実際の呼び出し引数の
    先頭が prefix_tuple と一致する最初のエントリを使う（fetch のように後続引数が長い呼び出しにも
    対応するため完全一致ではなく前方一致にしてある）。全呼び出しの完全な argv を `self.calls` に
    記録するので、self-test 側で「意図したサブコマンドが呼ばれているか」を assert できる。
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._responses: list[tuple[tuple[str, ...], int, str, str]] = []

    def register(self, prefix: tuple[str, ...], returncode: int, stdout: str = "", stderr: str = "") -> None:
        self._responses.append((prefix, returncode, stdout, stderr))

    def __call__(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(list(cmd))
        for prefix, returncode, stdout, stderr in self._responses:
            if tuple(cmd[: len(prefix)]) == prefix:
                return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
        # 未登録の呼び出しは「想定外のコマンドが呼ばれた」ことを明示するため非ゼロで返す
        # （黙って成功扱いにすると、実装が余計なコマンドを呼んでいても self-test が気づけない）。
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=f"未登録の呼び出し: {cmd!r}")


TREE_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
TREE_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _self_test_decide_no_drift() -> list[str]:
    failures = []
    result = decide(TREE_A, TREE_A)
    if result["drifted"] is not False:
        failures.append(f"tree 一致なのに drifted=True: {result}")
    if exit_code_for(result["drifted"]) != 0:
        failures.append("exit_code_for: drifted=False は exit 0 を期待")
    return failures


def _self_test_decide_no_drift_case_insensitive() -> list[str]:
    """症状バリアント: 大文字小文字表記ゆれ（`git rev-parse` は通常小文字だが、防御的に検証する）。"""
    failures = []
    result = decide(TREE_A.upper(), TREE_A)
    if result["drifted"] is not False:
        failures.append(f"大文字小文字違いのみで drifted=True になっている: {result}")
    return failures


def _self_test_decide_drift() -> list[str]:
    failures = []
    result = decide(TREE_A, TREE_B)
    if result["drifted"] is not True:
        failures.append(f"tree 不一致なのに drifted=False: {result}")
    if exit_code_for(result["drifted"]) != 1:
        failures.append("exit_code_for: drifted=True は exit 1 を期待")
    return failures


def _self_test_decide_drift_prefix_collision() -> list[str]:
    """症状バリアント: 前方一致するが別オブジェクトの tree ハッシュ（完全一致以外を等しいと誤判定しないこと）。"""
    failures = []
    prefix_a = TREE_A[:30] + "1111111111"
    prefix_b = TREE_A[:30] + "2222222222"
    result = decide(prefix_a, prefix_b)
    if result["drifted"] is not True:
        failures.append(f"前方が一致するだけの別ハッシュを同一と誤判定: {result}")
    return failures


def _self_test_indeterminate_exit_code() -> list[str]:
    failures = []
    if exit_code_for(None) != 2:
        failures.append("exit_code_for: drifted=None（判定不能）は exit 2（fail-closed）を期待")
    return failures


def _self_test_fetch_refs_success() -> list[str]:
    """fake runner の argv を検証する（#710 必須項目）: fetch が意図した refspec で 1 回だけ呼ばれる。"""
    failures = []
    fake = FakeGitRunner()
    fake.register(("git", "fetch", "origin"), 0, stdout="")
    ok, err = fetch_refs(runner=fake)
    if not ok or err is not None:
        failures.append(f"fetch_refs が成功ケースで失敗を返した: ok={ok} err={err!r}")
    if len(fake.calls) != 1:
        failures.append(f"fetch は 1 回だけ呼ばれるべき: calls={fake.calls!r}")
    else:
        call = fake.calls[0]
        if call[:3] != ["git", "fetch", "origin"]:
            failures.append(f"fetch の先頭引数が想定外: {call!r}")
        if "+main:refs/remotes/origin/main" not in call:
            failures.append(f"main の明示 refspec が argv に含まれていない: {call!r}")
        if "+gh-pages:refs/remotes/origin/gh-pages" not in call:
            failures.append(f"gh-pages の明示 refspec が argv に含まれていない: {call!r}")
    return failures


def _self_test_fetch_refs_failure() -> list[str]:
    """gh-pages 取得不能ケース（ネットワーク不通・権限不足・ブランチ不在等を fetch の非ゼロ終了で代表させる）。"""
    failures = []
    fake = FakeGitRunner()
    fake.register(("git", "fetch", "origin"), 128, stderr="fatal: unable to access 'origin': Could not resolve host")
    ok, err = fetch_refs(runner=fake)
    if ok or not err:
        failures.append(f"fetch 失敗を成功として扱っている: ok={ok} err={err!r}")
    return failures


def _self_test_resolve_main_site_tree() -> list[str]:
    failures = []
    fake = FakeGitRunner()
    fake.register(("git", "rev-parse", "origin/main:site"), 0, stdout=f"{TREE_A}\n")
    sha, err = resolve_main_site_tree("origin/main", runner=fake)
    if err is not None or sha != TREE_A:
        failures.append(f"main site tree の正常解決に失敗: sha={sha!r} err={err!r}")

    # 症状バリアント: site/ パスが main 上に存在しない（削除・リネーム）→ 判定不能へ倒す
    fake2 = FakeGitRunner()
    fake2.register(
        ("git", "rev-parse", "origin/main:site"), 128,
        stderr="fatal: path 'site' does not exist in 'origin/main'",
    )
    sha2, err2 = resolve_main_site_tree("origin/main", runner=fake2)
    if sha2 is not None or not err2:
        failures.append(f"main 上に site/ が無いケースを判定不能にしていない: sha={sha2!r} err={err2!r}")
    return failures


def _self_test_resolve_gh_pages_tree() -> list[str]:
    failures = []
    fake = FakeGitRunner()
    fake.register(("git", "rev-parse", "refs/remotes/origin/gh-pages^{tree}"), 0, stdout=f"{TREE_B}\n")
    sha, err = resolve_gh_pages_tree(runner=fake)
    if err is not None or sha != TREE_B:
        failures.append(f"gh-pages tree の正常解決に失敗: sha={sha!r} err={err!r}")

    # 症状バリアント: fetch は成功したが gh-pages ブランチ自体が存在しない（一度も公開されていない）
    fake2 = FakeGitRunner()
    fake2.register(
        ("git", "rev-parse", "refs/remotes/origin/gh-pages^{tree}"), 128,
        stderr="fatal: ambiguous argument 'refs/remotes/origin/gh-pages^{tree}': unknown revision",
    )
    sha2, err2 = resolve_gh_pages_tree(runner=fake2)
    if sha2 is not None or not err2:
        failures.append(f"gh-pages ブランチ不在ケースを判定不能にしていない: sha={sha2!r} err={err2!r}")
    return failures


def _self_test_main_entrypoint_no_drift() -> list[str]:
    """本番の主コードパス（変異対象）: CLI エントリポイント main() から exit code までを実際に貫通させる。"""
    failures = []
    fake = FakeGitRunner()
    fake.register(("git", "fetch", "origin"), 0)
    fake.register(("git", "rev-parse", "origin/main:site"), 0, stdout=f"{TREE_A}\n")
    fake.register(("git", "rev-parse", "refs/remotes/origin/gh-pages^{tree}"), 0, stdout=f"{TREE_A}\n")
    code = _run_cli(["--json"], runner=fake)
    if code != 0:
        failures.append(f"main() 経由の乖離なしケースで exit {code}（期待 0）")
    return failures


def _self_test_main_entrypoint_drift() -> list[str]:
    failures = []
    fake = FakeGitRunner()
    fake.register(("git", "fetch", "origin"), 0)
    fake.register(("git", "rev-parse", "origin/main:site"), 0, stdout=f"{TREE_A}\n")
    fake.register(("git", "rev-parse", "refs/remotes/origin/gh-pages^{tree}"), 0, stdout=f"{TREE_B}\n")
    code = _run_cli(["--json"], runner=fake)
    if code != 1:
        failures.append(f"main() 経由の乖離ありケースで exit {code}（期待 1）")
    return failures


def _self_test_main_entrypoint_unreachable_gh_pages() -> list[str]:
    """本番の主コードパス（gh-pages 取得不能）: fetch 失敗が main() の exit code へ正しく反映される。

    🔴 fetch 失敗後の rev-parse 呼び出しをあえて「成功すれば乖離なし（exit 0）を返せる」応答で
    登録しておく。こうしないと、fetch 失敗後に early return せず後続処理へ進んでも、後続の
    rev-parse が単に「未登録の呼び出し」でエラーになり結果的に exit 2 のまま変わらず、
    fail-closed の early return が抜け落ちる変異を self-test が検知できない（#474 項目4の
    「壊す前に変異が本当に当たったか」を、ここでは逆に「壊れていたら本当に違う結果になるか」で担保する）。
    """
    failures = []
    fake = FakeGitRunner()
    fake.register(("git", "fetch", "origin"), 128, stderr="fatal: could not read Username")
    # early return が抜け落ちても後続が完走してしまうように、あえて有効な応答を登録しておく。
    fake.register(("git", "rev-parse", "origin/main:site"), 0, stdout=f"{TREE_A}\n")
    fake.register(("git", "rev-parse", "refs/remotes/origin/gh-pages^{tree}"), 0, stdout=f"{TREE_A}\n")
    code = _run_cli(["--json"], runner=fake)
    if code != 2:
        failures.append(f"main() 経由の gh-pages 取得不能ケースで exit {code}（期待 2・fail-closed）")
    return failures


def run_self_test() -> int:
    groups = [
        ("乖離なし（tree 完全一致）", _self_test_decide_no_drift),
        ("乖離なし（大文字小文字ゆれを無視）", _self_test_decide_no_drift_case_insensitive),
        ("乖離あり（tree 不一致）", _self_test_decide_drift),
        ("乖離あり（前方一致だけの別ハッシュを誤同一視しない）", _self_test_decide_drift_prefix_collision),
        ("判定不能 → exit 2（fail-closed）", _self_test_indeterminate_exit_code),
        ("fetch 成功時の argv 検証（#710）", _self_test_fetch_refs_success),
        ("gh-pages 取得不能（fetch 失敗）", _self_test_fetch_refs_failure),
        ("main 側 site/ tree 解決（正常 + パス不在）", _self_test_resolve_main_site_tree),
        ("gh-pages 側 tree 解決（正常 + ブランチ不在）", _self_test_resolve_gh_pages_tree),
        ("main() 経由 乖離なし（本番の主コードパス）", _self_test_main_entrypoint_no_drift),
        ("main() 経由 乖離あり（本番の主コードパス）", _self_test_main_entrypoint_drift),
        ("main() 経由 gh-pages 取得不能（本番の主コードパス）", _self_test_main_entrypoint_unreachable_gh_pages),
    ]
    failed_groups = 0
    total_failures = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed_groups += 1
            total_failures += len(failures)
            for f in failures:
                print(f"FAIL[{name}]: {f}")

    if total_failures:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed_groups} グループ失敗 "
              f"({total_failures} 件の不一致)")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def _emit_error(message: str, as_json: bool) -> None:
    message = mask_text(message) or message
    if as_json:
        payload = {"drifted": None, "error": message, "checked_at": now_jst_str()}
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"ERROR: 判定不能: {message}", file=sys.stderr)


def _run_cli(argv: list[str], *, runner: GitRunner = _default_runner) -> int:
    """`main()` の実体。テスト容易性のため `runner` を注入可能にし、終了コードを返り値にする
    （`main()` は本関数を呼んで `sys.exit()` するだけの薄いラッパー。self-test は本関数を
    直接呼び、`main()` を経由しない内部関数の直呼びでは終わらせない・#710）。
    """
    parser = argparse.ArgumentParser(
        description="main の site/ と gh-pages ブランチのルートのドリフトを機械検知する"
                     "（読み取り専用・fail-closed）。0=乖離なし / 1=乖離あり / 2=判定不能。",
    )
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument(
        "--ref", default="origin/main",
        help="main 側の比較対象 ref（既定: origin/main）。site/ ディレクトリを含む ref を指定する。",
    )
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    ok, ferr = fetch_refs(runner=runner)
    if not ok:
        _emit_error(f"main / gh-pages の取得に失敗しました（{ferr}）", args.json)
        return 2

    main_tree, merr = resolve_main_site_tree(args.ref, runner=runner)
    if merr is not None:
        _emit_error(merr, args.json)
        return 2

    gh_pages_tree, gerr = resolve_gh_pages_tree(runner=runner)
    if gerr is not None:
        _emit_error(gerr, args.json)
        return 2

    result = decide(main_tree, gh_pages_tree)
    result["ref"] = args.ref
    result["checked_at"] = now_jst_str()

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["drifted"]:
            print(f"乖離あり: {result['reason']}")
            print(f"  main（{args.ref}）site/ tree: {result['main_site_tree']}")
            print(f"  gh-pages root tree:          {result['gh_pages_tree']}")
        else:
            print(f"乖離なし: {result['reason']}")

    return exit_code_for(result["drifted"])


def main() -> None:
    sys.exit(_run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
