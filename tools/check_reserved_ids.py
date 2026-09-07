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

終了コード:
  0 = 衝突なし（検査が実際に走り、対象を見たうえで違反が無かった）
  1 = 衝突あり（両側で独立に採番された ID / ローカル内での重複定義）
  2 = 判定不能（`git fetch` 失敗・merge-base 解決不可・宣言した定義元ファイルが読めない・
      定義元が 1 件も見つからない）。🔴 fail-closed（`0` に丸めない）。

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

# ADR は Markdown 本文でなくファイル名（`0013-foo.md`）で番号を確保する。
ADR_FILE_RE = re.compile(r"^(\d{3,4})-[^/]*\.md$")

# 表の第 1 セル / 見出しの先頭にある ID。装飾（`**` / バッククォート）は剥がしてから判定する。
LEADING_ID_RE = re.compile(r"^([A-Z]{1,3})-(\d+)\b")
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


def extract_definitions(text: str, kinds: tuple[str, ...]) -> dict[str, set[int]]:
    """1 ファイルの本文から「定義」として扱う ID を抽出する。

    定義とみなすのは次の 2 形だけ:
      - 表の第 1 セルが対象種別の ID で始まる行（`| **D-5 / D-7** | ...` のような併記は
        第 1 セル内の同種別 ID を全て拾う）
      - 見出しが対象種別の ID で始まる行（`## L-131: ...`）
    コードフェンス内の行は除外する（例示を予約とみなさないため）。
    """
    found: dict[str, set[int]] = {k: set() for k in kinds}
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
        for k2, num in ID_IN_TEXT_RE.findall(head_text):
            if k2 == kind:
                found[kind].add(int(num))
    return found


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


def _git(args: list[str], cwd: Path, runner: Runner) -> str:
    try:
        return run_git_or_raise(args, cwd, runner=runner)
    except RuntimeError as e:
        raise Undetermined(str(e)) from e


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


def _show(rev: str, path: str, cwd: Path, runner: Runner) -> str | None:
    """`rev` 側のファイル内容。存在しなければ None（その rev 時点では未作成 = 予約ゼロ）。"""
    try:
        return _git(["show", f"{rev}:{path}"], cwd, runner)
    except Undetermined:
        return None


def collect_ids_at_rev(rev: str, cwd: Path, runner: Runner) -> dict[str, set[int]]:
    """指定 rev 時点で確保されている ID を種別ごとに集める。"""
    result: dict[str, set[int]] = {k: set() for k in ID_SOURCES}
    result["L"] = set()
    result["ADR"] = set()

    by_file: dict[str, list[str]] = {}
    for kind, paths in ID_SOURCES.items():
        for p in paths:
            by_file.setdefault(p, []).append(kind)

    for path, kinds in by_file.items():
        text = _show(rev, path, cwd, runner)
        if text is None:
            continue
        for kind, nums in extract_definitions(text, tuple(kinds)).items():
            result[kind] |= nums

    for path in lesson_source_paths(
        _list_rev_files(rev, LESSONS_DIR, cwd, runner) + [LESSONS_CORE]
    ):
        text = _show(rev, path, cwd, runner)
        if text is None:
            continue
        result["L"] |= extract_definitions(text, ("L",))["L"]

    result["ADR"] |= extract_adr_numbers(_list_rev_files(rev, ADR_DIR, cwd, runner))
    return result


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
        for kind, nums in extract_definitions(text, tuple(kinds)).items():
            result[kind] |= nums
            occurrences[kind].extend((n, path) for n in sorted(nums))

    for path in _list_local_lessons(repo_root):
        nums = extract_definitions(_read_local(repo_root, path), ("L",))["L"]
        result["L"] |= nums
        occurrences["L"].extend((n, path) for n in sorted(nums))

    for name in _list_local_adr(repo_root):
        for n in extract_adr_numbers([name]):
            result["ADR"].add(n)
            occurrences["ADR"].append((n, f"{ADR_DIR}/{name}"))

    return result, occurrences


def find_duplicates(occurrences: dict[str, list[tuple[int, str]]]) -> list[dict[str, object]]:
    """同じ ID が 2 つ以上の **別ファイル** で定義されている状態を検出する。

    各要素（1 つ 1 つの定義行）は妥当でも、集合としての一意性が壊れている負ケース（#896）。
    同一ファイル内の重複は表の再掲・トレーサビリティ表で正当に起こりうるため対象にしない。
    """
    dups: list[dict[str, object]] = []
    for kind, items in occurrences.items():
        by_num: dict[int, set[str]] = {}
        for num, path in items:
            by_num.setdefault(num, set()).add(path)
        for num, paths in sorted(by_num.items()):
            if len(paths) > 1:
                dups.append({"kind": kind, "number": num, "paths": sorted(paths)})
    return dups


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
    if fetch:
        _git(["fetch", "origin", "main"], repo_root, runner)

    merge_base = _git(["merge-base", remote_ref, "HEAD"], repo_root, runner).strip()
    if not merge_base:
        raise Undetermined(f"merge-base({remote_ref}, HEAD) を解決できない")

    main_ids = collect_ids_at_rev(remote_ref, repo_root, runner)
    base_ids = collect_ids_at_rev(merge_base, repo_root, runner)
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
    report: dict[str, object] = {
        "merge_base": merge_base,
        "remote_ref": remote_ref,
        "collisions": collisions,
        "duplicates": duplicates,
        "next_free": next_free(main_ids, base_ids, local_ids),
    }
    return (1 if (collisions or duplicates) else 0), report


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
    print("\n次の空き番号（採番表の生成に使う）:")
    for kind, num in sorted(report["next_free"].items()):  # type: ignore[union-attr]
        print(f"  {kind}-{num}")


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


class _FakeResult:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def _make_fake_runner(responses: dict[tuple[str, ...], str], fail: set[tuple[str, ...]] | None = None) -> Runner:
    """argv を `_FAKE_CALLS` に記録する fake runner（終了コードだけ差し替える fake にしない・#710）。"""
    fail = fail or set()

    def runner(args, **kwargs):  # noqa: ANN001, ANN003
        _FAKE_CALLS.append(list(args))
        key = tuple(args)
        if key in fail:
            raise subprocess.CalledProcessError(1, args, output="", stderr="boom")
        if key not in responses:
            # 未知コマンドは「存在しない」扱い（git show の欠落パスを再現する）
            raise subprocess.CalledProcessError(128, args, output="", stderr="unknown path")
        return _FakeResult(stdout=responses[key])

    return runner


_MAIN_OPEN_Q = "| **D-25** | 決定 A |\n| **D-26** | 決定 B |\n"
_BASE_OPEN_Q = "| **D-25** | 決定 A |\n"
_LOCAL_OPEN_Q = "| **D-25** | 決定 A |\n| **D-26** | 別セッションと衝突する決定 |\n"
_PRD = "| **NFR-1** | 要件 |\n| `AC-1` 受け入れ基準 | x |\n"
_USM = "| **US-1** | ストーリー |\n| **SP-11** | スプリント |\n"
_ROADMAP = "| **M-1** | マイルストーン |\n"
_LESSON = "## L-131: 教訓\n本文\n"


def _write_worktree(root: Path, open_q: str, *, extra_lesson: str | None = None) -> None:
    (root / "docs/02_requirements").mkdir(parents=True, exist_ok=True)
    (root / "docs/adr").mkdir(parents=True, exist_ok=True)
    (root / "docs/rules/lessons").mkdir(parents=True, exist_ok=True)
    (root / OPEN_QUESTIONS).write_text(open_q, encoding="utf-8")
    (root / PRD).write_text(_PRD, encoding="utf-8")
    (root / USER_STORY_MAP).write_text(_USM, encoding="utf-8")
    (root / ROADMAP).write_text(_ROADMAP, encoding="utf-8")
    (root / f"{LESSONS_DIR}/session-safety.md").write_text(_LESSON, encoding="utf-8")
    (root / LESSONS_CORE).write_text("## L-077: 教訓\n", encoding="utf-8")
    (root / f"{ADR_DIR}/0013-foo.md").write_text("# ADR\n", encoding="utf-8")
    if extra_lesson is not None:
        (root / f"{LESSONS_DIR}/pr-review.md").write_text(extra_lesson, encoding="utf-8")


def _rev_responses(rev: str, open_q: str, adr: list[str]) -> dict[tuple[str, ...], str]:
    r: dict[tuple[str, ...], str] = {
        ("git", "show", f"{rev}:{OPEN_QUESTIONS}"): open_q,
        ("git", "show", f"{rev}:{PRD}"): _PRD,
        ("git", "show", f"{rev}:{USER_STORY_MAP}"): _USM,
        ("git", "show", f"{rev}:{ROADMAP}"): _ROADMAP,
        ("git", "show", f"{rev}:{LESSONS_DIR}/session-safety.md"): _LESSON,
        ("git", "show", f"{rev}:{LESSONS_CORE}"): "## L-077: 教訓\n",
        ("git", "ls-tree", "--name-only", rev, "--", f"{LESSONS_DIR}/"): f"{LESSONS_DIR}/session-safety.md\n",
        ("git", "ls-tree", "--name-only", rev, "--", f"{ADR_DIR}/"): "".join(
            f"{ADR_DIR}/{n}\n" for n in adr
        ),
    }
    return r


def _build_runner(*, main_open_q: str, base_open_q: str, main_adr: list[str], base_adr: list[str]) -> Runner:
    responses: dict[tuple[str, ...], str] = {
        ("git", "fetch", "origin", "main"): "",
        ("git", "merge-base", "origin/main", "HEAD"): "abc1234\n",
    }
    responses.update(_rev_responses("origin/main", main_open_q, main_adr))
    responses.update(_rev_responses("abc1234", base_open_q, base_adr))
    return _make_fake_runner(responses)


def _run_main(root: Path, runner: Runner, extra: list[str] | None = None) -> int:
    """self-test から `main()` を経由して終了コードまで貫通させる（出力は捨てる）。"""
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return main(["--repo-root", str(root), *(extra or [])], runner=runner)


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

    # 2: 定義とみなさないもの（参照・フェンス内例示・複合 ID）
    d = extract_definitions("| **M-1** | 説明 | `SP-1` / `D-11` |\n", ("D", "SP", "M"))
    check(d["D"] == set() and d["SP"] == set() and d["M"] == {1}, f"2: 第 2 セル以降を定義扱いした: {d}")
    d = extract_definitions("```\n| **D-99** | 例示 |\n```\n", ("D",))
    check(d["D"] == set(), f"2-b: コードフェンス内の例示を予約扱いした: {d}")
    d = extract_definitions("| **SD-1** | 別 ID 体系 |\n", ("D",))
    check(d["D"] == set(), f"2-c: 複合 ID `SD-1` を `D-1` と誤検出: {d}")
    d = extract_definitions("散文中の D-42 への言及\n", ("D",))
    check(d["D"] == set(), f"2-d: 散文中の参照を定義扱いした: {d}")

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

    if failures:
        for f in failures:
            print(f"❌ {f}", file=sys.stderr)
        print(f"self-test FAILED: {len(failures)} 件", file=sys.stderr)
        return 1
    print("✅ check_reserved_ids self-test PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
