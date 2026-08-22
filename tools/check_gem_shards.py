#!/usr/bin/env python3
"""check_gem_shards.py — 配信シャード（public/data/gem-index/）の機械的な回帰チェック（`SP-17`）

【なぜ必要か（PR #416 セルフレビュー指摘）】
`public/data/gem-index/` のシャードは #388 が cold start で読む **配信契約** だが、
`daily-digest.json`（`check_digest_freshness.py`）と違って生成物を検証するものが 1 つも無かった。
索引（`index.json`）とシャード実体がずれても、列定義が変わっても、サイズが青天井に太っても、
誰も気づかないまま本番へ出てしまう。本ツールはその穴を埋める **生成物の静的検査** である。

【検査内容】
  1. 索引整合: `index.json` の `shards[].fileName` の集合が、ディレクトリ内の `*.json`
     （`index.json` を除く）と完全一致する（孤児シャード・索引漏れの検出）
  2. 件数整合: `index.json` の `totalCount` が全シャードの `entries` 件数の合計と一致する
     （あわせて `shards[].count` が各シャードの実件数と一致することも見る）
  3. 列定義: 各シャードの `columns` が期待の 5 列と一致する
  4. 行の形: 各 `entries` の要素が 5 要素の配列で、型が正しい（文字列 2 + 数値 3）・
     `repositoryFullName` が `owner/repo` 形式
  5. サイズ予算: シャード合計の raw バイト数が上限以下、かつ 1 ファイルが上限以下
  6. 決定論: `entries` が `gemIndex` 昇順に並んでいる

【意図的に検査しないこと】
🔴 `stars >= 5` のような **閾値の検査は入れない**。閾値は生成側の `--min-stars` で可変であり、
   生成物側に固定すると設定変更のたびに嘘の失敗が出る。代わりに `index.json` に設定値
   （`minStars` 相当）が記録されている場合に限り、それと突き合わせる（無ければ検査しない）。

【ネットワーク非依存】
`tools/run_checks.sh` はオフラインで完走できることを保つ。本ツールはローカルの生成物しか読まない。

使い方:
    python3 tools/check_gem_shards.py            # 既定パスを検査（違反があれば非ゼロ終了）
    python3 tools/check_gem_shards.py --json     # 機械可読な JSON で出力
    python3 tools/check_gem_shards.py --dir path/to/gem-index
    python3 tools/check_gem_shards.py --self-test  # ネットワーク・実データ不要のユニットテスト
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SHARD_DIR = REPO_ROOT / "public" / "data" / "gem-index"
INDEX_FILE_NAME = "index.json"

# 期待する列定義（配信契約。#388 の読み取り側と同じ並び）
EXPECTED_COLUMNS = ["repositoryFullName", "packageName", "dependentCount", "stars", "gemIndex"]

# 🔴 サイズ予算は「`D-38` の `limits.cpu_ms = 50` に対する実測が出るまでの暫定値」である。
#    シャードは Worker の cold start で読まれるため、無制限に太ると `Exceeded CPU limit` で
#    落ちる。`--quota` を上げれば生成側はいくらでも太らせられるので、ここで機械的に止める。
#    2026-08-22 時点の実測は合計 約 3.5 MiB・最大 約 565 KiB（2 倍強の余裕を見た値）。
#    超えたら PR を落として再検討する（黙って上限だけ引き上げない）。
TOTAL_SIZE_BUDGET_BYTES = 8 * 1024 * 1024   # 8 MiB
PER_SHARD_SIZE_BUDGET_BYTES = 2 * 1024 * 1024  # 2 MiB

# `owner/repo` 形式（スラッシュ 1 個・空白なし・前後に空要素なし）
REPO_FULL_NAME_RE = re.compile(r"^[^/\s]+/[^/\s]+$")

# 行のサンプル報告数（違反が大量に出たときにログを溢れさせない）
MAX_REPORTED_PER_KIND = 5

# 終了コード
EXIT_OK = 0
EXIT_VIOLATION = 1


def _is_number(value: object) -> bool:
    """真偽値を除いた数値（int / float）判定。JSON の `true` は数値として扱わない。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _read_json(path: Path) -> tuple[object | None, str | None]:
    """JSON を読む。失敗時は (None, エラーメッセージ) を返す（例外で落とさない）。"""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{path.name}: ファイルがありません"
    except json.JSONDecodeError as exc:
        return None, f"{path.name}: JSON として解釈できません（{exc}）"
    except OSError as exc:
        return None, f"{path.name}: 読み込みに失敗しました（{exc}）"


def _configured_min_stars(index: dict) -> float | None:
    """`index.json` に記録された最小 star 閾値を探す（無ければ None）。

    生成側の設定値が配信物に記録されている場合にだけ突き合わせるための取得口。
    キー名は生成側の都合で変わりうるので、代表的な置き場所を順に探す。
    """
    candidates: list[object] = []
    for key in ("minStars", "min_stars"):
        candidates.append(index.get(key))
        for container in ("config", "options", "params", "meta"):
            section = index.get(container)
            if isinstance(section, dict):
                candidates.append(section.get(key))
    for value in candidates:
        if _is_number(value):
            return float(value)
    return None


def _check_entries(file_name: str, entries: list, min_stars: float | None) -> list[str]:
    """1 シャードの `entries`（行）を検査して違反メッセージを返す。"""
    violations: list[str] = []
    shape_errors: list[str] = []
    order_errors: list[str] = []
    min_stars_errors: list[str] = []
    previous_gem_index: float | None = None

    for i, row in enumerate(entries):
        if not isinstance(row, list) or len(row) != len(EXPECTED_COLUMNS):
            shape_errors.append(f"entries[{i}] は {len(EXPECTED_COLUMNS)} 要素の配列ではありません: {row!r:.120}")
            continue
        repo_full_name, package_name, dependent_count, stars, gem_index = row
        if not isinstance(repo_full_name, str) or not REPO_FULL_NAME_RE.match(repo_full_name):
            shape_errors.append(f"entries[{i}][0] が owner/repo 形式ではありません: {repo_full_name!r}")
        if not isinstance(package_name, str) or package_name == "":
            shape_errors.append(f"entries[{i}][1] が非空の文字列ではありません: {package_name!r}")
        for col, value in ((2, dependent_count), (3, stars), (4, gem_index)):
            if not _is_number(value):
                shape_errors.append(
                    f"entries[{i}][{col}]（{EXPECTED_COLUMNS[col]}）が数値ではありません: {value!r}"
                )
        if _is_number(gem_index):
            if previous_gem_index is not None and gem_index < previous_gem_index:
                order_errors.append(
                    f"entries[{i}] の gemIndex={gem_index} が直前の {previous_gem_index} より小さい"
                )
            previous_gem_index = float(gem_index)
        if min_stars is not None and _is_number(stars) and stars < min_stars:
            min_stars_errors.append(f"entries[{i}] の stars={stars} が minStars={min_stars} 未満")

    for label, errors in (
        ("行の形式", shape_errors),
        ("gemIndex 昇順（決定論）", order_errors),
        ("minStars 突き合わせ", min_stars_errors),
    ):
        if errors:
            shown = "; ".join(errors[:MAX_REPORTED_PER_KIND])
            suffix = f" ほか {len(errors) - MAX_REPORTED_PER_KIND} 件" if len(errors) > MAX_REPORTED_PER_KIND else ""
            violations.append(f"{file_name}: {label}違反 {len(errors)} 件 — {shown}{suffix}")
    return violations


def evaluate(shard_dir: Path) -> dict:
    """シャードディレクトリを検査し、結果を dict で返す（例外で落とさない）。

    status: "ok" | "skipped" | "violation"
    """
    if not shard_dir.is_dir():
        return {
            "status": "skipped",
            "reason": f"{shard_dir} が存在しないためスキップしました（アプリ未生成のリポジトリで落とさない）",
            "violations": [],
            "summary": {},
        }

    violations: list[str] = []
    index_path = shard_dir / INDEX_FILE_NAME
    index, error = _read_json(index_path)
    if error is not None:
        return {"status": "violation", "reason": error, "violations": [error], "summary": {}}
    if not isinstance(index, dict):
        message = f"{INDEX_FILE_NAME}: トップレベルがオブジェクトではありません"
        return {"status": "violation", "reason": message, "violations": [message], "summary": {}}

    # --- 1. 索引整合（孤児シャード・索引漏れ） -------------------------------
    raw_shards = index.get("shards")
    if not isinstance(raw_shards, list):
        message = f"{INDEX_FILE_NAME}: shards が配列ではありません"
        return {"status": "violation", "reason": message, "violations": [message], "summary": {}}

    indexed_names: list[str] = []
    for i, shard in enumerate(raw_shards):
        if not isinstance(shard, dict) or not isinstance(shard.get("fileName"), str):
            violations.append(f"{INDEX_FILE_NAME}: shards[{i}] に文字列の fileName がありません")
            continue
        indexed_names.append(shard["fileName"])

    actual_names = sorted(p.name for p in shard_dir.glob("*.json") if p.name != INDEX_FILE_NAME)
    indexed_set, actual_set = set(indexed_names), set(actual_names)
    if len(indexed_names) != len(indexed_set):
        duplicates = sorted({n for n in indexed_names if indexed_names.count(n) > 1})
        violations.append(f"{INDEX_FILE_NAME}: shards[].fileName が重複しています: {', '.join(duplicates)}")
    missing_in_dir = sorted(indexed_set - actual_set)
    orphan_in_dir = sorted(actual_set - indexed_set)
    if missing_in_dir:
        violations.append(f"索引にあるがファイルが無い（索引漏れの逆）: {', '.join(missing_in_dir)}")
    if orphan_in_dir:
        violations.append(f"ファイルがあるが索引に無い（孤児シャード）: {', '.join(orphan_in_dir)}")

    min_stars = _configured_min_stars(index)

    # --- 2〜6. 各シャードの検査 ---------------------------------------------
    total_entries = 0
    total_bytes = 0
    largest = ("", 0)
    declared_counts = {
        s["fileName"]: s.get("count")
        for s in raw_shards
        if isinstance(s, dict) and isinstance(s.get("fileName"), str)
    }

    for name in sorted(indexed_set & actual_set):
        path = shard_dir / name
        size = path.stat().st_size
        total_bytes += size
        if size > largest[1]:
            largest = (name, size)
        if size > PER_SHARD_SIZE_BUDGET_BYTES:
            violations.append(
                f"{name}: 単一シャードのサイズ予算超過（{size:,} バイト > "
                f"{PER_SHARD_SIZE_BUDGET_BYTES:,} バイト）"
            )

        shard, error = _read_json(path)
        if error is not None:
            violations.append(error)
            continue
        if not isinstance(shard, dict):
            violations.append(f"{name}: トップレベルがオブジェクトではありません")
            continue

        if shard.get("columns") != EXPECTED_COLUMNS:
            violations.append(
                f"{name}: columns が期待と一致しません（期待 {EXPECTED_COLUMNS} / 実際 {shard.get('columns')!r}）"
            )

        entries = shard.get("entries")
        if not isinstance(entries, list):
            violations.append(f"{name}: entries が配列ではありません")
            continue
        total_entries += len(entries)

        declared = declared_counts.get(name)
        if _is_number(declared) and declared != len(entries):
            violations.append(
                f"{name}: index.json の count={declared} が実件数 {len(entries)} と一致しません"
            )

        violations.extend(_check_entries(name, entries, min_stars))

    # --- 2. 総件数整合 -------------------------------------------------------
    total_count = index.get("totalCount")
    if not _is_number(total_count):
        violations.append(f"{INDEX_FILE_NAME}: totalCount が数値ではありません: {total_count!r}")
    elif not missing_in_dir and not orphan_in_dir and total_count != total_entries:
        violations.append(
            f"{INDEX_FILE_NAME}: totalCount={total_count} が全シャードの entries 合計 {total_entries} と一致しません"
        )

    # --- 5. サイズ予算（合計） -----------------------------------------------
    if total_bytes > TOTAL_SIZE_BUDGET_BYTES:
        violations.append(
            f"シャード合計のサイズ予算超過（{total_bytes:,} バイト > {TOTAL_SIZE_BUDGET_BYTES:,} バイト）。"
            "cold start の CPU 予算（D-38 limits.cpu_ms）を脅かすので、上限を上げる前に再検討する"
        )

    summary = {
        "shard_count": len(indexed_set & actual_set),
        "total_entries": total_entries,
        "total_bytes": total_bytes,
        "total_budget_bytes": TOTAL_SIZE_BUDGET_BYTES,
        "largest_shard": largest[0],
        "largest_shard_bytes": largest[1],
        "per_shard_budget_bytes": PER_SHARD_SIZE_BUDGET_BYTES,
        "min_stars": min_stars,
    }
    if violations:
        return {
            "status": "violation",
            "reason": f"{len(violations)} 件の違反",
            "violations": violations,
            "summary": summary,
        }
    return {
        "status": "ok",
        "reason": (
            f"{summary['shard_count']} シャード / {total_entries:,} 件 / "
            f"{total_bytes / 1024 / 1024:.2f} MiB（予算 {TOTAL_SIZE_BUDGET_BYTES / 1024 / 1024:.0f} MiB）"
        ),
        "violations": [],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# --self-test（ネットワーク・実データ不要のユニットテスト）
# ---------------------------------------------------------------------------

def _write_fixture(base: Path, shards: dict[str, dict], index_overrides: dict | None = None) -> Path:
    """一時ディレクトリに index.json + シャードを書き出して、そのディレクトリを返す。"""
    base.mkdir(parents=True, exist_ok=True)
    index = {
        "meta": {"source": "test"},
        "totalCount": sum(len(s["entries"]) for s in shards.values()),
        "shards": [
            {"registry": name, "fileName": name, "count": len(shard["entries"])}
            for name, shard in shards.items()
        ],
    }
    if index_overrides:
        index.update(index_overrides)
    (base / INDEX_FILE_NAME).write_text(json.dumps(index), encoding="utf-8")
    for name, shard in shards.items():
        (base / name).write_text(json.dumps(shard), encoding="utf-8")
    return base


def _valid_shard(entries: list | None = None) -> dict:
    return {
        "registry": "npmjs.org",
        "ecosystem": "npm",
        "columns": list(EXPECTED_COLUMNS),
        "entries": entries if entries is not None else [
            ["owner/repo-a", "pkg-a", 100, 6, -90.5],
            ["owner/repo-b", "pkg-b", 50, 7, -80.25],
        ],
    }


def run_self_test() -> int:
    """正常・異常のシャードを一時ディレクトリに作って判定ロジックを検証する。"""
    failures: list[str] = []

    def expect(label: str, result: dict, want_status: str, want_keyword: str | None = None) -> None:
        if result["status"] != want_status:
            failures.append(f"{label}: status={result['status']} を期待 {want_status}（{result['reason']}）")
            return
        if want_keyword and not any(want_keyword in v for v in result["violations"]):
            failures.append(f"{label}: 違反メッセージに {want_keyword!r} が含まれません: {result['violations']}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1) ディレクトリ不在 → SKIP
        expect("不在ディレクトリ", evaluate(root / "nope"), "skipped")

        # 2) 正常
        ok_dir = _write_fixture(root / "ok", {"a.json": _valid_shard()})
        expect("正常データ", evaluate(ok_dir), "ok")

        # 3) 孤児シャード（索引に無いファイル）
        orphan_dir = _write_fixture(root / "orphan", {"a.json": _valid_shard()})
        (orphan_dir / "b.json").write_text(json.dumps(_valid_shard()), encoding="utf-8")
        expect("孤児シャード", evaluate(orphan_dir), "violation", "孤児シャード")

        # 4) 索引にあるがファイルが無い
        missing_dir = _write_fixture(root / "missing", {"a.json": _valid_shard()})
        index = json.loads((missing_dir / INDEX_FILE_NAME).read_text(encoding="utf-8"))
        index["shards"].append({"registry": "x", "fileName": "ghost.json", "count": 0})
        (missing_dir / INDEX_FILE_NAME).write_text(json.dumps(index), encoding="utf-8")
        expect("索引にあるがファイル不在", evaluate(missing_dir), "violation", "ファイルが無い")

        # 5) totalCount 不一致
        count_dir = _write_fixture(root / "count", {"a.json": _valid_shard()}, {"totalCount": 999})
        expect("totalCount 不一致", evaluate(count_dir), "violation", "totalCount=999")

        # 6) columns 不一致
        bad_columns = _valid_shard()
        bad_columns["columns"] = ["repositoryFullName", "packageName"]
        expect(
            "columns 不一致",
            evaluate(_write_fixture(root / "columns", {"a.json": bad_columns})),
            "violation",
            "columns が期待と一致しません",
        )

        # 7) 行の要素数不足
        expect(
            "要素数不足",
            evaluate(_write_fixture(root / "arity", {"a.json": _valid_shard([["owner/repo", "pkg", 1]])})),
            "violation",
            "要素の配列ではありません",
        )

        # 8) 型違反（stars が文字列）
        expect(
            "型違反",
            evaluate(_write_fixture(root / "types", {"a.json": _valid_shard([["owner/repo", "pkg", 1, "6", -1.0]])})),
            "violation",
            "数値ではありません",
        )

        # 9) owner/repo 形式違反
        expect(
            "owner/repo 形式違反",
            evaluate(_write_fixture(root / "fullname", {"a.json": _valid_shard([["justrepo", "pkg", 1, 6, -1.0]])})),
            "violation",
            "owner/repo 形式ではありません",
        )

        # 10) gemIndex 降順（決定論違反）
        unsorted_entries = [["o/a", "pkg-a", 1, 6, -1.0], ["o/b", "pkg-b", 2, 7, -9.0]]
        expect(
            "gemIndex 昇順違反",
            evaluate(_write_fixture(root / "order", {"a.json": _valid_shard(unsorted_entries)})),
            "violation",
            "gemIndex 昇順",
        )

        # 11) サイズ予算（単一ファイル超過）— パディングで人工的に太らせる
        fat = _valid_shard()
        fat["_padding"] = "x" * (PER_SHARD_SIZE_BUDGET_BYTES + 1024)
        expect(
            "単一シャードのサイズ予算超過",
            evaluate(_write_fixture(root / "fat", {"a.json": fat})),
            "violation",
            "単一シャードのサイズ予算超過",
        )

        # 12) minStars が index.json にあるとき突き合わせる
        low_star = _valid_shard([["o/a", "pkg-a", 1, 2, -1.0]])
        expect(
            "minStars 突き合わせ",
            evaluate(_write_fixture(root / "minstars", {"a.json": low_star}, {"minStars": 5})),
            "violation",
            "minStars",
        )

        # 13) minStars が無ければ star 閾値は検査しない（閾値は可変なので固定しない）
        expect(
            "minStars 未記録なら閾値検査なし",
            evaluate(_write_fixture(root / "nominstars", {"a.json": low_star})),
            "ok",
        )

        # 14) index.json が壊れている
        broken = root / "broken"
        broken.mkdir()
        (broken / INDEX_FILE_NAME).write_text("{ not json", encoding="utf-8")
        expect("index.json 破損", evaluate(broken), "violation", "JSON として解釈できません")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"セルフテスト: {len(failures)} 件 FAIL", file=sys.stderr)
        return 1
    print("セルフテスト: 14 ケース全て PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="配信シャード（public/data/gem-index/）の静的検査")
    parser.add_argument("--dir", default=str(DEFAULT_SHARD_DIR), help="シャードディレクトリのパス")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク・実データ不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    result = evaluate(Path(args.dir))

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["status"] == "skipped":
        print(f"SKIP: {result['reason']}")
    elif result["status"] == "ok":
        print(f"OK: 配信シャードは健全です（{result['reason']}）")
    else:
        print(f"NG: 配信シャードに問題があります（{result['reason']}）", file=sys.stderr)
        for violation in result["violations"]:
            print(f"  - {violation}", file=sys.stderr)

    sys.exit(EXIT_VIOLATION if result["status"] == "violation" else EXIT_OK)


if __name__ == "__main__":
    main()
