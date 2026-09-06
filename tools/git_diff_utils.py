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

## 提供する 3 系統

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
- パス正規化系（`normalize_leading_dots()` / `normalize_abbreviated_paths()` /
  `resolve_abbreviated_path()`）: `check_agent_diff_claim.py` の claim 側（完了報告テキストからの
  抽出）と実 diff 側（`git status` / `git diff --stat` の出力）の両方が **同じ正規化関数** を
  通ることを保証する層。`normalize_leading_dots()` は先頭の `./` `../`（1 回以上）・3 文字目が
  `/` でない 2 個以上の連続ドット（`...utils.py` 等）を正規化する（Issue #948 / #968）。
  `normalize_abbreviated_paths()` / `resolve_abbreviated_path()` は `git diff --stat` が
  `.../` で省略した長いパスを候補集合からサフィックス一致で解決する（Issue #850）。

## テスト容易性

いずれの関数も `runner`（`subprocess.run` 互換の callable）を差し替え可能にしてあり、
実 git・実リポジトリに依存せず `--self-test` を検証できる（下記 `--self-test` 参照）。

## 使い方

    python3 tools/git_diff_utils.py --self-test
"""

from __future__ import annotations

import re
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

    🔴 Issue #880: 本関数は `-c core.quotePath=false` を注入しない（`check=True` の単純な
    stdout 取得のみが目的で、パス一覧の分割は行わないため）。日本語ファイル名を含む
    パス一覧が要る呼び出しは本関数ではなく `run_git_paths_or_raise()` を使うこと
    （`check_agent_diff_claim.py` の `git status --short` 呼び出しは untracked 検出のためだけに
    本関数を使い続けるが、パスの中身は `parse_status_short()` 側で
    `normalize_leading_dots()` により正規化される。`git status --short` は既定でクォート
    パスを日本語ファイル名に対して返しうる点は既知の残存差である — 本 Issue の対象範囲は
    `git diff --stat` 由来の 3 経路であり、`git status --short` の quotePath 対応は含まない）。
    """
    try:
        proc = runner(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
        return proc.stdout
    except FileNotFoundError as e:
        raise RuntimeError("git コマンドが見つかりません") from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"git {' '.join(args)} が失敗: {stderr}") from e


def run_git_paths_or_raise(
    args: list[str],
    cwd: Path | str,
    *,
    runner: Runner = subprocess.run,
) -> list[str]:
    """パス一覧を返す git サブコマンドを実行し、失敗時は `RuntimeError` を送出する（Issue #880）。

    `_run_git_paths()`（`-c core.quotePath=false` 注入 + `-z` NUL 区切り分割）を使うため、
    `run_git_or_raise()` と違って **日本語ファイル名がエスケープされず**、**改行やダブルクォート
    入りパスも 1 レコードのまま** 返る。`check_agent_diff_claim.py` の `get_real_diff_files()` は
    従来 `git diff --stat` / `git diff --cached --stat`（`run_git_or_raise()` 経由）を使っていたが、
    `--stat` は ① 幅指定をしても `.../` 省略が起こりうる（#850）② `run_git_or_raise()` は
    quotePath を注入しないため日本語パスが `"docs/\\346\\227\\245..."` 形にエスケープされたまま
    返る、という 2 つの偽陽性経路を持っていた。`parse_diff_stat()` は元々 `"|"` の左のパスしか
    使わず変更行数・記号列は一切使っていなかったため、`--name-only -z` へ置き換えることで
    両方の経路を発生源で解消する（`check_agent_diff_claim.py` の `get_real_diff_files()` docstring
    参照）。

    `args` には呼び出し側が `-z` を含めること（`_run_git_paths()` の規約を踏襲する）。
    git 実行そのものが失敗した場合（returncode != 0。git 未検出等の `OSError` 系も
    `_run_git()` 内で returncode=1 に丸められ、ここで拾われる）は `RuntimeError` を送出する。
    """
    paths, rc = _run_git_paths(args, cwd=cwd, runner=runner)
    if rc != 0:
        raise RuntimeError(f"git {' '.join(args)} が失敗")
    return paths


# --------------------------------------------------------------------------- パス正規化
# `git diff --stat` は長いパスを `.../` で省略して出力する（省略幅は端末幅・git config に依存する）。
# 省略パスと完全パスが同じ集合に混ざると同一ファイルが 2 件に数えられるため、集合比較の前段で
# 省略を解決する層をここに置く（Issue #850）。

ABBREV_PREFIX = ".../"

# Issue #968: `check_agent_diff_claim.py` の `_PATH_TOKEN_RE` 先頭文字クラスへ `.` を追加した
# 副作用で、`../bin/tool.sh`（相対パス）や `...utils.py`（日本語文中の三点リーダー + ファイル名が
# 融合したもの）のようなトークンが 1 個の候補としてそのまま抽出されるようになった。この 2 つは
# 「先頭ドット付きの実在パス」（`.github/x.yml` 等・#948）とは別カテゴリであり、実 diff 側は
# それぞれ `bin/tool.sh` / `utils.py`（先頭の相対参照・約物を含まない素のパス）を返すため、
# 放置すると実 diff 側が `missing_from_report`（報告漏れ・より重い警告）に落ちる。
#
# `.../`（`ABBREV_PREFIX`。#850 の省略記法）は絶対に壊さない: `_PARENT_DIR_RE` は 3 文字目が
# 厳密に `/` である "../" だけに一致するため "..." には一致せず、`_LEADING_DOTS_RE` は先読みで
# 直後が英数字/アンダースコアであることを要求するため直後が `/` の "..." には一致しない。
# いずれも `.../` の 3 文字目・4 文字目とは噛み合わないため、`.../` はどちらの正規化からも
# 保護される（`_self_test_normalize_leading_dots` の該当ケースで固定する）。
_PARENT_DIR_RE = re.compile(r"^(?:\.\./)+")
_LEADING_DOTS_RE = re.compile(r"^\.{2,}(?=[A-Za-z0-9_])")


def normalize_leading_dots(path: str) -> str:
    """パス先頭の相対参照ドット（`./` 1 回・`../` 1 回以上・3+ 連続ドット）を正規化する。

    3 段階を **この順序で** 適用する（順序を変えない。self-test が順序依存の結果を固定している）:

    1. `./` プレフィックスを 1 回だけ取り除く（`str.removeprefix("./")`・Issue #948）。
       `str.lstrip(chars)` は引数を「文字集合」として扱うため、`lstrip("./")` は
       `.github/workflows/x.yml` のような **先頭ドット付きの実在パス** に対して先頭の `.` まで
       連続的に食い荒らし `github/workflows/x.yml` を生む（`.` も `/` も引数の集合に含まれるため）。
       `removeprefix()`（完全一致の 1 回限りの除去・Python 3.9+）はこの巻き添えを起こさない。
    2. 先頭の `../` を 1 回以上まとめて取り除く（Issue #968）。完了報告が cwd 相対の
       `../bin/tool.sh` のように書いた場合、実 diff 側はリポジトリルート相対の `bin/tool.sh` を
       返すため、放置すると一致しない。
    3. 残った先頭の連続ドット（2 個以上）が **直後に英数字/アンダースコアへ続く場合だけ**
       取り除く（Issue #968）。直後が `/`（`.../` = `ABBREV_PREFIX`）なら先読みが不成立になり
       **絶対に触らない**（`.../` の省略解決は `resolve_abbreviated_path()` /
       `normalize_abbreviated_paths()` の担当のまま）。

    `.github/x.yml` はどの段にも該当しない（1: `./` で始まらない、2: `../` で始まらない、
    3: 先頭ドットが 1 個のみで `\\.{2,}` に一致しない）ため無傷で通過する。`./foo.py` は
    1 段目だけで `foo.py` になる。既に正規化済みのパスは変化しない（各段が冪等）。

    サブエージェントの完了報告（claim 側・`check_agent_diff_claim.py` の `_tokens_from_text`）と
    実 diff 側（同ファイルの `parse_status_short` / `parse_diff_stat`）の両方が **この関数だけ**
    を通ることで、片側だけ正規化されて食い違う構造的欠陥を防ぐ（`check_agent_diff_claim.py
    --self-test` の `run_self_test()` 内、`git_diff_utils.normalize_leading_dots` を差し替えて
    呼び出し回数を記録するブロックが両経路の配線を検証する）。
    """
    path = path.removeprefix("./")
    path = _PARENT_DIR_RE.sub("", path)
    path = _LEADING_DOTS_RE.sub("", path)
    return path


def resolve_abbreviated_path(path: str, candidates: set[str] | frozenset[str]) -> str | None:
    """`.../` で省略されたパスを候補集合からサフィックス一致で解決する（Issue #850）。

    戻り値:
      - 省略パスでない場合: `path` をそのまま返す（呼び出し側の分岐を減らすため）
      - 省略パスで候補が **一意に定まった** 場合: その完全パス
      - 候補が 0 件、または 2 件以上に一致して一意に定まらない場合: `None`
        （呼び出し側は `unresolved` として警告に落とし、集合比較には混ぜない）

    サフィックス一致は **パス境界を跨がない**: `.../bar.md` は `foo/bar.md` に一致するが
    `foobar.md` には一致しない（`str.endswith()` の素朴な前方/後方一致は別カテゴリまで巻き込む）。
    """
    if not path.startswith(ABBREV_PREFIX):
        return path
    suffix = path[len(ABBREV_PREFIX) :]
    if not suffix:
        return None
    matches = {c for c in candidates if c == suffix or c.endswith("/" + suffix)}
    if len(matches) == 1:
        return next(iter(matches))
    return None


def normalize_abbreviated_paths(
    paths: set[str] | frozenset[str],
    *,
    extra_candidates: set[str] | frozenset[str] | None = None,
    repo_root: Path | str | None = None,
    runner: Runner = subprocess.run,
) -> tuple[set[str], set[str]]:
    """パス集合から `.../` 省略を取り除き `(resolved, unresolved)` を返す（Issue #850）。

    候補は次の順に積む（省略パスが 1 件も無ければ git は呼ばない）:
      1. `paths` に含まれる **省略でないパス**（同じ収集で完全パスも得られていることが多い）
      2. `extra_candidates`（呼び出し側が別経路で得た完全パス）
      3. `repo_root` が与えられていれば `git ls-files`（作業ツリーの追跡ファイル全件）

    解決できなかった省略パスは `unresolved` に入れる。**黙って捨てない**（呼び出し側が
    「一意に解決できなかった」ことを報告できるようにするため）。
    """
    abbreviated = {p for p in paths if p.startswith(ABBREV_PREFIX)}
    concrete = set(paths) - abbreviated
    if not abbreviated:
        return concrete, set()

    candidates: set[str] = set(concrete)
    if extra_candidates:
        candidates |= set(extra_candidates)
    if repo_root is not None:
        tracked, rc = _run_git_paths(["ls-files", "-z"], cwd=repo_root, runner=runner)
        if rc == 0:
            candidates |= {t for t in tracked if t}

    resolved = set(concrete)
    unresolved: set[str] = set()
    for p in sorted(abbreviated):
        hit = resolve_abbreviated_path(p, candidates)
        if hit is None:
            unresolved.add(p)
        else:
            resolved.add(hit)
    return resolved, unresolved


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


def _self_test_run_git_paths_or_raise() -> list[str]:
    """Issue #880: `run_git_paths_or_raise()` の argv・成功時のパス返却・失敗時の RuntimeError を検証する。

    fake runner に argv を記録させ、① `-c core.quotePath=false` が注入されている
    ② `-z` を含むサブコマンドがそのまま渡っている ③ NUL 区切りが正しく分割される、を assert する
    （`docs/rules/check-tool-design-rules.md` §3 の fake runner argv 検証要件）。
    """
    failures: list[str] = []
    calls: list[list[str]] = []

    def recording_runner(args, **kwargs):  # noqa: ANN001, ANN003
        calls.append(list(args))
        return _FakeResult(stdout="tools/a.py\0docs/b.md\0", returncode=0)

    got = run_git_paths_or_raise(["diff", "--name-only", "-z"], cwd=".", runner=recording_runner)
    if got != ["tools/a.py", "docs/b.md"]:
        failures.append(f"成功時にパス一覧を返す: got={got!r}")
    if len(calls) != 1 or "-c" not in calls[0] or "core.quotePath=false" not in calls[0]:
        failures.append(f"-c core.quotePath=false が注入されていない: got={calls!r}")
    if calls and ("--name-only" not in calls[0] or "-z" not in calls[0]):
        failures.append(f"呼び出し側が指定したサブコマンド引数がそのまま渡っていない: got={calls!r}")
    if calls and calls[0][0] != "git":
        failures.append(f"先頭は 'git' であるべき: got={calls[0]!r}")

    fail_runner = _make_fake_runner(
        {}, fail_cmds=frozenset({("git", "-c", "core.quotePath=false", "diff", "--name-only", "-z")})
    )
    try:
        run_git_paths_or_raise(["diff", "--name-only", "-z"], cwd=".", runner=fail_runner)
        failures.append("run_git_paths_or_raise は git 失敗時に RuntimeError を送出すべき")
    except RuntimeError:
        pass

    return failures


def _self_test_resolve_abbreviated_path_boundary() -> list[str]:
    """Issue #880: `resolve_abbreviated_path()` の候補 **0 件**（完全な空集合）分岐を直接検証する。

    既存の `_self_test_normalize_abbreviated_paths` ケース2は `normalize_abbreviated_paths()`
    経由で「候補は非空だが一致 0 件」（`{"tools/other.py"}` に対して不一致）しか通っておらず、
    `resolve_abbreviated_path()` 自身に **文字どおり空の candidates**（`frozenset()`）を渡す
    経路が一度もテストされていなかった（#750 の「境界の外側の負ケース」の穴）。
    """
    failures: list[str] = []

    got_empty = resolve_abbreviated_path(".../infrastructure/x.md", frozenset())
    if got_empty is not None:
        failures.append(f"候補 0 件（完全な空集合）は None を返すべき: got={got_empty!r}")

    # 対で置く負ケース: 省略パスでない入力は candidates が空でもそのまま返す（早期リターン経路）
    got_not_abbrev = resolve_abbreviated_path("tools/x.py", frozenset())
    if got_not_abbrev != "tools/x.py":
        failures.append(f"省略パスでない入力は candidates に依らずそのまま返す: got={got_not_abbrev!r}")

    return failures


def _k_ls_files() -> tuple[str, ...]:
    return ("git", "-c", "core.quotePath=false", "ls-files", "-z")


def _self_test_normalize_abbreviated_paths() -> list[str]:
    """Issue #850: `git diff --stat` の `.../` 省略が同一ファイルを 2 件に増やさないこと。"""
    failures: list[str] = []
    full = "docs/03_design/infrastructure/cloudflare-infrastructure.md"
    abbrev = ".../infrastructure/cloudflare-infrastructure.md"

    # 1. 省略パスと完全パスの混在（#850 の実測ケース）→ 1 件に畳まれる
    resolved, unresolved = normalize_abbreviated_paths({abbrev, full})
    if resolved != {full} or unresolved:
        failures.append(f"混在の畳み込み: resolved={sorted(resolved)} unresolved={sorted(unresolved)}")

    # 2. 候補が 1 件も無い → unresolved（黙って捨てない・mismatch には混ぜない）
    resolved2, unresolved2 = normalize_abbreviated_paths({abbrev, "tools/other.py"})
    if resolved2 != {"tools/other.py"} or unresolved2 != {abbrev}:
        failures.append(f"候補なし: resolved={sorted(resolved2)} unresolved={sorted(unresolved2)}")

    # 3. 複数一致で一意に定まらない → unresolved（誤って片方へ寄せない）
    ambiguous = ".../notes.md"
    resolved3, unresolved3 = normalize_abbreviated_paths(
        {ambiguous}, extra_candidates={"a/notes.md", "b/notes.md"}
    )
    if resolved3 or unresolved3 != {ambiguous}:
        failures.append(f"曖昧一致: resolved={sorted(resolved3)} unresolved={sorted(unresolved3)}")

    # 4. サフィックス一致がパス境界を跨がない（`foobar.md` は `.../bar.md` に一致しない）
    resolved4, unresolved4 = normalize_abbreviated_paths(
        {".../bar.md"}, extra_candidates={"docs/foobar.md"}
    )
    if resolved4 or unresolved4 != {".../bar.md"}:
        failures.append(f"境界跨ぎ拒否: resolved={sorted(resolved4)} unresolved={sorted(unresolved4)}")

    # 5. 候補が集合内に無くても `git ls-files` から解決できる
    runner5 = _make_fake_runner({_k_ls_files(): f"{full}\0tools/x.py\0"})
    resolved5, unresolved5 = normalize_abbreviated_paths(
        {abbrev}, repo_root=".", runner=runner5
    )
    if resolved5 != {full} or unresolved5:
        failures.append(f"ls-files 解決: resolved={sorted(resolved5)} unresolved={sorted(unresolved5)}")

    # 6. 省略パスが 1 件も無ければ git を呼ばない（無駄な subprocess を出さない）
    calls: list[tuple[str, ...]] = []

    def recording_runner(args, **kwargs):  # noqa: ANN001, ANN003
        calls.append(tuple(args))
        return _FakeResult(stdout="", returncode=0)

    resolved6, unresolved6 = normalize_abbreviated_paths(
        {"a.py", "b.py"}, repo_root=".", runner=recording_runner
    )
    if resolved6 != {"a.py", "b.py"} or unresolved6 or calls:
        failures.append(f"省略なしで git 未実行: resolved={sorted(resolved6)} calls={calls}")

    # 7. `.../` だけ（サフィックスが空）は解決せず unresolved に落とす
    resolved7, unresolved7 = normalize_abbreviated_paths({".../"}, extra_candidates={"a.py"})
    if resolved7 or unresolved7 != {".../"}:
        failures.append(f"空サフィックス: resolved={sorted(resolved7)} unresolved={sorted(unresolved7)}")

    return failures


def _self_test_normalize_leading_dots() -> list[str]:
    """Issue #948 / #968: 先頭ドット系の正規化が意図どおりで、かつ `.../`（ABBREV_PREFIX）を
    絶対に壊さないことを固定する。
    """
    failures: list[str] = []

    cases = [
        ("./foo.py", "foo.py"),  # 通常の "./" プレフィックスは 1 回だけ剥がす
        (".github/workflows/x.yml", ".github/workflows/x.yml"),  # 先頭ドット付き実在パスは無傷
        (".claude/hooks/y.sh", ".claude/hooks/y.sh"),  # 同上（別ディレクトリ）
        ("foo.py", "foo.py"),  # プレフィックス無しは変化しない（冪等）
        ("././foo.py", "./foo.py"),  # 1 回だけ剥がす（`lstrip` のような連続除去はしない）
        # #968: "..." + 直後が英数字は「三点リーダー + ファイル名」の融合とみなして剥がす
        # （旧仕様は "...hidden.py" を無傷で通していたが、#968 の CRITICAL 修正でこのケース自体が
        # 対策対象になったため意図的に挙動を変える。実ファイル名が真に "...hidden.py" である
        # 可能性より、日本語文中の三点リーダー融合が起きる確率の方が既知の実害として高いため）。
        ("...hidden.py", "hidden.py"),
        ("...utils.py", "utils.py"),  # #968 CRITICAL 指摘そのものの再現ケース
        ("..hidden.py", "hidden.py"),  # 2 連続ドットでも同様に剥がす（下限は 2 個）
        # #968: 境界の外側（似ているが別カテゴリ・#750 の負ケース観点）
        (".hidden.py", ".hidden.py"),  # 単一ドットは対象外（隠しファイルの通常表記）
        (".../infrastructure/x.md", ".../infrastructure/x.md"),  # ABBREV_PREFIX は絶対に無傷
        ("..../x.py", "..../x.py"),  # 4連続ドット + "/" も直後が "/" のため先読み不成立で無傷
        # #968: "../"（相対パス上位参照）
        ("../foo.py", "foo.py"),
        ("../bin/tool.sh", "bin/tool.sh"),
        ("../../foo.py", "foo.py"),  # 連続する "../" は 1 回の sub でまとめて剥がれる
        ("../.../x.md", ".../x.md"),  # "../" を剥がした後に残る ABBREV_PREFIX は無傷のまま
    ]
    for given, expected in cases:
        got = normalize_leading_dots(given)
        if got != expected:
            failures.append(f"normalize_leading_dots({given!r}): expected={expected!r} got={got!r}")

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
        ("run_git_paths_or_raise（#880）", _self_test_run_git_paths_or_raise),
        ("resolve_abbreviated_path 候補0件境界（#880 / #750）", _self_test_resolve_abbreviated_path_boundary),
        ("normalize_abbreviated_paths（#850）", _self_test_normalize_abbreviated_paths),
        ("normalize_leading_dots（#948 / #968）", _self_test_normalize_leading_dots),
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
