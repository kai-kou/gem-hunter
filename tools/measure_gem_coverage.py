#!/usr/bin/env python3
"""measure_gem_coverage.py — Gem 候補プールの被覆率を GitHub 検索の実測で測る（`D-36` / `D-37`）

【なぜ必要か】
`D-36` の被覆率（react 32% / test framework 36% / image processing 19%）は **一般語 3 件のみ** の
測定であり、母集団全体を代表するかは未検証（Issue #380 レトロの申し送り 1）。`D-37` は
「枠の値（レジストリごとの取得件数）を見直すときは被覆率を測り直して決定ログに追記する」と
定めている。本ツールはその測定を **再現可能なコマンド 1 つ** にする。

【測り方】
1. `public/data/gem-index/*.json`（配信シャード）を読み、`repositoryFullName` の集合を作る。
2. キーワードごとに GitHub の検索 API（`GET /search/repositories`・`sort` 指定なし＝関連度順）で
   上位 `--top` 件（既定 100）を取得する。
3. 上位 N 件のうち何件がプールに含まれるかを数える（= 被覆率）。

【クラウド実行環境での経路（🔴 重要）】
クラウドセッションからは `api.github.com` への直叩きが **403 で止まる**（`L-114`・GitHub API
プロキシの許可範囲外）。そのため検索結果は `mcp__github__search_repositories` で取得し、
`{"keyword": ["owner/repo", ...]}` 形式の JSON へ落として `--search-results` で渡す
（本ツールは集計だけを行う）。ローカル実行や `GITHUB_TOKEN` が使える環境では
`--search-results` を省略して直接取得できる。

【レート制限（直接取得のとき）】
未認証の検索 API は **10 req/分**。既定で 1 リクエストごとに 6.5 秒待つ（`--sleep`）。
`GITHUB_TOKEN` が環境にあれば `Authorization` ヘッダを付け、待ち時間を 2 秒へ短縮する
（認証時は 30 req/分）。トークンは表示・記録しない。

【日時】
記録する日時は JST（`docs/rules/datetime-rules.md`）。内部の経過時間計算のみ UTC。

使い方:
    python3 tools/measure_gem_coverage.py                      # 既定の一般語 24 件
    python3 tools/measure_gem_coverage.py --keywords react,orm # 任意のキーワード
    python3 tools/measure_gem_coverage.py --json out.json      # 結果を JSON で保存
    python3 tools/measure_gem_coverage.py --search-results r.json  # 取得済み検索結果から集計
    python3 tools/measure_gem_coverage.py --self-test          # ネットワーク不要の自己テスト
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SHARD_DIR = REPO_ROOT / "public" / "data" / "gem-index"
JST = timezone(timedelta(hours=9))
USER_AGENT = "gem-hunter/0.1 (+https://github.com/kai-kou/gem-hunter)"

# 一般語 24 件。`D-36` の 3 件（react / test framework / image processing）を必ず含めたうえで、
# 言語・分野が偏らないように広げる（特定エコシステムに寄せると被覆率が実力より高く出る）。
DEFAULT_KEYWORDS = [
    "react",
    "test framework",
    "image processing",
    "orm",
    "http client",
    "logging",
    "cli",
    "json parser",
    "web framework",
    "database driver",
    "authentication",
    "markdown",
    "csv",
    "date time",
    "encryption",
    "graphql",
    "machine learning",
    "template engine",
    "validation",
    "queue",
    "websocket",
    "pdf",
    "compression",
    "state management",
]


def load_pool_repos(shard_dir: Path) -> set[str]:
    """配信シャードから `repositoryFullName` の集合を作る（小文字化して比較する）。"""
    repos: set[str] = set()
    if not shard_dir.is_dir():
        raise FileNotFoundError(f"シャードディレクトリが見つかりません: {shard_dir}")
    for path in sorted(shard_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        columns = doc.get("columns") or []
        if "repositoryFullName" not in columns:
            continue
        idx = columns.index("repositoryFullName")
        for entry in doc.get("entries") or []:
            if isinstance(entry, list) and len(entry) > idx and isinstance(entry[idx], str):
                repos.add(entry[idx].lower())
    return repos


def search_github(keyword: str, top: int, token: str | None) -> list[str]:
    """GitHub 検索 API で関連度順の上位 `top` 件（最大 100）の `full_name` を返す。"""
    params = urllib.parse.urlencode({"q": keyword, "per_page": str(min(top, 100))})
    url = f"https://api.github.com/search/repositories?{params}"
    headers = {"user-agent": USER_AGENT, "accept": "application/vnd.github+json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as res:  # noqa: S310 (固定ホスト)
        body = json.load(res)
    return [item["full_name"] for item in body.get("items", [])][:top]


def measure(
    keywords: list[str],
    repos: set[str],
    top: int,
    sleep_seconds: float,
    token: str | None,
    prefetched: dict[str, list[str]] | None = None,
) -> dict:
    started = datetime.now(timezone.utc)
    rows = []
    for i, keyword in enumerate(keywords):
        if prefetched is not None:
            names = [n for n in prefetched.get(keyword, []) if isinstance(n, str)][:top]
            if not names:
                print(
                    f"[measure_gem_coverage] WARN: {keyword!r} の検索結果が渡されていません",
                    file=sys.stderr,
                )
                continue
        else:
            if i > 0:
                time.sleep(sleep_seconds)
            try:
                names = search_github(keyword, top, token)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as err:
                print(
                    f"[measure_gem_coverage] WARN: {keyword!r} の取得に失敗しました: {err}",
                    file=sys.stderr,
                )
                continue
        hits = [n for n in names if n.lower() in repos]
        rows.append(
            {
                "keyword": keyword,
                "searched": len(names),
                "hits": len(hits),
                "coverage": round(len(hits) / len(names) * 100, 1) if names else 0.0,
                "sampleHits": hits[:5],
            }
        )
        print(
            f"[measure_gem_coverage] {keyword}: {len(hits)}/{len(names)} "
            f"({rows[-1]['coverage']}%)",
            file=sys.stderr,
        )
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    coverages = [r["coverage"] for r in rows]
    total_searched = sum(r["searched"] for r in rows)
    total_hits = sum(r["hits"] for r in rows)
    return {
        "measuredAt": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "poolSize": len(repos),
        "top": top,
        "keywordCount": len(rows),
        "elapsedSeconds": round(elapsed, 1),
        "meanCoverage": round(sum(coverages) / len(coverages), 1) if coverages else 0.0,
        "medianCoverage": round(sorted(coverages)[len(coverages) // 2], 1) if coverages else 0.0,
        "minCoverage": min(coverages) if coverages else 0.0,
        "maxCoverage": max(coverages) if coverages else 0.0,
        "weightedCoverage": (
            round(total_hits / total_searched * 100, 1) if total_searched else 0.0
        ),
        "zeroHitKeywords": [r["keyword"] for r in rows if r["hits"] == 0],
        "rows": rows,
    }


def render_markdown(result: dict) -> str:
    lines = [
        f"| キーワード | 上位 {result['top']} 件中のヒット | 被覆率 |",
        "|---|---|---|",
    ]
    for row in result["rows"]:
        lines.append(f"| `{row['keyword']}` | {row['hits']} / {row['searched']} | {row['coverage']}% |")
    lines.append("")
    lines.append(
        f"- 母集団: **{result['poolSize']:,} リポジトリ** / 測定: {result['measuredAt']} / "
        f"キーワード {result['keywordCount']} 件"
    )
    lines.append(
        f"- 平均 **{result['meanCoverage']}%** / 中央値 {result['medianCoverage']}% / "
        f"最小 {result['minCoverage']}% / 最大 {result['maxCoverage']}% / "
        f"加重（総ヒット ÷ 総件数）{result['weightedCoverage']}%"
    )
    if result["zeroHitKeywords"]:
        lines.append(f"- 🔴 0 件ヒットのキーワード: {', '.join(result['zeroHitKeywords'])}")
    else:
        lines.append("- 0 件ヒットのキーワードなし")
    return "\n".join(lines)


def self_test() -> int:
    """ネットワークを使わない自己テスト（集計ロジックの検証）。"""
    repos = {"a/b", "c/d"}
    result = measure([], repos, 100, 0, None)
    assert result["keywordCount"] == 0, result
    assert result["meanCoverage"] == 0.0, result

    # 取得済み検索結果からの集計（クラウド経路）
    prefetched_result = measure(
        ["x"], repos, 100, 0, None, {"x": ["A/B", "e/f", "c/d"]}
    )
    assert prefetched_result["rows"][0]["hits"] == 2, prefetched_result
    assert prefetched_result["rows"][0]["searched"] == 3, prefetched_result

    # シャード読み込み（列順に依存しないこと）
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "npmjs-org.json").write_text(
            json.dumps(
                {
                    "columns": ["packageName", "repositoryFullName", "gemIndex"],
                    "entries": [["x", "Owner/Repo", -1.0], ["y", "o2/r2", -2.0]],
                }
            ),
            encoding="utf-8",
        )
        (d / "index.json").write_text(json.dumps({"totalCount": 2}), encoding="utf-8")
        loaded = load_pool_repos(d)
    assert loaded == {"owner/repo", "o2/r2"}, loaded

    rendered = render_markdown(
        {
            "top": 100,
            "rows": [{"keyword": "react", "hits": 30, "searched": 100, "coverage": 30.0}],
            "poolSize": 100,
            "measuredAt": "2026-08-22 12:00 JST",
            "keywordCount": 1,
            "meanCoverage": 30.0,
            "medianCoverage": 30.0,
            "minCoverage": 30.0,
            "maxCoverage": 30.0,
            "weightedCoverage": 30.0,
            "zeroHitKeywords": [],
        }
    )
    assert "`react`" in rendered and "30.0%" in rendered, rendered
    print("[measure_gem_coverage] self-test PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shard-dir", default=str(DEFAULT_SHARD_DIR))
    parser.add_argument("--keywords", help="カンマ区切り（既定は一般語 24 件）")
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=None, help="リクエスト間の待機秒数")
    parser.add_argument("--json", dest="json_out", help="結果 JSON の保存先")
    parser.add_argument(
        "--search-results",
        help='取得済み検索結果の JSON（{"keyword": ["owner/repo", ...]}）。クラウドでは MCP 経由で作る',
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    token = os.environ.get("GITHUB_TOKEN") or None
    sleep_seconds = args.sleep if args.sleep is not None else (2.0 if token else 6.5)
    prefetched = None
    if args.search_results:
        prefetched = json.loads(Path(args.search_results).read_text(encoding="utf-8"))
        if not isinstance(prefetched, dict):
            raise SystemExit("--search-results は {キーワード: [owner/repo, ...]} の JSON を指定してください")
    keywords = (
        [k.strip() for k in args.keywords.split(",") if k.strip()]
        if args.keywords
        else (list(prefetched.keys()) if prefetched else list(DEFAULT_KEYWORDS))
    )

    repos = load_pool_repos(Path(args.shard_dir))
    result = measure(keywords, repos, args.top, sleep_seconds, token, prefetched)
    print(render_markdown(result))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
