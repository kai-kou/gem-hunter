#!/usr/bin/env python3
"""check_prod_drift.py — `main` の HEAD と本番 Worker の乖離を機械検知する（読み取り専用・fail-closed）

【背景】Issue #288 完了条件 3。本番デプロイ（`npm run deploy`）が Claude Code の auto mode
classifier にブロックされ、`main` にマージしても本番へ反映されない事態が発生した
（実測: main=64d2aa3 に対し本番は旧版のまま）。「反映されていないこと」に気づいたセッションしか
気づけない状態を解消するため、機械的に検知する手段として本スクリプトを追加する。

【本番側の版の取得手段（実測して選定）】
`npx wrangler deployments list --json` を実行し、`annotations["workers/triggered_by"]
== "deployment"`（= `wrangler deploy` で 100% 昇格された実デプロイ。`version_upload` は
preview alias へのアップロードに過ぎず本番には出ていないため区別する）の中から
`created_on` 最大のものを「現在本番で稼働中のバージョン」として採用する。実測（2026-08-20）:

    $ npx wrangler deployments list --json
    [... {"id": "...", "annotations": {"workers/triggered_by": "deployment"}, ...
          "versions": [{"version_id": "913f839b-...", "percentage": 100}],
          "created_on": "2026-08-20T19:30:23.803431Z"}, ...]

そのバージョンの詳細を `npx wrangler versions view <version_id> --json` で取得すると
`annotations` に `workers/tag`（`wrangler deploy --tag "$SHA"` 等で明示的に埋め込んだ場合のみ
出現。retire_preview_aliases.py が退役 alias に `retired-<sha12>` 形式で使っている前例あり）が
含まれる。実測時点では **本番デプロイ（`npm run deploy` = `wrangler deploy`、`--tag` 引数なし）は
tag/message とも空**（`wrangler versions view` の出力で `Tag: -` / `Message: -`）だったため、
判定は 2 段構えにする:

    1. exact モード: tag が付いていれば `main` HEAD の SHA と突き合わせる（完全一致 or
       短縮形どうしの前方一致・最短 7 桁）。✅ 2026-08-21 に `package.json` の `deploy` を
       `wrangler deploy --tag "$(git rev-parse --short=12 HEAD)"` へ変更済みのため、以降の
       本番デプロイは exact モードで判定される（本スクリプト側の変更は不要だった）。
    2. heuristic モード: tag が無い場合のフォールバック。「本番の最終デプロイ日時」と
       「`main` HEAD のコミット日時」を比較し、**HEAD のコミット日時が最終デプロイより後であれば
       乖離とみなす**（その内容を含みようがないため必要条件として健全）。デプロイが HEAD 以降なら
       「乖離なし」と判定するが、これは SHA の完全一致を保証しない緩い判定なので `--json` の
       `confidence` フィールドで `"heuristic"` と明示する。

【終了コード（fail-closed・tools/check_deploy_gate.py の規約を踏襲）】
  0 = 乖離なし
  1 = 乖離あり（stdout/stderr に理由を出力）
  2 = 判定不能（wrangler 到達不可・JSON パース失敗・本番デプロイ実績が 0 件 等）。
      呼び出し側はこの場合「異常なし」として扱わない（フェイルオープン禁止）

【呼び出し元（本判定は自動配線済み・Issue #460）】
  🔴 **本判定（引数なし実行）の呼び出し元の正本は `.claude/skills/sprint-cycle-router/SKILL.md`
  §1.5 Step 0.2**（毎 firing の前置チェック）。判定結果ごとの後続手順（再トリガー・Issue 起票・
  fail-closed 記録）は同 SKILL.md 側にのみ書く。**本ヘッダに手順を複製しない**（Issue #477）。

  一方 **`tools/run_checks.sh` には本判定を配線しない**（ネットワーク非依存であるべき PR 作成前
  チェックに本番疎通依存の検査を混ぜると、本番側の一時的な事情で PR が赤くなるため）。
  ただし **`--self-test` はネットワーク非依存なので配線済み**（判定ロジック自体の退行を機械で守る）。

【禁止事項】本スクリプトは読み取り専用コマンドのみを実行する。`wrangler deploy` /
`wrangler versions deploy` / `wrangler rollback` 等の書き込み系コマンドは一切呼ばない。

日時の扱い: `docs/rules/datetime-rules.md` の SSOT に従い、表示・記録用の `checked_at` は JST。
デプロイ日時・コミット日時の内部比較は元の UTC のまま行う（機械比較用途のため）。

使い方:
    python3 tools/check_prod_drift.py
    python3 tools/check_prod_drift.py --json
    python3 tools/check_prod_drift.py --ref HEAD          # 比較対象の git ref（既定: origin/main）
    python3 tools/check_prod_drift.py --self-test         # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
from typing import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_secrets import mask_text  # noqa: E402
from workers_build_diagnostics import no_triggers_message  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))

WRANGLER_TAG_ANNOTATION = "workers/tag"
DEPLOYMENT_TRIGGER = "deployment"  # 100% 昇格された実デプロイのみを対象にする
MIN_SHA_PREFIX_LEN = 7  # git の短縮 SHA の最短妥当長（`git rev-parse --short` の既定に合わせる）

REASON_NO_TAG_HEAD_NEWER = (
    "本番の最終デプロイに SHA タグが無く、main HEAD のコミット日時が最終デプロイより新しいため、"
    "HEAD の変更が反映されていないと判定しました（heuristic）"
)
REASON_TAG_MISMATCH = "本番の最終デプロイの SHA タグが main HEAD と一致しません（exact）"
REASON_NO_DEPLOYMENT_FOUND = "本番への実デプロイ実績（triggered_by=deployment）が見つかりません"


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械比較には使わない（datetime-rules.md）。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def _parse_iso8601(ts: str) -> datetime:
    """`Z` 終端の ISO8601 を aware な datetime に変換する（Python 3.10 以下互換のため置換する）。"""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ──────────────────────────────────────────────
# subprocess ラッパー（読み取り専用コマンドのみ・書き込み系は一切呼ばない）
# ──────────────────────────────────────────────


def _run(cmd: list[str], timeout: int = 60) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        return False, f"コマンドがタイムアウトしました（{timeout}秒）: {' '.join(cmd)}"
    except OSError as e:
        # FileNotFoundError（npx 不在）も PermissionError も OSError のサブクラス。
        # ここで捕まえ損ねると呼び出し元まで例外が抜け、fail-closed の exit 2 を通らずに
        # Python 既定の exit 1（＝「乖離あり」と誤読される）で落ちる。
        return False, f"コマンドを実行できません（{type(e).__name__}: {e}）: {' '.join(cmd)}"
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        # 失敗理由は Issue / PR コメントへ転記されうるため、秘匿値を必ず落としてから返す。
        return False, mask_text(err) or f"コマンド実行失敗（exit {result.returncode}）: {' '.join(cmd)}"
    return True, result.stdout


def _extract_json(raw: str) -> object:
    """wrangler の stdout には先頭に警告バナー等の非 JSON 行が混じることがあるため、
    最初に現れる `[` または `{` から末尾までを JSON として解釈する。
    """
    start_candidates = [i for i in (raw.find("["), raw.find("{")) if i != -1]
    if not start_candidates:
        raise json.JSONDecodeError("JSON の開始位置が見つかりません", raw, 0)
    start = min(start_candidates)
    return json.loads(raw[start:])


# ──────────────────────────────────────────────
# 取得系（実 I/O。--self-test の対象外）
# ──────────────────────────────────────────────


def fetch_latest_production_deployment() -> tuple[dict | None, str | None]:
    """`wrangler deployments list --json` から、実際に本番へ昇格された（triggered_by=deployment）
    最新のデプロイを 1 件返す。Returns (deployment_or_none, error_reason)。
    """
    ok, out = _run(["npx", "wrangler", "deployments", "list", "--json"])
    if not ok:
        return None, f"wrangler deployments list 失敗（{out}）"
    try:
        data = _extract_json(out)
    except json.JSONDecodeError as e:
        return None, f"wrangler deployments list の JSON パースに失敗（{e}）"
    return select_latest_deployment(data)


def fetch_version_tag(version_id: str) -> tuple[str | None, str | None]:
    """`wrangler versions view <id> --json` からそのバージョンの SHA タグ（あれば）を返す。
    Returns (tag_or_none, error_reason)。タグ自体が存在しないのは正常系（error_reason=None）。
    """
    ok, out = _run(["npx", "wrangler", "versions", "view", version_id, "--json"])
    if not ok:
        return None, f"wrangler versions view 失敗（{out}）"
    try:
        data = _extract_json(out)
    except json.JSONDecodeError as e:
        return None, f"wrangler versions view の JSON パースに失敗（{e}）"
    if not isinstance(data, dict):
        return None, "wrangler versions view の応答形式が想定外です（オブジェクトでない）"
    tag = (data.get("annotations") or {}).get(WRANGLER_TAG_ANNOTATION)
    return (tag or None), None


def resolve_head(ref: str) -> tuple[dict | None, str | None]:
    """`ref`（既定 HEAD）の SHA とコミット日時（committer date, ISO8601）を取得する。"""
    ok_sha, sha_out = _run(["git", "rev-parse", ref])
    if not ok_sha:
        return None, f"git rev-parse {ref} 失敗（{sha_out}）"
    ok_ts, ts_out = _run(["git", "log", "-1", "--format=%cI", ref])
    if not ok_ts:
        return None, f"git log {ref} 失敗（{ts_out}）"
    return {"sha": sha_out.strip(), "committed_at": ts_out.strip()}, None


# ──────────────────────────────────────────────
# 判定ロジック（純関数・API/subprocess 非依存 = --self-test の対象）
# ──────────────────────────────────────────────


def select_latest_deployment(data: object) -> tuple[dict | None, str | None]:
    """`wrangler deployments list --json` のパース済み応答から、実際に本番へ昇格された
    最新デプロイを 1 件選ぶ。Returns (deployment_or_none, error_reason)。

    🔴 **`fetch_latest_production_deployment` からフィルタ条件を分離してあるのは、
    この判定を `--self-test` で検証できるようにするため**（self-test 側に同じ条件を
    複製すると、本体の条件が壊れても self-test は PASS のままになる）。
    """
    if not isinstance(data, list):
        return None, "wrangler deployments list の応答形式が想定外です（配列でない）"

    real_deployments = [
        d for d in data
        if isinstance(d, dict)
        and (d.get("annotations") or {}).get("workers/triggered_by") == DEPLOYMENT_TRIGGER
        and d.get("versions")
    ]
    if not real_deployments:
        return None, REASON_NO_DEPLOYMENT_FOUND

    latest = max(real_deployments, key=lambda d: d.get("created_on") or "")
    versions = latest.get("versions") or []
    # 🔴 段階デプロイ（`wrangler versions deploy --percentage`・#40 で導入検討中）が走ると
    # versions に複数版が同居する。先頭を無条件に「本番稼働版」とすると、10% しか出ていない
    # 新版を見て「反映済み」と誤判定しうる（フェイルオープン）。100% の版が 1 つに定まる
    # ときだけ判定し、それ以外は判定不能へ倒す。
    fully_promoted = [v for v in versions if v.get("percentage") == 100]
    if len(fully_promoted) != 1:
        return None, (
            "本番デプロイが段階昇格中（100% の版が一意に定まらない）ため判定不能です"
            f"（versions={[(v.get('version_id'), v.get('percentage')) for v in versions]}）"
        )
    version_id = fully_promoted[0].get("version_id")
    if not version_id:
        return None, "最新デプロイに version_id が含まれていません"
    return {"version_id": version_id, "created_on": latest.get("created_on")}, None


def count_build_triggers() -> tuple[int, str | None, str | None] | None:
    """Cloudflare の build trigger 件数を実測する（読み取り専用・#693）。

    判定材料が揃わないとき（トークン未供給・API 失敗・wrangler.jsonc 不在）は
    **`None` を返して「分からない」と表明する**。0 件と混同すると、単なる権限不足を
    「デプロイ経路が構成されていない」と誤って断定してしまう（fail-safe）。
    """
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not token:
        return None
    try:
        from trigger_workers_build import (
            fetch_build_triggers,
            fetch_worker_scripts,
            worker_tag_from_scripts,
        )
        from wrangler_config import parse_worker_name

        wrangler_path = REPO_ROOT / "wrangler.jsonc"
        worker_name = parse_worker_name(wrangler_path.read_text(encoding="utf-8"))
        worker_tag = worker_tag_from_scripts(fetch_worker_scripts(account_id, token), worker_name)
        if worker_tag is None:
            return None
        return len(fetch_build_triggers(account_id, token, worker_tag)), worker_name, worker_tag
    except Exception:  # noqa: BLE001 — 診断の精緻化は本判定を止めてまで行わない
        return None


def refine_no_deployment_reason(
    reason: str | None,
    *,
    count_triggers: Callable[[], tuple[int, str | None, str | None] | None] = count_build_triggers,
) -> tuple[str | None, bool]:
    """「実デプロイ実績なし」を build trigger の実件数で切り分ける（#693）。

    Returns (reason, trigger_not_configured)。**trigger が 0 件と実測できたときだけ**
    共通診断（`workers_build_diagnostics.no_triggers_message`）へ差し替える。
    件数を取れなかった場合（`None`）は従来文言のまま返す — 「引けなかった」と
    「0 件だった」は別の事実であり、混同すると誤った断定になる。
    """
    if reason != REASON_NO_DEPLOYMENT_FOUND:
        return reason, False
    counted = count_triggers()
    if counted is None:
        return reason, False
    count, worker_name, worker_tag = counted
    if count == 0:
        return no_triggers_message(worker_name, worker_tag), True
    return reason, False


def sha_matches(tag: str, head_sha: str) -> bool:
    """本番タグと main HEAD の SHA が同一コミットを指すかを判定する。

    タグ・HEAD SHA のどちらかが短縮形（`git rev-parse --short` 等）でありうるため、
    双方を小文字化したうえで短い方が長い方の接頭辞になっているかで判定する
    （`retire_preview_aliases.py` の `retired-<sha12>` 慣行に合わせ、7 桁未満は
    誤検知リスクが高いため一致とみなさない）。
    """
    a = tag.strip().lower()
    b = head_sha.strip().lower()
    if not a or not b:
        return False
    if len(a) < MIN_SHA_PREFIX_LEN or len(b) < MIN_SHA_PREFIX_LEN:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return longer.startswith(shorter)


def decide(
    head: dict,
    deployment: dict,
    tag: str | None,
) -> dict:
    """1 回分の判定を行う純関数。

    Args:
        head: {"sha": str, "committed_at": ISO8601}
        deployment: {"version_id": str, "created_on": ISO8601}
        tag: 本番バージョンの SHA タグ（無ければ None）

    Returns:
        {"drifted": bool, "confidence": "exact"|"heuristic", "reason": str}
    """
    if tag:
        if sha_matches(tag, head["sha"]):
            return {"drifted": False, "confidence": "exact", "reason": "本番タグが main HEAD と一致しています"}
        return {"drifted": True, "confidence": "exact", "reason": REASON_TAG_MISMATCH}

    # heuristic: タグが無いので日時で必要条件をチェックする
    head_time = _parse_iso8601(head["committed_at"])
    deploy_time = _parse_iso8601(deployment["created_on"])
    if head_time > deploy_time:
        return {"drifted": True, "confidence": "heuristic", "reason": REASON_NO_TAG_HEAD_NEWER}
    return {
        "drifted": False,
        "confidence": "heuristic",
        "reason": "本番の最終デプロイが main HEAD のコミット日時以降のため、反映済みの可能性が高いと判定しました（heuristic・SHA タグによる完全一致ではありません）",
    }


def exit_code_for(drifted: bool | None) -> int:
    """判定結果を終了コードへ写像する唯一の関数（0/1/2 のマッピングを一元化）。

    drifted=None は「判定不能」を表し fail-closed で 2 を返す（0 を既定値にしない）。
    """
    if drifted is None:
        return 2
    return 1 if drifted else 0


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_sha_matches() -> list[str]:
    failures = []
    cases = [
        ("64d2aa316e503125fd8ea6d11ed7c71ab376cf68", "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", True, "完全一致"),
        ("64d2aa3", "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", True, "短縮形(7桁) vs 完全形"),
        ("64d2aa316e50", "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", True, "短縮形(12桁) vs 完全形"),
        ("64D2AA3", "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", True, "大文字小文字を無視する"),
        ("1b2be10", "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", False, "別コミットの短縮形は不一致"),
        ("64d2aa3", "64d2aa416e503125fd8ea6d11ed7c71ab376cf68", False, "接頭辞は一致するが以降が異なる別コミット"),
        ("64d2a", "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", False, "7桁未満は短すぎるため不一致扱い"),
        ("", "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", False, "空タグは不一致"),
    ]
    for tag, head_sha, want, label in cases:
        got = sha_matches(tag, head_sha)
        if got != want:
            failures.append(f"sha_matches({tag!r}, {head_sha!r}) [{label}] = {got}（期待 {want}）")
    return failures


def _self_test_decide_no_drift() -> list[str]:
    """乖離なしケース（exact モード: タグが HEAD と一致）。"""
    failures = []
    head = {"sha": "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", "committed_at": "2026-08-20T22:38:23+09:00"}
    deployment = {"version_id": "v1", "created_on": "2026-08-20T19:30:23.803431Z"}
    result = decide(head, deployment, tag="64d2aa3")
    if result["drifted"] is not False:
        failures.append(f"exact モードでタグ一致なのに drifted=True: {result}")
    if result["confidence"] != "exact":
        failures.append(f"exact モードのはずが confidence={result['confidence']}")
    if exit_code_for(result["drifted"]) != 0:
        failures.append("exit_code_for: drifted=False は exit 0 を期待")
    return failures


def _self_test_decide_drift() -> list[str]:
    """乖離ありケース（exact モード: タグが HEAD と不一致 = 実測の本番陳腐化パターン想定）。"""
    failures = []
    head = {"sha": "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", "committed_at": "2026-08-20T22:38:23+09:00"}
    deployment = {"version_id": "v1", "created_on": "2026-08-19T03:01:40.443777Z"}
    result = decide(head, deployment, tag="1b2be107d0ed")  # 別コミットのタグ
    if result["drifted"] is not True:
        failures.append(f"exact モードでタグ不一致なのに drifted=False: {result}")
    if result["reason"] != REASON_TAG_MISMATCH:
        failures.append(f"reason が REASON_TAG_MISMATCH でない: {result['reason']!r}")
    if exit_code_for(result["drifted"]) != 1:
        failures.append("exit_code_for: drifted=True は exit 1 を期待")
    return failures


def _self_test_decide_heuristic() -> list[str]:
    """タグが無い場合の heuristic モード（実測時点の本番デプロイの実態に対応）。"""
    failures = []

    # HEAD のコミット日時が最終デプロイより新しい → 乖離あり（実測の再現ケース）
    head_newer = {"sha": "64d2aa316e503125fd8ea6d11ed7c71ab376cf68", "committed_at": "2026-08-20T22:38:23+00:00"}
    deployment_older = {"version_id": "913f839b", "created_on": "2026-08-20T19:30:23.803431Z"}
    result = decide(head_newer, deployment_older, tag=None)
    if result["drifted"] is not True or result["confidence"] != "heuristic":
        failures.append(f"heuristic: HEAD がデプロイより新しいのに乖離なしと判定: {result}")
    if exit_code_for(result["drifted"]) != 1:
        failures.append("heuristic 乖離ありのケースで exit 1 になっていない")

    # デプロイが HEAD のコミット日時以降 → 乖離なし
    head_older = {"sha": "1b2be107d0ed5201862dd32025ea0ceb69d659ff", "committed_at": "2026-08-20T18:00:00+00:00"}
    deployment_newer = {"version_id": "v2", "created_on": "2026-08-20T19:30:23.803431Z"}
    result = decide(head_older, deployment_newer, tag=None)
    if result["drifted"] is not False or result["confidence"] != "heuristic":
        failures.append(f"heuristic: デプロイが HEAD より新しいのに乖離ありと判定: {result}")
    if exit_code_for(result["drifted"]) != 0:
        failures.append("heuristic 乖離なしのケースで exit 0 になっていない")

    # 同時刻（境界）→ 乖離なし（HEAD > deploy のときだけ乖離とする厳密な不等号の確認）
    same_time = {"sha": "x", "committed_at": "2026-08-20T19:30:23.803431Z"}
    deployment_same = {"version_id": "v3", "created_on": "2026-08-20T19:30:23.803431Z"}
    result = decide(same_time, deployment_same, tag=None)
    if result["drifted"] is not False:
        failures.append(f"heuristic: 同時刻境界で乖離ありと誤判定: {result}")

    return failures


def _self_test_indeterminate_exit_code() -> list[str]:
    """本番情報取得失敗（fetch 系が None 相当を返すケース）は呼び出し側で drifted=None を扱い、
    exit_code_for(None) が fail-closed で 2 を返すことを保証する。
    """
    failures = []
    if exit_code_for(None) != 2:
        failures.append("exit_code_for: drifted=None（判定不能）は exit 2（fail-closed）を期待")
    return failures


def _self_test_extract_json() -> list[str]:
    """wrangler stdout に警告バナー等の非 JSON 行が混じっても JSON 部分だけを抽出できることを保証する。"""
    failures = []
    raw = "⚠ WARNING some banner\n\n[ {\"a\": 1} ]"
    got = _extract_json(raw)
    if got != [{"a": 1}]:
        failures.append(f"_extract_json: バナー付き配列の抽出に失敗: {got!r}")
    raw_obj = "banner line\n{\"id\": \"x\"}"
    got_obj = _extract_json(raw_obj)
    if got_obj != {"id": "x"}:
        failures.append(f"_extract_json: バナー付きオブジェクトの抽出に失敗: {got_obj!r}")
    return failures


def _self_test_fetch_deployment_filters_non_deployment() -> list[str]:
    """本体の `select_latest_deployment` を **直接呼んで** 検証する（実データ形状を使う）。

    🔴 フィルタ条件をここに複製しないこと。複製すると本体が壊れても PASS のままになる。
    """
    failures = []
    upload_newer = {
        # 実測（2026-08-21）では preview アップロードの triggered_by は "upload" で返る。
        "id": "d1", "annotations": {"workers/triggered_by": "upload"},
        "versions": [{"version_id": "vX", "percentage": 100}],
        "created_on": "2026-08-20T20:00:00.000000Z",
    }
    deployment_older = {
        "id": "d2", "annotations": {"workers/triggered_by": "deployment"},
        "versions": [{"version_id": "vY", "percentage": 100}],
        "created_on": "2026-08-19T03:01:40.443777Z",
    }

    # ① version_upload（新しい）より deployment（古い）を選ぶ = preview を本番と誤認しない
    got, err = select_latest_deployment([upload_newer, deployment_older])
    if err is not None or not got or got.get("version_id") != "vY":
        failures.append(f"version_upload を誤って本番デプロイとして選んでいる: got={got!r} err={err!r}")

    # ② deployment が複数あるときは created_on 最大を選ぶ
    deployment_newer = {
        "id": "d3", "annotations": {"workers/triggered_by": "deployment"},
        "versions": [{"version_id": "vZ", "percentage": 100}],
        "created_on": "2026-08-20T19:30:23.803431Z",
    }
    got, err = select_latest_deployment([deployment_older, deployment_newer])
    if err is not None or not got or got.get("version_id") != "vZ":
        failures.append(f"最新の deployment を選べていない: got={got!r} err={err!r}")

    # ③ version_upload しか無ければ「本番デプロイ実績なし」= 判定不能へ倒す（fail-closed）
    got, err = select_latest_deployment([upload_newer])
    if got is not None or err != REASON_NO_DEPLOYMENT_FOUND:
        failures.append(f"version_upload のみの応答を本番デプロイとして扱っている: got={got!r} err={err!r}")

    # ③-2 段階昇格中（100% の版が一意でない）は判定不能へ倒す（フェイルオープン防止）
    got, err = select_latest_deployment([{
        "id": "d5", "annotations": {"workers/triggered_by": "deployment"},
        "versions": [{"version_id": "vNEW", "percentage": 10}, {"version_id": "vOLD", "percentage": 90}],
        "created_on": "2026-08-20T19:30:23.803431Z",
    }])
    if got is not None or not err:
        failures.append(f"段階昇格中を確定した本番版として扱っている: got={got!r} err={err!r}")

    # ④ 応答形式が想定外（配列でない）なら判定不能へ倒す
    got, err = select_latest_deployment({"unexpected": True})
    if got is not None or not err:
        failures.append(f"配列でない応答をエラーにしていない: got={got!r} err={err!r}")

    # ⑤ version_id 欠落は判定不能へ倒す（空文字を版として採用しない）
    got, err = select_latest_deployment([{
        "id": "d4", "annotations": {"workers/triggered_by": "deployment"},
        "versions": [{"percentage": 100}], "created_on": "2026-08-20T19:30:23.803431Z",
    }])
    if got is not None or not err:
        failures.append(f"version_id 欠落を判定不能にしていない: got={got!r} err={err!r}")
    return failures


def _self_test_refine_no_deployment_reason() -> list[str]:
    """🔴 #693 完了条件: trigger 0 件のとき専用メッセージが選ばれる（両スクリプト共通文言）。"""
    from workers_build_diagnostics import NO_TRIGGERS_REGISTERED_HINT

    failures: list[str] = []

    reason, flag = refine_no_deployment_reason(
        REASON_NO_DEPLOYMENT_FOUND, count_triggers=lambda: (0, "gem-hunter", "tag-1"),
    )
    if NO_TRIGGERS_REGISTERED_HINT not in reason:
        failures.append(f"trigger 0 件で共通診断へ差し替わっていない: {reason!r}")
    if "worker=gem-hunter" not in reason:
        failures.append(f"worker / tag のコンテキストが伝わっていない: {reason!r}")
    if not flag:
        failures.append("trigger 0 件で trigger_not_configured フラグが立っていない")

    reason, flag = refine_no_deployment_reason(
        REASON_NO_DEPLOYMENT_FOUND, count_triggers=lambda: (2, "gem-hunter", "tag-1"),
    )
    if reason != REASON_NO_DEPLOYMENT_FOUND or flag:
        failures.append(f"trigger 1 件以上では従来文言のままにする: {reason!r} flag={flag}")

    # 「引けなかった」を「0 件だった」と混同しない（fail-safe）
    reason, flag = refine_no_deployment_reason(
        REASON_NO_DEPLOYMENT_FOUND, count_triggers=lambda: None,
    )
    if reason != REASON_NO_DEPLOYMENT_FOUND or flag:
        failures.append(f"件数を取れないときは従来文言のままにする: {reason!r} flag={flag}")

    other = "本番デプロイが段階昇格中のため判定不能です"
    reason, flag = refine_no_deployment_reason(other, count_triggers=lambda: (0, "w", "t"))
    if reason != other or flag:
        failures.append(f"別の理由まで差し替えてはいけない: {reason!r} flag={flag}")

    return failures


def _self_test_emit_error_trigger_flag() -> list[str]:
    """判定不能 JSON に `trigger_not_configured` が載る／載らないことを固定する（#694）。"""
    import contextlib

    failures: list[str] = []
    for flag, expected in ((True, True), (False, False)):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            _emit_error("テスト", True, trigger_not_configured=flag)
        payload = json.loads(buffer.getvalue())
        if payload.get("trigger_not_configured", False) != expected:
            failures.append(
                f"trigger_not_configured={flag} のとき JSON が {payload!r}"
            )
        if payload.get("drifted", "missing") is not None:
            failures.append(f"判定不能では drifted=None を維持する: {payload!r}")
    return failures


def run_self_test() -> int:
    groups = [
        ("SHA 短縮形/完全形の突合", _self_test_sha_matches),
        ("乖離なし（exact: タグ一致）", _self_test_decide_no_drift),
        ("乖離あり（exact: タグ不一致）", _self_test_decide_drift),
        ("タグ無し時の heuristic 判定", _self_test_decide_heuristic),
        ("判定不能 → exit 2（fail-closed）", _self_test_indeterminate_exit_code),
        ("wrangler stdout の JSON 抽出", _self_test_extract_json),
        ("deployment/version_upload の判別", _self_test_fetch_deployment_filters_non_deployment),
        ("trigger 0 件の共通診断への切り替え（#693）", _self_test_refine_no_deployment_reason),
        ("判定不能 JSON の trigger_not_configured フラグ（#694）", _self_test_emit_error_trigger_flag),
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
# CLI
# ──────────────────────────────────────────────


def _emit_error(message: str, as_json: bool, *, trigger_not_configured: bool = False) -> None:
    """判定不能を出力する。

    `trigger_not_configured=True` のときは JSON に機械可読フラグを載せる（#694）。
    `trigger_workers_build.py` の `_emit_error` と同じフィールド名にしてあるので、
    呼び出し側（`sprint-cycle-router` Step 0.2）は 2 本のスクリプトを同じ形で扱える。
    """
    if as_json:
        payload = {"drifted": None, "error": message, "checked_at": now_jst_str()}
        if trigger_not_configured:
            payload["trigger_not_configured"] = True
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"ERROR: 判定不能: {message}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="main の HEAD と本番 Worker の乖離を機械検知する（読み取り専用・fail-closed）。"
                     "0=乖離なし / 1=乖離あり / 2=判定不能。",
    )
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument(
        "--ref", default="origin/main",
        help="比較対象の git ref（既定: origin/main）。作業ブランチの HEAD を既定にすると、"
             "別ブランチ上のセッションが古いコミットと比べて『乖離なし』と誤判定するため origin/main を既定にする。"
             "呼び出し前に `git fetch origin main` しておくこと（fetch 済みでなければ解決に失敗し exit 2）。",
    )
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    head, herr = resolve_head(args.ref)
    if herr is not None:
        _emit_error(f"main HEAD の解決に失敗しました（{herr}）", args.json)
        sys.exit(2)

    deployment, derr = fetch_latest_production_deployment()
    if derr is not None:
        derr, not_configured = refine_no_deployment_reason(derr)
        _emit_error(
            f"本番デプロイ情報の取得に失敗しました（{derr}）",
            args.json,
            trigger_not_configured=not_configured,
        )
        sys.exit(2)

    tag, terr = fetch_version_tag(deployment["version_id"])
    if terr is not None:
        _emit_error(f"本番バージョン詳細の取得に失敗しました（{terr}）", args.json)
        sys.exit(2)

    try:
        result = decide(head, deployment, tag)
    except (ValueError, TypeError) as e:
        # 日時文字列が想定外（小数秒の桁数・タイムゾーン表記のゆれ等）でも、無捕捉例外で
        # exit 1（＝「乖離あり」）に化けさせない。判定不能として exit 2 に倒す。
        _emit_error(f"日時の解釈に失敗したため判定できません（{type(e).__name__}: {e}）", args.json)
        sys.exit(2)
    result["head_sha"] = head["sha"]
    result["head_committed_at"] = head["committed_at"]
    result["prod_version_id"] = deployment["version_id"]
    result["prod_deployed_at"] = deployment["created_on"]
    result["prod_tag"] = tag
    result["checked_at"] = now_jst_str()

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["drifted"]:
            print(f"乖離あり（{result['confidence']}）: {result['reason']}")
            print(f"  main HEAD: {result['head_sha']}（{result['head_committed_at']}）")
            print(f"  本番デプロイ: version={result['prod_version_id']}（{result['prod_deployed_at']}）"
                  f" tag={result['prod_tag'] or '(なし)'}")
        else:
            print(f"乖離なし（{result['confidence']}）: {result['reason']}")

    sys.exit(exit_code_for(result["drifted"]))


if __name__ == "__main__":
    main()
