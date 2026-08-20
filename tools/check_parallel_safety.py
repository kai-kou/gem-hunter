#!/usr/bin/env python3
"""check_parallel_safety.py — 進行中 PR / 進行中スプリントと候補 Issue の並行着手可否を検査する（#197）

## なぜ既存の `check_agent_scope_overlap.py` に相乗りしなかったか

`check_agent_scope_overlap.py` は「**対称な**レーン間グロブ重複」を見るツールである（並列委譲する
サブエージェント同士の担当ファイルが重ならないかを、同じ性質のレーン同士で総当たり比較する）。

本ツールが必要とするのは性質が異なる 3 点の判定である。

1. **非対称な比較**: 「進行中 PR の実ファイル一覧（GitHub API 由来・確定済み）」×「候補 Issue の
   想定変更ファイル（人間 or Claude の見積もり・未確定でありうる）」という、片方が確定情報で
   片方が見積もりという非対称な組を比較する。対称なレーン総当たりのモデルに無理に載せると、
   「進行中 PR 側もグロブ展開してよいのか」「候補側は展開しなくてよいのか」が契約として濁る。
2. **第 3 の判定 `undetermined`**: 既存ツールは `has_overlap`（重複あり/なし）の二値だが、本ツールは
   「候補の想定変更ファイルがそもそも未宣言（＝並行可否を判定する材料がない）」を **`conflict` とも
   `parallel_safe` とも異なる第 3 の verdict** として明示する必要がある（Issue #197 の完了条件:
   「想定変更ファイルが未確定の候補は『並行可能』と判定されない」）。これを既存ツールの二値の上に
   後付けすると、既存の呼び出し元（並列委譲の事前チェック）まで巻き込んで契約が濁る。
3. **入力ソースの違い**: 進行中 PR 側は `mcp__github__pull_request_read(method="get_files")` の生 JSON
   を直接読める経路（`--in-flight-json`）が要る。候補側にこの経路は要らない。

以上の理由で判定ロジックは新設し、**グロブ展開（`expand_lane`）だけは既存ツールから import して
再利用する**（ロジックを複製しない）。「新規作成予定でまだディスクに無いファイルをリテラルパスと
して拾う」フォールバックも `expand_lane` 側の改修（#197）でそのまま恩恵を受ける。

## 判定モデル

候補ごとに 3 verdict のいずれかを返す。

| verdict | 条件 |
|---|---|
| `conflict` | 候補の展開結果と、いずれかの in-flight ファイル集合に共通要素がある |
| `undetermined` | 候補の想定変更ファイルが未宣言（`--candidate "#199:"` のようにコロンの後が空） |
| `parallel_safe` | 宣言済みで、どの in-flight とも共通要素なし |

**in-flight 側は glob 展開しない（常にリテラル）**: GitHub API が返すファイルパスは実ファイル名
そのものであり、グロブとして解釈する理由がない。むしろ `[` `]` を含む実在パス（例:
`app/[locale]/repos/[owner]/[repo]/page.tsx`）をグロブの文字クラスとして誤展開してしまう事故を
防ぐため、`--in-flight` / `--in-flight-json` のパスは一切 glob 展開せずそのまま集合に入れる。

**候補側は glob 展開する（`expand_lane` を再利用）**: 候補の想定変更ファイルはグロブで書くのが
自然（例 `src/usecases/**`）なので、既存ツールの `expand_lane()` をそのまま使う。

## 使い方

    python3 tools/check_parallel_safety.py \\
        --in-flight "PR#183:app/[locale]/repos/[owner]/[repo]/page.tsx,src/foo.ts" \\
        --candidate "#172:src/usecases/**,src/composition/container.ts" \\
        --candidate "#199:"
    python3 tools/check_parallel_safety.py --self-test

終了コード: 全候補が `parallel_safe` なら 0、`conflict` が 1 件以上あれば 1、`conflict` は無いが
`undetermined` が 1 件以上あれば 3（「並行可能」と誤読させないため 0 を返さない）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_agent_scope_overlap import expand_lane  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────
# 入力パース
# ──────────────────────────────────────────────


def parse_in_flight_args(specs: list[str]) -> dict[str, set[str]]:
    """`--in-flight "label:path1,path2"` の繰り返し指定をラベルごとのファイル集合へ変換する。

    リテラルパスとして扱い glob 展開はしない（GitHub API 由来の実ファイル名のため）。
    """
    result: dict[str, set[str]] = {}
    for spec in specs:
        if ":" not in spec:
            raise ValueError(f"--in-flight は 'label:path1,path2' 形式で指定する（不正: {spec!r}）")
        label, _, paths_str = spec.partition(":")
        label = label.strip()
        if not label:
            raise ValueError(f"--in-flight のラベルが空: {spec!r}")
        paths = {p.strip() for p in paths_str.split(",") if p.strip()}
        result[label] = result.get(label, set()) | paths
    return result


def _extract_filenames_from_json(data: object, source: str) -> list[str]:
    """`get_files` 系 API の生 JSON からファイル名一覧を取り出す。

    3 形を受け付ける: ① オブジェクト配列（各要素の `filename`）② 文字列配列
    ③ `{"files": [...]}` のようにトップレベルが配列を保持するオブジェクト。
    想定外の形は黙って空にせず ValueError で落とす。
    """
    payload = data
    if isinstance(payload, dict):
        # トップレベルが配列を包んでいる形（例: {"files": [...]}）
        list_values = [v for v in payload.values() if isinstance(v, list)]
        if len(list_values) == 1:
            payload = list_values[0]
        else:
            raise ValueError(
                f"{source}: オブジェクトの中に配列フィールドが 1 つに定まらない（想定外の形）"
            )

    if not isinstance(payload, list):
        raise ValueError(f"{source}: トップレベルが配列でもオブジェクトでもない（想定外の形）")

    filenames: list[str] = []
    for item in payload:
        if isinstance(item, str):
            filenames.append(item)
        elif isinstance(item, dict) and isinstance(item.get("filename"), str):
            filenames.append(item["filename"])
        else:
            raise ValueError(f"{source}: 配列要素の形が想定外（filename を持つ object か string のみ許可）")
    return filenames


def parse_in_flight_json(paths: list[str]) -> dict[str, set[str]]:
    """`--in-flight-json FILE` の繰り返し指定を読み込み、ファイル stem をラベルにして返す。"""
    result: dict[str, set[str]] = {}
    for file_path in paths:
        p = Path(file_path)
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        filenames = _extract_filenames_from_json(data, str(p))
        label = p.stem
        result[label] = result.get(label, set()) | set(filenames)
    return result


def parse_candidate_args(specs: list[str]) -> dict[str, list[str] | None]:
    """`--candidate "label:glob1,glob2"` の繰り返し指定を候補辞書へ変換する。

    コロンの後が空（`"label:"`）は「想定変更ファイル未確定」を意味し None を格納する。
    コロンが 1 つも無い指定は ValueError。
    """
    result: dict[str, list[str] | None] = {}
    for spec in specs:
        if ":" not in spec:
            raise ValueError(f"--candidate は 'label:glob1,glob2' 形式で指定する（不正: {spec!r}）")
        label, _, globs_str = spec.partition(":")
        label = label.strip()
        if not label:
            raise ValueError(f"--candidate のラベルが空: {spec!r}")
        globs = [g.strip() for g in globs_str.split(",") if g.strip()]
        result[label] = globs if globs else None
    return result


# ──────────────────────────────────────────────
# 判定ロジック
# ──────────────────────────────────────────────


def judge_candidate(
    label: str,
    globs: list[str] | None,
    in_flight: dict[str, set[str]],
    root: Path,
) -> dict:
    """候補 1 件を判定する（`undetermined` / `conflict` / `parallel_safe`）。"""
    if globs is None:
        return {
            "label": label,
            "verdict": "undetermined",
            "files": [],
            "conflicts_with": {},
            "warnings": [],
        }

    files, empty_globs, out_of_scope, unmaterialized_literals = expand_lane(globs, root)
    warnings: list[str] = []
    for g in empty_globs:
        warnings.append(f"候補 `{label}` のグロブ `{g}` はファイルに一致しませんでした（対象なし）")
    for m in out_of_scope:
        warnings.append(f"候補 `{label}` の `{m}` はリポジトリ外（パストラバーサル）のため除外しました")
    for p in unmaterialized_literals:
        warnings.append(f"候補 `{label}` の `{p}` は未作成のリテラルパスとして扱いました")

    conflicts_with: dict[str, list[str]] = {}
    for in_flight_label, in_flight_files in in_flight.items():
        common = files & in_flight_files
        if common:
            conflicts_with[in_flight_label] = sorted(common)

    verdict = "conflict" if conflicts_with else "parallel_safe"
    return {
        "label": label,
        "verdict": verdict,
        "files": sorted(files),
        "conflicts_with": conflicts_with,
        "warnings": warnings,
    }


def decide_exit_code(verdicts: list[str]) -> int:
    """verdict 一覧から終了コードを決定する（`main()` を介さず単体テストできる純粋関数）。

    優先順位: conflict が 1 件でもあれば 1。conflict は無いが undetermined が 1 件でも
    あれば 3（「並行可能」と誤読させないため 0 を返さない）。どちらも無ければ 0。
    """
    if "conflict" in verdicts:
        return 1
    if "undetermined" in verdicts:
        return 3
    return 0


def check_parallel_safety(
    in_flight: dict[str, set[str]],
    candidates: dict[str, list[str] | None],
    root: Path = REPO_ROOT,
) -> dict:
    """全候補を判定し、集計結果を構造化して返す（`--json` 出力・人間向け出力の共通土台）。"""
    warnings: list[str] = []
    if not in_flight:
        warnings.append("in-flight（進行中 PR / 進行中スプリントの占有ファイル）が 1 件も指定されていません")

    results = [judge_candidate(label, globs, in_flight, root) for label, globs in candidates.items()]
    for r in results:
        warnings.extend(r.pop("warnings"))

    verdicts = [r["verdict"] for r in results]
    return {
        "candidates": results,
        "has_conflict": "conflict" in verdicts,
        "has_undetermined": "undetermined" in verdicts,
        "warnings": warnings,
    }


# ──────────────────────────────────────────────
# 出力
# ──────────────────────────────────────────────


def print_report(result: dict) -> None:
    for c in result["candidates"]:
        label, verdict = c["label"], c["verdict"]
        if verdict == "conflict":
            print(f"❌ 候補 `{label}`: conflict（{len(c['files'])} ファイル中に衝突あり）")
            for in_flight_label, files in c["conflicts_with"].items():
                for f in files:
                    print(f"    - {f}（in-flight `{in_flight_label}` と衝突）")
        elif verdict == "undetermined":
            print(f"❓ 候補 `{label}`: undetermined（想定変更ファイル未宣言）")
            print("    次の一手: 実装調査で想定変更ファイルを確定させてから再実行する")
        else:
            print(f"✅ 候補 `{label}`: parallel_safe（{len(c['files'])} ファイル・衝突なし）")

    for w in result["warnings"]:
        print(f"⚠️  {w}")


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

    # ── parse_in_flight_args ──
    inflight = parse_in_flight_args(["PR#183:app/x.tsx,src/foo.ts"])
    check(
        "parse_in_flight_args 正常系",
        inflight == {"PR#183": {"app/x.tsx", "src/foo.ts"}},
        str(inflight),
    )
    try:
        parse_in_flight_args(["broken"])
        check("parse_in_flight_args コロンなしで ValueError", False)
    except ValueError:
        check("parse_in_flight_args コロンなしで ValueError", True)

    # ── parse_candidate_args ──
    cands = parse_candidate_args(["#172:src/usecases/**,src/x.ts", "#199:"])
    check(
        "parse_candidate_args 正常系（宣言済み + 未確定の空指定）",
        cands == {"#172": ["src/usecases/**", "src/x.ts"], "#199": None},
        str(cands),
    )
    try:
        parse_candidate_args(["broken"])
        check("parse_candidate_args コロンなしで ValueError", False)
    except ValueError:
        check("parse_candidate_args コロンなしで ValueError", True)
    try:
        parse_candidate_args([":glob"])
        check("parse_candidate_args ラベル空で ValueError", False)
    except ValueError:
        check("parse_candidate_args ラベル空で ValueError", True)

    # ── decide_exit_code（純粋関数のみで検証） ──
    check("exit code: conflict あり→1", decide_exit_code(["conflict", "parallel_safe"]) == 1)
    check("exit code: undetermined のみ→3", decide_exit_code(["undetermined", "parallel_safe"]) == 3)
    check("exit code: conflict と undetermined 混在→1（衝突優先）", decide_exit_code(["conflict", "undetermined"]) == 1)
    check("exit code: 全 safe→0", decide_exit_code(["parallel_safe", "parallel_safe"]) == 0)
    check("exit code: 候補ゼロ→0", decide_exit_code([]) == 0)

    # ── _extract_filenames_from_json ──
    obj_array = [{"filename": "a.py"}, {"filename": "b.py"}]
    check(
        "JSON形式①（オブジェクト配列）",
        _extract_filenames_from_json(obj_array, "test") == ["a.py", "b.py"],
    )
    str_array = ["a.py", "b.py"]
    check(
        "JSON形式②（文字列配列）",
        _extract_filenames_from_json(str_array, "test") == ["a.py", "b.py"],
    )
    wrapped = {"files": [{"filename": "a.py"}]}
    check(
        "JSON形式③（トップレベルオブジェクトが配列を保持）",
        _extract_filenames_from_json(wrapped, "test") == ["a.py"],
    )
    try:
        _extract_filenames_from_json({"unexpected": "shape"}, "test")
        check("JSON想定外の形（配列フィールドなし）で ValueError", False)
    except ValueError:
        check("JSON想定外の形（配列フィールドなし）で ValueError", True)
    try:
        _extract_filenames_from_json(123, "test")
        check("JSON想定外の形（配列でもオブジェクトでもない）で ValueError", False)
    except ValueError:
        check("JSON想定外の形（配列でもオブジェクトでもない）で ValueError", True)
    try:
        _extract_filenames_from_json([1, 2, 3], "test")
        check("JSON配列要素が想定外の形で ValueError", False)
    except ValueError:
        check("JSON配列要素が想定外の形で ValueError", True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "foo.ts").write_text("x")
        (root / "src" / "usecases").mkdir()
        (root / "src" / "usecases" / "a.ts").write_text("x")

        # in-flight は glob 展開されない（`[` `]` を含むパスも文字クラス扱いされずリテラル一致）
        in_flight_bracket = {"PR#1": {"app/[locale]/page.tsx"}}
        result_bracket = judge_candidate(
            "#1", ["app/[locale]/page.tsx"], in_flight_bracket, root
        )
        check(
            "in-flight・候補ともブラケットパスがリテラル一致で衝突検出",
            result_bracket["verdict"] == "conflict"
            and result_bracket["conflicts_with"].get("PR#1") == ["app/[locale]/page.tsx"],
            str(result_bracket),
        )

        # 衝突検出
        result_conflict = judge_candidate("#172", ["src/usecases/**"], {"PR#183": {"src/usecases/a.ts"}}, root)
        check(
            "衝突を正しく検出",
            result_conflict["verdict"] == "conflict"
            and result_conflict["conflicts_with"] == {"PR#183": ["src/usecases/a.ts"]},
            str(result_conflict),
        )

        # 衝突なし
        result_safe = judge_candidate("#172", ["src/foo.ts"], {"PR#183": {"src/usecases/a.ts"}}, root)
        check("衝突なしを正しく parallel_safe", result_safe["verdict"] == "parallel_safe", str(result_safe))

        # 未宣言の候補が parallel_safe にならず undetermined になる（Issue #197 の完了条件そのもの）
        result_undetermined = judge_candidate("#199", None, {"PR#183": {"src/usecases/a.ts"}}, root)
        check(
            "未宣言の候補は undetermined（parallel_safe にならない）",
            result_undetermined["verdict"] == "undetermined",
            str(result_undetermined),
        )

        # check_parallel_safety 全体の集計
        overall = check_parallel_safety(
            {"PR#183": {"src/usecases/a.ts"}},
            {"#172": ["src/usecases/**"], "#199": None, "#200": ["src/foo.ts"]},
            root=root,
        )
        check(
            "check_parallel_safety の集計（conflict と undetermined を両方検出）",
            overall["has_conflict"] is True and overall["has_undetermined"] is True,
            str(overall),
        )

        # in-flight が 1 件も無い場合は宣言済み候補が parallel_safe になる
        overall_no_inflight = check_parallel_safety({}, {"#172": ["src/foo.ts"]}, root=root)
        check(
            "in-flight ゼロなら宣言済み候補は parallel_safe",
            overall_no_inflight["candidates"][0]["verdict"] == "parallel_safe",
            str(overall_no_inflight),
        )

    print(f"\nセルフテスト: {passed} passed, {failed} failed / {passed + failed} cases")
    return 0 if failed == 0 else 1


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in-flight", action="append", default=[], help="'label:path1,path2' 形式で繰り返し指定（リテラル）")
    parser.add_argument("--in-flight-json", action="append", default=[], help="get_files 系 API の生 JSON ファイルパス（繰り返し指定可）")
    parser.add_argument("--candidate", action="append", default=[], help="'label:glob1,glob2' 形式で繰り返し指定。'label:' は未確定を表す")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="セルフテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.candidate:
        parser.print_help()
        return 2

    try:
        in_flight = parse_in_flight_args(args.in_flight)
        for label, files in parse_in_flight_json(args.in_flight_json).items():
            in_flight[label] = in_flight.get(label, set()) | files
        candidates = parse_candidate_args(args.candidate)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"❌ 入力の解析に失敗: {e}", file=sys.stderr)
        return 2

    result = check_parallel_safety(in_flight, candidates)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return decide_exit_code([c["verdict"] for c in result["candidates"]])


if __name__ == "__main__":
    sys.exit(main())
