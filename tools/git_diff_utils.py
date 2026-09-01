#!/usr/bin/env python3
"""git_diff_utils.py — 「変更ファイル一覧を git から取る」ロジックの共有ヘルパー（Issue #195）

## なぜ必要か

`tools/self_review_check.py` / `tools/check_architecture_boundaries.py` /
`tools/check_cjk_markdown.py` / `tools/check_agent_diff_claim.py` の 4 箇所に、ほぼ同じ
「git diff / git status から変更ファイル一覧を集める」ロジックが独立に実装され、揺れ
（cached を見る/見ない・untracked を含める/含めない・存在チェックの有無・ソート有無）が
生まれていた。本モジュールへ集約し、各ツールは薄いラッパーとして既存シグネチャ・既存挙動を
維持する（呼び出し元の既存挙動は変えない・#195 完了条件 2）。

**例外（意図的な挙動変更・2 件）**:
- `check_architecture_boundaries.py` の `changed_files()` は base range の解決を
  `origin/main` 固定 → `default_branch()`（`symbolic-ref` 解決・失敗時 `main` フォールバック）へ
  変更した。`origin/HEAD` が未設定、または `main` を指す環境（本リポジトリの現状）でのみ
  従来と同一結果になる（他 3 ツールは元々 dynamic 解決だったため、これに合わせて統一した・
  #195 指摘4/6/7・詳細は同ファイルの `changed_files()` docstring）。
- `scan_dangerous_patterns.py` の `_changed_python_files()` は `r.stdout.split()` →
  `splitlines()`（本モジュール内部）へ変わったことで、スペースを含むパスが複数トークンに
  誤分割されるバグが解消され、1 件のパスとして正しく扱われるようになった（#195 指摘4）。

## 提供する 2 系統

- `collect_changed_files()`: `git diff --name-only`（base range・worktree・cached）+
  `git ls-files --others --exclude-standard`（untracked）を収集ソースごとに ON/OFF できる。
  `self_review_check.py` / `check_architecture_boundaries.py` / `check_cjk_markdown.py` が使う。
- `run_git_or_raise()`: `check_agent_diff_claim.py` 専用。**性質が違う**（作業ツリー実差分のみ・
  git 失敗を `RuntimeError` として送出する）ため、`collect_changed_files()` には混ぜず、
  「git 実行 + エラーハンドリング」部分だけをここへ寄せる。`raw` 文字列の中身・例外送出という
  挙動は変えない。**検証の分担**（#195 指摘5・PR #723 レビュー）: 例外型・メッセージ書式そのもの
  （`RuntimeError` への変換・"git ... が失敗" / "git コマンドが見つかりません" の文言）は
  本モジュールの `python3 tools/git_diff_utils.py --self-test`（`_self_test_run_git_or_raise`）が
  検証する。`check_agent_diff_claim.py --self-test` は「`run_git()` 経由で
  `git_diff_utils.run_git_or_raise()` へ正しい引数（`args` と `cwd` の順序）で配線されているか」
  （`get_real_diff_files()` 経由の呼び出し配線）を検証する — 例外の中身ではなく配線の正しさが担当。

## テスト容易性

いずれの関数も `runner`（`subprocess.run` 互換の callable）を差し替え可能にしてあり、
実 git・実リポジトリに依存せず `--self-test` を検証できる（下記 `--self-test` 参照）。

## 使い方

    python3 tools/git_diff_utils.py --self-test
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

# subprocess.run 互換 callable の型（runner 差し替え用）
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _run_git(
    args: list[str],
    *,
    cwd: Path | str | None = None,
    timeout: int = 20,
    runner: Runner = subprocess.run,
) -> tuple[str, int]:
    """1 コマンドを実行し (stdout, returncode) を返す。例外は投げない（失敗時は returncode!=0 扱い）。"""
    try:
        r = runner(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return "", 1
    return r.stdout, r.returncode


def _run_git_paths(
    args: list[str],
    *,
    cwd: Path | str | None = None,
    timeout: int = 20,
    runner: Runner = subprocess.run,
) -> tuple[list[str], int]:
    """パス一覧を返す git サブコマンド専用の実行ヘルパー（Issue #748）。

    既定（`core.quotePath=true`）では非 ASCII パスが `"docs/\\346\\227\\245.md"` の形にクォート
    ＋8進エスケープされ、改行を含むパスも `"multi\\nline.md"` のようにエスケープされる。
    `git -c core.quotePath=false ... -z` の組み合わせで両方回避できる（実測で確認済み・#748）:
      - `core.quotePath=false` だけでは非 ASCII は解けるが、改行・ダブルクォートを含むパスは
        依然クォート＋エスケープされる（NUL 区切りでない限り改行はレコード境界と衝突するため）。
      - `-z` を付けて NUL 区切りで受け取ると、`core.quotePath=false` と合わせて改行・ダブルクォート
        入りパスも生のバイト列のまま 1 レコードとして返る。
    呼び出し側は `args` に `-z` を含める必要がある（本関数は `-c core.quotePath=false` の注入と
    NUL 分割だけを担当し、どのサブコマンドで `-z` を使うかは呼び出し側が決める）。
    """
    out, rc = _run_git(["git", "-c", "core.quotePath=false", *args], cwd=cwd, timeout=timeout, runner=runner)
    if rc != 0:
        return [], rc
    # NUL 区切り。末尾に区切り文字由来の空要素が付くので取り除く。
    parts = out.split("\0")
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts, rc


def default_branch(
    *,
    cwd: Path | str | None = None,
    runner: Runner = subprocess.run,
) -> str:
    """`origin/HEAD` が指すデフォルトブランチ名を返す。解決できなければ `main` にフォールバックする。"""
    out, rc = _run_git(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=cwd, runner=runner
    )
    if rc == 0 and out.strip():
        return out.strip().split("/")[-1]
    return "main"


def collect_changed_files(
    *,
    include_base_range: bool = True,
    include_worktree: bool = True,
    include_cached: bool = True,
    include_untracked: bool = True,
    require_existing: bool = True,
    sort: bool = False,
    cwd: Path | str | None = None,
    base: str | None = None,
    runner: Runner = subprocess.run,
    exists_fn: Callable[[str], bool] | None = None,
) -> list[str]:
    """変更ファイル一覧を収集する。収集ソース・存在チェック・ソートは引数で選べる。

    収集順（意図的な差異は呼び出し元コメントに 1 行残す・#195 完了条件 2）:
      1. base range（`{base}...HEAD`。`base` 未指定なら `origin/{default_branch()}`）
      2. worktree（`git diff --name-only`）
      3. cached（`git diff --cached --name-only`）
      4. untracked（`git ls-files --others --exclude-standard`）

    `require_existing=True` のとき、`exists_fn`（既定は `(cwd or '.') / f` の `is_file()`）で
    実在するファイルのみ残す。パス分割は `-z`（NUL 区切り）+ `core.quotePath=false` を使う
    `_run_git_paths()` を通す（非 ASCII パス・改行入りパスの誤分割を避けるため・#748。
    `splitlines()` / `split()` は使わない）。
    """
    files: list[str] = []

    if include_base_range:
        b = base if base is not None else f"origin/{default_branch(cwd=cwd, runner=runner)}"
        # `-` で始まる base は git がオプションとして解釈する（argument injection）。
        # 呼び出し元ごとのガード複製に頼らず、共有モジュール側で一元的に拒否する
        # （従来は count_change_scatter.py だけが自前で拒否していた・PR #761 Layer 1 レビュー）。
        if b.startswith("-"):
            raise ValueError(
                f"base に - で始まる値は使えません（git のオプションとして解釈されるため）: {b!r}"
            )
        paths, rc = _run_git_paths(["diff", "--name-only", "-z", f"{b}...HEAD"], cwd=cwd, runner=runner)
        if rc == 0:
            files += paths

    if include_worktree:
        paths, rc = _run_git_paths(["diff", "--name-only", "-z"], cwd=cwd, runner=runner)
        if rc == 0:
            files += paths

    if include_cached:
        paths, rc = _run_git_paths(["diff", "--cached", "--name-only", "-z"], cwd=cwd, runner=runner)
        if rc == 0:
            files += paths

    if include_untracked:
        paths, rc = _run_git_paths(
            ["ls-files", "--others", "--exclude-standard", "-z"], cwd=cwd, runner=runner
        )
        if rc == 0:
            files += paths

    if exists_fn is None:
        base_dir = Path(cwd) if cwd else Path(".")

        def exists_fn(f: str) -> bool:  # noqa: E731 (可読性優先の局所関数)
            return (base_dir / f).is_file()

    seen: set[str] = set()
    out_list: list[str] = []
    for f in files:
        if not f.strip():
            continue
        if f in seen:
            continue
        if require_existing and not exists_fn(f):
            continue
        seen.add(f)
        out_list.append(f)

    return sorted(out_list) if sort else out_list


def run_git_or_raise(
    args: list[str],
    cwd: Path | str,
    *,
    runner: Runner = subprocess.run,
) -> str:
    """git を実行し stdout を返す。失敗時は `RuntimeError` を送出する（`check_agent_diff_claim.py` 専用の性質）。

    `check_agent_diff_claim.py` は作業ツリーの実差分だけを見る性質が違うツールで、git 失敗を
    握りつぶさず `RuntimeError` として上位へ伝える（`--self-test` が例外送出そのものを検証する
    ため、メッセージ書式・例外型は変えない）。
    """
    try:
        proc = runner(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
        return proc.stdout
    except FileNotFoundError as e:
        raise RuntimeError("git コマンドが見つかりません") from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"git {' '.join(args)} が失敗: {stderr}") from e


# --------------------------------------------------------------------------- self-test
# ネットワーク・実 git リポジトリに依存しない（runner を差し替えて決定的に検証する）


class _FakeResult:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def _make_fake_runner(
    responses: dict[tuple[str, ...], str],
    fail_cmds: frozenset[tuple[str, ...]] = frozenset(),
    raise_missing: bool = False,
) -> Runner:
    """テスト用の `subprocess.run` 互換 callable を作る。

    `responses` に無いコマンドは stdout="" / returncode=0 を返す（未知コマンドで例外にしない）。
    `fail_cmds` に含まれるコマンドは、`check=True` 呼び出しなら `CalledProcessError` を送出し、
    それ以外なら returncode=1 を返す。`raise_missing=True` なら `FileNotFoundError` を送出する。
    """

    def runner(args, **kwargs):  # noqa: ANN001, ANN003 (subprocess.run 互換のため型は緩める)
        key = tuple(args)
        if raise_missing:
            raise FileNotFoundError("git not found")
        if key in fail_cmds:
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, args, output="", stderr="boom")
            return _FakeResult(stdout="", returncode=1)
        return _FakeResult(stdout=responses.get(key, ""), returncode=0)

    return runner


def _k_base_range(base_range: str) -> tuple[str, ...]:
    """base range 取得コマンドのキー（`_run_git_paths` が組み立てる実引数と一致させる）。"""
    return ("git", "-c", "core.quotePath=false", "diff", "--name-only", "-z", base_range)


def _k_worktree() -> tuple[str, ...]:
    return ("git", "-c", "core.quotePath=false", "diff", "--name-only", "-z")


def _k_cached() -> tuple[str, ...]:
    return ("git", "-c", "core.quotePath=false", "diff", "--cached", "--name-only", "-z")


def _k_untracked() -> tuple[str, ...]:
    return ("git", "-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard", "-z")


def _self_test_default_branch() -> list[str]:
    failures: list[str] = []

    r1 = _make_fake_runner({("git", "symbolic-ref", "refs/remotes/origin/HEAD"): "refs/remotes/origin/develop\n"})
    got = default_branch(runner=r1)
    if got != "develop":
        failures.append(f"default_branch 解決成功: expected='develop' got={got!r}")

    r2 = _make_fake_runner(
        {},
        fail_cmds=frozenset({("git", "symbolic-ref", "refs/remotes/origin/HEAD")}),
    )
    got2 = default_branch(runner=r2)
    if got2 != "main":
        failures.append(f"default_branch フォールバック: expected='main' got={got2!r}")

    return failures


def _self_test_collect_changed_files_sources() -> list[str]:
    """4 収集ソースそれぞれの ON/OFF が効くこと・重複排除・出現順維持を確認する。"""
    failures: list[str] = []

    responses = {
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): "refs/remotes/origin/main\n",
        _k_base_range("origin/main...HEAD"): "a.py\0b.py\0",
        _k_worktree(): "b.py\0c.py\0",  # b.py は base range と重複
        _k_cached(): "d.py\0",
        _k_untracked(): "e.py\0",
    }
    runner = _make_fake_runner(responses)

    got_all = collect_changed_files(require_existing=False, runner=runner)
    if got_all != ["a.py", "b.py", "c.py", "d.py", "e.py"]:
        failures.append(f"全ソース有効・出現順維持・重複排除: got={got_all!r}")

    got_base_only = collect_changed_files(
        include_worktree=False,
        include_cached=False,
        include_untracked=False,
        require_existing=False,
        runner=runner,
    )
    if got_base_only != ["a.py", "b.py"]:
        failures.append(f"base range のみ: got={got_base_only!r}")

    got_no_untracked = collect_changed_files(
        include_untracked=False, require_existing=False, runner=runner
    )
    if "e.py" in got_no_untracked:
        failures.append(f"include_untracked=False で e.py が混入: got={got_no_untracked!r}")

    got_no_cached = collect_changed_files(
        include_cached=False, require_existing=False, runner=runner
    )
    if "d.py" in got_no_cached:
        failures.append(f"include_cached=False で d.py が混入: got={got_no_cached!r}")

    # include_worktree=False の単独ケース（#195 追加指摘8）。上の include_cached / include_untracked
    # と対称: worktree だけ OFF にして c.py（worktree 由来）が消えることを見る。
    # このケースが無いと include_worktree のガードがテストされない（他 3 ソース ON のまま
    # worktree だけ壊しても緑のまま通り得た）。
    got_no_worktree = collect_changed_files(
        include_worktree=False, require_existing=False, runner=runner
    )
    if "c.py" in got_no_worktree:
        failures.append(f"include_worktree=False で c.py が混入: got={got_no_worktree!r}")

    # include_base_range=False の単独ケース。他 3 ソースと違い「base range のみ」ケース
    # （残り 3 つを同時に False にする）では base range 側の分岐を壊しても緑のまま通るため、
    # このケースが無いと include_base_range のガードがテストされない（#195 の敵対的検証で検出）
    got_no_base = collect_changed_files(
        include_base_range=False, require_existing=False, runner=runner
    )
    if got_no_base != ["b.py", "c.py", "d.py", "e.py"]:
        failures.append(f"include_base_range=False: got={got_no_base!r}")

    return failures


def _self_test_collect_changed_files_require_existing() -> list[str]:
    """require_existing のフィルタと exists_fn 注入が効くこと。"""
    failures: list[str] = []
    responses = {
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): "",  # フォールバックで main を使う
        _k_base_range("origin/main...HEAD"): "exists.py\0ghost.py\0",
        _k_worktree(): "",
        _k_cached(): "",
        _k_untracked(): "",
    }
    runner = _make_fake_runner(responses)

    got = collect_changed_files(
        require_existing=True,
        runner=runner,
        exists_fn=lambda f: f == "exists.py",
    )
    if got != ["exists.py"]:
        failures.append(f"require_existing=True でファイル実在フィルタ: got={got!r}")

    got_off = collect_changed_files(require_existing=False, runner=runner)
    if got_off != ["exists.py", "ghost.py"]:
        failures.append(f"require_existing=False は実在チェックしない: got={got_off!r}")

    return failures


def _self_test_collect_changed_files_sort_and_base_override() -> list[str]:
    failures: list[str] = []
    responses = {
        _k_base_range("custom-base...HEAD"): "z.py\0a.py\0",
        _k_worktree(): "",
        _k_cached(): "",
        _k_untracked(): "",
    }
    runner = _make_fake_runner(responses)

    got_unsorted = collect_changed_files(
        base="custom-base",
        include_worktree=False,
        include_cached=False,
        include_untracked=False,
        require_existing=False,
        runner=runner,
    )
    if got_unsorted != ["z.py", "a.py"]:
        failures.append(f"sort=False は出現順維持: got={got_unsorted!r}")

    got_sorted = collect_changed_files(
        base="custom-base",
        include_worktree=False,
        include_cached=False,
        include_untracked=False,
        require_existing=False,
        sort=True,
        runner=runner,
    )
    if got_sorted != ["a.py", "z.py"]:
        failures.append(f"sort=True はソート済み: got={got_sorted!r}")

    return failures


def _self_test_collect_changed_files_blank_lines() -> list[str]:
    """空要素（連続 NUL・末尾 NUL 由来）を混入させない。"""
    failures: list[str] = []
    responses = {
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): "refs/remotes/origin/main\n",
        _k_base_range("origin/main...HEAD"): "a.py\0\0b.py\0",
        _k_worktree(): "",
        _k_cached(): "",
        _k_untracked(): "",
    }
    runner = _make_fake_runner(responses)
    got = collect_changed_files(require_existing=False, runner=runner)
    if got != ["a.py", "b.py"]:
        failures.append(f"空要素を除外: got={got!r}")
    return failures


def _self_test_collect_changed_files_space_in_path() -> list[str]:
    """スペースを含むパスを 1 件として扱うこと（NUL 区切りなので空白では分割されない）。"""
    failures: list[str] = []
    responses = {
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): "refs/remotes/origin/main\n",
        _k_base_range("origin/main...HEAD"): "docs/my report.md\0b.py\0",
        _k_worktree(): "",
        _k_cached(): "",
        _k_untracked(): "",
    }
    runner = _make_fake_runner(responses)
    got = collect_changed_files(require_existing=False, runner=runner)
    if got != ["docs/my report.md", "b.py"]:
        failures.append(f"スペース入りパスを 1 件として保持: got={got!r}")
    return failures


def _self_test_collect_changed_files_non_ascii_and_newline_path() -> list[str]:
    """非 ASCII パス・改行入りパス・ダブルクォート入りパスを 1 件のまま正しく扱う（Issue #748 本体）。

    `core.quotePath=true`（git 既定）だと非 ASCII パスは `"docs/\\346\\227\\245.md"` の形で
    クォート＋8進エスケープされ、改行・ダブルクォート入りパスも同様にエスケープされる
    （実測で確認済み・本ファイル冒頭のモジュール docstring 相当の検証）。ここでは
    `_run_git_paths()`（`-c core.quotePath=false` + `-z` 区切り）を経由した後の「素のパスが
    NUL 区切りでそのまま渡ってくる」状態を模して、呼び出し側が正しく 1 パスとして復元できるかを見る。
    """
    failures: list[str] = []
    non_ascii = "docs/rules/日.md"
    with_newline = "multi\nline.md"
    with_quote = 'quo"te.md'
    responses = {
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): "refs/remotes/origin/main\n",
        _k_base_range("origin/main...HEAD"): f"{non_ascii}\0{with_newline}\0{with_quote}\0",
        _k_worktree(): "",
        _k_cached(): "",
        _k_untracked(): "",
    }
    runner = _make_fake_runner(responses)
    got = collect_changed_files(require_existing=False, runner=runner)
    if got != [non_ascii, with_newline, with_quote]:
        failures.append(
            f"非 ASCII / 改行 / ダブルクォート入りパスを 1 件ずつ保持: got={got!r}"
        )
    return failures


def _self_test_collect_changed_files_rejects_option_like_base() -> list[str]:
    """`-` で始まる base を拒否すること（argument injection の一元ガード・PR #761 レビュー）。

    許容側（拒否してはいけない値）も同じテストで固定する。`-` を **含む** だけのブランチ名
    （`feature-x`・`origin/release-1.2`）や、`-` で始まらない通常の ref は通す。
    """
    failures: list[str] = []
    responses = {
        _k_base_range("--output=/tmp/pwned...HEAD"): "",
        _k_base_range("origin/release-1.2...HEAD"): "a.py\0",
        _k_worktree(): "",
        _k_cached(): "",
        _k_untracked(): "",
    }
    for bad in ("--output=/tmp/pwned", "-x", "--upload-pack=touch /tmp/x"):
        runner = _make_fake_runner(responses)
        try:
            collect_changed_files(require_existing=False, base=bad, runner=runner)
        except ValueError:
            pass
        else:
            failures.append(f"オプション様の base を拒否していない: base={bad!r}")

    runner = _make_fake_runner(responses)
    try:
        got = collect_changed_files(require_existing=False, base="origin/release-1.2", runner=runner)
    except ValueError as exc:
        failures.append(f"`-` を含むだけの正常な base を誤って拒否した: {exc}")
    else:
        if got != ["a.py"]:
            failures.append(f"`-` を含むだけの正常な base の収集結果: got={got!r}")
    return failures


def _self_test_run_git_paths_quotepath_and_z_injected() -> list[str]:
    """`_run_git_paths()` が `-c core.quotePath=false` を注入し、NUL 分割・末尾空要素除去をすること。

    変異テスト対象（`-c core.quotePath=false` の注入を外す・`-z` split を `splitlines()` に
    戻す等）に対する直接の回帰検知。呼び出しコマンドを記録する fake runner で検証する。
    """
    failures: list[str] = []
    calls: list[list[str]] = []

    def recording_runner(args, **kwargs):
        calls.append(list(args))
        return _FakeResult(stdout="a.py\0b.py\0", returncode=0)

    got, rc = _run_git_paths(["diff", "--name-only", "-z"], runner=recording_runner)
    if rc != 0:
        failures.append(f"正常系の returncode は 0: got={rc}")
    if got != ["a.py", "b.py"]:
        failures.append(f"NUL 分割・末尾空要素除去: got={got!r}")
    if len(calls) != 1 or "-c" not in calls[0] or "core.quotePath=false" not in calls[0]:
        failures.append(f"-c core.quotePath=false が注入されていない: got={calls!r}")
    if calls and calls[0][0] != "git":
        failures.append(f"先頭は 'git' であるべき: got={calls[0]!r}")

    # 空出力（変更なし）でも例外なく空リストを返す
    def empty_runner(args, **kwargs):
        return _FakeResult(stdout="", returncode=0)

    got_empty, rc_empty = _run_git_paths(["diff", "--name-only", "-z"], runner=empty_runner)
    if got_empty != [] or rc_empty != 0:
        failures.append(f"空出力は空リスト・rc=0: got=({got_empty!r}, {rc_empty})")

    # git 失敗時は空リスト・非ゼロ rc を返す（例外は投げない）
    fail_runner = _make_fake_runner(
        {}, fail_cmds=frozenset({("git", "-c", "core.quotePath=false", "diff", "--name-only", "-z")})
    )
    got_fail, rc_fail = _run_git_paths(["diff", "--name-only", "-z"], runner=fail_runner)
    if rc_fail == 0 or got_fail != []:
        failures.append(f"git 失敗時は空リスト・rc!=0: got=({got_fail!r}, {rc_fail})")

    return failures


def _self_test_collect_changed_files_real_filesystem_exists() -> list[str]:
    """`require_existing=True` かつ `exists_fn=None`（本番の 4 ラッパー全てが通る唯一の経路）が、

    実ファイルシステムに対して正しく存在チェックすることを確認する（#195 指摘1）。
    `exists_fn` を注入せず、実際に `tempfile.TemporaryDirectory()` へファイルを作って
    `cwd` 経由で存在確認させる。旧来の自己テストは全て `exists_fn` を注入していたため、
    実測で「`(base_dir / f).is_file()` を常に `True` を返すよう壊しても 5 つの self-test が
    全て緑のまま」という無検知が起きていた。
    """
    failures: list[str] = []
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "exists.py").write_text("x", encoding="utf-8")
        # ghost.py はあえて作らない（存在しないパスとして扱われるべき）

        responses = {
            ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): "",  # フォールバックで main
            _k_base_range("origin/main...HEAD"): "exists.py\0ghost.py\0",
            _k_worktree(): "",
            _k_cached(): "",
            _k_untracked(): "",
        }
        runner = _make_fake_runner(responses)

        got = collect_changed_files(
            require_existing=True,
            cwd=tmp_path,
            runner=runner,
        )
        if got != ["exists.py"]:
            failures.append(
                f"実ファイルシステムでの存在チェック（exists_fn 未注入）: expected=['exists.py'] got={got!r}"
            )

    return failures


def _self_test_run_git_cwd_and_timeout_forwarded() -> list[str]:
    """`_run_git()` が受け取った `cwd` / `timeout` を実際に `runner` へ転送していることを確認する。

    （#195 指摘2）`check_architecture_boundaries.py` は `cwd=REPO_ROOT` を指定して呼ぶため、
    `_run_git` 内の `cwd=cwd` 転送が抜けると無検知の回帰になる（実測: 削除しても旧来の
    self-test は全て緑のまま）。fake runner が受け取った kwargs を記録し、期待値と突き合わせる。
    """
    failures: list[str] = []
    calls: list[dict] = []

    def recording_runner(args, **kwargs):
        calls.append(kwargs)
        return _FakeResult(stdout="", returncode=0)

    out, rc = _run_git(
        ["git", "status"], cwd="/tmp/fake-repo-dir", timeout=7, runner=recording_runner
    )
    if len(calls) != 1:
        failures.append(f"_run_git は runner をちょうど 1 回呼ぶべき: got {len(calls)} 回")
    else:
        if calls[0].get("cwd") != "/tmp/fake-repo-dir":
            failures.append(f"cwd が runner へ転送されていない: got={calls[0].get('cwd')!r}")
        if calls[0].get("timeout") != 7:
            failures.append(f"timeout が runner へ転送されていない: got={calls[0].get('timeout')!r}")

    return failures


def _self_test_run_git_or_raise() -> list[str]:
    failures: list[str] = []

    class _OkResult:
        stdout = "clean\n"

    def ok_runner(args, **kwargs):
        return _OkResult()

    got = run_git_or_raise(["status"], cwd=".", runner=ok_runner)
    if got != "clean\n":
        failures.append(f"run_git_or_raise 成功時に stdout を返す: got={got!r}")

    fail_runner = _make_fake_runner({}, fail_cmds=frozenset({("git", "status")}))
    try:
        run_git_or_raise(["status"], cwd=".", runner=fail_runner)
        failures.append("run_git_or_raise は CalledProcessError 時に RuntimeError を送出すべき")
    except RuntimeError as e:
        if "git status が失敗" not in str(e):
            failures.append(f"RuntimeError メッセージ書式が変わった: {e}")

    missing_runner = _make_fake_runner({}, raise_missing=True)
    try:
        run_git_or_raise(["status"], cwd=".", runner=missing_runner)
        failures.append("run_git_or_raise は FileNotFoundError 時に RuntimeError を送出すべき")
    except RuntimeError as e:
        if "git コマンドが見つかりません" not in str(e):
            failures.append(f"FileNotFoundError 変換メッセージが変わった: {e}")

    return failures


def run_self_test() -> int:
    groups = [
        ("default_branch", _self_test_default_branch),
        ("collect_changed_files ソース ON/OFF", _self_test_collect_changed_files_sources),
        ("collect_changed_files require_existing", _self_test_collect_changed_files_require_existing),
        (
            "collect_changed_files 実ファイルシステム存在チェック",
            _self_test_collect_changed_files_real_filesystem_exists,
        ),
        ("collect_changed_files sort/base override", _self_test_collect_changed_files_sort_and_base_override),
        ("collect_changed_files 空行除外", _self_test_collect_changed_files_blank_lines),
        ("collect_changed_files スペース入りパス", _self_test_collect_changed_files_space_in_path),
        (
            "collect_changed_files 非ASCII/改行/ダブルクォート入りパス",
            _self_test_collect_changed_files_non_ascii_and_newline_path,
        ),
        (
            "collect_changed_files オプション様 base の拒否",
            _self_test_collect_changed_files_rejects_option_like_base,
        ),
        (
            "_run_git_paths core.quotePath 注入・NUL分割",
            _self_test_run_git_paths_quotepath_and_z_injected,
        ),
        ("_run_git cwd/timeout 転送", _self_test_run_git_cwd_and_timeout_forwarded),
        ("run_git_or_raise", _self_test_run_git_or_raise),
    ]
    total_fail = 0
    for label, fn in groups:
        failures = fn()
        if failures:
            total_fail += len(failures)
            for f in failures:
                print(f"FAIL[{label}]: {f}")
        else:
            print(f"✅ {label}")

    if total_fail:
        print(f"❌ git_diff_utils --self-test FAILED（{total_fail} 件）")
        return 1
    print("✅ git_diff_utils --self-test PASSED")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return run_self_test()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
