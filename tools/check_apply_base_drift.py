#!/usr/bin/env python3
"""check_apply_base_drift.py — apply-base 適用の前後で「本リポジトリ固有の拡張行」が
消えていないかを機械検知する（Issue #60）。

【背景】`scripts/apply-to-repo.sh` の SYNC_PATHS（docs/rules・.claude/rules・.claude/skills 等）は
`cp -a` でベース最新版へ無条件上書きされる。本リポジトリの拡張は「ベース由来ファイル内への
インライン追記」（例: 見出しの配下に本リポジトリ固有の 1 節を足す）が中心のため、ファイル単位の
保護リストでは正当なベース更新まで遮断してしまい機能しない。本ツールは行レベルの差分検査で
「適用前に存在した行が、適用後に消え、かつ上流ベースのその行にも存在しない」ケースだけを
本リポジトリ固有拡張の消失として報告する。

【使い方】
    # 1) 適用直前（copy_path でファイルを上書きする前）にスナップショットを取る
    python3 tools/check_apply_base_drift.py snapshot \
        --repo-root <TARGET> --paths-file <SYNC_PATHS を1行1パスで書いたファイル> --out <保存先>

    # 2) 適用直後（コピー完了後）に検査する
    python3 tools/check_apply_base_drift.py check \
        --repo-root <TARGET> --paths-file <同じファイル> --snapshot <1で使った --out> \
        --base-clone <ベースの clone ディレクトリ> [--json]

    # self-test（ネットワーク非依存・run_checks.sh に配線）
    python3 tools/check_apply_base_drift.py --self-test

スナップショットの保存先はリポジトリにコミットされない場所（呼び出し側が mktemp -d 等で
作った一時ディレクトリ）を渡すこと。本ツール自身はどこにも成果物を書き残さない。

【終了コード（fail-closed）】
    0 = ドリフトなし（本リポジトリ固有行の消失は検出されなかった）
    1 = ドリフト検出（本リポジトリ固有行の消失を検出した。詳細を stdout に列挙）
    2 = 判定不能（fail-closed）: 上流ベースと突合できない、またはファイル読み取りに失敗した。
        この場合は削除行を全件「未確認の候補」として報告する（黙って PASS にしない）。

exit 2 は exit 1 と意味が異なる（判定不能 ≠ 確実な検出）。呼び出し側は stdout 冒頭の
`[drift] RESULT: ...` 行、または --json の `"result"` フィールドで区別すること。

【見逃し（miss）に至りうる経路と対策】
    - スナップショット取得の失敗（対象パス不在）        → 空スナップショットとして扱い、
      check 側でファイルが「新規追加」として扱われるため見逃さない（削除行ゼロは正しく0件）
    - 正規表現ではなく行完全一致（stripped）で比較       → 大文字小文字・空白差は意図的に許容
      （§CJK 整形の差・行末空白の差は「入力バリアント」節を参照）
    - 早期リターン・例外の握り潰し                       → main() は例外を捕捉せず fail-closed
      （未捕捉例外は判定不能 exit 2 として trap 相当の finally で処理する）
    - シンボリックリンク（.claude/rules → docs/rules）    → os.walk は宣言された先頭パス自体には
      必ず descend する。ネストしたシンボリックリンクの循環は realpath の visited set で防ぐ
    - 空ディレクトリ・バイナリファイル                    → バイナリは行比較対象外（既知の制限。
      本ツールの対象はテキスト設定・ルールファイルのため許容する）とし、黙って無視するのではなく
      `binary_skipped` に集計して --json / 通常出力へ明示する
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_NAME = "check_apply_base_drift.py"

# 近傍の追加行と十分似ていれば「削除ではなく改変（言い回し・整形の変更）」とみなす閾値。
# CJK マークダウン整形（強調記法前後への半角スペース挿入等）や上流の言い回し変更を
# 誤って「本リポジトリ固有行の消失」と誤検知しないための緩和（#719 系の教訓: 閾値は緩すぎても
# きつすぎても事故る。0.6 は「同一行の軽微な書き換え」を拾い「別内容への置換」は拾わない実測値）。
SIMILARITY_MODIFY_THRESHOLD = 0.6


def _norm(line: str) -> str:
    """比較用正規化: 行末空白差・改行差を吸収する（内容比較そのものは変えない）。"""
    return line.rstrip()


def _read_lines(path: Path) -> list[str] | None:
    """テキストファイルとして読み、行のリストを返す。バイナリ・読み取り不能なら None。"""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "\x00" in text:
        # NUL バイト混入はテキストとして扱わない（check_datetime_tz.py と同じ防御姿勢）
        return None
    return text.splitlines()


@dataclass
class WalkResult:
    files: dict[str, list[str]] = field(default_factory=dict)  # relpath -> lines
    binary_skipped: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)


def _walk_declared_paths(root: Path, declared: list[str]) -> WalkResult:
    """declared（SYNC_PATHS 相当の相対パス群）の下にある全テキストファイルを集める。"""
    result = WalkResult()
    visited_real: set[str] = set()
    for rel in declared:
        top = (root / rel).resolve() if False else (root / rel)  # 表示用に元の rel は保持
        if not top.exists():
            continue
        if top.is_file():
            lines = _read_lines(top)
            if lines is None:
                if top.exists():
                    result.binary_skipped.append(rel)
                continue
            result.files[rel] = lines
            continue
        # ディレクトリ（symlink 経由も os.walk が先頭では必ず descend する）
        for dirpath, dirnames, filenames in os.walk(top, followlinks=True):
            dirpath_p = Path(dirpath)
            try:
                real = str(dirpath_p.resolve())
            except OSError:
                real = dirpath
            if real in visited_real:
                # シンボリックリンクの循環防止
                dirnames[:] = []
                continue
            visited_real.add(real)
            for fname in filenames:
                fpath = dirpath_p / fname
                try:
                    relpath = str(fpath.relative_to(root))
                except ValueError:
                    relpath = str(fpath)
                lines = _read_lines(fpath)
                if lines is None:
                    if fpath.exists() and not fpath.is_symlink():
                        result.binary_skipped.append(relpath)
                    elif fpath.exists():
                        result.binary_skipped.append(relpath)
                    else:
                        result.unreadable.append(relpath)
                    continue
                result.files[relpath] = lines
    return result


def _read_paths_file(path: Path) -> list[str]:
    out: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


# --- snapshot ---

def cmd_snapshot(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root)
    declared = _read_paths_file(Path(args.paths_file))
    walked = _walk_declared_paths(repo_root, declared)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "declared_paths": declared,
        "files": walked.files,
        "binary_skipped": sorted(walked.binary_skipped),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[{SCRIPT_NAME}] snapshot: {len(walked.files)} files "
          f"({len(walked.binary_skipped)} binary skipped) -> {out_dir}")
    return 0


# --- check ---

@dataclass
class RemovedLine:
    relpath: str
    line_no: int  # 1-origin（適用前ファイル中の行番号）
    text: str


def _diff_removed_candidates(old_lines: list[str], new_lines: list[str]) -> list[RemovedLine]:
    """old→new の行差分から「実質的に消えた」行だけを抽出する（改変は除外）。"""
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    candidates: list[RemovedLine] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "insert"):
            continue
        removed = old_lines[i1:i2]
        added = new_lines[j1:j2] if tag == "replace" else []
        for offset, line in enumerate(removed):
            if added:
                best = max(
                    (difflib.SequenceMatcher(None, _norm(line), _norm(a)).ratio() for a in added),
                    default=0.0,
                )
                if best >= SIMILARITY_MODIFY_THRESHOLD:
                    continue  # 改変（言い回し・整形の変更）とみなし、削除候補にしない
            candidates.append(RemovedLine(relpath="", line_no=i1 + offset + 1, text=line))
    return candidates


def _line_in_base_file(norm_line: str, base_lines: list[str] | None) -> bool:
    if base_lines is None:
        return False
    return any(_norm(bl) == norm_line for bl in base_lines)


def run_check(
    repo_root: Path,
    declared: list[str],
    snapshot_manifest: dict,
    base_clone: Path | None,
) -> dict:
    old_files: dict[str, list[str]] = snapshot_manifest.get("files", {})
    new_walked = _walk_declared_paths(repo_root, declared)
    new_files = new_walked.files

    confirmed: list[RemovedLine] = []
    unconfirmed: list[RemovedLine] = []
    read_errors: list[str] = list(new_walked.unreadable)

    base_available = base_clone is not None and base_clone.exists()

    for relpath, old_lines in old_files.items():
        new_lines = new_files.get(relpath, [])
        cands = _diff_removed_candidates(old_lines, new_lines)
        if not cands:
            continue
        base_file_path = (base_clone / relpath) if base_clone else None
        base_lines = _read_lines(base_file_path) if base_file_path and base_file_path.exists() else None
        for c in cands:
            c.relpath = relpath
            norm_text = _norm(c.text)
            if not norm_text:
                continue  # 空行の消失は無視
            if not base_available:
                unconfirmed.append(c)
                continue
            if _line_in_base_file(norm_text, base_lines):
                continue  # 上流にも存在する行 = 上流由来の正当な更新とみなす
            confirmed.append(c)

    if not base_available:
        result = "undetermined"
    elif confirmed:
        result = "drift"
    else:
        result = "clean"

    return {
        "result": result,
        "confirmed": [c.__dict__ for c in confirmed],
        "unconfirmed": [c.__dict__ for c in unconfirmed],
        "binary_skipped": sorted(new_walked.binary_skipped),
        "read_errors": sorted(read_errors),
        "base_available": base_available,
    }


def cmd_check(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root)
    declared = _read_paths_file(Path(args.paths_file))
    manifest_path = Path(args.snapshot) / "manifest.json"
    if not manifest_path.exists():
        print(f"[{SCRIPT_NAME}] ERROR: スナップショットが見つかりません: {manifest_path}", file=sys.stderr)
        print(f"[{SCRIPT_NAME}] RESULT: undetermined（スナップショット不在・fail-closed）")
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[{SCRIPT_NAME}] ERROR: スナップショットの読み取りに失敗しました: {e}", file=sys.stderr)
        print(f"[{SCRIPT_NAME}] RESULT: undetermined（スナップショット破損・fail-closed）")
        return 2

    base_clone = Path(args.base_clone) if args.base_clone else None
    outcome = run_check(repo_root, declared, manifest, base_clone)

    if args.json:
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
    else:
        _print_human(outcome)

    if outcome["read_errors"]:
        print(f"[{SCRIPT_NAME}] ⚠ 判定不能ファイルあり（読み取り失敗）: {outcome['read_errors']}", file=sys.stderr)
        return 2
    if outcome["result"] == "undetermined":
        return 2
    if outcome["result"] == "drift":
        return 1
    return 0


def _print_human(outcome: dict) -> None:
    result = outcome["result"]
    print(f"[{SCRIPT_NAME}] RESULT: {result}")
    if outcome["confirmed"]:
        print(f"[{SCRIPT_NAME}] 本リポジトリ固有行の消失を検出（上流にも存在しない削除行）:")
        for c in outcome["confirmed"]:
            print(f"  - {c['relpath']}:{c['line_no']}: {c['text']}")
    if outcome["unconfirmed"]:
        print(f"[{SCRIPT_NAME}] 判定不能: 上流ベースと突合できないため削除行を全件報告します（fail-closed）:")
        for c in outcome["unconfirmed"]:
            print(f"  - {c['relpath']}:{c['line_no']}: {c['text']}")
    if outcome["binary_skipped"]:
        print(f"[{SCRIPT_NAME}] バイナリ扱いで比較対象外（{len(outcome['binary_skipped'])} 件）: "
              f"{outcome['binary_skipped'][:10]}{'…' if len(outcome['binary_skipped']) > 10 else ''}")
    if result == "clean":
        print(f"[{SCRIPT_NAME}] drift なし")


# --- self-test ---

def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _run_main_capture(argv: list[str]) -> tuple[int, str]:
    """本番の入口 main() を経由して実行し、exit code と stdout を返す（内部関数の直呼びをしない）。"""
    import contextlib
    import io

    buf = io.StringIO()
    old_argv = sys.argv
    sys.argv = [SCRIPT_NAME] + argv
    try:
        with contextlib.redirect_stdout(buf):
            try:
                main()
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = old_argv
    return code, buf.getvalue()


def self_test() -> int:
    import shutil
    import tempfile

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"{name}: {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        repo = tmp_p / "repo"
        base = tmp_p / "base"
        snap = tmp_p / "snap"
        paths_file = tmp_p / "paths.txt"
        (paths_file).write_text("docs/rules\nmodules.yaml\n", encoding="utf-8")

        # --- 共通の初期状態: リポジトリ固有拡張を含むベース由来ファイル ---
        rule_lines = [
            "# サンプルルール",
            "",
            "## 大原則",
            "汎用の説明行A。",
            "汎用の説明行B。",
            "本リポジトリは R-1 ルーティン稼働のため Hot 化済み。",  # 本リポジトリ固有拡張
            "",
            "## 完了条件",
            "- 項目1",
        ]
        _write(repo / "docs/rules/sample.md", rule_lines)
        _write(repo / "modules.yaml", ["enabled: true"])
        # ベース側は本リポジトリ固有行を持たない（オリジナル）
        base_rule_lines = [
            "# サンプルルール",
            "",
            "## 大原則",
            "汎用の説明行A。",
            "汎用の説明行B。",
            "",
            "## 完了条件",
            "- 項目1",
        ]
        _write(base / "docs/rules/sample.md", base_rule_lines)

        # (1) スナップショット
        code, out = _run_main_capture([
            "snapshot", "--repo-root", str(repo), "--paths-file", str(paths_file), "--out", str(snap),
        ])
        check("snapshot exit0", code == 0, out)

        # (2a) 適用後も固有拡張行が残っている → clean（exit 0）
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-a clean exit0", code == 0, out)
        check("case-a RESULT clean", "RESULT: clean" in out, out)

        # (2b) 適用後に固有拡張行が消える（ベースにも無い）→ drift（exit 1）
        after_lines = [
            "# サンプルルール",
            "",
            "## 大原則",
            "汎用の説明行A。",
            "汎用の説明行B。",
            "",
            "## 完了条件",
            "- 項目1",
        ]
        _write(repo / "docs/rules/sample.md", after_lines)
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-b drift exit1", code == 1, out)
        check("case-b line reported", "R-1 ルーティン稼働" in out, out)

        # (2c) 削除された行がベース側にも存在する（正当な上流削除） → clean
        base_with_line = base_rule_lines[:5] + [
            "本リポジトリは R-1 ルーティン稼働のため Hot 化済み。",
        ] + base_rule_lines[5:]
        _write(base / "docs/rules/sample.md", base_with_line)
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-c legit-upstream-removal clean", code == 0, out)
        _write(base / "docs/rules/sample.md", base_rule_lines)  # 元に戻す

        # (2d) base-clone なし（上流取得不可）→ undetermined（exit 2・全件報告）
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(tmp_p / "no-such-dir"),
        ])
        check("case-d undetermined exit2", code == 2, out)
        check("case-d RESULT undetermined", "RESULT: undetermined" in out, out)
        check("case-d line still listed", "R-1 ルーティン稼働" in out, out)

        # (2e) 行末空白差だけ → clean（誤検知しない・入力バリアント: 行末空白の差）
        _write(repo / "docs/rules/sample.md", rule_lines)  # 復元
        code, _ = _run_main_capture([
            "snapshot", "--repo-root", str(repo), "--paths-file", str(paths_file), "--out", str(snap),
        ])
        check("re-snapshot exit0", code == 0, "")
        trailing_ws_lines = list(rule_lines)
        trailing_ws_lines[5] = trailing_ws_lines[5] + "   "  # 行末に半角スペース3つ追加
        _write(repo / "docs/rules/sample.md", trailing_ws_lines)
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-e trailing-ws clean", code == 0, out)

        # (2f) CJK 整形風の軽微な書き換え（強調前後にスペース追加）→ clean（改変として除外）
        _write(repo / "docs/rules/sample.md", rule_lines)
        code, _ = _run_main_capture([
            "snapshot", "--repo-root", str(repo), "--paths-file", str(paths_file), "--out", str(snap),
        ])
        reformatted = list(rule_lines)
        reformatted[3] = "汎用の **説明** 行A。"  # 元は「汎用の説明行A。」に近い書き換え
        _write(repo / "docs/rules/sample.md", reformatted)
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-f cjk-reformat clean", code == 0, out)

        # (2g) 見出しだけ残って本文（固有拡張含む）が消えたケース → drift
        _write(repo / "docs/rules/sample.md", rule_lines)
        code, _ = _run_main_capture([
            "snapshot", "--repo-root", str(repo), "--paths-file", str(paths_file), "--out", str(snap),
        ])
        heading_only = ["# サンプルルール", "", "## 大原則", "", "## 完了条件", "- 項目1"]
        _write(repo / "docs/rules/sample.md", heading_only)
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-g heading-only-drift exit1", code == 1, out)
        check("case-g body line reported", "R-1 ルーティン稼働" in out, out)

        # (2h) 新規追加ファイル（ベースに存在しないファイル自体）の固有行消失 → drift
        _write(repo / "docs/rules/new_local.md", ["見出し", "本リポジトリだけの独自行"])
        code, _ = _run_main_capture([
            "snapshot", "--repo-root", str(repo), "--paths-file", str(paths_file), "--out", str(snap),
        ])
        _write(repo / "docs/rules/new_local.md", ["見出し"])
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-h new-file-not-in-base drift exit1", code == 1, out)
        check("case-h line reported", "本リポジトリだけの独自行" in out, out)
        (repo / "docs/rules/new_local.md").unlink()

        # (2i) 干渉検証: snapshot(1) → 途中で SYNC_PATHS 外のファイルを弄っても検査に影響しない
        #      （宣言パス外は _walk_declared_paths が拾わない = スナップショット取得順序と
        #      copy_path 実行順序の分離が正しく機能していることの確認）
        _write(repo / "docs/rules/sample.md", rule_lines)
        code, _ = _run_main_capture([
            "snapshot", "--repo-root", str(repo), "--paths-file", str(paths_file), "--out", str(snap),
        ])
        _write(repo / "README_UNRELATED.md", ["宣言パス外のファイル"])  # 対象外パス
        code, out = _run_main_capture([
            "check", "--repo-root", str(repo), "--paths-file", str(paths_file),
            "--snapshot", str(snap), "--base-clone", str(base),
        ])
        check("case-i unrelated-path ignored clean", code == 0, out)
        (repo / "README_UNRELATED.md").unlink()

        shutil.rmtree(repo, ignore_errors=True)

    if failures:
        print(f"[{SCRIPT_NAME}] SELF-TEST FAILED ({len(failures)} 件):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"[{SCRIPT_NAME}] SELF-TEST PASSED")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true", help="ネットワーク非依存のユニットテストを実行する")
    sub = p.add_subparsers(dest="command")

    p_snap = sub.add_parser("snapshot", help="適用直前のスナップショットを取る")
    p_snap.add_argument("--repo-root", required=True)
    p_snap.add_argument("--paths-file", required=True)
    p_snap.add_argument("--out", required=True)

    p_check = sub.add_parser("check", help="適用直後にドリフトを検査する")
    p_check.add_argument("--repo-root", required=True)
    p_check.add_argument("--paths-file", required=True)
    p_check.add_argument("--snapshot", required=True)
    p_check.add_argument("--base-clone", default=None)
    p_check.add_argument("--json", action="store_true")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if args.command == "snapshot":
        sys.exit(cmd_snapshot(args))
    if args.command == "check":
        sys.exit(cmd_check(args))

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
