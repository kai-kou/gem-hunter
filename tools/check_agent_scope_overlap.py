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

## 入力形式（採用・オーケストレーターが Bash から 1 コマンドで叩けることを最優先にした）

**主形式**: `--lane "name:glob1,glob2,..."` を担当（レーン）の数だけ繰り返し指定する。

    python3 tools/check_agent_scope_overlap.py \\
        --lane "impl:src/foo/**,src/bar.py" \\
        --lane "test:tests/**"

**副形式**: JSON `{"レーン名": ["glob", ...], ...}` を `--lanes-json` に文字列で渡すか、
`--stdin` で標準入力から読む（プログラムから呼ぶ場合向け）。

    echo '{"impl": ["src/foo/**"], "test": ["tests/**"]}' \\
        | python3 tools/check_agent_scope_overlap.py --stdin

`--lane` / `--lanes-json` / `--stdin` は併用不可（いずれか 1 つ）。`--json` を付けると結果を
JSON で出力する（人間向けテキストの既定出力と排他ではなく整形先の切り替え）。

## 使い方

    python3 tools/check_agent_scope_overlap.py --lane "a:src/a/**" --lane "b:src/b/**"
    python3 tools/check_agent_scope_overlap.py --self-test

重複があれば exit 1（重複ファイル一覧を表示）、なければ exit 0。
"""

from __future__ import annotations

import argparse
import glob as glob_mod
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def expand_lane(patterns: list[str], root: Path) -> tuple[set[str], list[str]]:
    """グロブ一覧を実ファイル（root からの相対パス文字列）の集合へ展開する。

    展開結果が空だったグロブは empty_globs に記録して呼び出し元が警告できるようにする。
    ディレクトリ一致はファイルではないため集合に含めない。
    """
    files: set[str] = set()
    empty_globs: list[str] = []
    for pattern in patterns:
        matches = glob_mod.glob(pattern, root_dir=root, recursive=True)
        file_matches = [m for m in matches if (root / m).is_file()]
        if not file_matches:
            empty_globs.append(pattern)
        files.update(file_matches)
    return files, empty_globs


def check_overlap(lanes: dict[str, list[str]], root: Path = REPO_ROOT) -> dict:
    """レーンごとにグロブを展開し、レーン間のファイル重複を検出する。"""
    expanded: dict[str, set[str]] = {}
    warnings: list[str] = []
    for name, patterns in lanes.items():
        files, empty_globs = expand_lane(patterns, root)
        expanded[name] = files
        for g in empty_globs:
            warnings.append(f"レーン `{name}` のグロブ `{g}` は展開結果が空です（対象なし）")

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
        files, empty_globs = expand_lane(["dirA"], root)
        check("ディレクトリ単体一致はファイル扱いしない", files == set(), f"files={files}")

    print(f"\nセルフテスト: {passed} passed, {failed} failed / {passed + failed} cases")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lane", action="append", default=[], help="'name:glob1,glob2' 形式で繰り返し指定（主形式）")
    parser.add_argument("--lanes-json", dest="lanes_json", default=None, help="JSON 文字列 {\"レーン名\": [\"glob\",...]} で一括指定")
    parser.add_argument("--stdin", action="store_true", help="標準入力から同形式の JSON を読む")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="セルフテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    sources_used = sum([bool(args.lane), bool(args.lanes_json), args.stdin])
    if sources_used == 0:
        parser.print_help()
        return 2
    if sources_used > 1:
        print("❌ --lane / --lanes-json / --stdin は併用できません（いずれか 1 つ）", file=sys.stderr)
        return 2

    try:
        if args.lane:
            lanes = parse_lane_args(args.lane)
        else:
            raw = args.lanes_json if args.lanes_json is not None else sys.stdin.read()
            lanes = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"❌ 入力の解析に失敗: {e}", file=sys.stderr)
        return 2

    if not isinstance(lanes, dict) or len(lanes) < 2:
        print("⚠️  レーンが 2 未満のため重複判定はスキップします（比較対象がありません）")
        return 0

    result = check_overlap(lanes)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return 1 if result["has_overlap"] else 0


if __name__ == "__main__":
    sys.exit(main())
