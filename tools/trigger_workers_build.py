#!/usr/bin/env python3
"""trigger_workers_build.py — デプロイゲートが開いたときに Workers Builds を再トリガーする CLI

【背景（Issue #451）】
gem-hunter は Cloudflare Workers Builds で `main` への push ごとに自動ビルド・デプロイする
構成（`D-31`）。Deploy command（`tools/workers_build_deploy.sh`）は `tools/check_deploy_gate.py`
を実行し、exit 0 のときだけ `npm run deploy` へ進む fail-closed 設計（`D-32`）。

実測で判明したこと:
  - Workers Builds は push のたびに正常に発火していた（直近 24 件すべて）。
  - しかし全件 `build_outcome: "fail"` で、デプロイゲートが閉じていたため止まっていた。
  - **ゲートが後で開いても、その push を再ビルドする経路が存在しない**ため、
    SP-17 / SP-18 / SP-19 の 3 スプリント分が本番未反映のまま滞留した。

本 CLI は「ゲートが開いたときに main の最新コミットで Workers Builds を再トリガーする」経路を
提供する（waiting-user-handler / sprint-cycle-router 等から定期的に呼び出す想定）。

【判定ロジック】
  1. `--skip-gate-check` が無ければ `tools/check_deploy_gate.py` を subprocess で実行する。
     終了コード 0（デプロイ可）以外は **トリガー段へ進まない**（`--dry-run` を除く。後述）。
  2. Cloudflare API で Worker 名（`wrangler.jsonc` の `name`）→ Worker tag（UUID）→
     対象ブランチの `branch_includes` に一致する本番 trigger（UUID）の順に解決する。
  3. `POST /accounts/{account_id}/builds/triggers/{trigger_uuid}/builds` で再ビルドをトリガーする。

【`--dry-run` の挙動（設計判断）】
  `--dry-run` は API への POST だけを止める安全な確認モードなので、ゲートが閉じていても
  Worker tag / trigger の GET 解決までは実行し、「送信していたら何が飛ぶか」を提示する
  （ゲートが閉じている間も trigger 解決の疎通確認ができるようにするため）。
  ただし終了コードは実行時と同じ意味を保つ（ゲートが閉じていれば dry-run でも exit 1/2 を返す。
  「dry-run は常に exit 0」にはしない — fail-closed の意味を dry-run でも壊さないため）。
  この判定（「API 呼び出し段へ進むべきか」）は `should_call_api()` に一元化する
  （Layer 1 セルフレビュー CRITICAL-1・PR #460。以前は `main()` 内の条件式が純関数化されておらず、
  条件を反転する変異を入れても `--self-test` が全 PASS のまま通っていた）。

【終了コード（fail-closed。呼び出し側の唯一の分岐点は `exit_code_for()`）】
  0 = ビルドをトリガーした（`--dry-run` 時は「トリガーしていたはずの」状態。build_uuid を出力）
  1 = トリガーしなかった（デプロイゲートが閉じている＝待機中。異常ではない）
  2 = 判定不能・API エラー（fail-closed。トークン未設定・trigger 取得失敗・POST 失敗等）

【秘匿情報】
`CLOUDFLARE_API_TOKEN` の値は stdout/stderr に一切出力しない。外部 API のエラーメッセージは
念のため `mask_secrets.mask_text()` を通してから出力する（万一トークンがエコーバックされても隠す）。

使い方:
    python3 tools/trigger_workers_build.py
    python3 tools/trigger_workers_build.py --branch main --commit-hash <sha>
    python3 tools/trigger_workers_build.py --skip-gate-check
    python3 tools/trigger_workers_build.py --dry-run --json
    python3 tools/trigger_workers_build.py --self-test    # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_secrets import mask_text  # noqa: E402
from wrangler_config import parse_worker_name  # noqa: E402

JST = timezone(timedelta(hours=9))

REPO_ROOT = Path(__file__).resolve().parent.parent
WRANGLER_PATH = REPO_ROOT / "wrangler.jsonc"
GATE_SCRIPT = REPO_ROOT / "tools" / "check_deploy_gate.py"

CF_API_BASE = "https://api.cloudflare.com/client/v4"

# 終了コードの唯一の写像先（0=proceed / 1=waiting / 2=error）。
_EXIT_CODES = {"proceed": 0, "waiting": 1, "error": 2}


class ApiError(Exception):
    """外部 API 呼び出しの失敗（fail-closed で exit 2 に写像する）。"""


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械処理には使わない（datetime-rules.md）。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def exit_code_for(outcome: str) -> int:
    """判定結果を終了コードへ写像する唯一の関数（0/1/2 のマッピングを一元化する）。

    outcome は "proceed"（デプロイ可 / トリガー成功）/ "waiting"（ゲート待機）/
    "error"（判定不能・API エラー・fail-closed）のいずれか。
    """
    if outcome not in _EXIT_CODES:
        raise ValueError(f"unknown outcome: {outcome!r}")
    return _EXIT_CODES[outcome]


def gate_outcome_from_returncode(code: int) -> str:
    """`check_deploy_gate.py` の終了コードを行動へ写像する（純関数・exit_code_for と語彙を共有）。

    0 → "proceed"（デプロイ可）/ 1 → "waiting"（待機）/ それ以外（2・起動失敗の -1 等）→ "error"
    （fail-closed。想定外の終了コードを「デプロイ可」の既定値にしない）。
    """
    if code == 0:
        return "proceed"
    if code == 1:
        return "waiting"
    return "error"


def should_call_api(gate_outcome: str, dry_run: bool) -> bool:
    """ゲート判定と `--dry-run` から「API 呼び出し段（trigger 解決）へ進むべきか」を判定する。

    `main()` 内の条件式を純関数化したもの（Layer 1 セルフレビュー CRITICAL-1・PR #460）。
    非 dry-run はゲートが "proceed" のときだけ進む（fail-closed）。dry-run はゲート状態に
    関わらず常に進む（POST だけを止める。モジュール docstring の「--dry-run の挙動」参照）。

    期待値テーブル（self-test で固定）:
        ("proceed", False) -> True   / ("waiting", False) -> False
        ("error",   False) -> False  / ("waiting", True)  -> True
        ("proceed", True)  -> True
    """
    if dry_run:
        return True
    return gate_outcome == "proceed"


# ──────────────────────────────────────────────
# 判定ロジック（純関数・API 非依存 = --self-test の対象）
# ──────────────────────────────────────────────


def worker_tag_from_scripts(scripts: list[dict[str, Any]], worker_name: str) -> str | None:
    """`GET .../workers/scripts` の結果一覧から Worker 名に一致する tag（UUID）を返す。

    レスポンス項目は `{"id": <worker名>, "tag": <UUID>, ...}`。Builds API は Worker 名ではなく
    この tag を要求する。
    """
    for item in scripts:
        if item.get("id") == worker_name:
            tag = item.get("tag")
            return str(tag) if tag else None
    return None


def _branch_matches(branch: str, patterns: list[str]) -> bool:
    """branch が patterns のいずれかに一致するか（glob。`main` のような完全一致も glob として扱える）。"""
    return any(fnmatch.fnmatch(branch, p) for p in patterns)


def select_production_trigger(triggers: list[dict[str, Any]], branch: str) -> dict[str, Any] | None:
    """`branch_includes` に branch を含み、`branch_excludes` には含まれない trigger を選ぶ。

    本番用 trigger と preview 用 trigger が併存しうるため、branch 一致で本番用を絞り込む。
    **複数該当した場合は fail-closed で `ApiError` を送出して停止する**（Layer 1 セルフレビュー
    WARNING-5・PR #460。以前は `trigger_uuid` 昇順で先頭を選んでいたが、この並び順に
    「本番かどうか」の意味は無く、誤って preview 用 trigger を選ぶと preview の
    `deploy_command` でビルドが走り本番が更新されないまま `exit 0` を返してしまう）。
    """
    candidates = [
        t
        for t in triggers
        if _branch_matches(branch, t.get("branch_includes") or [])
        and not _branch_matches(branch, t.get("branch_excludes") or [])
    ]
    if not candidates:
        return None
    if len(candidates) > 1:
        raise ApiError(
            mask_text(
                f"branch='{branch}' に複数の trigger が一致しました"
                f"（{[t.get('trigger_uuid') for t in candidates]}）。"
                "production / preview を判別できないため停止します。"
            )
        )
    return candidates[0]


def build_trigger_payload(branch: str, commit_hash: str | None) -> dict[str, str]:
    """POST ボディを組み立てる。`commit_hash` 省略時は branch だけを渡す（API 仕様どおり）。"""
    payload = {"branch": branch}
    if commit_hash:
        payload["commit_hash"] = commit_hash
    return payload


def extract_build_uuid(response: dict[str, Any]) -> str | None:
    """トリガー POST のレスポンスから `build_uuid` を取り出す（無ければ None）。"""
    result = response.get("result")
    if not isinstance(result, dict):
        return None
    build_uuid = result.get("build_uuid") or result.get("id")
    return str(build_uuid) if build_uuid else None


def should_fetch_next_worker_scripts_page(
    result_info: dict[str, Any], fetched_count: int, page_item_count: int
) -> bool:
    """`GET workers/scripts` のページング継続判定（純関数・Layer 1 セルフレビュー WARNING-4）。

    `tools/retire_preview_aliases.py` の `should_fetch_next_page()` と同じ判定ロジック
    （Cloudflare API の `result_info`（page/per_page/count/total_count）形式は共通）。
    Worker が 21 件以上（既定 `per_page=20`）あって対象が 2 ページ目以降にあると、
    1 ページ目しか見ない実装では再トリガー経路が恒常的に exit 2 で死ぬ問題の修正。
    """
    if page_item_count == 0:
        return False
    total_count = result_info.get("total_count")
    if total_count is None:
        # total_count が取れない応答は継続条件を判定できないため、無限ループを避けて打ち切る。
        return False
    return fetched_count < total_count


# ──────────────────────────────────────────────
# 外部 I/O（gh/Cloudflare API・subprocess）
# ──────────────────────────────────────────────


def run_gate_check(repo_root: Path) -> int:
    """`check_deploy_gate.py` を subprocess で実行し、終了コードをそのまま返す。

    起動自体に失敗した場合（ファイル不在・タイムアウト等）は -1 を返す
    （`gate_outcome_from_returncode()` が 0/1 以外を "error" として fail-closed に倒す）。
    """
    try:
        result = subprocess.run(
            [sys.executable, str(repo_root / "tools" / "check_deploy_gate.py")],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1
    return result.returncode


def _http_json(
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """`opener` は既定で `urllib.request.urlopen`。self-test では差し替えて、ネットワーク非依存に
    異常系（2xx + 不正 JSON・`HTTPError` + 非 JSON ボディ）を再現する
    （Layer 1 セルフレビュー WARNING-3・PR #460）。
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            # Cloudflare API は 4xx でも success:false の JSON ボディを返すことが多い
            # （呼び出し側で success を見て ApiError に変換する）。
            return parsed
        raise ApiError(mask_text(f"HTTP {error.code}: {body[:300]}")) from error
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise ApiError(mask_text(f"{type(error).__name__}: {error}")) from error


def fetch_worker_scripts(account_id: str, token: str) -> list[dict[str, Any]]:
    """`GET .../workers/scripts` の全ページを回収する（WARNING-4・21 件以上あるアカウント対応）。"""
    per_page = 50
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        url = f"{CF_API_BASE}/accounts/{account_id}/workers/scripts?per_page={per_page}&page={page}"
        payload = _http_json(url, {"Authorization": f"Bearer {token}"})
        if not payload.get("success"):
            raise ApiError(mask_text(f"workers/scripts の取得に失敗しました: {payload.get('errors')}"))
        page_items = payload.get("result") or []
        items.extend(page_items)
        if not should_fetch_next_worker_scripts_page(
            payload.get("result_info") or {}, len(items), len(page_items)
        ):
            break
        page += 1
    return items


def fetch_build_triggers(account_id: str, token: str, worker_tag: str) -> list[dict[str, Any]]:
    url = f"{CF_API_BASE}/accounts/{account_id}/builds/workers/{worker_tag}/triggers"
    payload = _http_json(url, {"Authorization": f"Bearer {token}"})
    if not payload.get("success"):
        raise ApiError(mask_text(f"triggers の取得に失敗しました: {payload.get('errors')}"))
    return payload.get("result") or []


def post_trigger_build(
    account_id: str, token: str, trigger_uuid: str, body: dict[str, str]
) -> dict[str, Any]:
    url = f"{CF_API_BASE}/accounts/{account_id}/builds/triggers/{trigger_uuid}/builds"
    payload = _http_json(
        url,
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
        payload=body,
    )
    if not payload.get("success"):
        raise ApiError(mask_text(f"ビルドのトリガーに失敗しました: {payload.get('errors')}"))
    return payload


def _read_worker_name(wrangler_path: Path) -> str:
    """wrangler.jsonc から Worker 名を読み取る（`wrangler_config` の `ValueError` を `ApiError` へ
    wrap する。パース本体のテストは `wrangler_config.py` の self-test 側の責務・WARNING-6）。"""
    if not wrangler_path.exists():
        raise ApiError(f"{wrangler_path} が見つかりません")
    try:
        return parse_worker_name(wrangler_path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ApiError(str(error)) from error


def resolve_trigger(
    branch: str,
    account_id: str,
    token: str,
    wrangler_path: Path,
    *,
    fetch_scripts: Callable[[str, str], list[dict[str, Any]]] = fetch_worker_scripts,
    fetch_triggers: Callable[[str, str, str], list[dict[str, Any]]] = fetch_build_triggers,
) -> dict[str, Any]:
    """Worker 名 → tag → 対象ブランチの trigger まで解決する（合成関数）。

    `branch` を明示的な実引数として受け取り、HTTP フェッチを差し替え可能にすることで、
    `main()` の `--branch` 渡しがトリガー選択まで実際に伝搬しているかを self-test で
    ネットワーク非依存に検証できるようにしている（Layer 1 セルフレビュー CRITICAL-2・PR #460。
    以前は `select_production_trigger(triggers, args.branch)` の呼び出しが `main()` にしかなく、
    この行を固定ブランチへハードコードする変異を入れても `--self-test` は全 PASS のまま通っていた）。
    """
    worker_name = _read_worker_name(wrangler_path)
    scripts = fetch_scripts(account_id, token)
    worker_tag = worker_tag_from_scripts(scripts, worker_name)
    if worker_tag is None:
        raise ApiError(f"Worker '{worker_name}' が workers/scripts 一覧に見つかりません")
    triggers = fetch_triggers(account_id, token, worker_tag)
    trigger = select_production_trigger(triggers, branch)
    if trigger is None:
        raise ApiError(f"branch_includes に '{branch}' を含む trigger が見つかりません")
    return {"worker_name": worker_name, "worker_tag": worker_tag, "trigger": trigger}


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_read_worker_name_wraps_error() -> list[str]:
    """`wrangler_config.parse_worker_name` の `ValueError` を `ApiError` へ wrap できているかだけを
    確認する（コメント除去等のパース本体のテストは `wrangler_config.py` の self-test の責務・
    WARNING-6・重複を残さない）。
    """
    failures = []

    with tempfile.NamedTemporaryFile("w", suffix=".jsonc", delete=False) as handle:
        handle.write('{"main": "src/index.ts"}')  # name が無い
        tmp_path = Path(handle.name)
    try:
        _read_worker_name(tmp_path)
        failures.append("_read_worker_name: name が無いのに ApiError を送出していない")
    except ApiError:
        pass
    finally:
        tmp_path.unlink(missing_ok=True)

    try:
        _read_worker_name(Path("/nonexistent-dir/wrangler.jsonc"))
        failures.append("_read_worker_name: ファイル不在なのに ApiError を送出していない")
    except ApiError:
        pass

    return failures


def _self_test_worker_tag_from_scripts() -> list[str]:
    failures = []
    scripts = [
        {"id": "other-worker", "tag": "tag-a"},
        {"id": "gem-hunter", "tag": "tag-b"},
    ]
    if worker_tag_from_scripts(scripts, "gem-hunter") != "tag-b":
        failures.append("worker_tag_from_scripts: 一致する id の tag を取れていない")
    if worker_tag_from_scripts(scripts, "not-found") is not None:
        failures.append("worker_tag_from_scripts: 一致しない name で None 以外を返した")
    if worker_tag_from_scripts([{"id": "gem-hunter", "tag": ""}], "gem-hunter") is not None:
        failures.append("worker_tag_from_scripts: tag が空文字なのに None 以外を返した")
    return failures


def _self_test_select_production_trigger() -> list[str]:
    failures = []
    prod = {"trigger_uuid": "uuid-prod", "trigger_name": "prod", "branch_includes": ["main"]}
    preview = {
        "trigger_uuid": "uuid-preview",
        "trigger_name": "preview",
        "branch_includes": ["pr-*"],
    }
    triggers = [preview, prod]

    got = select_production_trigger(triggers, "main")
    if got is None or got["trigger_uuid"] != "uuid-prod":
        failures.append(f"select_production_trigger: main で本番 trigger を選べていない: {got}")

    got = select_production_trigger(triggers, "pr-123")
    if got is None or got["trigger_uuid"] != "uuid-preview":
        failures.append(f"select_production_trigger: pr-* パターンに一致していない: {got}")

    got = select_production_trigger(triggers, "feature/x")
    if got is not None:
        failures.append(f"select_production_trigger: 一致しないブランチで None 以外を返した: {got}")

    # branch_excludes に一致する trigger は除外する
    excluded = {
        "trigger_uuid": "uuid-excluded",
        "branch_includes": ["*"],
        "branch_excludes": ["main"],
    }
    got = select_production_trigger([excluded, prod], "main")
    if got is None or got["trigger_uuid"] != "uuid-prod":
        failures.append(f"select_production_trigger: branch_excludes を無視して誤選択した: {got}")

    # 複数該当時は fail-closed で ApiError を送出する（WARNING-5・並び順で誤って preview を選ばない）
    dup_a = {"trigger_uuid": "uuid-b", "branch_includes": ["main"]}
    dup_b = {"trigger_uuid": "uuid-a", "branch_includes": ["main"]}
    try:
        select_production_trigger([dup_a, dup_b], "main")
        failures.append("select_production_trigger: 複数該当時に ApiError を送出していない")
    except ApiError:
        pass

    return failures


def _self_test_build_trigger_payload() -> list[str]:
    failures = []
    if build_trigger_payload("main", None) != {"branch": "main"}:
        failures.append("build_trigger_payload: commit_hash 省略時に branch のみを返していない")
    if build_trigger_payload("main", "") != {"branch": "main"}:
        failures.append("build_trigger_payload: commit_hash が空文字なのに含めている")
    want = {"branch": "main", "commit_hash": "abc123"}
    if build_trigger_payload("main", "abc123") != want:
        failures.append("build_trigger_payload: commit_hash 指定時のペイロードが不一致")
    return failures


def _self_test_extract_build_uuid() -> list[str]:
    failures = []
    if extract_build_uuid({"result": {"build_uuid": "u-1"}}) != "u-1":
        failures.append("extract_build_uuid: build_uuid を取れていない")
    if extract_build_uuid({"result": {"id": "u-2"}}) != "u-2":
        failures.append("extract_build_uuid: build_uuid が無いときに id へフォールバックしていない")
    if extract_build_uuid({"result": {}}) is not None:
        failures.append("extract_build_uuid: 空の result で None 以外を返した")
    if extract_build_uuid({"result": None}) is not None:
        failures.append("extract_build_uuid: result が None のとき None 以外を返した")
    if extract_build_uuid({}) is not None:
        failures.append("extract_build_uuid: result キー自体が無いとき None 以外を返した")
    return failures


def _self_test_gate_outcome_and_exit_code() -> list[str]:
    failures = []
    cases = [(0, "proceed"), (1, "waiting"), (2, "error"), (-1, "error"), (127, "error")]
    for code, want in cases:
        got = gate_outcome_from_returncode(code)
        if got != want:
            failures.append(f"gate_outcome_from_returncode({code}): {got!r}（期待 {want!r}）")

    for outcome, want_code in _EXIT_CODES.items():
        if exit_code_for(outcome) != want_code:
            failures.append(f"exit_code_for({outcome!r}): {want_code} を期待")

    try:
        exit_code_for("unknown-outcome")
        failures.append("exit_code_for: 未知の outcome で例外を送出していない")
    except ValueError:
        pass

    return failures


def _self_test_should_call_api() -> list[str]:
    """CRITICAL-1: fail-closed のゲート判定（`main()` の分岐そのもの）を純関数として固定する。"""
    failures = []
    cases = [
        (("proceed", False), True),
        (("waiting", False), False),
        (("error", False), False),
        (("waiting", True), True),
        (("proceed", True), True),
    ]
    for (gate_outcome, dry_run), want in cases:
        got = should_call_api(gate_outcome, dry_run)
        if got != want:
            failures.append(
                f"should_call_api({gate_outcome!r}, dry_run={dry_run}): {got!r}（期待 {want!r}）"
            )
    return failures


def _self_test_resolve_trigger_branch_wiring() -> list[str]:
    """CRITICAL-2: `--branch` が trigger 選択まで実際に伝搬しているかを、HTTP フェッチを
    フェイクへ差し替えて（ネットワーク非依存に）検証する。"""
    failures: list[str] = []
    prod = {"trigger_uuid": "uuid-prod", "trigger_name": "prod", "branch_includes": ["main"]}
    preview = {
        "trigger_uuid": "uuid-preview",
        "trigger_name": "preview",
        "branch_includes": ["pr-*"],
    }

    def fake_scripts(account_id: str, token: str) -> list[dict[str, Any]]:  # noqa: ARG001
        return [{"id": "gem-hunter", "tag": "worker-tag-x"}]

    def fake_triggers(account_id: str, token: str, worker_tag: str) -> list[dict[str, Any]]:  # noqa: ARG001
        return [preview, prod]

    with tempfile.NamedTemporaryFile("w", suffix=".jsonc", delete=False) as handle:
        handle.write('{"name": "gem-hunter"}')
        tmp_path = Path(handle.name)
    try:
        got = resolve_trigger(
            "pr-123", "acc", "tok", tmp_path, fetch_scripts=fake_scripts, fetch_triggers=fake_triggers
        )
        if got["trigger"]["trigger_uuid"] != "uuid-preview":
            failures.append(
                "resolve_trigger: branch='pr-123' で preview trigger を選べていない"
                f"（--branch の伝搬が壊れている可能性）: {got}"
            )

        got = resolve_trigger(
            "main", "acc", "tok", tmp_path, fetch_scripts=fake_scripts, fetch_triggers=fake_triggers
        )
        if got["trigger"]["trigger_uuid"] != "uuid-prod":
            failures.append(f"resolve_trigger: branch='main' で本番 trigger を選べていない: {got}")

        got = resolve_trigger(
            "feature/x", "acc", "tok", tmp_path, fetch_scripts=fake_scripts, fetch_triggers=fake_triggers
        )
        failures.append(f"resolve_trigger: 一致しないブランチで例外を送出していない: {got}")
    except ApiError:
        pass
    finally:
        tmp_path.unlink(missing_ok=True)

    return failures


class _FakeHttpResponse:
    """`urllib.request.urlopen` の戻り値（context manager + `.read()`）を模倣する（self-test 専用）。"""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _self_test_http_json_error_handling() -> list[str]:
    """WARNING-3: `_http_json` の異常系 2 ケースがいずれも（マスク済みの）`ApiError` になることを
    ネットワーク非依存に確認する。"""
    failures: list[str] = []

    def opener_2xx_bad_json(request: Any, timeout: int = 30) -> _FakeHttpResponse:  # noqa: ARG001
        return _FakeHttpResponse(b"not-json")

    try:
        _http_json("https://example.test/a", {}, opener=opener_2xx_bad_json)
        failures.append("_http_json: 2xx + 不正 JSON なのに ApiError を送出していない")
    except ApiError:
        pass
    except Exception as error:  # noqa: BLE001
        failures.append(
            f"_http_json: 2xx + 不正 JSON で ApiError 以外が飛んだ: {type(error).__name__}: {error}"
        )

    def opener_http_error(request: Any, timeout: int = 30) -> Any:  # noqa: ARG001
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "Internal Server Error",
            None,
            io.BytesIO(b"Authorization: Bearer sk-abcdefghijklmnop1234567890 invalid"),
        )

    try:
        _http_json("https://example.test/b", {}, opener=opener_http_error)
        failures.append("_http_json: HTTPError + 非 JSON ボディなのに ApiError を送出していない")
    except ApiError as error:
        if "sk-abcdefghijklmnop1234567890" in str(error):
            failures.append("_http_json: HTTPError のメッセージにトークンがマスクされず残っている")
    except Exception as error:  # noqa: BLE001
        failures.append(
            "_http_json: HTTPError + 非 JSON ボディで ApiError 以外が飛んだ: "
            f"{type(error).__name__}: {error}"
        )

    return failures


def _self_test_should_fetch_next_worker_scripts_page() -> list[str]:
    """WARNING-4: `workers/scripts` のページング継続判定を固定する。"""
    failures = []
    cases = [
        (
            "1 ページで全件取得できたら継続しない",
            {"page": 1, "per_page": 50, "count": 20, "total_count": 20},
            20,
            20,
            False,
        ),
        (
            "total_count が per_page を超えるなら継続する（21 件以上の見落とし防止）",
            {"page": 1, "per_page": 50, "count": 50, "total_count": 120},
            50,
            50,
            True,
        ),
        (
            "累積が total_count に達したら継続しない（最終ページ）",
            {"page": 3, "per_page": 50, "count": 20, "total_count": 120},
            120,
            20,
            False,
        ),
        (
            "このページが 0 件なら継続しない（無限ループ防止）",
            {"page": 5, "per_page": 50, "total_count": 120},
            100,
            0,
            False,
        ),
        (
            "total_count が取れない応答は継続しない（fail-safe・無限ループ防止）",
            {"page": 1, "per_page": 50, "count": 10},
            10,
            10,
            False,
        ),
    ]
    for label, result_info, fetched_count, page_item_count, expected in cases:
        got = should_fetch_next_worker_scripts_page(result_info, fetched_count, page_item_count)
        if got != expected:
            failures.append(f"{label}: 期待 {expected} / 実際 {got}")
    return failures


def run_self_test() -> int:
    groups = [
        ("Worker 名読み取りの例外 wrap", _self_test_read_worker_name_wraps_error),
        ("Worker tag の解決", _self_test_worker_tag_from_scripts),
        ("本番 trigger の選択（複数該当は fail-closed）", _self_test_select_production_trigger),
        ("トリガー POST ペイロード組み立て", _self_test_build_trigger_payload),
        ("build_uuid の抽出", _self_test_extract_build_uuid),
        ("ゲート終了コード ↔ 行動 ↔ 最終終了コードの写像", _self_test_gate_outcome_and_exit_code),
        ("fail-closed 判定（should_call_api）", _self_test_should_call_api),
        ("trigger 解決の branch 伝搬（resolve_trigger）", _self_test_resolve_trigger_branch_wiring),
        ("_http_json の異常系（不正 JSON / HTTPError）", _self_test_http_json_error_handling),
        ("workers/scripts ページング判定", _self_test_should_fetch_next_worker_scripts_page),
    ]
    failed_groups = 0
    total_failures = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed_groups += 1
            total_failures += len(failures)
            for f in failures:
                print(f"FAIL[{name}]: {f}")

    if total_failures:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed_groups} グループ失敗 "
              f"({total_failures} 件の不一致)")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


# ──────────────────────────────────────────────
# 出力ヘルパー
# ──────────────────────────────────────────────


def _emit_error(message: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"error": message, "checked_at": now_jst_str()}, ensure_ascii=False))
    else:
        print(f"ERROR: {message}", file=sys.stderr)


def _emit_gate_blocked(gate_outcome: str, gate_returncode: int | None, as_json: bool) -> None:
    if gate_outcome == "waiting":
        message = "デプロイゲートが待機中です（Sprint Review 判定待ち等）。トリガーしません。"
    else:
        message = "デプロイゲートの判定が不能です（fail-closed）。トリガーしません。"
    if as_json:
        print(json.dumps(
            {
                "triggered": False,
                "gate_outcome": gate_outcome,
                "gate_returncode": gate_returncode,
                "message": message,
                "checked_at": now_jst_str(),
            },
            ensure_ascii=False,
        ))
    else:
        print(message)
        if gate_returncode is not None:
            print(f"（check_deploy_gate.py 終了コード: {gate_returncode}）")


def _emit_dry_run(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"[dry-run] ゲート状態: {result['gate_outcome']}（終了コード: {result['gate_returncode']}）")
    print(f"[dry-run] Worker: {result['worker_name']} (tag={result['worker_tag']})")
    print(f"[dry-run] trigger: {result.get('trigger_name')} ({result['trigger_uuid']})")
    print(f"[dry-run] POST {result['url']}")
    print(f"[dry-run] body: {json.dumps(result['payload'], ensure_ascii=False)}")


def _emit_success(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"ビルドをトリガーしました: build_uuid={result['build_uuid']}")
        print(f"（worker_tag={result['worker_tag']} / trigger_uuid={result['trigger_uuid']} "
              f"/ branch={result['branch']}）")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="デプロイゲートが開いたときに Workers Builds を再トリガーする"
                     "（0=トリガーした / 1=ゲート待機 / 2=判定不能・エラー）。",
    )
    parser.add_argument("--branch", default="main", help="ビルド対象ブランチ（既定: main）")
    parser.add_argument("--commit-hash", default=None, help="対象コミット（既定: 省略）")
    parser.add_argument(
        "--skip-gate-check", action="store_true", help="事前のデプロイゲート確認をスキップする"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="API へ POST せず、送信予定のエンドポイントとペイロードだけ出力する",
    )
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    gate_outcome = "proceed"
    gate_returncode: int | None = None
    if not args.skip_gate_check:
        gate_returncode = run_gate_check(REPO_ROOT)
        gate_outcome = gate_outcome_from_returncode(gate_returncode)

    # 非 dry-run はゲートが閉じている／判定不能なら即座に終了する（fail-closed。トリガー段へ進まない）。
    # dry-run はゲートの状態に関わらず trigger 解決まで進めて疎通確認できるようにする
    # （POST だけを止める。終了コードはゲート状態を正直に反映する。モジュール docstring 参照）。
    if not should_call_api(gate_outcome, args.dry_run):
        _emit_gate_blocked(gate_outcome, gate_returncode, args.json)
        sys.exit(exit_code_for(gate_outcome))

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not token:
        _emit_error(
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN がセッション環境にありません",
            args.json,
        )
        sys.exit(exit_code_for("error"))

    try:
        resolved = resolve_trigger(args.branch, account_id, token, WRANGLER_PATH)
    except (ApiError, OSError, ValueError) as error:
        _emit_error(str(error), args.json)
        sys.exit(exit_code_for("error"))

    worker_name = resolved["worker_name"]
    worker_tag = resolved["worker_tag"]
    trigger = resolved["trigger"]
    trigger_uuid = str(trigger["trigger_uuid"])
    payload = build_trigger_payload(args.branch, args.commit_hash)
    post_url = f"{CF_API_BASE}/accounts/{account_id}/builds/triggers/{trigger_uuid}/builds"

    if args.dry_run:
        result = {
            "dry_run": True,
            "gate_outcome": gate_outcome,
            "gate_returncode": gate_returncode,
            "worker_name": worker_name,
            "worker_tag": worker_tag,
            "trigger_uuid": trigger_uuid,
            "trigger_name": trigger.get("trigger_name"),
            "url": post_url,
            "payload": payload,
            "checked_at": now_jst_str(),
        }
        _emit_dry_run(result, args.json)
        sys.exit(exit_code_for(gate_outcome))

    try:
        response = post_trigger_build(account_id, token, trigger_uuid, payload)
    except ApiError as error:
        _emit_error(str(error), args.json)
        sys.exit(exit_code_for("error"))

    result = {
        "triggered": True,
        "build_uuid": extract_build_uuid(response),
        "worker_name": worker_name,
        "worker_tag": worker_tag,
        "trigger_uuid": trigger_uuid,
        "branch": args.branch,
        "commit_hash": args.commit_hash,
        "checked_at": now_jst_str(),
    }
    _emit_success(result, args.json)
    sys.exit(exit_code_for("proceed"))


if __name__ == "__main__":
    main()
