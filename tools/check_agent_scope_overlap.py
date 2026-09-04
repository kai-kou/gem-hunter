#!/usr/bin/env python3
"""check_agent_scope_overlap.py — 並列委譲の前にサブエージェント間のファイルスコープ重複を検査する（#103）

## なぜ必要か

`agent-team-summary.md` は「並列化の前提は設計時点でのファイル非重複分割」と定めているが、
その分割は親（オーケストレーター）の頭の中にしかなく機械的な確認がない。SP-2 では 6 役割を
委譲した際、実際に同じ 2 ファイルを 2 担当が触りかける場面が発生した（親が気づいて片方を
停止して回避）。本ツールは `Agent` を複数起動する **直前** に、各担当（レーン）の担当ファイル・
グロブ一覧を渡すと重複を検出する軽量チェックを提供する。

## 検査方法

各レーンのグロブをリポジトリ内の実ファイルへ展開し（`glob.glob(..., recursive=True)`）、
展開結果の集合同士の積（交差）を取ってレーン間の重複ファイルを検出する。展開結果が空の
グロブは「対象なし」として警告する（意図したファイルが 1 つも存在しない = 設計ミスの兆候）。
ディレクトリはファイルではないため重複判定の対象から除外する。

**リテラルパス・フォールバックとワイルドカードの区別（#220 F-1）**: 並列委譲では「これから
新規作成するファイル」を担当として宣言するのが普通で、ディスク上にまだ存在しないため
グロブ展開が空になる。この場合に **リテラルパスとして再解釈** してファイル集合へ加えるのは、
パターンが `*` `?` を **含まない** ときに限る。`*` `?` を含むのに展開が 0 件だったパターン
（例: 未作成ディレクトリ配下の `src/newmodule/**`）は、文字列そのものをファイル扱いすると
「`**` という文字列がファイルであるかのように重複判定に混入する」という偽陰性を生むため、
ファイル集合には加えず **`unresolved_globs`** に記録して警告する（重複判定からは除外され、
「対象が未確定」であることが呼び出し元に伝わる）。`[` `]` のみを含むパターン（`*` `?` を
含まない）は従来どおりリテラル解釈の対象である — Next.js 動的ルートの実在パス
（`app/[locale]/repos/[owner]/[repo]/page.tsx` 等）で `[` `]` を素朴に「グロブの印」と判定すると
誤判定するため、判定基準は常に「`*` `?` の有無」であって「メタ文字全般の有無」ではない。

**パストラバーサル対策**: `glob.glob(..., root_dir=root)` は `root_dir` を指定してもパターン内の
`..` を禁止しない（例: `--lane "evil:../../../../etc/*"` はリポジトリ外へ展開されうる）。展開後の
各マッチを `(root / m).resolve()` し、`root.resolve()` 配下でないものは重複判定の集合に含めず、
黙って捨てずに `out_of_scope` として警告に記録する。

**OSError 耐性（#220 F-5）**: リテラル・フォールバック内の `resolve()` / `is_dir()` / `exists()` は
未検証の文字列（極端に長いパス名・シンボリックリンクループ等）に対して `OSError`
（`ENAMETOOLONG` / `ELOOP` / `EACCES` 等）を送出しうる。これを捕捉しなければツール全体が
スタックトレースで異常終了する。本ツールは該当パターンを `resolve_errors` に記録して処理を
継続し、CLI 全体をクラッシュさせない。

## 入力形式

`--lane "name:glob1,glob2,..."` を担当（レーン）の数だけ繰り返し指定する
（オーケストレーターが Bash から 1 コマンドで叩けることを最優先にした唯一の形式）。

    python3 tools/check_agent_scope_overlap.py \\
        --lane "impl:src/foo/**,src/bar.py" \\
        --lane "test:tests/**"

`--json` を付けると結果を JSON で出力する（人間向けテキストの既定出力と排他ではなく整形先の切り替え）。

## 使い方

    python3 tools/check_agent_scope_overlap.py --lane "a:src/a/**" --lane "b:src/b/**"
    python3 tools/check_agent_scope_overlap.py --self-test

重複があれば exit 1（重複ファイル一覧を表示）、なければ exit 0。入力解析・展開時の
`OSError` は exit 2（`❌ 入力の解析に失敗: ...`）に正規化する。
"""

# tool-wiring-ok: 並列委譲の直前に親セッションが手動実行する運用ツール
# （docs/rules/agent-team-summary.md）。委譲前に効く判定で、PR 直前の一括検査では手遅れになる。

from __future__ import annotations

import argparse
import glob as glob_mod
import json
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent


class LaneExpansion(NamedTuple):
    """`expand_lane()` の戻り値（#220 F-7: 呼び出し元同期漏れを防ぐための構造化）。"""

    files: set[str]
    empty_globs: list[str]
    out_of_scope: list[str]
    unmaterialized_literals: list[str]
    unresolved_globs: list[str]
    resolve_errors: list[tuple[str, str]]


def expand_lane(patterns: list[str], root: Path) -> LaneExpansion:
    """グロブ一覧を実ファイル（root からの相対パス文字列）の集合へ展開する。

    グロブ展開が真に空（マッチ 0 件）で、かつパターンが `*` `?` を含まない場合のみ
    **リテラルパスとして再解釈** し、ディスク上の存否を問わずファイル集合へ加える
    （これから新規作成する予定のファイルを拾うため）。存在しない場合は
    `unmaterialized_literals` に記録して呼び出し元が警告できるようにする（黙って拾わない）。

    `*` `?` を含むのに展開が 0 件だったパターンは **ファイル集合に加えず** `unresolved_globs`
    に記録する（#220 F-1・偽陰性対策）。

    グロブがマッチしたがファイルではなかった場合（ディレクトリのみ一致）は empty_globs に
    記録する。`root` 配下から外れたマッチ・リテラルパス（パストラバーサル）は集合に含めず
    out_of_scope に記録する（黙って捨てない・警告として可視化する）。

    `resolve()` / `is_dir()` / `exists()` が `OSError` を送出した場合は該当パターンを
    `resolve_errors` に記録して処理を継続する（#220 F-5）。
    """
    files: set[str] = set()
    empty_globs: list[str] = []
    out_of_scope: list[str] = []
    unmaterialized_literals: list[str] = []
    unresolved_globs: list[str] = []
    resolve_errors: list[tuple[str, str]] = []
    resolved_root = root.resolve()
    for pattern in patterns:
        matches = glob_mod.glob(pattern, root_dir=root, recursive=True)

        if not matches:
            has_wildcard = "*" in pattern or "?" in pattern
            if has_wildcard:
                # ワイルドカードを含むのに 0 件展開 → リテラル扱いせず未解決として記録する
                # （#220 F-1: "**" のような文字列がファイル扱いされる偽陰性を防ぐ）
                unresolved_globs.append(pattern)
                continue

            # グロブ展開が真に空 かつ メタ文字（`*` `?`）を含まない → リテラルパスとして
            # 再解釈する（#197）。`[` `]` のみを含むパターン（Next.js 動的ルート等）はここに
            # 含まれる — `glob.glob()` 自身の展開結果が空かどうかだけを基準にすることで、
            # そうした実在パスは文字クラスとしては何にもマッチせず展開が空になるため、
            # 正しくリテラルパスとして拾われる。
            try:
                candidate = (root / pattern).resolve()
            except OSError as e:
                resolve_errors.append((pattern, str(e)))
                continue
            if not candidate.is_relative_to(resolved_root):
                out_of_scope.append(pattern)
                continue
            try:
                is_directory = candidate.is_dir()
                candidate_exists = candidate.exists()
            except OSError as e:
                resolve_errors.append((pattern, str(e)))
                continue
            if is_directory:
                # 既存ディレクトリはファイルではないため対象外（従来どおり「対象なし」扱い）
                empty_globs.append(pattern)
                continue
            rel_str = candidate.relative_to(resolved_root).as_posix()
            files.add(rel_str)
            if not candidate_exists:
                unmaterialized_literals.append(pattern)
            continue

        file_matches: list[str] = []
        pattern_out_of_scope: list[str] = []
        for m in matches:
            try:
                candidate = (root / m).resolve()
            except OSError as e:
                resolve_errors.append((m, str(e)))
                continue
            if not candidate.is_relative_to(resolved_root):
                pattern_out_of_scope.append(m)
                continue
            try:
                is_file = candidate.is_file()
            except OSError as e:
                resolve_errors.append((m, str(e)))
                continue
            if is_file:
                file_matches.append(m)
        if not file_matches and not pattern_out_of_scope:
            empty_globs.append(pattern)
        out_of_scope.extend(pattern_out_of_scope)
        files.update(file_matches)
    return LaneExpansion(
        files=files,
        empty_globs=empty_globs,
        out_of_scope=out_of_scope,
        unmaterialized_literals=unmaterialized_literals,
        unresolved_globs=unresolved_globs,
        resolve_errors=resolve_errors,
    )


def format_expand_warnings(subject_label: str, subject_word: str, expansion: LaneExpansion) -> list[str]:
    """`expand_lane()` の戻り値を警告文リストへ整形する（#220 F-7: レーン／候補で共有）。

    `subject_word` には呼び出し元の主語（「レーン」または「候補」）を渡す。
    """
    warnings: list[str] = []
    for g in expansion.empty_globs:
        warnings.append(
            f"{subject_word} `{subject_label}` のグロブ `{g}` はファイルに一致しませんでした"
            "（ディレクトリのみ一致、または対象なし）"
        )
    for g in expansion.unresolved_globs:
        warnings.append(
            f"{subject_word} `{subject_label}` のグロブ `{g}` は 0 件展開のため未解決として扱いました"
            "（ワイルドカードを含むためリテラル解釈はしません。対象ファイルが未確定です）"
        )
    for m in expansion.out_of_scope:
        warnings.append(
            f"{subject_word} `{subject_label}` の `{m}` はリポジトリ外（パストラバーサル）のため除外しました"
        )
    for p in expansion.unmaterialized_literals:
        warnings.append(
            f"{subject_word} `{subject_label}` の `{p}` は未作成のリテラルパスとして扱いました"
            "（ファイルはまだ存在しません）"
        )
    for pattern, err in expansion.resolve_errors:
        warnings.append(
            f"{subject_word} `{subject_label}` の `{pattern}` は解決時にエラーが発生したため除外しました"
            f"（{err}）"
        )
    return warnings


def check_overlap(lanes: dict[str, list[str]], root: Path = REPO_ROOT) -> dict:
    """レーンごとにグロブを展開し、レーン間のファイル重複を検出する。"""
    expanded: dict[str, set[str]] = {}
    warnings: list[str] = []
    for name, patterns in lanes.items():
        expansion = expand_lane(patterns, root)
        expanded[name] = expansion.files
        warnings.extend(format_expand_warnings(name, "レーン", expansion))

    names = list(expanded.keys())
    overlaps: dict[str, list[str]] = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            common = expanded[a] & expanded[b]
            if common:
                overlaps[f"{a}×{b}"] = sorted(common)

    return {
        "lanes": {name: sorted(files) for name, files in expanded.items()},
        "overlaps": overlaps,
        "warnings": warnings,
        "has_overlap": bool(overlaps),
    }


def parse_lane_args(lane_args: list[str]) -> dict[str, list[str]]:
    """`--lane` の繰り返し指定（'name:glob1,glob2'）をレーン辞書へ変換する。"""
    lanes: dict[str, list[str]] = {}
    for spec in lane_args:
        if ":" not in spec:
            raise ValueError(f"--lane は 'name:glob1,glob2' 形式で指定する（不正: {spec!r}）")
        name, _, globs_str = spec.partition(":")
        name = name.strip()
        globs = [g.strip() for g in globs_str.split(",") if g.strip()]
        if not name:
            raise ValueError(f"--lane のレーン名が空: {spec!r}")
        if not globs:
            raise ValueError(f"--lane にグロブが 1 つもない: {spec!r}")
        lanes[name] = lanes.get(name, []) + globs
    return lanes


def print_report(result: dict) -> None:
    for name, files in result["lanes"].items():
        print(f"  レーン `{name}`: {len(files)} ファイル")
    for w in result["warnings"]:
        print(f"⚠️  {w}")
    if result["has_overlap"]:
        print("❌ ファイルスコープの重複を検出しました:")
        for pair, files in result["overlaps"].items():
            print(f"  {pair}:")
            for f in files:
                print(f"    - {f}")
        print(
            "\n判断の指針: 重複ファイルを含む担当は (1) 逐次実行に切り替える、"
            "または (2) 担当分割を再設計してから並列委譲する（docs/rules/agent-team-summary.md）。"
        )
    else:
        print("✅ ファイルスコープの重複なし")


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def run_self_test() -> int:
    import tempfile

    passed, failed = 0, 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {label}" + (f" — {detail}" if detail else ""))

    # parse_lane_args: 正常系
    lanes = parse_lane_args(["impl:src/a.py,src/b.py", "test:tests/**"])
    check("parse_lane_args 正常系", lanes == {"impl": ["src/a.py", "src/b.py"], "test": ["tests/**"]}, str(lanes))

    # parse_lane_args: 同名レーンはマージされる
    lanes2 = parse_lane_args(["impl:a.py", "impl:b.py"])
    check("parse_lane_args 同名マージ", lanes2 == {"impl": ["a.py", "b.py"]}, str(lanes2))

    # parse_lane_args: 異常系（コロンなし）
    try:
        parse_lane_args(["broken"])
        check("parse_lane_args コロンなしで ValueError", False)
    except ValueError:
        check("parse_lane_args コロンなしで ValueError", True)

    # parse_lane_args: 異常系（グロブなし）
    try:
        parse_lane_args(["impl:"])
        check("parse_lane_args グロブなしで ValueError", False)
    except ValueError:
        check("parse_lane_args グロブなしで ValueError", True)

    # parse_lane_args: 異常系（レーン名が空）
    try:
        parse_lane_args([":glob"])
        check("parse_lane_args レーン名が空で ValueError", False)
    except ValueError:
        check("parse_lane_args レーン名が空で ValueError", True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "dirA").mkdir()
        (root / "dirB").mkdir()
        (root / "dirA" / "x.py").write_text("x")
        (root / "dirB" / "y.py").write_text("y")
        (root / "shared.py").write_text("s")

        # 重複なし
        result_ok = check_overlap({"a": ["dirA/**"], "b": ["dirB/**"]}, root=root)
        check("重複なしを正しく判定", result_ok["has_overlap"] is False, str(result_ok))

        # 重複あり（shared.py を両方が含む）
        result_ng = check_overlap({"a": ["shared.py", "dirA/**"], "b": ["shared.py"]}, root=root)
        check(
            "重複ありを正しく判定",
            result_ng["has_overlap"] is True and result_ng["overlaps"].get("a×b") == ["shared.py"],
            str(result_ng),
        )

        # 空グロブは警告になる
        result_empty = check_overlap({"a": ["nonexistent/**"]}, root=root)
        check("空グロブが警告になる", len(result_empty["warnings"]) == 1, str(result_empty))

        # ディレクトリ一致はファイル集合に含まれない
        expansion_dir = expand_lane(["dirA"], root)
        check("ディレクトリ単体一致はファイル扱いしない", expansion_dir.files == set(), f"files={expansion_dir.files}")

        # パストラバーサル: root 配下から外れたマッチは除外され警告として記録される
        outside = root.parent / f"outside_{root.name}.txt"
        try:
            outside.write_text("secret")
            expansion_traversal = expand_lane(["../" + outside.name], root)
            check(
                "パストラバーサルは重複判定の集合から除外される",
                expansion_traversal.files == set(),
                f"files={expansion_traversal.files}",
            )
            check(
                "パストラバーサルは out_of_scope に記録される（黙って捨てない）",
                len(expansion_traversal.out_of_scope) == 1,
                f"out_of_scope={expansion_traversal.out_of_scope}",
            )
            result_traversal = check_overlap(
                {"evil": ["../" + outside.name], "ok": ["dirA/**"]}, root=root
            )
            check(
                "check_overlap 経由でもパストラバーサルは warnings に記録される",
                any("パストラバーサル" in w for w in result_traversal["warnings"]),
                str(result_traversal["warnings"]),
            )
        finally:
            if outside.exists():
                outside.unlink()

        # パストラバーサル（リテラルフォールバック経路）: 実在しないパスでも
        # `..` で root の外へ出るものは out_of_scope として除外される
        expansion_literal_traversal = expand_lane(["../nonexistent_literal_probe.txt"], root)
        check(
            "リテラルフォールバックでもパストラバーサルは除外される",
            expansion_literal_traversal.files == set() and len(expansion_literal_traversal.out_of_scope) == 1,
            f"files={expansion_literal_traversal.files} out_of_scope={expansion_literal_traversal.out_of_scope}",
        )

        # リテラルパス・フォールバック（#197）: 存在しないファイルもリテラルパスとして
        # ファイル集合に加わり、2 レーンで宣言されていれば重複として検出される
        result_literal_dup = check_overlap(
            {"a": ["not/yet/created.py"], "b": ["not/yet/created.py"]}, root=root
        )
        check(
            "未作成のリテラルパスも重複として検出される",
            result_literal_dup["has_overlap"] is True
            and result_literal_dup["overlaps"].get("a×b") == ["not/yet/created.py"],
            str(result_literal_dup),
        )
        check(
            "未作成のリテラルパスは warnings に記録される（黙って拾わない）",
            any("未作成のリテラルパス" in w for w in result_literal_dup["warnings"]),
            str(result_literal_dup["warnings"]),
        )

        # `[` `]` を含む実在パス（Next.js 動的ルート）はメタ文字判定せずリテラル一致する
        (root / "app" / "[locale]" / "repos" / "[owner]" / "[repo]").mkdir(parents=True)
        bracket_path = root / "app" / "[locale]" / "repos" / "[owner]" / "[repo]" / "page.tsx"
        bracket_path.write_text("export default function Page() {}\n")
        bracket_pattern = "app/[locale]/repos/[owner]/[repo]/page.tsx"
        expansion_bracket = expand_lane([bracket_pattern], root)
        check(
            "ブラケットを含む実在パスがメタ文字判定なしでリテラル一致する",
            expansion_bracket.files == {bracket_pattern} and expansion_bracket.unmaterialized_literals == [],
            f"files={expansion_bracket.files} unmat={expansion_bracket.unmaterialized_literals}",
        )

        # ── #220 F-1: ワイルドカードを含むパターンが 0 件展開でもリテラル化されない ──
        expansion_wildcard = expand_lane(["src/newmodule/**"], root)
        check(
            "ワイルドカードを含む 0 件展開はファイル集合に加わらない（偽陰性対策）",
            expansion_wildcard.files == set() and expansion_wildcard.unresolved_globs == ["src/newmodule/**"],
            f"files={expansion_wildcard.files} unresolved={expansion_wildcard.unresolved_globs}",
        )
        result_wildcard_vs_literal = check_overlap(
            {"impl": ["src/newmodule/**"], "test": ["src/newmodule/foo_test.py"]}, root=root
        )
        check(
            "0 件展開のワイルドカードは lanes のファイル一覧に文字列として混入しない",
            result_wildcard_vs_literal["lanes"]["impl"] == [],
            str(result_wildcard_vs_literal["lanes"]),
        )
        check(
            "0 件展開のワイルドカードは unresolved として warnings に記録される",
            any("未解決" in w for w in result_wildcard_vs_literal["warnings"]),
            str(result_wildcard_vs_literal["warnings"]),
        )

        # ── #220 F-5: 極端に長いパス名でも OSError が伝播せず継続する ──
        long_name = "a" * 300
        try:
            expansion_long = expand_lane([long_name], root)
            check(
                "極端に長いパス名でも例外が伝播しない",
                long_name not in expansion_long.files,
                f"files={expansion_long.files} resolve_errors={expansion_long.resolve_errors}",
            )
        except OSError as e:
            check("極端に長いパス名でも例外が伝播しない", False, f"OSError が伝播した: {e}")

    print(f"\nセルフテスト: {passed} passed, {failed} failed / {passed + failed} cases")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lane", action="append", default=[], help="'name:glob1,glob2' 形式で繰り返し指定")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    # selftest-wiring-ok: 並列委譲の直前に親が手動で叩く運用ツールで、PR 前の品質ゲートではない
    parser.add_argument("--self-test", action="store_true", help="セルフテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.lane:
        parser.print_help()
        return 2

    try:
        lanes = parse_lane_args(args.lane)
    except ValueError as e:
        print(f"❌ 入力の解析に失敗: {e}", file=sys.stderr)
        return 2

    if not isinstance(lanes, dict) or len(lanes) < 2:
        print("⚠️  レーンが 2 未満のため重複判定はスキップします（比較対象がありません）")
        return 0

    try:
        result = check_overlap(lanes)
    except OSError as e:
        print(f"❌ 入力の解析に失敗: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return 1 if result["has_overlap"] else 0


if __name__ == "__main__":
    sys.exit(main())
