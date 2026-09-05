#!/usr/bin/env python3
"""check_cloudflare_cost.py — Cloudflare の課金額を日次でポーリングし、撤退ライン超過と急増を検知する

【背景（Issue #247 / `D-19`）】
`D-19`（2026-08-18・飼い主決定）は Workers Paid への切替とセットで **「撤退ラインを月額 $10 とし、
Billable Usage API の監視閾値に用いる」** と定めたが、実装が存在しなかった。`*.workers.dev` は
自ゾーンに属さず WAF レート制限を適用できず、アプリ内 `RATE_LIMITER` は Worker 起動後にしか
効かない（＝リクエスト数課金そのものは止められない）ため、**検知が唯一の防御**である。

【2 軸判定（Issue #247 対応方針）】
  ① 月内累計が `--threshold-usd`（既定 10.0 = `D-19` の撤退ライン）を超えたか
  ② 直近日が前日比で `--surge-ratio`（既定 3.0）倍以上に急増したか
日次ポーリングは最大 24 時間の検知ラグがあるため、月末に一発で閾値へ到達するパターンを ② で拾う。
①・② は **どちらも独立に評価する**（片方が真でも他方の評価を飛ばさない・#725 の干渉検証対象）。

【フェイルセーフ（fail-closed）】
現行の `CLOUDFLARE_API_TOKEN` には Billing 系 Read 権限が無く、課金系エンドポイントは
`Authentication error` を返す（Issue #247「前提（ユーザー作業）」）。この状態を
**`auth_missing: true` + exit 2** として明確に区別する。「権限が無いから正常」と `0` に丸めない
（`docs/rules/check-tool-design-rules.md` §1）。取得できたレコードが 0 件のときも同様に exit 2
（同 §2「対象 0 件は fail-closed」）。

【応答形式について（未検証・重要）】
本アカウントは Billing Read 権限が未付与のため、`GET /accounts/{id}/billable-usage` の実応答を
**実測できていない**（CP-2 の観点で、記憶に基づく決め打ちのパースはしない）。そのため
`extract_records()` は「日付らしいキー」「金額らしいキー」の候補集合から拾い、**1 件も解釈できな
ければ exit 2 に倒す**（誤ったキー名で 0 件と読んで「正常」を返す fail-open を避ける）。権限付与後に
実応答を確認したら、候補集合を実測値へ絞り込むこと。

【終了コード】
  0 = 閾値内（正常）。月内累計が閾値以下で、前日比の急増も検知しなかった
  1 = 要対応。閾値超過 **または** 前日比急増を検知した（どちらか一方でも真なら 1）
  2 = 判定不能（fail-closed）。認証情報の欠落・Billing 権限不足・API 失敗・応答の必須フィールド
      欠落・**対象 0 件** を含む。呼び出し側はこれを「異常なし」として扱わない

【実行場所（`check-tool-design-rules.md` §5.2 に従い本判定と self-test を別々に決めている）】
  本判定: `.claude/hooks/stop-slack-notify.sh` が `--gate-daily` 付きで起動する（JST 当日 1 回・
    `tools/commit_cost_telemetry.py` と同じ流儀。終了コードは stderr へ出すが Stop はブロックしない）。
    **`tools/run_checks.sh` には本判定を配線しない** — Cloudflare Billing API への実疎通が必要で、
    外部要因で全 PR が赤くなるため（`check_prod_drift.py` と同じ扱い）。
  `--self-test`: `tools/run_checks.sh` に配線済み（ネットワーク非依存なので PR ごとに走らせる）。

【Issue 起票をしない理由】
超過時の記録は stdout の 1 行のみで、GitHub API は叩かない。起票は呼び出し側（親セッション /
Stop hook 配線）の責務で、本スクリプトは読み取り専用の検知器に徹する。出力する 1 行は
`tools/triage_notification.py classify` が **A 区分（A-6: 課金設定）** と判定する文面にしてある。

日時の扱い: `docs/rules/datetime-rules.md` に従い、表示・記録用（`checked_at`）は JST。
月の決定も「JST の今日」基準（請求月は人間が読む単位のため）。API へ渡す値・内部比較は文字列日付。

使い方:
    python3 tools/check_cloudflare_cost.py
    python3 tools/check_cloudflare_cost.py --json
    python3 tools/check_cloudflare_cost.py --gate-daily        # JST 当日に実行済みならスキップ
    python3 tools/check_cloudflare_cost.py --dry-run           # 判定のみ（マーカー stamp もしない）
    python3 tools/check_cloudflare_cost.py --threshold-usd 10.0
    python3 tools/check_cloudflare_cost.py --surge-ratio 3.0
    python3 tools/check_cloudflare_cost.py --self-test         # ネットワーク不要のユニットテスト
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloudflare_api import CF_PAGE_SIZE, should_fetch_next_page  # noqa: E402
from mask_secrets import mask_text  # noqa: E402

# `_http_json`（HTTPError + 非 JSON ボディのマスク処理を含む）は `trigger_workers_build.py` の
# 実装をそのまま使う。同じ処理を書き写すと `cloudflare_api.py` 新設（#476）で解消したはずの
# 「同一ロジックの独立したコピー」を再生産することになるため、本 PR では複製せず再利用する。
from trigger_workers_build import ApiError, _http_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))

CF_API_BASE = "https://api.cloudflare.com/client/v4"
BILLABLE_USAGE_PATH = "billable-usage"

DEFAULT_THRESHOLD_USD = 10.0  # D-19 の撤退ライン（月額 $10）
DEFAULT_SURGE_RATIO = 3.0

# 急増判定の下限。$0.00 → $0.02 のような微小な立ち上がりで A-6 通知を撃たないための床。
# これが無いと月初 1 日目や前日 0 円の日に毎回 surge が真になり、通知が信用されなくなる。
SURGE_MIN_ABS_USD = 1.0

MARKER_REL = "content/pipeline-state/.cloudflare_cost_check_date"

# 応答形式が未実測（docstring 参照）のため候補で拾う。実測できたら 1 つに絞ること。
DATE_KEYS = ("date", "day", "usage_date", "period_start", "occurred_at")
AMOUNT_KEYS = ("billable_usd", "billable_amount", "amount_usd", "amount", "cost_usd", "cost", "total_usd")
# `result` が配列でなくオブジェクトで返る場合に、日次配列が入りうるキー。
RESULT_LIST_KEYS = ("daily", "usage", "billable_usage", "items", "records")

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

# Cloudflare が権限不足で返す代表的なシグナル（HTTP 403/401 のボディを含む）。
_AUTH_ERROR_RE = re.compile(
    r"authentication\s+error|not\s+authorized|unauthorized|permission|forbidden|"
    r"insufficient\s+scope|invalid\s+api\s+token",
    re.IGNORECASE,
)
_AUTH_ERROR_CODES = {1000, 9106, 9109, 10000}


class AuthMissingError(ApiError):
    """Billing Read 権限の欠落（`auth_missing: true` + exit 2 として区別する・Issue #247）。"""


# ──────────────────────────────────────────────
# 日時（表示・記録は JST）
# ──────────────────────────────────────────────


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械比較には使わない（datetime-rules.md）。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def current_month_jst() -> str:
    """判定対象の請求月（JST 基準の `YYYY-MM`）。"""
    return datetime.now(JST).strftime("%Y-%m")


# ──────────────────────────────────────────────
# 日次ゲート（commit_cost_telemetry.py と同じ流儀）
# ──────────────────────────────────────────────


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or REPO_ROOT)


def marker_path() -> Path:
    return project_dir() / MARKER_REL


def already_ran_today() -> bool:
    today = datetime.now(JST).strftime("%Y-%m-%d")
    try:
        return marker_path().read_text(encoding="utf-8").strip() == today
    except OSError:
        return False


def stamp_today() -> None:
    """マーカーは **判定できた後** に打つ（失敗日は同日中に再試行できる・#243 と同じ設計）。"""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    path = marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(today + "\n", encoding="utf-8")
    except OSError:
        pass


# ──────────────────────────────────────────────
# 判定ロジック（純関数・--self-test の対象）
# ──────────────────────────────────────────────


def is_auth_error(payload: dict[str, Any]) -> bool:
    """Cloudflare の `success: false` 応答が「権限不足」を意味するか判定する。

    権限不足を単なる API 失敗と混ぜると、ユーザーだけが解決できる A-6（トークンへ Billing Read を
    付与する）が埋もれる。逆に何でも権限不足と読むと A-6 通知が誤爆するため、
    `errors[].code` と文言の両方を見る。
    """
    errors = payload.get("errors")
    if not isinstance(errors, list):
        errors = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        code = error.get("code")
        if isinstance(code, int) and code in _AUTH_ERROR_CODES:
            return True
        message = error.get("message")
        if isinstance(message, str) and _AUTH_ERROR_RE.search(message):
            return True
    return False


def normalize_result(result: Any) -> list[dict[str, Any]] | None:
    """`result` を日次レコードの配列へ正規化する。解釈できなければ `None`（→ 判定不能）。"""
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        for key in RESULT_LIST_KEYS:
            value = result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return None


def _pick(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def extract_records(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """生レコードから `{"date": "YYYY-MM-DD", "usd": float}` の列を作る（純関数）。

    Returns (records, error_reason)。**1 件も解釈できなければ error** を返す（fail-closed）。
    金額が int で返る実装・float で返る実装のどちらでも受けるため `float()` に通す。
    """
    records: list[dict[str, Any]] = []
    for item in items:
        raw_date = _pick(item, DATE_KEYS)
        raw_amount = _pick(item, AMOUNT_KEYS)
        if not isinstance(raw_date, str):
            continue
        matched = _DATE_RE.match(raw_date.strip())
        if not matched:
            continue
        if isinstance(raw_amount, bool) or not isinstance(raw_amount, (int, float, str)):
            continue
        try:
            usd = float(raw_amount)
        except (TypeError, ValueError):
            continue
        records.append({"date": "-".join(matched.groups()), "usd": usd})

    if not records:
        return [], (
            "billable-usage の応答から日次レコードを 1 件も解釈できませんでした"
            "（応答形式の変更、または対象期間にデータが無い可能性があります。"
            "対象の選択が意図どおりか確認してください）"
        )
    records.sort(key=lambda r: r["date"])
    return records, None


def evaluate(
    records: list[dict[str, Any]],
    month: str,
    threshold_usd: float,
    surge_ratio: float,
) -> dict[str, Any]:
    """2 軸判定（純関数）。①閾値超過 と ②前日比急増 は **互いに独立** に評価する。

    🔴 早期 return を置かない（#725 の干渉）。急増が算出不能でも閾値超過の評価は必ず行い、
    閾値内でも急増の評価は必ず行う。
    """
    # ① 月内累計（対象月のレコードだけを合計する）
    monthly = [r for r in records if r["date"].startswith(month + "-")]
    billable_usd = round(sum(r["usd"] for r in monthly), 6)
    exceeded = billable_usd > threshold_usd

    # ② 前日比。月境界をまたぐ比較を成立させるため、**月フィルタ前の全レコード** を使う
    #    （月初 1 日目に「前日が無い」として毎月 1 回検知不能になるのを避ける）。
    latest_day_usd: float | None = records[-1]["usd"] if records else None
    prev_day_usd: float | None = records[-2]["usd"] if len(records) >= 2 else None

    ratio: float | None = None
    surge_detected = False
    if latest_day_usd is not None and prev_day_usd is not None:
        if prev_day_usd > 0:
            ratio = round(latest_day_usd / prev_day_usd, 6)
        # 前日 0 円は倍率を算出できない（ratio は null のまま）が、急増そのものは起こりうる。
        # 微小な立ち上がりでの誤爆を避けるため SURGE_MIN_ABS_USD の床を併用する。
        if latest_day_usd >= SURGE_MIN_ABS_USD:
            if prev_day_usd > 0:
                surge_detected = latest_day_usd >= prev_day_usd * surge_ratio
            else:
                surge_detected = True

    return {
        "month": month,
        "billable_usd": billable_usd,
        "threshold_usd": threshold_usd,
        "exceeded": exceeded,
        "latest_day_usd": latest_day_usd,
        "prev_day_usd": prev_day_usd,
        "surge_ratio": ratio,
        "surge_detected": surge_detected,
    }


def exit_code_for(result: dict[str, Any] | None) -> int:
    """判定結果を終了コードへ写像する唯一の関数（0/1/2 を一元化）。

    `None` は判定不能を表し fail-closed で 2 を返す（0 を既定値にしない）。
    """
    if result is None:
        return 2
    return 1 if (result.get("exceeded") or result.get("surge_detected")) else 0


def alert_line(result: dict[str, Any]) -> str:
    """超過・急増を 1 行で記録する（`triage_notification.py` が A-6 と判定する文面）。

    「課金」「上限」を含め、ユーザーだけができる操作（課金設定の確認・上限変更）を明示する
    （`user-notification-triage.md` §3 の必須要素）。
    """
    reasons = []
    if result.get("exceeded"):
        reasons.append(
            f"月内累計 ${result['billable_usd']:.2f} が撤退ライン ${result['threshold_usd']:.2f} を超過"
        )
    if result.get("surge_detected"):
        ratio = result.get("surge_ratio")
        ratio_text = f" {ratio:.2f} 倍" if isinstance(ratio, (int, float)) else "（前日 $0.00 からの立ち上がり）"
        reasons.append(
            f"直近日 ${result['latest_day_usd']:.2f} が前日 ${result['prev_day_usd']:.2f} 比で{ratio_text}に急増"
        )
    return (
        f"⚠️ Cloudflare の課金額が要対応水準です（{result['month']}）: "
        + " / ".join(reasons)
        + "。Cloudflare ダッシュボードの課金設定で請求上限とプランを確認してください"
        "（A-6: 課金設定はアカウント権限が物理的に必要）。未対応だと請求額が増え続けます。"
    )


# ──────────────────────────────────────────────
# 取得系（実 I/O。opener 差し替えで self-test から検証できる）
# ──────────────────────────────────────────────


def fetch_billable_usage(
    account_id: str,
    token: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    """`GET /accounts/{id}/billable-usage` を全ページ取得する。

    ページングの継続判定は `cloudflare_api.should_fetch_next_page()` を再利用する
    （同じロジックを再実装しない・#476）。
    """
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        url = (
            f"{CF_API_BASE}/accounts/{account_id}/{BILLABLE_USAGE_PATH}"
            f"?per_page={CF_PAGE_SIZE}&page={page}"
        )
        payload = _http_json(url, {"Authorization": f"Bearer {token}"}, opener=opener)
        if not isinstance(payload, dict):
            raise ApiError("billable-usage の応答形式が想定外です（オブジェクトでない）")
        if not payload.get("success"):
            message = mask_text(f"billable-usage の取得に失敗しました: {payload.get('errors')}")
            if is_auth_error(payload):
                raise AuthMissingError(message)
            raise ApiError(message)
        page_items = normalize_result(payload.get("result"))
        if page_items is None:
            raise ApiError("billable-usage の応答に日次レコードの配列が含まれていません")
        items.extend(page_items)
        if not should_fetch_next_page(payload.get("result_info") or {}, len(items), len(page_items)):
            break
        page += 1
    return items


# ──────────────────────────────────────────────
# 出力
# ──────────────────────────────────────────────


def _empty_payload() -> dict[str, Any]:
    """`--json` の出力キー集合（判定不能時も同じキーを過不足なく出す）。"""
    return {
        "month": None,
        "billable_usd": None,
        "threshold_usd": None,
        "exceeded": None,
        "latest_day_usd": None,
        "prev_day_usd": None,
        "surge_ratio": None,
        "surge_detected": None,
        "checked_at": now_jst_str(),
        "error": None,
        "auth_missing": False,
    }


def emit_error(message: str, as_json: bool, *, auth_missing: bool = False) -> None:
    message = mask_text(message) or message
    if as_json:
        payload = _empty_payload()
        payload["error"] = message
        payload["auth_missing"] = auth_missing
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"ERROR: 判定不能: {message}", file=sys.stderr)


def emit_result(result: dict[str, Any], as_json: bool, *, dry_run: bool) -> None:
    payload = _empty_payload()
    payload.update(result)
    payload["error"] = None
    payload["auth_missing"] = False
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    if result.get("exceeded") or result.get("surge_detected"):
        line = alert_line(result)
        # --dry-run でも判定内容は見せる（副作用＝マーカー stamp を起こさないだけ）。
        print(f"[dry-run] {line}" if dry_run else line)
    else:
        print(
            f"閾値内: {result['month']} の月内累計 ${result['billable_usd']:.2f} "
            f"（撤退ライン ${result['threshold_usd']:.2f}）。前日比の急増も検知していません。"
        )


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main(argv: list[str] | None = None, *, opener: Callable[..., Any] = urllib.request.urlopen) -> int:
    parser = argparse.ArgumentParser(
        description="Cloudflare の課金額（Billable Usage）を監視する。"
                     "0=閾値内 / 1=閾値超過または急増 / 2=判定不能（fail-closed）。",
    )
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument("--gate-daily", action="store_true",
                        help="JST 当日に既に実行済みならスキップ（Stop hook から毎回呼ぶ用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="判定のみ。マーカーの stamp を行わない")
    parser.add_argument("--threshold-usd", type=float, default=DEFAULT_THRESHOLD_USD,
                        help=f"月内累計の閾値 USD（既定 {DEFAULT_THRESHOLD_USD} = D-19 の撤退ライン）")
    parser.add_argument("--surge-ratio", type=float, default=DEFAULT_SURGE_RATIO,
                        help=f"前日比の急増倍率（既定 {DEFAULT_SURGE_RATIO}）")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテスト")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if args.gate_daily and already_ran_today():
        return 0

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not token:
        emit_error(
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN がセッション環境にありません",
            args.json,
            auth_missing=True,
        )
        return 2

    try:
        items = fetch_billable_usage(account_id, token, opener=opener)
    except AuthMissingError as error:
        emit_error(
            f"Cloudflare API トークンに Billing Read 権限がありません（{error}）",
            args.json,
            auth_missing=True,
        )
        return 2
    except ApiError as error:
        emit_error(f"billable-usage の取得に失敗しました（{error}）", args.json)
        return 2

    records, rerr = extract_records(items)
    if rerr is not None:
        emit_error(rerr, args.json)
        return 2

    result = evaluate(records, current_month_jst(), args.threshold_usd, args.surge_ratio)
    emit_result(result, args.json, dry_run=args.dry_run)

    # マーカーは判定できた後にだけ打つ（exit 2 の日は同日中に再試行できる）。
    if args.gate_daily and not args.dry_run:
        stamp_today()

    return exit_code_for(result)


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


class _FakeHttpResponse:
    """`urllib.request.urlopen` の戻り値（context manager + `.read()`）を模倣する。"""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class _RecordingOpener:
    """呼び出し URL・ヘッダ・メソッドを **記録する** fake opener（#710）。

    終了コードだけを差し替える fake は「判定結果を固定値へ潰す変異」を見逃すため、
    ① 意図したエンドポイントを叩いているか ② `main()` から実際に呼ばれたか、を assert できる形にする。
    """

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: int = 30) -> _FakeHttpResponse:  # noqa: ARG002
        self.calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "has_auth_header": any(k.lower() == "authorization" for k in request.headers),
        })
        index = min(len(self.calls) - 1, len(self._pages) - 1)
        return _FakeHttpResponse(json.dumps(self._pages[index]).encode("utf-8"))


class _RaisingOpener:
    """HTTP エラーを送出する fake opener（argv も記録する）。"""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.calls: list[str] = []

    def __call__(self, request: Any, timeout: int = 30) -> Any:  # noqa: ARG002
        self.calls.append(request.full_url)
        raise urllib.error.HTTPError(
            request.full_url, self.status, "err", None, io.BytesIO(self.body)
        )


def _ok_page(items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    page: dict[str, Any] = {"success": True, "errors": [], "result": items}
    page.update(extra)
    return page


@contextlib.contextmanager
def _env(**values: str | None):
    saved = {k: os.environ.get(k) for k in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_main(argv: list[str], opener: Any, *, creds: bool = True) -> tuple[int, str]:
    """`main()` を通して終了コードと stdout を得る（内部関数の直呼びで済ませない）。"""
    buffer = io.StringIO()
    env = (
        {"CLOUDFLARE_ACCOUNT_ID": "acct-test", "CLOUDFLARE_API_TOKEN": "tok-test"}
        if creds
        else {"CLOUDFLARE_ACCOUNT_ID": None, "CLOUDFLARE_API_TOKEN": None}
    )
    with _env(**env), contextlib.redirect_stdout(buffer):
        code = main(argv, opener=opener)
    return code, buffer.getvalue()


# ── グループ 1: 閾値判定（① 単体） ──────────────────


def _self_test_threshold() -> list[str]:
    failures: list[str] = []
    base = [{"date": "2026-09-01", "usd": 4.0}, {"date": "2026-09-02", "usd": 4.0}]

    within = evaluate(base, "2026-09", 10.0, 3.0)
    if within["exceeded"]:
        failures.append(f"$8.00 は閾値 $10 以内なのに exceeded=True: {within}")
    if exit_code_for(within) != 0:
        failures.append("閾値内・急増なしは exit 0 を期待")

    over = evaluate(base + [{"date": "2026-09-03", "usd": 4.0}], "2026-09", 10.0, 99.0)
    if not over["exceeded"]:
        failures.append(f"$12.00 は閾値 $10 超過のはず: {over}")
    if exit_code_for(over) != 1:
        failures.append("閾値超過は exit 1 を期待")

    # 境界: ちょうど閾値は超過ではない（比較の向きの変異を検出する）
    exact = evaluate([{"date": "2026-09-01", "usd": 10.0}], "2026-09", 10.0, 99.0)
    if exact["exceeded"]:
        failures.append("ちょうど閾値ぴったりは超過扱いにしない（> で比較する）")

    # 別月のレコードは月内累計に混ぜない
    mixed = evaluate(
        [{"date": "2026-08-31", "usd": 99.0}, {"date": "2026-09-01", "usd": 1.0}],
        "2026-09", 10.0, 99.0,
    )
    if mixed["billable_usd"] != 1.0:
        failures.append(f"対象月以外を合計に混ぜている: {mixed['billable_usd']}")
    return failures


# ── グループ 2: 前日比の急増（② 単体・入力バリアント） ──────────────────


def _self_test_surge() -> list[str]:
    failures: list[str] = []

    # int / float 混在（実応答の型ゆれ）
    surge = evaluate(
        [{"date": "2026-09-10", "usd": 1}, {"date": "2026-09-11", "usd": 6.0}],
        "2026-09", 1000.0, 3.0,
    )
    if not surge["surge_detected"]:
        failures.append(f"1 → 6（6 倍）は急増のはず: {surge}")
    if surge["surge_ratio"] != 6.0:
        failures.append(f"surge_ratio が 6.0 でない: {surge['surge_ratio']}")
    if exit_code_for(surge) != 1:
        failures.append("急増検知は（閾値内でも）exit 1 を期待")

    calm = evaluate(
        [{"date": "2026-09-10", "usd": 2.0}, {"date": "2026-09-11", "usd": 3.0}],
        "2026-09", 1000.0, 3.0,
    )
    if calm["surge_detected"]:
        failures.append(f"1.5 倍は急増ではない: {calm}")

    # 前日 0 円（ゼロ除算）: 倍率は算出不能（null）だが、床を超える立ち上がりは急増とみなす
    from_zero = evaluate(
        [{"date": "2026-09-10", "usd": 0.0}, {"date": "2026-09-11", "usd": 5.0}],
        "2026-09", 1000.0, 3.0,
    )
    if from_zero["surge_ratio"] is not None:
        failures.append(f"前日 0 円で surge_ratio が null でない: {from_zero['surge_ratio']}")
    if not from_zero["surge_detected"]:
        failures.append("前日 0 円 → $5.00 は急増として拾う")

    # 微小な立ち上がりは床（SURGE_MIN_ABS_USD）で抑止する（通知の誤爆防止）
    tiny = evaluate(
        [{"date": "2026-09-10", "usd": 0.0}, {"date": "2026-09-11", "usd": 0.02}],
        "2026-09", 1000.0, 3.0,
    )
    if tiny["surge_detected"]:
        failures.append("$0.02 の立ち上がりは急増として扱わない（床で抑止）")

    # 月境界をまたぐ前日比（月初 1 日目でも判定できる）
    boundary = evaluate(
        [{"date": "2026-08-31", "usd": 1.0}, {"date": "2026-09-01", "usd": 9.0}],
        "2026-09", 1000.0, 3.0,
    )
    if not boundary["surge_detected"]:
        failures.append(f"月境界をまたぐ 1 → 9 は急増のはず: {boundary}")
    if boundary["prev_day_usd"] != 1.0:
        failures.append(f"前日が前月のレコードから取れていない: {boundary['prev_day_usd']}")

    # 前日データが無い（レコード 1 件）→ 倍率も検知も出せないが、閾値評価は生きている
    single = evaluate([{"date": "2026-09-01", "usd": 50.0}], "2026-09", 10.0, 3.0)
    if single["surge_ratio"] is not None or single["surge_detected"]:
        failures.append(f"1 件だけで急増を断定してはいけない: {single}")
    if not single["exceeded"]:
        failures.append("前日が無くても閾値超過の評価は行う")
    return failures


# ── グループ 3: 干渉検証（#725・①と②が互いの前提を壊していない） ──────────────────


def _self_test_interference() -> list[str]:
    """①閾値超過 と ②急増 は同じ `records` を通るが、片方の早期 return で他方が
    評価されなくなっていないことを示す（両方向を確認する）。"""
    failures: list[str] = []

    # A: 急増が算出不能（前日なし）でも閾値超過は検知される
    only_threshold = evaluate([{"date": "2026-09-01", "usd": 20.0}], "2026-09", 10.0, 3.0)
    if not (only_threshold["exceeded"] and not only_threshold["surge_detected"]):
        failures.append(f"急増算出不能でも閾値超過は生きているべき: {only_threshold}")
    if exit_code_for(only_threshold) != 1:
        failures.append("閾値超過のみでも exit 1")

    # B: 閾値内でも急増は検知される（閾値内で早期 return していない）
    only_surge = evaluate(
        [{"date": "2026-09-10", "usd": 1.0}, {"date": "2026-09-11", "usd": 5.0}],
        "2026-09", 1000.0, 3.0,
    )
    if not (only_surge["surge_detected"] and not only_surge["exceeded"]):
        failures.append(f"閾値内でも急増は検知されるべき: {only_surge}")
    if exit_code_for(only_surge) != 1:
        failures.append("急増のみでも exit 1")

    # C: 両方真のときも両フィールドが立つ（片方が他方を上書きしていない）
    both = evaluate(
        [{"date": "2026-09-10", "usd": 2.0}, {"date": "2026-09-11", "usd": 20.0}],
        "2026-09", 10.0, 3.0,
    )
    if not (both["exceeded"] and both["surge_detected"]):
        failures.append(f"両方成立すべきケースで片方しか立っていない: {both}")

    # D: フェイルセーフ（exit 2）が①②の前提を壊していない
    #    = 取得に失敗した経路では判定結果そのものが存在しない（None → 2）
    if exit_code_for(None) != 2:
        failures.append("判定不能は exit 2（0 に丸めない）")
    return failures


# ── グループ 4: 応答パース（必須フィールド欠落・0 件） ──────────────────


def _self_test_extract_records() -> list[str]:
    failures: list[str] = []

    records, err = extract_records([
        {"date": "2026-09-02", "billable_usd": "3.5"},
        {"date": "2026-09-01", "billable_usd": 1},
    ])
    if err is not None:
        failures.append(f"正常系でエラーになった: {err}")
    elif [r["date"] for r in records] != ["2026-09-01", "2026-09-02"]:
        failures.append(f"日付昇順にソートされていない: {records}")
    elif records[1]["usd"] != 3.5:
        failures.append(f"文字列金額を float に変換できていない: {records}")

    _, err_empty = extract_records([])
    if err_empty is None:
        failures.append("対象 0 件は fail-closed（エラーを返す）")

    _, err_missing = extract_records([{"date": "2026-09-01"}, {"billable_usd": 1.0}])
    if err_missing is None:
        failures.append("必須フィールド欠落のみのレコード群はエラーにする")

    _, err_bad_date = extract_records([{"date": "not-a-date", "billable_usd": 1.0}])
    if err_bad_date is None:
        failures.append("日付として解釈できないレコードのみならエラーにする")

    if normalize_result({"daily": [{"date": "2026-09-01"}]}) is None:
        failures.append("result がオブジェクトでも日次配列を取り出せるべき")
    if normalize_result("nope") is not None:
        failures.append("result が想定外の型なら None（判定不能へ倒す）")
    return failures


def _self_test_auth_detection() -> list[str]:
    failures: list[str] = []
    if not is_auth_error({"errors": [{"code": 10000, "message": "Authentication error"}]}):
        failures.append("code 10000 / Authentication error を権限不足と判定できていない")
    if not is_auth_error({"errors": [{"code": 1234, "message": "You are not authorized"}]}):
        failures.append("文言ベースの権限不足を検出できていない")
    if is_auth_error({"errors": [{"code": 7003, "message": "Could not route to /x"}]}):
        failures.append("無関係なエラーを権限不足と誤判定している（A-6 通知の誤爆）")
    if is_auth_error({"errors": "broken"}):
        failures.append("errors が想定外の型でも例外にせず False を返すべき")
    return failures


# ── グループ 5: main() を通した終了コード経路 + fake の argv 検証 ──────────────────


def _self_test_main_paths() -> list[str]:
    failures: list[str] = []
    month = current_month_jst()

    # 正常系（閾値内 → exit 0）。fake は URL を記録し、main() から実際に呼ばれたことを assert する。
    opener_ok = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.5}])])
    code, out = _run_main(["--json"], opener_ok)
    if code != 0:
        failures.append(f"閾値内なのに main() が exit {code}")
    if not opener_ok.calls:
        failures.append("main() から HTTP opener が一度も呼ばれていない（判定が固定値に潰れている）")
    else:
        url = opener_ok.calls[0]["url"]
        if f"/accounts/acct-test/{BILLABLE_USAGE_PATH}" not in url:
            failures.append(f"意図したエンドポイントを叩いていない: {url}")
        if "per_page=" not in url or "page=1" not in url:
            failures.append(f"ページングパラメータが付いていない: {url}")
        if opener_ok.calls[0]["method"] != "GET":
            failures.append(f"読み取り専用のはずが {opener_ok.calls[0]['method']}")
        if not opener_ok.calls[0]["has_auth_header"]:
            failures.append("Authorization ヘッダを付けていない")
    try:
        payload = json.loads(out)
    except ValueError:
        payload = {}
        failures.append(f"--json の出力が JSON でない: {out!r}")
    expected_keys = {
        "month", "billable_usd", "threshold_usd", "exceeded", "latest_day_usd",
        "prev_day_usd", "surge_ratio", "surge_detected", "checked_at", "error", "auth_missing",
    }
    if payload and set(payload) != expected_keys:
        failures.append(f"--json のキー集合が契約と不一致: {sorted(set(payload) ^ expected_keys)}")
    if payload.get("checked_at", "").endswith("JST") is False:
        failures.append(f"checked_at が JST 表記でない: {payload.get('checked_at')}")

    # 閾値超過 → exit 1（main() 経由）
    opener_over = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
    code, out = _run_main([], opener_over)
    if code != 1:
        failures.append(f"閾値超過なのに main() が exit {code}")
    if "課金" not in out:
        failures.append(f"超過時の 1 行に A-6 判定用の文言が無い: {out!r}")

    # 急増のみ（閾値は高く設定）→ exit 1
    opener_surge = _RecordingOpener([_ok_page([
        {"date": f"{month}-01", "billable_usd": 1.0},
        {"date": f"{month}-02", "billable_usd": 9.0},
    ])])
    code, _ = _run_main(["--threshold-usd", "1000"], opener_surge)
    if code != 1:
        failures.append(f"急増検知なのに main() が exit {code}")

    # --dry-run でも判定内容は出るが、終了コードは同じ（副作用のみ抑止）
    opener_dry = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
    code, out = _run_main(["--dry-run"], opener_dry)
    if code != 1 or "dry-run" not in out:
        failures.append(f"--dry-run の挙動が想定外: exit={code} out={out!r}")

    # 認証情報の欠落 → exit 2 + auth_missing
    opener_unused = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 1.0}])])
    code, out = _run_main(["--json"], opener_unused, creds=False)
    if code != 2:
        failures.append(f"認証情報欠落は exit 2 のはずが {code}")
    if opener_unused.calls:
        failures.append("認証情報が無いのに API を叩いている")
    if json.loads(out).get("auth_missing") is not True:
        failures.append(f"認証情報欠落で auth_missing=true になっていない: {out!r}")

    # Billing 権限不足（success:false + Authentication error）→ exit 2 + auth_missing
    opener_denied = _RecordingOpener([
        {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}], "result": None}
    ])
    code, out = _run_main(["--json"], opener_denied)
    if code != 2:
        failures.append(f"権限不足は exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not True:
        failures.append(f"権限不足で auth_missing=true になっていない: {out!r}")

    # HTTP エラー（非 JSON ボディ）→ exit 2（auth_missing は立てない）
    opener_http = _RaisingOpener(500, b"upstream exploded")
    code, out = _run_main(["--json"], opener_http)
    if code != 2:
        failures.append(f"HTTP エラーは exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not False:
        failures.append("HTTP エラーを権限不足と混同している")
    if not opener_http.calls:
        failures.append("HTTP エラー経路でも opener は呼ばれるはず")

    # success:false（権限とは無関係）→ exit 2
    opener_fail = _RecordingOpener([{"success": False, "errors": [{"code": 7003, "message": "no route"}]}])
    code, out = _run_main(["--json"], opener_fail)
    if code != 2:
        failures.append(f"success:false は exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not False:
        failures.append("無関係な API 失敗で auth_missing を立てている")

    # 日次データ 0 件 → exit 2（fail-closed。0 に丸めない）
    opener_empty = _RecordingOpener([_ok_page([])])
    code, out = _run_main(["--json"], opener_empty)
    if code != 2:
        failures.append(f"対象 0 件は exit 2 のはずが {code}")
    if not json.loads(out).get("error"):
        failures.append("対象 0 件で error が空")

    # 必須フィールド欠落 → exit 2
    opener_broken = _RecordingOpener([_ok_page([{"foo": "bar"}])])
    code, _ = _run_main(["--json"], opener_broken)
    if code != 2:
        failures.append(f"必須フィールド欠落は exit 2 のはずが {code}")

    # ページング: result_info に従って 2 ページ目を取りに行く（should_fetch_next_page の再利用）
    opener_paged = _RecordingOpener([
        _ok_page(
            [{"date": f"{month}-01", "billable_usd": 1.0}],
            result_info={"page": 1, "per_page": 1, "count": 1, "total_count": 2},
        ),
        _ok_page(
            [{"date": f"{month}-02", "billable_usd": 1.0}],
            result_info={"page": 2, "per_page": 1, "count": 1, "total_count": 2},
        ),
    ])
    code, _ = _run_main(["--threshold-usd", "1000"], opener_paged)
    if len(opener_paged.calls) != 2:
        failures.append(f"ページングされていない（呼び出し {len(opener_paged.calls)} 回）")
    elif "page=2" not in opener_paged.calls[1]["url"]:
        failures.append(f"2 ページ目の URL が想定外: {opener_paged.calls[1]['url']}")

    return failures


def _self_test_gate_daily() -> list[str]:
    """`--gate-daily` が JST 当日 1 回に収束し、stamp が **成功後** に行われることを確認する。"""
    import tempfile

    failures: list[str] = []
    month = current_month_jst()
    with tempfile.TemporaryDirectory() as tmp:
        with _env(CLAUDE_PROJECT_DIR=tmp):
            # 失敗日は stamp しない（同日中に再試行できる）
            opener_fail = _RecordingOpener([_ok_page([])])
            code, _ = _run_main(["--gate-daily", "--json"], opener_fail)
            if code != 2:
                failures.append(f"判定不能なのに exit {code}")
            if marker_path().exists():
                failures.append("判定不能の日にマーカーを stamp している（再試行できなくなる）")

            # 成功したら stamp する
            opener_ok = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.1}])])
            code, _ = _run_main(["--gate-daily"], opener_ok)
            if code != 0 or not marker_path().exists():
                failures.append(f"成功後に stamp されていない: exit={code}")
            if not already_ran_today():
                failures.append("stamp 直後に already_ran_today() が False")

            # 2 回目は API を叩かずスキップ
            opener_second = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
            code, _ = _run_main(["--gate-daily"], opener_second)
            if code != 0 or opener_second.calls:
                failures.append(f"同日 2 回目がスキップされていない: exit={code} calls={len(opener_second.calls)}")

            # --dry-run は stamp しない
            marker_path().unlink()
            opener_dry = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.1}])])
            _run_main(["--gate-daily", "--dry-run"], opener_dry)
            if marker_path().exists():
                failures.append("--dry-run で副作用（stamp）が起きている")
    return failures


def _self_test_alert_line() -> list[str]:
    """超過時の 1 行が A-6 判定に必要な語（課金・上限）を含むことを固定する。

    実測（2026-09-05 JST）: 本文面を `python3 tools/triage_notification.py classify` に渡すと
    `action_class=A` / `boundary=A-6` / `mention=true` になることを確認済み。
    """
    failures: list[str] = []
    line = alert_line({
        "month": "2026-09", "billable_usd": 12.5, "threshold_usd": 10.0,
        "exceeded": True, "latest_day_usd": 6.0, "prev_day_usd": 1.0,
        "surge_ratio": 6.0, "surge_detected": True,
    })
    for word in ("課金", "上限", "A-6"):
        if word not in line:
            failures.append(f"超過通知文に `{word}` が含まれていない: {line!r}")
    if "12.50" not in line or "10.00" not in line:
        failures.append(f"金額が文面に入っていない: {line!r}")

    zero_prev = alert_line({
        "month": "2026-09", "billable_usd": 1.0, "threshold_usd": 10.0,
        "exceeded": False, "latest_day_usd": 5.0, "prev_day_usd": 0.0,
        "surge_ratio": None, "surge_detected": True,
    })
    if "課金" not in zero_prev:
        failures.append("前日 0 円ケースの文面が A-6 判定語を欠いている")
    return failures


def run_self_test() -> int:
    groups = [
        ("① 閾値超過の判定", _self_test_threshold),
        ("② 前日比の急増（型ゆれ・ゼロ除算・月境界）", _self_test_surge),
        ("①②③ の干渉検証（#725）", _self_test_interference),
        ("応答パース（必須欠落・0 件は fail-closed）", _self_test_extract_records),
        ("権限不足の判別（A-6 の切り分け）", _self_test_auth_detection),
        ("main() を通した終了コード経路 + fake の URL 検証", _self_test_main_paths),
        ("--gate-daily の日次収束と stamp のタイミング", _self_test_gate_daily),
        ("超過通知 1 行の A-6 判定語", _self_test_alert_line),
    ]
    failed_groups = 0
    total = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed_groups += 1
            total += len(failures)
            for failure in failures:
                print(f"FAIL[{name}]: {failure}")
    if total:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed_groups} グループ失敗（{total} 件の不一致）")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
