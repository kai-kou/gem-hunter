#!/usr/bin/env python3
"""retire_preview_aliases.py — 完了スプリントのプレビュー環境を退役（retire）させる

【背景・設計の正本】
`content/discussions/sprint-env-lifecycle-20260820/whiteboard.md`（Issue #231・議論型レビュー
round 3・lead 判定「A/E: スプリント環境の後始末」）。要点:

  - Cloudflare Workers の **version / preview alias を PR 単位で削除する CLI・REST API は
    存在しない**（実測で確認。自動失効は「直近 1000 alias の LRU」のみ）。
  - Worker 全体の `previews_enabled` トグルは並行中の他 PR のプレビューまで巻き添えにするため
    通常運用では使わない（`SD-1` と両立しない）。
  - 一方 **同名 alias の張り替えは可能**（`versions upload --preview-alias <name>` を同じ名前で
    再実行すると、その alias は新しい version を指す）。
  - よって後始末は「削除」ではなく **退役（retire）= 完了スプリントの alias を本番と同じ
    ビルドで張り替える** で実現する（飼い主の選択・2026-08-20 JST）。URL は生き続けるが、
    古いスプリントのコードを配信し続ける状態は解消される。

【前提】
退役は「いま手元にあるビルド成果物」をアップロードする。したがって **本番デプロイ直後
（`npm run deploy` が main HEAD で作った `.open-next` が残っている状態）に実行する** のが
正しい使い方である。既定では HEAD が `origin/main` と一致することを要求し、一致しなければ
実行しない（fail-closed。`--allow-non-main` で明示的に回避できる）。

【終了コード】
  0 = 成功（`--list` は常に 0。退役対象ゼロも 0）
  1 = 一部または全部の退役に失敗した
  2 = 前提を満たさない（認証情報なし・ビルド成果物なし・HEAD が main でない・API 到達不可）

使い方:
    python3 tools/retire_preview_aliases.py --list
    python3 tools/retire_preview_aliases.py --alias pr-212
    python3 tools/retire_preview_aliases.py --closed-prs
    python3 tools/retire_preview_aliases.py --closed-prs --dry-run
    python3 tools/retire_preview_aliases.py --self-test    # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mask_secrets import mask_text, mask_value  # noqa: E402
from repo_slug import resolve_repo_slug  # noqa: E402
from wrangler_config import parse_worker_name  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CF_API_BASE = "https://api.cloudflare.com/client/v4"
GH_API_BASE = "https://api.github.com"
BUILD_OUTPUT = os.path.join(REPO_ROOT, ".open-next", "worker.js")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PRECONDITION = 2

# alias 名から PR 番号を取り出すパターン（`pr-<N>` 形式のみを PR 由来とみなす）
PR_ALIAS_RE = re.compile(r"^pr-(\d+)$")

# select_closed_pr_aliases() が退役対象とみなす状態（#613）。
# "issue:closed" は `pr-<N>` の N が実際には PR ではなく Issue 番号として起票された
# ケース（`/pulls/<N>` が 404 で `/issues/<N>` にフォールバックした結果）を指す。
RETIRABLE_STATES = ("closed", "merged", "issue:closed")


class Precondition(Exception):
    """前提を満たさないときに送出する（終了コード 2 に対応）。"""


# ---------------------------------------------------------------------------
# 純粋関数（self-test の対象）
# ---------------------------------------------------------------------------


def _read_worker_name(jsonc_text: str) -> str:
    """wrangler.jsonc の中身から Worker 名を読み取る（共有パーサは `wrangler_config.py`。
    Layer 1 セルフレビュー WARNING-6・PR #460 — `trigger_workers_build.py` と一言一句同一だった
    パースロジックを共有モジュールへ一本化し、ここでは `ValueError` を `Precondition` へ wrap
    するだけにする）。
    """
    try:
        return parse_worker_name(jsonc_text)
    except ValueError as error:
        raise Precondition(str(error)) from error


def latest_alias_map(versions: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """version 一覧から「alias -> 最新 version」の対応を作る。

    同じ alias が複数の version に紐づく（＝過去に張り替えた）ことがあるため、
    `metadata.created_on` が最大のものを現在の指し先として採用する。
    """
    latest: dict[str, dict[str, str]] = {}
    for item in versions:
        alias = ((item.get("annotations") or {}).get("workers/alias") or "").strip()
        if not alias:
            continue
        created = ((item.get("metadata") or {}).get("created_on") or "")
        current = latest.get(alias)
        if current is None or created > current["created_on"]:
            latest[alias] = {
                "version_id": str(item.get("id") or ""),
                "created_on": created,
                "tag": str((item.get("annotations") or {}).get("workers/tag") or ""),
            }
    return latest


def alias_pr_number(alias: str) -> int | None:
    """alias 名が `pr-<N>` 形式ならその PR 番号を返す。それ以外は None。"""
    matched = PR_ALIAS_RE.match(alias.strip())
    return int(matched.group(1)) if matched else None


def select_closed_pr_aliases(
    alias_map: dict[str, dict[str, str]],
    pr_states: dict[int, str],
    retired_prefix: str = "retired-",
) -> list[str]:
    """クローズ済み（merged 含む）PR に紐づき、まだ退役していない alias を選ぶ。

    - `pr-<N>` 形式でない alias（`sp1` 等）は自動選別の対象にしない（`--alias` で明示指定する）
    - PR が open のものは対象にしない（レビュー中のプレビューを壊さないため）
    - PR 状態が取得できなかったものは対象にしない（fail-closed）
    - `<N>` が PR ではなく Issue として起票されていた場合（`issue:closed` / `issue:open`）も、
      Issue が closed なら対象にする（open なら PR の open と同じく対象にしない・#613）
    - 現在の指し先の tag が `retired-` で始まる alias は退役済みとみなして再実行しない
    """
    targets = []
    for alias, info in alias_map.items():
        number = alias_pr_number(alias)
        if number is None:
            continue
        state = pr_states.get(number)
        if state not in RETIRABLE_STATES:
            continue
        if info.get("tag", "").startswith(retired_prefix):
            continue
        targets.append(alias)
    return sorted(targets, key=lambda a: alias_pr_number(a) or 0)


def build_retire_command(alias: str, tag: str) -> list[str]:
    """退役に使う wrangler コマンドを組み立てる。"""
    if not alias:
        raise ValueError("alias が空です")
    return [
        "npx",
        "wrangler",
        "versions",
        "upload",
        "--preview-alias",
        alias,
        "--tag",
        tag,
    ]


def retire_tag(sha: str) -> str:
    """退役であることが後から分かるタグ文字列を作る（wrangler のタグ長制限に配慮して短縮する）。"""
    short = (sha or "unknown")[:12]
    return f"retired-{short}"


def exit_code_for(results: list[dict[str, Any]]) -> int:
    """退役結果の一覧から終了コードを決める（1 件でも失敗があれば 1）。"""
    if not results:
        return EXIT_OK
    return EXIT_FAILED if any(not r.get("ok") for r in results) else EXIT_OK


def should_fetch_next_page(result_info: dict[str, Any], fetched_count: int, page_item_count: int) -> bool:
    """Cloudflare API の `result_info`（page/per_page/count/total_count）を見て
    次ページを取得すべきか判定する（純粋関数）。

    実測（2026-08-20 JST・GET .../versions?per_page=100）: `result_info` はペイロード直下にあり、
    `{"page": 1, "per_page": 100, "count": 35, "total_count": 35}` の形。`total_pages` フィールドは
    無いため `total_count` との比較で継続判定する。
    """
    if page_item_count == 0:
        return False
    total_count = result_info.get("total_count")
    if total_count is None:
        # total_count が取れない応答は継続条件を判定できないため、無限ループを避けて打ち切る
        return False
    return fetched_count < total_count


# ---------------------------------------------------------------------------
# 外部 I/O
# ---------------------------------------------------------------------------


def _http_json(url: str, headers: dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def fetch_versions(account_id: str, token: str, worker: str) -> list[dict[str, Any]]:
    """Cloudflare API から version 一覧を取得する（`result_info.total_count` を見て全ページ取得）。

    100 件（1 ページの上限）を超えると古い alias から順に見落とすため（WARNING・PR #235）、
    `should_fetch_next_page()` の判定に従ってページングする。
    """
    per_page = 100
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        url = (
            f"{CF_API_BASE}/accounts/{account_id}/workers/scripts/{worker}/versions"
            f"?per_page={per_page}&page={page}"
        )
        try:
            payload = _http_json(url, {"Authorization": f"Bearer {token}"})
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as error:
            raise Precondition(f"Cloudflare API に到達できません: {error}") from error
        if not payload.get("success"):
            raise Precondition(f"Cloudflare API がエラーを返しました: {payload.get('errors')}")
        result = payload.get("result")
        page_items = result.get("items", []) if isinstance(result, dict) else (result or [])
        items.extend(page_items)
        if not should_fetch_next_page(payload.get("result_info") or {}, len(items), len(page_items)):
            break
        page += 1
    return items


def fetch_pr_states(repo: str, numbers: list[int]) -> dict[int, str]:
    """GitHub API で PR の状態を取得する（取得できなかった番号は結果に入れない）。

    `pr-<N>` 形式の alias でも、`<N>` が実際には PR ではなく **Issue 番号**として起票された
    作業単位を指すことがある（本プロジェクトの運用上、`SP-n` の作業が PR ではなく Issue 単位で
    完結するケース。#613 の実測で `pr-442` / `pr-388` 等 5 件が該当し、`/pulls/<N>` の 404 で
    fail-closed のまま退役対象から永久に外れていた）。`/pulls/<N>` が 404 のときだけ
    `/issues/<N>` へフォールバックする（PR が本当に存在しない番号を Issue 扱いするだけなので、
    PR が open/closed どちらであってもフォールバックしない＝誤判定の余地はない）。
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "retire-preview-aliases"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    states: dict[int, str] = {}
    for number in numbers:
        try:
            data = _http_json(f"{GH_API_BASE}/repos/{repo}/pulls/{number}", headers)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                issue_state = _fetch_issue_state(repo, number, headers)
                if issue_state is not None:
                    states[number] = issue_state
            continue
        except (urllib.error.URLError, ValueError, OSError):
            continue
        if data.get("merged_at"):
            states[number] = "merged"
        else:
            states[number] = str(data.get("state") or "")
    return states


def _fetch_issue_state(repo: str, number: int, headers: dict[str, str]) -> str | None:
    """`/pulls/<N>` が 404 のとき、`<N>` が Issue として起票されていないか確認する。

    Issue が見つかれば `"issue:<state>"`（例: `"issue:closed"`）、見つからない・取得できない
    ときは None を返す（従来どおり fail-closed のまま）。
    """
    try:
        data = _http_json(f"{GH_API_BASE}/repos/{repo}/issues/{number}", headers)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return None
    state = str(data.get("state") or "")
    return f"issue:{state}" if state else None


def git_head_sha() -> str:
    proc = subprocess.run(
        ["git", "-C", REPO_ROOT, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def head_matches_main() -> bool:
    """HEAD が origin/main と一致するか（退役アップロードの中身が本番と同じであることの確認）。"""
    head = git_head_sha()
    proc = subprocess.run(
        ["git", "-C", REPO_ROOT, "rev-parse", "origin/main"],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(head) and proc.returncode == 0 and proc.stdout.strip() == head




def mask_output(text: str, secrets: dict[str, str] | None = None) -> str:
    """wrangler 等の出力から既知の秘匿値を除去する（純粋関数・Issue/PR コメント記録用・WARNING PR #235）。

    実体は `mask_secrets.mask_text()`（PR #289 で共通化。`check_prod_drift.py` と共有する）。
    本関数は後方互換のための薄い別名であり、新規コードは `mask_text()` を直接使う。
    """
    return mask_text(text, secrets)


def run_retire(alias: str, tag: str, dry_run: bool) -> dict[str, Any]:
    command = build_retire_command(alias, tag)
    if dry_run:
        return {"alias": alias, "ok": True, "dry_run": True, "command": " ".join(command)}
    proc = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    output = mask_output(f"{proc.stdout}\n{proc.stderr}")
    url_match = re.search(r"https://[a-zA-Z0-9.-]+\.workers\.dev", output)
    return {
        "alias": alias,
        "ok": proc.returncode == 0,
        "dry_run": False,
        "url": url_match.group(0) if url_match else "",
        "error": "" if proc.returncode == 0 else output.strip()[-800:],
    }


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def self_test() -> int:
    failures: list[str] = []
    check_count = 0

    def check(label: str, actual: Any, expected: Any) -> None:
        nonlocal check_count
        check_count += 1
        if actual != expected:
            failures.append(f"{label}: 期待 {expected!r} / 実際 {actual!r}")

    # parse_worker_name 本体（コメント除去・パース）のテストは共有モジュール
    # `wrangler_config.py` の self-test 側の責務（Layer 1 セルフレビュー WARNING-6・重複を残さない）。
    # ここでは `ValueError` → `Precondition` への wrap だけを確認する。
    try:
        _read_worker_name('{"main": "src/index.ts"}')  # name が無い
        failures.append("_read_worker_name: name が無いのに Precondition を送出していない")
    except Precondition:
        pass

    versions = [
        {
            "id": "aaa",
            "metadata": {"created_on": "2026-08-19T04:22:19Z"},
            "annotations": {"workers/alias": "pr-96"},
        },
        {
            "id": "bbb",
            "metadata": {"created_on": "2026-08-19T04:52:39Z"},
            "annotations": {"workers/alias": "pr-96", "workers/tag": "abc123"},
        },
        {
            "id": "ccc",
            "metadata": {"created_on": "2026-08-20T05:45:10Z"},
            "annotations": {"workers/alias": "pr-212"},
        },
        {"id": "ddd", "metadata": {"created_on": "2026-08-20T06:00:00Z"}, "annotations": {}},
    ]
    alias_map = latest_alias_map(versions)
    check("同名 alias は最新 version を採用する", alias_map["pr-96"]["version_id"], "bbb")
    check("alias なしの version は無視する", sorted(alias_map), ["pr-212", "pr-96"])

    check("alias から PR 番号を取る", alias_pr_number("pr-212"), 212)
    check("PR 由来でない alias は None", alias_pr_number("sp1"), None)
    check("末尾に余計な語が付く alias は None", alias_pr_number("pr-212-old"), None)

    states = {96: "merged", 212: "open", 143: "closed", 442: "issue:closed", 388: "issue:open"}
    wide_map = {
        "pr-96": {"version_id": "bbb", "created_on": "x", "tag": ""},
        "pr-212": {"version_id": "ccc", "created_on": "x", "tag": ""},
        "pr-143": {"version_id": "eee", "created_on": "x", "tag": ""},
        "pr-999": {"version_id": "fff", "created_on": "x", "tag": ""},
        "sp1": {"version_id": "ggg", "created_on": "x", "tag": ""},
        "pr-88": {"version_id": "hhh", "created_on": "x", "tag": "retired-0123456789ab"},
        "pr-442": {"version_id": "iii", "created_on": "x", "tag": ""},
        "pr-388": {"version_id": "jjj", "created_on": "x", "tag": ""},
    }
    selected = select_closed_pr_aliases(wide_map, states)
    check(
        "open PR / PR 由来でない alias / 退役済み / Issue open を除く",
        selected,
        ["pr-96", "pr-143", "pr-442"],
    )
    check(
        "状態を取得できなかった PR は対象外（fail-closed）",
        "pr-999" in select_closed_pr_aliases(wide_map, states),
        False,
    )
    check(
        "N が Issue 番号で closed なら退役対象にする（#613）",
        "pr-442" in selected,
        True,
    )
    check(
        "N が Issue 番号でも open なら退役対象にしない",
        "pr-388" in selected,
        False,
    )

    check(
        "退役コマンドの組み立て",
        build_retire_command("pr-212", "retired-abc123def456"),
        [
            "npx",
            "wrangler",
            "versions",
            "upload",
            "--preview-alias",
            "pr-212",
            "--tag",
            "retired-abc123def456",
        ],
    )
    check("退役タグは 12 桁に短縮する", retire_tag("abcdef0123456789abcdef"), "retired-abcdef012345")

    check("対象ゼロは成功扱い", exit_code_for([]), EXIT_OK)
    check("全件成功", exit_code_for([{"ok": True}, {"ok": True}]), EXIT_OK)
    check("1 件でも失敗したら 1", exit_code_for([{"ok": True}, {"ok": False}]), EXIT_FAILED)

    # --- C: ページング判定（should_fetch_next_page・PR #235 CRITICAL の再発防止） ---
    check(
        "1 ページで全件取得できたら継続しない（実測 total_count=35, per_page=100 相当）",
        should_fetch_next_page({"page": 1, "per_page": 100, "count": 35, "total_count": 35}, 35, 35),
        False,
    )
    check(
        "total_count が per_page を超えるなら継続する（100 件超の見落とし防止）",
        should_fetch_next_page({"page": 1, "per_page": 100, "count": 100, "total_count": 250}, 100, 100),
        True,
    )
    check(
        "累積が total_count に達したら継続しない（最終ページ）",
        should_fetch_next_page({"page": 3, "per_page": 100, "count": 50, "total_count": 250}, 250, 50),
        False,
    )
    check(
        "このページが 0 件なら継続しない（無限ループ防止）",
        should_fetch_next_page({"page": 5, "per_page": 100, "total_count": 250}, 200, 0),
        False,
    )
    check(
        "total_count が取れない応答は継続しない（fail-safe・無限ループ防止）",
        should_fetch_next_page({"page": 1, "per_page": 100, "count": 10}, 10, 10),
        False,
    )

    # --- D: 出力マスク（mask_output・PR #235 WARNING） ---
    check(
        "既知の秘匿値（環境変数実値）をマスクする",
        mask_output(
            "error: token=abcdef123456 invalid", secrets={"CLOUDFLARE_API_TOKEN": "abcdef123456"}
        ),
        f"error: token={mask_value('abcdef123456')} invalid",
    )
    check(
        "Bearer <token> 形式を除去する",
        mask_output("Authorization: Bearer sk-abcdefghijklmnop1234567890", secrets={}),
        "Authorization: Bearer ****",
    )
    check("空文字はそのまま返す", mask_output("", secrets={}), "")
    check(
        "秘匿値を含まないテキストは変化しない",
        mask_output("wrangler deploy 成功しました", secrets={"X": "abcdef123456"}),
        "wrangler deploy 成功しました",
    )

    # --- E: 退役ブロック判定（should_block_retire・PR #235 WARNING） ---
    check(
        "ビルド成果物が無ければブロックする",
        should_block_retire(build_exists=False, head_is_main=True, allow_non_main=False) is not None,
        True,
    )
    check(
        "HEAD が main でなく --allow-non-main も無ければブロックする",
        should_block_retire(build_exists=True, head_is_main=False, allow_non_main=False) is not None,
        True,
    )
    check(
        "HEAD が main でなくても --allow-non-main ならブロックしない",
        should_block_retire(build_exists=True, head_is_main=False, allow_non_main=True),
        None,
    )
    check(
        "ビルド成果物あり・HEAD が main ならブロックしない",
        should_block_retire(build_exists=True, head_is_main=True, allow_non_main=False),
        None,
    )

    if failures:
        print("セルフテスト: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return EXIT_FAILED
    print(f"セルフテスト: 全 {check_count} ケース PASS")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_context() -> tuple[str, str, str]:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not token:
        raise Precondition(
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN がセッション環境にありません"
        )
    with open(os.path.join(REPO_ROOT, "wrangler.jsonc"), encoding="utf-8") as handle:
        worker = _read_worker_name(handle.read())
    return account_id, token, worker


def cmd_list(args: argparse.Namespace) -> int:
    account_id, token, worker = load_context()
    versions = fetch_versions(account_id, token, worker)
    alias_map = latest_alias_map(versions)
    numbers = [n for n in (alias_pr_number(a) for a in alias_map) if n is not None]
    states = fetch_pr_states(args.repo, numbers)
    retirable = select_closed_pr_aliases(alias_map, states)

    rows = []
    for alias in sorted(alias_map, key=lambda a: alias_map[a]["created_on"], reverse=True):
        info = alias_map[alias]
        number = alias_pr_number(alias)
        rows.append(
            {
                "alias": alias,
                "version_id": info["version_id"][:8],
                "created_on": info["created_on"][:19],
                "pr": number,
                "pr_state": states.get(number, "") if number else "",
                "tag": info["tag"],
                "retirable": alias in retirable,
            }
        )

    if args.json:
        print(json.dumps({"versions": len(versions), "aliases": rows}, ensure_ascii=False, indent=2))
        return EXIT_OK

    print(f"version 総数: {len(versions)} / alias 付き: {len(alias_map)}")
    print(f"{'alias':<18} {'version':<10} {'作成日時(UTC)':<20} {'PR':<7} {'退役対象'}")
    for row in rows:
        mark = "✅" if row["retirable"] else "-"
        pr_label = f"#{row['pr']}({row['pr_state'] or '状態不明'})" if row["pr"] else "-"
        print(
            f"{row['alias']:<18} {row['version_id']:<10} {row['created_on']:<20} {pr_label:<7} {mark}"
        )
    print(f"\n退役対象: {len(retirable)} 件 → {' '.join(retirable) if retirable else 'なし'}")
    return EXIT_OK


def should_block_retire(*, build_exists: bool, head_is_main: bool, allow_non_main: bool) -> str | None:
    """退役実行前の安全装置（純粋関数・WARNING PR #235）。

    ブロックすべきならその理由（メッセージ）を返し、問題なければ None を返す。
    `cmd_retire` はこの結果をそのまま `Precondition` に渡すだけにし、分岐そのものを self-test で固定する。
    """
    if not build_exists:
        return (
            f"ビルド成果物 {BUILD_OUTPUT} がありません。"
            " 本番デプロイ（npm run deploy）の直後に実行してください"
        )
    if not allow_non_main and not head_is_main:
        return (
            "HEAD が origin/main と一致しません。退役は本番と同じ内容を張り替える操作なので、"
            " main HEAD で実行してください（意図的に外すときは --allow-non-main）"
        )
    return None


def cmd_retire(args: argparse.Namespace, aliases: list[str]) -> int:
    if not aliases:
        print("退役対象はありません。")
        return EXIT_OK
    if not args.dry_run:
        block_reason = should_block_retire(
            build_exists=os.path.exists(BUILD_OUTPUT),
            head_is_main=head_matches_main(),
            allow_non_main=args.allow_non_main,
        )
        if block_reason:
            raise Precondition(block_reason)

    tag = retire_tag(git_head_sha())
    results = [run_retire(alias, tag, args.dry_run) for alias in aliases]

    if args.json:
        print(json.dumps({"tag": tag, "results": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            if result.get("dry_run"):
                print(f"[dry-run] {result['alias']}: {result['command']}")
            elif result["ok"]:
                print(f"✅ 退役しました: {result['alias']} → {result.get('url') or '(URL 未取得)'}")
            else:
                print(f"❌ 退役に失敗しました: {result['alias']}\n{result.get('error')}")
    return exit_code_for(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="完了スプリントのプレビュー環境を本番と同じ内容へ張り替えて退役させる"
    )
    parser.add_argument("--list", action="store_true", help="alias の一覧と退役対象を表示する")
    parser.add_argument("--alias", action="append", default=[], help="退役する alias 名（複数可）")
    parser.add_argument(
        "--closed-prs", action="store_true", help="クローズ済み PR 由来の alias を一括退役する"
    )
    parser.add_argument("--dry-run", action="store_true", help="実行せず対象とコマンドだけ表示する")
    parser.add_argument(
        "--allow-non-main", action="store_true", help="HEAD が origin/main でなくても実行する"
    )
    # owner/repo 解決は resolve_repo_slug() が SSOT（#215・check_deploy_gate.py と同じパターン）。
    # ハードコードすると下流の bootstrap 済みリポジトリで誤ったリポジトリを参照する。
    parser.add_argument(
        "--repo", default=resolve_repo_slug(), help="PR 状態を引く GitHub リポジトリ（既定: git remote から解決）"
    )
    parser.add_argument("--json", action="store_true", help="JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要の単体テスト")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    try:
        if args.list:
            return cmd_list(args)
        if args.closed_prs:
            account_id, token, worker = load_context()
            alias_map = latest_alias_map(fetch_versions(account_id, token, worker))
            numbers = [n for n in (alias_pr_number(a) for a in alias_map) if n is not None]
            targets = select_closed_pr_aliases(alias_map, fetch_pr_states(args.repo, numbers))
            targets = sorted(set(targets) | set(args.alias))
            return cmd_retire(args, targets)
        if args.alias:
            return cmd_retire(args, sorted(set(args.alias)))
    except Precondition as error:
        print(f"前提を満たしていません: {error}", file=sys.stderr)
        return EXIT_PRECONDITION

    parser.print_help()
    return EXIT_PRECONDITION


if __name__ == "__main__":
    sys.exit(main())
