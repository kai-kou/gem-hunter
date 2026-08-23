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
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_secrets import mask_text  # noqa: E402

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


# ──────────────────────────────────────────────
# 判定ロジック（純関数・API 非依存 = --self-test の対象）
# ──────────────────────────────────────────────


def parse_worker_name(jsonc_text: str) -> str:
    """wrangler.jsonc から Worker 名を取り出す（行コメントを除去してから JSON として読む）。

    `tools/retire_preview_aliases.py` の同名関数と同じロジック（意図的に重複させ、
    このファイルの self-test だけでネットワーク非依存に検証できるようにしている）。
    """
    without_comments = re.sub(r"^\s*//.*$", "", jsonc_text, flags=re.MULTILINE)
    data = json.loads(without_comments)
    name = data.get("name")
    if not name:
        raise ApiError("wrangler.jsonc に name がありません")
    return str(name)


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
    複数該当した場合は `trigger_uuid` 昇順で先頭を決定的に選ぶ（曖昧さを残さない）。
    """
    candidates = []
    for t in triggers:
        includes = t.get("branch_includes") or []
        excludes = t.get("branch_excludes") or []
        if _branch_matches(branch, includes) and not _branch_matches(branch, excludes):
            candidates.append(t)
    if not candidates:
        return None
    candidates.sort(key=lambda t: str(t.get("trigger_uuid") or ""))
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
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
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
    url = f"{CF_API_BASE}/accounts/{account_id}/workers/scripts"
    payload = _http_json(url, {"Authorization": f"Bearer {token}"})
    if not payload.get("success"):
        raise ApiError(mask_text(f"workers/scripts の取得に失敗しました: {payload.get('errors')}"))
    return payload.get("result") or []


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
    if not wrangler_path.exists():
        raise ApiError(f"{wrangler_path} が見つかりません")
    return parse_worker_name(wrangler_path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_parse_worker_name() -> list[str]:
    failures = []
    text = '{\n  // コメント\n  "name": "gem-hunter",\n  "main": "src/index.ts"\n}\n'
    if parse_worker_name(text) != "gem-hunter":
        failures.append("parse_worker_name: 行コメントを除去して name を取れていない")
    try:
        parse_worker_name('{"main": "src/index.ts"}')
        failures.append("parse_worker_name: name が無いのに例外を送出していない")
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

    # 複数該当時は trigger_uuid 昇順で決定的に選ぶ
    dup_a = {"trigger_uuid": "uuid-b", "branch_includes": ["main"]}
    dup_b = {"trigger_uuid": "uuid-a", "branch_includes": ["main"]}
    got = select_production_trigger([dup_a, dup_b], "main")
    if got is None or got["trigger_uuid"] != "uuid-a":
        failures.append(f"select_production_trigger: 複数該当時の決定的選択が崩れている: {got}")

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


def run_self_test() -> int:
    groups = [
        ("wrangler.jsonc の Worker 名パース", _self_test_parse_worker_name),
        ("Worker tag の解決", _self_test_worker_tag_from_scripts),
        ("本番 trigger の選択", _self_test_select_production_trigger),
        ("トリガー POST ペイロード組み立て", _self_test_build_trigger_payload),
        ("build_uuid の抽出", _self_test_extract_build_uuid),
        ("ゲート終了コード ↔ 行動 ↔ 最終終了コードの写像", _self_test_gate_outcome_and_exit_code),
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
    if gate_outcome != "proceed" and not args.dry_run:
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
        worker_name = _read_worker_name(WRANGLER_PATH)
        scripts = fetch_worker_scripts(account_id, token)
        worker_tag = worker_tag_from_scripts(scripts, worker_name)
        if worker_tag is None:
            raise ApiError(f"Worker '{worker_name}' が workers/scripts 一覧に見つかりません")
        triggers = fetch_build_triggers(account_id, token, worker_tag)
        trigger = select_production_trigger(triggers, args.branch)
        if trigger is None:
            raise ApiError(f"branch_includes に '{args.branch}' を含む trigger が見つかりません")
    except (ApiError, OSError, ValueError) as error:
        _emit_error(str(error), args.json)
        sys.exit(exit_code_for("error"))

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
