#!/usr/bin/env python3
"""新しい ID を採番する前に、`origin/main` で既に確保された ID を機械的に確認する（Issue #256）。

背景: PR #254 で **ID 衝突がマージ直前まで検知されなかった**。作業ブランチが `main` を
一度も取り込まないまま作業している間に、別セッションが `main` へマージした PR が
`D-25` / `D-26` / ADR `0013` を確保していた。決定ログの末尾に別々の行として追記される
ため git は自動マージしてしまい、`session-concurrency-rules.md` の多層防御（層 1 / 層 3）
はいずれも ID の予約状況を見ていない。PR #414 では同じ構造の衝突が lessons の `L-n`
でも起きた（Issue #256 コメント 2）。

本ツールがやること:
  1. `git fetch origin main` した最新の `origin/main` から、確保済みの ID を抽出する
  2. `merge-base(origin/main, HEAD)` を基準に「作業ブランチ側で新規追加された ID」と
     「`main` 側で新規追加された ID」を突き合わせ、**両側で独立に採番された ID**（＝衝突）
     を検出する
  3. 衝突が無ければ、種別ごとの「次の空き番号」を出力する（採番表の生成に使える）

🔴 **スコープ外（意図的）**: 衝突が起きた後の **繰り下げ支援**（参照グラフ全体の書き換え）は
本ツールでは実装しない（Issue #256 コメント 1 の追加要件は検知と次番号の提示までを本 Issue の
射程とする）。繰り下げは別 Issue で扱う。

検出できないこと（既知の限界）:
  - 定義行の書式（表の第 1 セル先頭 / 見出し先頭）に従わない ID 定義は「定義」として拾えない。
    本文中の参照（第 2 セル以降・散文中）は意図的に定義として扱わない（参照まで定義扱いに
    すると、他ドキュメントからの言及が全て「予約」になり誤検知だらけになるため）。
  - コードフェンス内の例示は `tools/md_fence.py` で除外する（例示の `| **D-99** |` を
    予約とみなさない）。
  - **単一 ID で始まる参照見出し**（`### D-3 の決定から従属的に確定する事項`）は、定義見出し
    （`### D-3 事業目的`）と字面が同型のため定義として拾う。過大に拾う方向＝ fail-closed
    （誤ブロック）であり、衝突の見逃しにはならない。複数 ID の併記で始まる参照見出し
    （`### D-31 / D-32 の決定から…`）は `extract_definitions()` の規則で除外する。

終了コード:
  0 = 衝突なし（検査が実際に走り、対象を見たうえで違反が無かった）
  1 = 衝突あり（両側で独立に採番された ID / 別ファイル間での重複定義 /
      merge-base 時点で確保済みの ID に対する定義行の増加＝再利用）
  2 = 判定不能（`git fetch` 失敗・タイムアウト・merge-base 解決不可・`git show` 失敗・
      宣言した定義元ファイルが読めない・定義元が 1 件も見つからない）。
      🔴 fail-closed（`0` に丸めない）。
      🔴 ただし **呼び出し側（`.claude/hooks/pre-pr-create-check.sh` 4.9 節）は exit 2 を
      ブロックしない**（判定器・ネットワーク側の事情で PR 作成そのものを止めないため、
      非ブロッキング警告へ降格する）。本ツール側の「0 に丸めない」宣言と、フック側の
      「exit 1 のときだけブロックする」判断は **別の格** であり矛盾しない。

使い方:
  python3 tools/check_reserved_ids.py                # fetch して検査（衝突なら exit 1）
  python3 tools/check_reserved_ids.py --no-fetch     # fetch を省略（オフライン検証用）
  python3 tools/check_reserved_ids.py --json         # 機械可読出力
  python3 tools/check_reserved_ids.py --self-test    # 検査ロジック自体の自己テスト
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from git_diff_utils import Runner, run_git_or_raise  # noqa: E402
from md_fence import fence_flags  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

OPEN_QUESTIONS = "docs/02_requirements/open-questions.md"
PRD = "docs/02_requirements/prd.md"
USER_STORY_MAP = "docs/02_requirements/user-story-map.md"
ROADMAP = "docs/02_requirements/roadmap.md"
ADR_DIR = "docs/adr"
LESSONS_DIR = "docs/rules/lessons"
LESSONS_CORE = "docs/rules/lessons-core.md"

# 種別 -> 定義元ファイル（複数可・和集合を予約とみなす）。
# `US-n` は user-story-map.md が定義元だが、prd.md 側にも定義行が置かれうるため両方を見る。
ID_SOURCES: dict[str, tuple[str, ...]] = {
    "D": (OPEN_QUESTIONS,),
    "Q": (OPEN_QUESTIONS,),
    "R": (OPEN_QUESTIONS,),
    "US": (PRD, USER_STORY_MAP),
    "AC": (PRD,),
    "AR": (PRD,),
    "NFR": (PRD,),
    "GR": (PRD,),
    "TR": (PRD,),
    "FR": (PRD,),
    "A": (USER_STORY_MAP,),
    "E": (USER_STORY_MAP,),
    "SP": (USER_STORY_MAP,),
    "S": (USER_STORY_MAP,),
    "M": (ROADMAP,),
}

# 複数の定義元ファイルに定義行が置かれることを **許す** 種別（`ID_SOURCES` の宣言と
# `find_duplicates()` の判定を一致させるための明示・PR #1044 レビュー指摘）。
# `US-n` は `user-story-map.md` が正本だが `prd.md` 側にもトレーサビリティ行が置かれうるため、
# 別ファイル間の再掲を違反にしない（同一ファイル内での二重定義は種別を問わず違反のまま）。
MULTI_SOURCE_KINDS: frozenset[str] = frozenset({"US"})

# `--remote-ref` に許す文字（`git show <ref>:<path>` の位置引数へ渡るため、
# `-` 始まりのオプション偽装と `..` によるレンジ指定を弾く）。
REMOTE_REF_RE = re.compile(r"[A-Za-z0-9._/-]+")

# git の stderr に載りうる資格情報付き remote URL（`https://user:token@host/...`）のマスク。
CREDENTIAL_IN_URL_RE = re.compile(r"://[^/@\s]+@")

# `git fetch` は本ツール唯一のネットワーク I/O。外部の `timeout` コマンドに依存せず
# 自前で上限を持つ（フック側が `timeout` 不在環境で無限に待つのを防ぐ・PR #1044 レビュー指摘）。
GIT_TIMEOUT_SECONDS = 45

# ADR は Markdown 本文でなくファイル名（`0013-foo.md`）で番号を確保する。
ADR_FILE_RE = re.compile(r"^(\d{3,4})-[^/]*\.md$")

# 表の第 1 セル / 見出しの先頭にある ID。装飾（`**` / バッククォート）は剥がしてから判定する。
LEADING_ID_RE = re.compile(r"^([A-Z]{1,3})-(\d+)\b")
# 先頭 ID から始まる「併記トークン列」（`D-5 / D-7`・`D-5、D-7`）。ここで切り出した範囲だけを
# 走査対象にする（第 1 セル / 見出し **全体** を走査すると参照 ID まで定義として予約するため）。
LEADING_ID_RUN_RE = re.compile(r"^[A-Z]{1,3}-\d+(?:\s*[/、,]\s*[A-Z]{1,3}-\d+)*")
ID_IN_TEXT_RE = re.compile(r"(?<![A-Za-z])([A-Z]{1,3})-(\d+)\b")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
DECORATION_CHARS = "*`_ 「【[（("


def lesson_source_paths(paths: list[str]) -> list[str]:
    """`L-n` の定義元とみなすパスだけを返す（境界の外側を混ぜないための判定・#256）。

    含む: `docs/rules/lessons/<name>.md`（直下のみ）・`docs/rules/lessons-core.md`
    含まない: `docs/rules/lessons-management.md`（運用ルールであり定義元ではない）・
              `docs/rules-old/lessons/*.md`（別ディレクトリの近似パス）
    """
    out = []
    for p in paths:
        if p == LESSONS_CORE:
            out.append(p)
            continue
        prefix = LESSONS_DIR + "/"
        if p.startswith(prefix) and "/" not in p[len(prefix) :] and p.endswith(".md"):
            out.append(p)
    return out


def strip_decoration(cell: str) -> str:
    return cell.strip().lstrip(DECORATION_CHARS).strip()


def extract_definition_lists(text: str, kinds: tuple[str, ...]) -> dict[str, list[int]]:
    """`extract_definitions()` の重複を保った版（同一ファイル内の再定義検出に使う）。

    定義行 1 行につき 1 要素（併記は要素が増える）を積む。同じ番号が 2 行に現れれば
    リストにも 2 回現れるため、呼び出し側は「同一ファイル内での二重定義」を検出できる。

    定義とみなすのは次の 2 形だけ:
      - 表の第 1 セルが対象種別の ID で始まる行（`| **D-5 / D-7** | ...` のような併記は
        第 1 セル内の同種別 ID を全て拾う）
      - 見出しが対象種別の ID で始まる行（`## L-131: ...`）

    🔴 走査範囲は **先頭 ID から始まる併記トークン列**（`LEADING_ID_RUN_RE`）に限定する。
    第 1 セル / 見出し全体を走査すると、後続の散文に現れる **参照** ID まで定義として
    予約してしまう（`| **D-12**（旧 kindD-7） |` の `D-7` 等）。
    さらに **併記（2 個以上）の直後に散文が続く行は定義とみなさない**。実データの
    `### D-31 / D-32 の決定から従属的に確定する事項` は複数の既存決定を参照する見出しであり、
    これを定義扱いすると「ブランチは何も採番していないのに衝突」と誤判定する。
    コードフェンス内の行は除外する（例示を予約とみなさないため）。
    """
    found: dict[str, list[int]] = {k: [] for k in kinds}
    lines = text.splitlines()
    flags = fence_flags(lines)
    for line, in_fence in zip(lines, flags):
        if in_fence:
            continue
        head_text: str | None = None
        m = HEADING_RE.match(line)
        if m:
            head_text = m.group(1)
        elif line.lstrip().startswith("|"):
            cells = line.strip().strip("|").split("|")
            if cells:
                head_text = cells[0]
        if head_text is None:
            continue
        stripped = strip_decoration(head_text)
        lead = LEADING_ID_RE.match(stripped)
        if not lead or lead.group(1) not in found:
            continue
        kind = lead.group(1)
        run_match = LEADING_ID_RUN_RE.match(stripped)
        if run_match is None:  # pragma: no cover - LEADING_ID_RE が通れば必ず一致する
            continue
        run = run_match.group(0)
        rest = stripped[run_match.end() :].strip(DECORATION_CHARS).strip()
        ids = [(k2, num) for k2, num in ID_IN_TEXT_RE.findall(run) if k2 == kind]
        if len(ids) > 1 and rest:
            # 併記 + 後続の散文 = 既存 ID の参照見出し（定義ではない）
            continue
        for _k2, num in ids:
            found[kind].append(int(num))
    return found


def extract_definitions(text: str, kinds: tuple[str, ...]) -> dict[str, set[int]]:
    """1 ファイルの本文から「定義」として扱う ID を集合で返す（規則は上の関数の docstring）。"""
    return {k: set(v) for k, v in extract_definition_lists(text, kinds).items()}


def extract_adr_numbers(names: list[str]) -> set[int]:
    """`docs/adr/` のファイル名一覧から ADR 番号を抽出する。"""
    out: set[int] = set()
    for name in names:
        base = name.rsplit("/", 1)[-1]
        m = ADR_FILE_RE.match(base)
        if m:
            out.add(int(m.group(1)))
    return out


class Undetermined(Exception):
    """判定不能（exit 2）。"""


def mask_credentials(msg: str) -> str:
    """git の stderr に載りうる資格情報付き remote URL をマスクする。

    `https://x-access-token:<token>@github.com/...` がフックの additionalContext や
    ログへそのまま流れるのを防ぐ（本ツールの例外メッセージは全てここを通す）。
    """
    return CREDENTIAL_IN_URL_RE.sub("://***@", msg)


def _with_timeout(runner: Runner, timeout: float) -> Runner:
    """`runner` に自前の timeout を注入する（`run_git_or_raise` は timeout を渡さないため）。

    共有ヘルパー（`git_diff_utils.run_git_or_raise`）の挙動は変えずに、本ツールの
    呼び出しだけへ上限を掛ける。超過時の `subprocess.TimeoutExpired` は `_git()` が
    `Undetermined`（exit 2）へ写す。
    """

    def wrapped(args, **kwargs):  # noqa: ANN001, ANN003
        kwargs.setdefault("timeout", timeout)
        return runner(args, **kwargs)

    return wrapped


def _git(args: list[str], cwd: Path, runner: Runner) -> str:
    try:
        return run_git_or_raise(args, cwd, runner=_with_timeout(runner, GIT_TIMEOUT_SECONDS))
    except subprocess.TimeoutExpired as e:
        raise Undetermined(
            f"git {' '.join(args)} が {GIT_TIMEOUT_SECONDS} 秒でタイムアウトした"
        ) from e
    except RuntimeError as e:
        raise Undetermined(mask_credentials(str(e))) from e


def _read_local(repo_root: Path, path: str) -> str:
    f = repo_root / path
    if not f.is_file():
        raise Undetermined(f"定義元ファイルが作業ツリーに存在しない: {path}")
    return f.read_text(encoding="utf-8", errors="replace")


def _list_local_adr(repo_root: Path) -> list[str]:
    d = repo_root / ADR_DIR
    if not d.is_dir():
        raise Undetermined(f"ADR ディレクトリが作業ツリーに存在しない: {ADR_DIR}")
    return sorted(p.name for p in d.iterdir() if p.is_file())


def _list_local_lessons(repo_root: Path) -> list[str]:
    candidates: list[str] = []
    d = repo_root / LESSONS_DIR
    if d.is_dir():
        candidates.extend(f"{LESSONS_DIR}/{p.name}" for p in sorted(d.iterdir()) if p.is_file())
    if (repo_root / LESSONS_CORE).is_file():
        candidates.append(LESSONS_CORE)
    return lesson_source_paths(candidates)


def _list_rev_files(rev: str, prefix: str, cwd: Path, runner: Runner) -> list[str]:
    out = _git(["ls-tree", "--name-only", rev, "--", f"{prefix}/"], cwd, runner)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _path_exists_at_rev(rev: str, path: str, cwd: Path, runner: Runner) -> bool:
    """`rev` にそのパスが存在するか。`ls-tree` 自体の失敗は `Undetermined` として上へ抜ける。"""
    out = _git(["ls-tree", "--name-only", rev, "--", path], cwd, runner)
    return any(line.strip() == path for line in out.splitlines())


def _show(rev: str, path: str, cwd: Path, runner: Runner) -> str | None:
    """`rev` 側のファイル内容。存在しなければ None（その rev 時点では未作成 = 予約ゼロ）。

    🔴 **存在確認と読み取りを分ける**（PR #1044 レビュー指摘・fail-open の修正）。
    以前は `git show` の失敗を種類を問わず `None`（＝予約ゼロ）へ丸めていたため、
    partial clone のオンデマンド取得失敗・オブジェクト破損で `show` が落ちると、
    真の ID 衝突があっても「✅ 衝突なし」で exit 0 を返していた（無音の fail-open）。
    存在するときだけ `show` し、`show` の失敗は `Undetermined` として exit 2 に倒す。
    """
    if not _path_exists_at_rev(rev, path, cwd, runner):
        return None
    return _git(["show", f"{rev}:{path}"], cwd, runner)


def collect_ids_at_rev(
    rev: str, cwd: Path, runner: Runner
) -> tuple[dict[str, set[int]], dict[str, list[tuple[int, str]]]]:
    """指定 rev 時点で確保されている ID と、(番号, 定義元パス) の一覧を種別ごとに集める。

    一覧は **定義行ごとに 1 要素**（重複を保つ）。作業ツリー側の同じ一覧と件数を突き合わせて
    「既に確保済みの ID に対して定義行を増やした（再利用）」を検出するために使う。
    """
    result: dict[str, set[int]] = {k: set() for k in ID_SOURCES}
    result["L"] = set()
    result["ADR"] = set()
    occurrences: dict[str, list[tuple[int, str]]] = {k: [] for k in result}

    by_file: dict[str, list[str]] = {}
    for kind, paths in ID_SOURCES.items():
        for p in paths:
            by_file.setdefault(p, []).append(kind)

    for path, kinds in by_file.items():
        text = _show(rev, path, cwd, runner)
        if text is None:
            continue
        for kind, nums in extract_definition_lists(text, tuple(kinds)).items():
            result[kind] |= set(nums)
            occurrences[kind].extend((n, path) for n in nums)

    for path in lesson_source_paths(
        _list_rev_files(rev, LESSONS_DIR, cwd, runner) + [LESSONS_CORE]
    ):
        text = _show(rev, path, cwd, runner)
        if text is None:
            continue
        nums = extract_definition_lists(text, ("L",))["L"]
        result["L"] |= set(nums)
        occurrences["L"].extend((n, path) for n in nums)

    for name in _list_rev_files(rev, ADR_DIR, cwd, runner):
        for n in extract_adr_numbers([name]):
            result["ADR"].add(n)
            occurrences["ADR"].append((n, name))
    return result, occurrences


def collect_ids_local(repo_root: Path) -> tuple[dict[str, set[int]], dict[str, list[tuple[int, str]]]]:
    """作業ツリー側の ID と、重複検出用の (番号, 定義元パス) 一覧を返す。"""
    result: dict[str, set[int]] = {k: set() for k in ID_SOURCES}
    result["L"] = set()
    result["ADR"] = set()
    occurrences: dict[str, list[tuple[int, str]]] = {k: [] for k in result}

    by_file: dict[str, list[str]] = {}
    for kind, paths in ID_SOURCES.items():
        for p in paths:
            by_file.setdefault(p, []).append(kind)

    for path, kinds in by_file.items():
        text = _read_local(repo_root, path)
        for kind, nums in extract_definition_lists(text, tuple(kinds)).items():
            result[kind] |= set(nums)
            occurrences[kind].extend((n, path) for n in nums)

    for path in _list_local_lessons(repo_root):
        nums = extract_definition_lists(_read_local(repo_root, path), ("L",))["L"]
        result["L"] |= set(nums)
        occurrences["L"].extend((n, path) for n in nums)

    for name in _list_local_adr(repo_root):
        for n in extract_adr_numbers([name]):
            result["ADR"].add(n)
            occurrences["ADR"].append((n, f"{ADR_DIR}/{name}"))

    return result, occurrences


def find_duplicates(occurrences: dict[str, list[tuple[int, str]]]) -> list[dict[str, object]]:
    """同じ ID が 2 つ以上の **別ファイル** で定義されている状態を検出する。

    各要素（1 つ 1 つの定義行）は妥当でも、集合としての一意性が壊れている負ケース（#896）。

    🔴 `MULTI_SOURCE_KINDS`（`ID_SOURCES` が複数の定義元を宣言した種別）は除外する。
    宣言と判定が矛盾していると、ID 衝突が無いのに全 PR がブロックされる（PR #1044 指摘 (a)）。

    🔵 同一ファイル内の重複は **ここでは扱わない**。本リポジトリの実データでは 1 つの ID を
    「節見出し」と「決定ログの表の行」の両方で書く形が標準（実測: `open-questions.md` の
    `D-3` 等・`roadmap.md` の `M-1`〜`M-6`）で、一律に違反とすると全 PR が誤ブロックされる。
    既に確保済みの ID へ **新たに定義行を増やした** 場合（fail-open だった経路・指摘 (b)）は
    `find_reused_ids()` が merge-base との件数差で検出する。
    """
    dups: list[dict[str, object]] = []
    for kind, items in occurrences.items():
        if kind in MULTI_SOURCE_KINDS:
            continue
        by_num: dict[int, set[str]] = {}
        for num, path in items:
            by_num.setdefault(num, set()).add(path)
        for num, paths in sorted(by_num.items()):
            if len(paths) > 1:
                dups.append({"kind": kind, "number": num, "paths": sorted(paths)})
    return dups


def find_reused_ids(
    local_occurrences: dict[str, list[tuple[int, str]]],
    base_occurrences: dict[str, list[tuple[int, str]]],
) -> list[dict[str, object]]:
    """merge-base 時点で **既に確保済み** の ID へ定義行を増やした状態を検出する。

    `main` 側との差分比較（`added_local & added_main`）は「両側で **新規** に採番した ID」しか
    見ないため、「merge-base 時点で既にある `D-30` を、stale な手元 grep を元にブランチが同じ
    ファイルへ 2 行目として追記する」経路が exit 0 で素通りしていた（PR #1044 指摘 (b)）。
    定義行の **件数** を merge-base と突き合わせ、既存 ID の件数が増えていれば違反とする
    （もともと複数行で書かれている ID の件数が変わらない限り発火しない＝実データで誤検知しない）。
    """
    out: list[dict[str, object]] = []
    for kind, items in sorted(local_occurrences.items()):
        local_counts: dict[int, int] = {}
        local_paths: dict[int, list[str]] = {}
        for num, path in items:
            local_counts[num] = local_counts.get(num, 0) + 1
            local_paths.setdefault(num, []).append(path)
        base_counts: dict[int, int] = {}
        for num, _path in base_occurrences.get(kind, []):
            base_counts[num] = base_counts.get(num, 0) + 1
        for num in sorted(local_counts):
            base_n = base_counts.get(num, 0)
            if base_n == 0:  # 新規採番は衝突判定（added_local & added_main）の担当
                continue
            if local_counts[num] > base_n:
                out.append(
                    {
                        "kind": kind,
                        "number": num,
                        "paths": sorted(set(local_paths[num])),
                        "base_count": base_n,
                        "local_count": local_counts[num],
                    }
                )
    return out


def next_free(*id_maps: dict[str, set[int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    kinds = set()
    for m in id_maps:
        kinds |= set(m)
    for kind in sorted(kinds):
        used: set[int] = set()
        for m in id_maps:
            used |= m.get(kind, set())
        out[kind] = (max(used) + 1) if used else 1
    return out


def run_check(
    *,
    repo_root: Path,
    fetch: bool,
    remote_ref: str,
    runner: Runner,
) -> tuple[int, dict[str, object]]:
    """本判定。戻り値は (終了コード, レポート)。"""
    # `--remote-ref` は `git show <ref>:<path>` の位置引数へ渡る。`-` 始まりの値は git の
    # オプションとして解釈され、`..` はレンジ指定になるため、判定不能（exit 2）で弾く。
    if (
        not REMOTE_REF_RE.fullmatch(remote_ref)
        or remote_ref.startswith("-")
        or ".." in remote_ref
    ):
        raise Undetermined(f"--remote-ref の値が不正: {remote_ref!r}")

    if fetch:
        _git(["fetch", "origin", "main"], repo_root, runner)

    merge_base = _git(["merge-base", remote_ref, "HEAD"], repo_root, runner).strip()
    if not merge_base:
        raise Undetermined(f"merge-base({remote_ref}, HEAD) を解決できない")

    main_ids, _main_occ = collect_ids_at_rev(remote_ref, repo_root, runner)
    base_ids, base_occ = collect_ids_at_rev(merge_base, repo_root, runner)
    # rev 側も「対象 0 件は fail-closed」（作業ツリー側と同じ扱い）。ここが 0 件のまま進むと
    # `added_main` が空になり、真の衝突を「衝突なし」として見逃す（fail-open）。
    for label, ids in ((remote_ref, main_ids), (f"merge-base({merge_base})", base_ids)):
        if sum(len(v) for v in ids.values()) == 0:
            raise Undetermined(
                f"{label} 側で ID 定義が 1 件も見つからなかった（定義元の選択・rev の解決が壊れている可能性）"
            )

    local_ids, occurrences = collect_ids_local(repo_root)

    total_local = sum(len(v) for v in local_ids.values())
    if total_local == 0:
        # 対象 0 件は fail-closed（定義元の選択が壊れているのか本当に 0 件かを区別できない）。
        raise Undetermined("作業ツリー側で ID 定義が 1 件も見つからなかった（定義元の選択が壊れている可能性）")

    collisions: list[dict[str, object]] = []
    for kind in sorted(local_ids):
        added_local = local_ids[kind] - base_ids.get(kind, set())
        # `- base_ids` は意味上の明示（`added_local` は base を含まないため、この差集合を
        # 外しても結果は変わらない＝等価変異。読み手に「両側の新規採番同士の比較」だと示すために残す）。
        added_main = main_ids.get(kind, set()) - base_ids.get(kind, set())
        for num in sorted(added_local & added_main):
            collisions.append({"kind": kind, "number": num})

    duplicates = find_duplicates(occurrences)
    reused = find_reused_ids(occurrences, base_occ)
    report: dict[str, object] = {
        "merge_base": merge_base,
        "remote_ref": remote_ref,
        "collisions": collisions,
        "duplicates": duplicates,
        "reused": reused,
        "next_free": next_free(main_ids, base_ids, local_ids),
    }
    return (1 if (collisions or duplicates or reused) else 0), report


def format_next_free(kind: str, num: int) -> str:
    """「次の空き番号」の 1 行表記。

    🔴 ADR は Markdown 本文ではなく **ファイル名**（`ADR_FILE_RE` = `^(\\d{3,4})-`）で番号を
    確保するため、`ADR-17` と出すと出力どおりに `docs/adr/17-foo.md` を作られ、予約として
    認識されないファイル名が生まれる（次セッションが同じ番号を再提示して ADR が二重になる）。
    4 桁ゼロ埋めとファイル名例を併記する。
    """
    if kind == "ADR":
        return f"ADR-{num:04d}（ファイル名: docs/adr/{num:04d}-<slug>.md）"
    return f"{kind}-{num}"


def _print_report(report: dict[str, object], code: int) -> None:
    collisions = report["collisions"]
    duplicates = report["duplicates"]
    if code == 0:
        print("✅ ID 衝突なし（origin/main で確保済みの ID との突き合わせ完了）")
    for c in collisions:  # type: ignore[union-attr]
        print(
            f"❌ ID 衝突: {c['kind']}-{c['number']} は origin/main 側でも新規に確保されている"
            "（別セッションの採番と衝突）",
            file=sys.stderr,
        )
    for d in duplicates:  # type: ignore[union-attr]
        print(
            f"❌ ID 重複定義: {d['kind']}-{d['number']} が複数ファイルで定義されている: "
            + ", ".join(d["paths"]),  # type: ignore[arg-type]
            file=sys.stderr,
        )
    for r in report.get("reused", []):  # type: ignore[union-attr]
        print(
            f"❌ ID 再利用: {r['kind']}-{r['number']} は merge-base 時点で既に確保済みなのに"
            f"定義行が {r['base_count']} → {r['local_count']} 件に増えている: "
            + ", ".join(r["paths"]),  # type: ignore[arg-type]
            file=sys.stderr,
        )
    print("\n次の空き番号（採番表の生成に使う）:")
    for kind, num in sorted(report["next_free"].items()):  # type: ignore[union-attr]
        print(f"  {format_next_free(kind, int(num))}")  # type: ignore[arg-type]


def main(argv: list[str] | None = None, runner: Runner = subprocess.run) -> int:
    parser = argparse.ArgumentParser(description="origin/main で確保済みの ID との衝突を検査する")
    parser.add_argument("--no-fetch", action="store_true", help="git fetch を省略する（オフライン検証用）")
    parser.add_argument("--json", action="store_true", help="機械可読出力")
    parser.add_argument("--remote-ref", default="origin/main", help="比較対象の ref（既定: origin/main）")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="リポジトリルート（self-test 用）")
    parser.add_argument("--self-test", action="store_true", help="検査ロジック自体の自己テスト")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    try:
        code, report = run_check(
            repo_root=Path(args.repo_root),
            fetch=not args.no_fetch,
            remote_ref=args.remote_ref,
            runner=runner,
        )
    except Undetermined as e:
        print(f"⚠️ 判定不能: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({"undetermined": str(e)}, ensure_ascii=False))
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report, code)
    return code


# --------------------------------------------------------------------------- self-test
# 実 git・ネットワークに依存しない（runner を差し替え、作業ツリーは tmpdir で組み立てる）。

_FAKE_CALLS: list[list[str]] = []
_FAKE_TIMEOUTS: list[object] = []


class _FakeResult:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def _make_fake_runner(
    responses: dict[tuple[str, ...], str],
    fail: set[tuple[str, ...]] | None = None,
    *,
    fail_stderr: str = "boom",
    timeout_on: set[tuple[str, ...]] | None = None,
) -> Runner:
    """argv を `_FAKE_CALLS` に記録する fake runner（終了コードだけ差し替える fake にしない・#710）。

    🔴 「パスが存在しない」と「git コマンドが失敗した」を **別状態** として再現できること
    （PR #1044 レビュー指摘の fail-open を self-test で突くための必須要件）:
      - 存在しないパス: `ls-tree` の応答を空文字列で登録する（`_show` は `None` を返す）
      - git の失敗:     `fail` に載せる（`CalledProcessError` → `Undetermined` → exit 2）
      - タイムアウト:   `timeout_on` に載せる（`subprocess.TimeoutExpired` → exit 2）
    未登録のコマンドは「登録漏れ」として失敗させる（黙って「存在しない」に丸めない）。
    """
    fail = fail or set()
    timeout_on = timeout_on or set()

    def runner(args, **kwargs):  # noqa: ANN001, ANN003
        _FAKE_CALLS.append(list(args))
        _FAKE_TIMEOUTS.append(kwargs.get("timeout"))
        key = tuple(args)
        if key in timeout_on:
            raise subprocess.TimeoutExpired(list(args), kwargs.get("timeout") or 0)
        if key in fail:
            raise subprocess.CalledProcessError(1, args, output="", stderr=fail_stderr)
        if key not in responses:
            raise subprocess.CalledProcessError(
                128, args, output="", stderr="fake runner: 未登録のコマンド"
            )
        return _FakeResult(stdout=responses[key])

    return runner


_MAIN_OPEN_Q = "| **D-25** | 決定 A |\n| **D-26** | 決定 B |\n"
_BASE_OPEN_Q = "| **D-25** | 決定 A |\n"
_LOCAL_OPEN_Q = "| **D-25** | 決定 A |\n| **D-26** | 別セッションと衝突する決定 |\n"
_PRD = "| **NFR-1** | 要件 |\n| `AC-1` 受け入れ基準 | x |\n"
_USM = "| **US-1** | ストーリー |\n| **SP-11** | スプリント |\n"
_ROADMAP = "| **M-1** | マイルストーン |\n"
_LESSON = "## L-131: 教訓\n本文\n"


def _write_worktree(
    root: Path,
    open_q: str,
    *,
    extra_lesson: str | None = None,
    prd: str | None = None,
    usm: str | None = None,
    adr_files: tuple[str, ...] = ("0013-foo.md",),
) -> None:
    (root / "docs/02_requirements").mkdir(parents=True, exist_ok=True)
    (root / "docs/adr").mkdir(parents=True, exist_ok=True)
    (root / "docs/rules/lessons").mkdir(parents=True, exist_ok=True)
    (root / OPEN_QUESTIONS).write_text(open_q, encoding="utf-8")
    (root / PRD).write_text(_PRD if prd is None else prd, encoding="utf-8")
    (root / USER_STORY_MAP).write_text(_USM if usm is None else usm, encoding="utf-8")
    (root / ROADMAP).write_text(_ROADMAP, encoding="utf-8")
    (root / f"{LESSONS_DIR}/session-safety.md").write_text(_LESSON, encoding="utf-8")
    (root / LESSONS_CORE).write_text("## L-077: 教訓\n", encoding="utf-8")
    for name in adr_files:
        (root / f"{ADR_DIR}/{name}").write_text("# ADR\n", encoding="utf-8")
    if extra_lesson is not None:
        (root / f"{LESSONS_DIR}/pr-review.md").write_text(extra_lesson, encoding="utf-8")


def _rev_responses(
    rev: str, open_q: str, adr: list[str], *, missing: tuple[str, ...] = ()
) -> dict[tuple[str, ...], str]:
    """rev 側の `ls-tree`（存在確認）と `show`（読み取り）の応答を組み立てる。

    `missing` に挙げたパスは「その rev に存在しない」状態（`ls-tree` が空を返し、
    `show` は登録しない）として再現する。
    """
    contents = {
        OPEN_QUESTIONS: open_q,
        PRD: _PRD,
        USER_STORY_MAP: _USM,
        ROADMAP: _ROADMAP,
        f"{LESSONS_DIR}/session-safety.md": _LESSON,
        LESSONS_CORE: "## L-077: 教訓\n",
    }
    r: dict[tuple[str, ...], str] = {
        ("git", "ls-tree", "--name-only", rev, "--", f"{LESSONS_DIR}/"): (
            f"{LESSONS_DIR}/session-safety.md\n"
            if f"{LESSONS_DIR}/session-safety.md" not in missing
            else ""
        ),
        ("git", "ls-tree", "--name-only", rev, "--", f"{ADR_DIR}/"): "".join(
            f"{ADR_DIR}/{n}\n" for n in adr
        ),
    }
    for path, text in contents.items():
        exists = path not in missing
        r[("git", "ls-tree", "--name-only", rev, "--", path)] = f"{path}\n" if exists else ""
        if exists:
            r[("git", "show", f"{rev}:{path}")] = text
    return r


def _build_runner(
    *,
    main_open_q: str,
    base_open_q: str,
    main_adr: list[str],
    base_adr: list[str],
    missing: tuple[str, ...] = (),
    show_fails: set[tuple[str, ...]] | None = None,
) -> Runner:
    responses: dict[tuple[str, ...], str] = {
        ("git", "fetch", "origin", "main"): "",
        ("git", "merge-base", "origin/main", "HEAD"): "abc1234\n",
    }
    responses.update(_rev_responses("origin/main", main_open_q, main_adr, missing=missing))
    responses.update(_rev_responses("abc1234", base_open_q, base_adr, missing=missing))
    return _make_fake_runner(responses, fail=show_fails)


def _run_main_capture(root: Path, runner: Runner, extra: list[str] | None = None) -> tuple[int, str]:
    """self-test から `main()` を経由して (終了コード, stdout) を得る。"""
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = main(["--repo-root", str(root), *(extra or [])], runner=runner)
    return code, buf.getvalue()


def _run_main(root: Path, runner: Runner, extra: list[str] | None = None) -> int:
    """self-test から `main()` を経由して終了コードまで貫通させる（出力は捨てる）。"""
    return _run_main_capture(root, runner, extra)[0]


def run_self_test() -> int:  # noqa: C901
    import tempfile

    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # 1: 抽出ロジック（表の第 1 セル / 見出し / 併記 / 装飾）
    d = extract_definitions("| **D-5 / D-7** | 併記 |\n| **D-9** | 単独 |\n", ("D",))
    check(d["D"] == {5, 7, 9}, f"1: 併記セルの抽出に失敗: {d}")
    d = extract_definitions("| `AC-1` 受け入れ基準 | x |\n", ("AC",))
    check(d["AC"] == {1}, f"1-b: バッククォート装飾の第 1 セルを拾えない: {d}")
    d = extract_definitions("## L-131: 教訓\n", ("L",))
    check(d["L"] == {131}, f"1-c: 見出し定義を拾えない: {d}")
    # ゼロ埋め表記
    d = extract_definitions("| **D-007** | ゼロ埋め |\n", ("D",))
    check(d["D"] == {7}, f"1-d: ゼロ埋め番号を正規化できない: {d}")
    # 1-e: 正ケース（併記）と対にする負ケース。第 1 セル **全体** を走査すると、後続の散文に
    # 現れる近似 ID（`kindD-7`）まで定義として予約してしまう（走査範囲を先頭の併記列に限定
    # していることの回帰テスト）。
    d = extract_definitions("| **D-12 / D-13** | 併記 |\n", ("D",))
    check(d["D"] == {12, 13}, f"1-e: 併記の正ケースが壊れた: {d}")
    d = extract_definitions("| **D-12**（旧 kindD-7） | x |\n", ("D",))
    check(d["D"] == {12}, f"1-e-neg: 第 1 セル後半の近似 ID を定義扱いした: {d}")
    # 1-f: 第 1 セル後半に **正規の書式** の参照 ID が続く形（後読み否定では防げず、
    # 走査範囲の限定だけが効く）。ここが緩むと参照 ID まで予約され、他ブランチが
    # 正当に採番しただけで偽の衝突としてブロックされる。
    d = extract_definitions("| **D-12**（旧 D-7 は欠番） | x |\n", ("D",))
    check(d["D"] == {12}, f"1-f: 第 1 セル後半の参照 ID を定義扱いした（走査範囲が広い）: {d}")
    d = extract_definitions("## L-131: 教訓（L-77 の姉妹則）\n", ("L",))
    check(d["L"] == {131}, f"1-g: 見出し後半の参照 ID を定義扱いした（走査範囲が広い）: {d}")

    # 2: 定義とみなさないもの（参照・フェンス内例示・複合 ID）
    d = extract_definitions("| **M-1** | 説明 | `SP-1` / `D-11` |\n", ("D", "SP", "M"))
    check(d["D"] == set() and d["SP"] == set() and d["M"] == {1}, f"2: 第 2 セル以降を定義扱いした: {d}")
    d = extract_definitions("```\n| **D-99** | 例示 |\n```\n", ("D",))
    check(d["D"] == set(), f"2-b: コードフェンス内の例示を予約扱いした: {d}")
    d = extract_definitions("| **SD-1** | 別 ID 体系 |\n", ("D",))
    check(d["D"] == set(), f"2-c: 複合 ID `SD-1` を `D-1` と誤検出: {d}")
    d = extract_definitions("散文中の D-42 への言及\n", ("D",))
    check(d["D"] == set(), f"2-d: 散文中の参照を定義扱いした: {d}")
    # 2-e: 実在書式の参照見出し（併記 + 後続の散文）は定義ではない。上の 1（併記の正ケース
    # `| **D-5 / D-7** |` → {5,7}）と **対** で、走査範囲の限定と参照見出しの除外を同時に固定する。
    d = extract_definitions("### D-31 / D-32 の決定から従属的に確定する事項\n", ("D",))
    check(d["D"] == set(), f"2-e: 併記の参照見出しを定義扱いした（誤ブロックの原因）: {d}")

    # 2-f: 定義行ごとの重複を保つ抽出（同一ファイル内の二重定義の検出に使う）
    lists = extract_definition_lists("| **D-25** | A |\n| **D-25** | 再掲 |\n", ("D",))
    check(lists["D"] == [25, 25], f"2-f: 同一ファイル内の重複が潰れている: {lists}")

    # 3: 境界の外側の負ケース（lessons の定義元判定）
    got = lesson_source_paths(
        [
            f"{LESSONS_DIR}/session-safety.md",
            LESSONS_CORE,
            "docs/rules/lessons-management.md",
            "docs/rules-old/lessons/x.md",
            f"{LESSONS_DIR}/sub/deep.md",
        ]
    )
    check(
        got == [f"{LESSONS_DIR}/session-safety.md", LESSONS_CORE],
        f"3: lessons 定義元の境界判定が誤り: {got}",
    )

    # 4: ADR 番号抽出（近似だが別カテゴリの負ケースを対にする）
    check(extract_adr_numbers(["0013-foo.md"]) == {13}, "4: ADR 番号を抽出できない")
    # 近似だが別カテゴリであるべき入力（前方一致でない番号・接頭辞付き・桁不足）を正ケースと対にする
    check(
        extract_adr_numbers(["README.md", "notes-0013.md", "draft-0013-foo.md", "13-foo.md"]) == set(),
        "4-b: ADR 以外のファイル名を番号扱いした（先頭一致でない `draft-0013-foo.md` を含む）",
    )
    # 4-c: 桁不足のファイル名は予約として認識されない ＝ 次番号をゼロ埋めなしで出すと、
    # 出力どおり採番した ADR が本ツールから見えなくなる（同じ番号が二重に配られる）。
    check(extract_adr_numbers(["17-foo.md"]) == set(), "4-c: 桁不足のファイル名を ADR 番号扱いした")
    fmt = format_next_free("ADR", 17)
    check(
        "ADR-0017" in fmt and "0017-<slug>.md" in fmt,
        f"4-d: ADR の次番号がゼロ埋め + ファイル名例になっていない: {fmt}",
    )
    check(format_next_free("D", 17) == "D-17", f"4-e: ADR 以外の書式が変わった: {format_next_free('D', 17)}")

    # 5: main() 経由の衝突検出（PR #254 の再現: main に D-26 があるのに作業ブランチも D-26 を追加）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _LOCAL_OPEN_Q)
        _FAKE_CALLS.clear()
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q,
            base_open_q=_BASE_OPEN_Q,
            main_adr=["0013-foo.md"],
            base_adr=["0013-foo.md"],
        )
        code = _run_main(root, runner)
        check(code == 1, f"5: 衝突を exit 1 にできない（実際: {code}）")
        # fake runner の argv 検証（#710）: main() の経路から意図した git が実際に呼ばれている
        joined = [" ".join(c) for c in _FAKE_CALLS]
        check("git fetch origin main" in joined, f"5-b: git fetch が呼ばれていない: {joined[:4]}")
        check("git merge-base origin/main HEAD" in joined, f"5-c: merge-base が呼ばれていない: {joined[:4]}")
        check(
            any(c[:2] == ["git", "show"] and c[2].startswith("origin/main:") for c in _FAKE_CALLS),
            "5-d: origin/main 側の git show が呼ばれていない",
        )
        check(
            any(c[:3] == ["git", "ls-tree", "--name-only"] and "--" in c for c in _FAKE_CALLS),
            "5-e: ls-tree の pathspec 区切り `--` が省略されている",
        )
        # 5-f: すべての git 呼び出しに自前の timeout が渡っている（外部 `timeout` コマンド
        # 不在環境でフックがハングしないための境界）
        check(
            bool(_FAKE_TIMEOUTS) and all(t == GIT_TIMEOUT_SECONDS for t in _FAKE_TIMEOUTS),
            f"5-f: git 呼び出しに自前 timeout が渡っていない: {set(_FAKE_TIMEOUTS)}",
        )
        # 5-g: 存在確認（ls-tree）を経由してから show している（show 失敗を「パス不在」に
        # 丸めないための分離。指定パスの ls-tree が呼ばれていなければ分離が消えている）
        check(
            any(
                c[:3] == ["git", "ls-tree", "--name-only"] and c[-1] == OPEN_QUESTIONS
                for c in _FAKE_CALLS
            ),
            "5-h: パス単位の存在確認（ls-tree <rev> -- <path>）が呼ばれていない",
        )

    # 6: 衝突なし（ブランチが D-27 を採番、main は D-26 を追加）→ exit 0 と次番号
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _BASE_OPEN_Q + "| **D-27** | 別番号 |\n")
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q,
            base_open_q=_BASE_OPEN_Q,
            main_adr=["0013-foo.md"],
            base_adr=["0013-foo.md"],
        )
        code = _run_main(root, runner)
        check(code == 0, f"6: 衝突なしで exit 0 にならない（実際: {code}）")
        _, report = run_check(repo_root=root, fetch=False, remote_ref="origin/main", runner=runner)
        nf = report["next_free"]  # type: ignore[index]
        check(nf["D"] == 28, f"6-b: 次の空き番号が誤り: {nf['D']}")
        check(nf["ADR"] == 14, f"6-c: ADR の次番号が誤り: {nf['ADR']}")
        # 6-d: 出力書式（ADR はゼロ埋め + ファイル名例）。ここが崩れると、出力どおり採番した
        # ファイル名が `ADR_FILE_RE` に一致せず予約として認識されない。
        _, out = _run_main_capture(root, runner)
        check("ADR-0014（ファイル名: docs/adr/0014-<slug>.md）" in out, f"6-d: ADR 次番号の出力書式が誤り: {out}")
        check("\n  D-28\n" in out, f"6-e: ADR 以外の次番号の出力書式が変わった: {out}")

    # 6.5: ADR 番号の衝突（main が 0014 を追加、ブランチも 0014 を追加）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _BASE_OPEN_Q)
        (root / f"{ADR_DIR}/0014-branch.md").write_text("# ADR\n", encoding="utf-8")
        runner = _build_runner(
            main_open_q=_BASE_OPEN_Q,
            base_open_q=_BASE_OPEN_Q,
            main_adr=["0013-foo.md", "0014-main.md"],
            base_adr=["0013-foo.md"],
        )
        code = _run_main(root, runner)
        check(code == 1, f"6.5: ADR 番号衝突を検出できない（実際: {code}）")

    # 7: 関係性の負ケース（各定義行は妥当だが、同じ ID が別ファイルで二重定義・#896）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _BASE_OPEN_Q, extra_lesson="## L-131: 別ファイルで重複\n")
        runner = _build_runner(
            main_open_q=_BASE_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=["0013-foo.md"], base_adr=["0013-foo.md"]
        )
        code = _run_main(root, runner)
        check(code == 1, f"7: 別ファイル間の ID 重複定義を検出できない（実際: {code}）")

    # 8: 判定不能（fetch 失敗 / merge-base 失敗 / 定義元ファイル欠落）は exit 2（0 に丸めない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _BASE_OPEN_Q)
        failing = _make_fake_runner({}, fail={("git", "fetch", "origin", "main")})
        check(_run_main(root, failing) == 2, "8: fetch 失敗が exit 2 にならない")

        responses = {("git", "fetch", "origin", "main"): ""}
        no_mb = _make_fake_runner(responses, fail={("git", "merge-base", "origin/main", "HEAD")})
        check(_run_main(root, no_mb) == 2, "8-b: merge-base 失敗が exit 2 にならない")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)  # 作業ツリーが空（定義元ファイル無し）
        runner = _build_runner(
            main_open_q=_BASE_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=[], base_adr=[]
        )
        check(_run_main(root, runner) == 2, "8-c: 定義元ファイル欠落が exit 2 にならない")

    # 9: --json でも終了コードは同じ（出力形式が判定を変えない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _LOCAL_OPEN_Q)
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=[], base_adr=[]
        )
        check(_run_main(root, runner, ["--json"]) == 1, "9: --json で衝突の exit 1 が失われる")

    # 10: `git show` の 2 状態を **別ケース** として固定する（fail-open の回帰テスト）
    # 10-a: パス不在（その rev では未作成）→ 予約ゼロとして扱い exit 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _LOCAL_OPEN_Q)
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q,
            base_open_q=_BASE_OPEN_Q,
            main_adr=["0013-foo.md"],
            base_adr=["0013-foo.md"],
            missing=(OPEN_QUESTIONS,),
        )
        check(_run_main(root, runner) == 0, "10-a: rev 側にパスが無い場合は予約ゼロで exit 0 にならない")

    # 10-b: パスは存在するが `git show` が失敗 → 予約ゼロに丸めず exit 2（fail-closed）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _LOCAL_OPEN_Q)  # main と D-26 で衝突する状態
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q,
            base_open_q=_BASE_OPEN_Q,
            main_adr=["0013-foo.md"],
            base_adr=["0013-foo.md"],
            show_fails={("git", "show", f"origin/main:{OPEN_QUESTIONS}")},
        )
        check(
            _run_main(root, runner) == 2,
            "10-b: git show の失敗を予約ゼロへ丸めている（真の衝突を exit 0 で素通しする fail-open）",
        )

    # 10-c: rev 側の定義が 1 件も取れない（対象 0 件は fail-closed・作業ツリー側と同じ扱い）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _LOCAL_OPEN_Q)
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q,
            base_open_q=_BASE_OPEN_Q,
            main_adr=[],
            base_adr=[],
            missing=(
                OPEN_QUESTIONS,
                PRD,
                USER_STORY_MAP,
                ROADMAP,
                LESSONS_CORE,
                f"{LESSONS_DIR}/session-safety.md",
            ),
        )
        check(_run_main(root, runner) == 2, "10-c: rev 側 0 件が fail-closed（exit 2）になっていない")

    # 11: 作業ツリー側の定義が 0 件（定義元ファイルは全て存在するが定義行が無い）→ exit 2
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(
            root,
            "| 決定 | 内容 |\n|---|---|\n",  # 表はあるが ID 定義行が 1 件も無い
            prd="| 要件 | 内容 |\n",
            usm="| ストーリー | 内容 |\n",
            adr_files=(),
        )
        (root / f"{LESSONS_DIR}/session-safety.md").write_text("## 教訓（ID なし）\n", encoding="utf-8")
        (root / LESSONS_CORE).write_text("## 教訓（ID なし）\n", encoding="utf-8")
        (root / ROADMAP).write_text("| マイルストーン | 内容 |\n", encoding="utf-8")
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=["0013-foo.md"], base_adr=["0013-foo.md"]
        )
        check(
            _run_main(root, runner) == 2,
            "11: 作業ツリー側の定義 0 件が fail-closed（exit 2）になっていない",
        )

    # 12: 複数定義元を宣言した種別（US）は別ファイルに両方あっても違反にしない（宣言と判定の一致）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(
            root,
            _BASE_OPEN_Q,
            prd=_PRD + "| **US-3** | トレーサビリティ行 |\n",
            usm=_USM + "| **US-3** | ストーリー |\n",
        )
        runner = _build_runner(
            main_open_q=_BASE_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=["0013-foo.md"], base_adr=["0013-foo.md"]
        )
        check(
            _run_main(root, runner) == 0,
            "12: 複数定義元を許す種別（US）の別ファイル定義を違反にしている（誤ブロック）",
        )

    # 12-b: その種別でも、既存 ID へ定義行を増やせば違反（許容範囲を広げすぎない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _BASE_OPEN_Q, usm=_USM + "| **US-1** | 同一ファイル内で再定義 |\n")
        runner = _build_runner(
            main_open_q=_BASE_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=["0013-foo.md"], base_adr=["0013-foo.md"]
        )
        check(_run_main(root, runner) == 1, "12-b: US の同一ファイル内二重定義を見逃した")

    # 13: main に既にある ID の同一ファイル再利用（差分比較では検出できない fail-open 経路）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # D-25 は merge-base 時点で既にある。それを同じファイルへ 2 行目として追記した状態。
        _write_worktree(root, _BASE_OPEN_Q + "| **D-25** | stale な grep を元に再利用 |\n")
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=["0013-foo.md"], base_adr=["0013-foo.md"]
        )
        check(
            _run_main(root, runner) == 1,
            "13: 既存 ID の同一ファイル再利用（定義行の増加）を exit 0 で素通しした",
        )

    # 13-b: 境界の外側（誤ブロックしないこと）。1 つの ID を「節見出し」と「表の行」の
    # 両方で書く形は本リポジトリの実データの標準（`open-questions.md` の `D-3` 等）。
    # merge-base 側でも同じ件数なら違反にしない（同一ファイル内の重複を一律違反にすると
    # 全 PR が誤ブロックされる）。
    _two_rows = _BASE_OPEN_Q + "### D-25 の決定から従属的に確定する事項\n"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _two_rows)
        runner = _build_runner(
            main_open_q=_two_rows, base_open_q=_two_rows, main_adr=["0013-foo.md"], base_adr=["0013-foo.md"]
        )
        check(
            _run_main(root, runner) == 0,
            "13-b: 元から複数行で書かれている ID を重複定義として誤ブロックした",
        )

    # 13-c: 判定関数の単体（別ファイル間の重複と、複数定義元を許す種別の除外）
    dups = find_duplicates({"D": [(1, "a.md"), (1, "b.md")], "US": [(1, "a.md"), (1, "b.md")]})
    check(
        [d["kind"] for d in dups] == ["D"],
        f"13-c: 複数定義元を許す種別の別ファイル定義を違反にした / 通常種別を見逃した: {dups}",
    )

    # 14: CLI 経路（`--no-fetch` で fetch を実際に呼ばない / `--remote-ref` の値検証）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _BASE_OPEN_Q + "| **D-27** | 別番号 |\n")
        runner = _build_runner(
            main_open_q=_MAIN_OPEN_Q, base_open_q=_BASE_OPEN_Q, main_adr=["0013-foo.md"], base_adr=["0013-foo.md"]
        )
        _FAKE_CALLS.clear()
        code = _run_main(root, runner, ["--no-fetch"])
        joined = [" ".join(c) for c in _FAKE_CALLS]
        check(code == 0, f"14: --no-fetch で exit 0 にならない（実際: {code}）")
        check(
            not any(c[:2] == ["git", "fetch"] for c in _FAKE_CALLS),
            f"14-b: --no-fetch なのに git fetch を呼んでいる: {joined[:4]}",
        )

        # `-` 始まりは argparse が値として受け取れるよう `--opt=value` 形式で渡す
        # （実運用でも自動化からこの形で渡りうる）。🔴 exit 2 の確認だけでは不十分:
        # 検証を外しても不正な ref は git 側で失敗して結局 exit 2 になるため、
        # 「git へ渡る前に弾いている」ことを **git が 1 度も呼ばれていない** ことで確かめる。
        for bad in ("-x", "--upload-pack=evil", "origin/main..HEAD", "origin/main;rm"):
            _FAKE_CALLS.clear()
            code = _run_main(root, runner, ["--no-fetch", f"--remote-ref={bad}"])
            check(code == 2, f"14-c: 不正な --remote-ref を弾いていない: {bad}（exit={code}）")
            check(
                _FAKE_CALLS == [],
                f"14-c-git: 不正な --remote-ref を git へ渡している: {bad} -> {_FAKE_CALLS[:2]}",
            )
        check(
            _run_main(root, runner, ["--no-fetch", "--remote-ref", "origin/main"]) == 0,
            "14-d: 正当な --remote-ref まで弾いている",
        )

    # 15: `git fetch` のタイムアウトは判定不能（exit 2）へ写す（外部 timeout 不在でもハングしない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_worktree(root, _BASE_OPEN_Q)
        hung = _make_fake_runner({}, timeout_on={("git", "fetch", "origin", "main")})
        check(_run_main(root, hung) == 2, "15: fetch のタイムアウトが exit 2 にならない")

    # 16: git の stderr に載る資格情報付き URL をマスクしてから外へ出す
    leaky = _make_fake_runner(
        {},
        fail={("git", "fetch", "origin", "main")},
        fail_stderr="fatal: unable to access 'https://x-access-token:SECRET_TOKEN_VALUE@github.com/o/r'",
    )
    masked = ""
    try:
        _git(["fetch", "origin", "main"], Path("."), leaky)
    except Undetermined as e:
        masked = str(e)
    check("SECRET_TOKEN_VALUE" not in masked, f"16: git stderr の資格情報をマスクしていない: {masked}")
    check("://***@" in masked, f"16-b: マスク後の書式が想定と違う: {masked}")

    if failures:
        for f in failures:
            print(f"❌ {f}", file=sys.stderr)
        print(f"self-test FAILED: {len(failures)} 件", file=sys.stderr)
        return 1
    print("✅ check_reserved_ids self-test PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
