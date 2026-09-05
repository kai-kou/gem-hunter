#!/usr/bin/env python3
"""check_cloudflare_cost.py — Cloudflare の課金額を日次でポーリングし、撤退ライン超過と急増を検知する

【背景（Issue #247 / `D-19`）】
`D-19`（2026-08-18・飼い主決定）は Workers Paid への切替とセットで **「撤退ラインを月額 $10 とし、
Billable Usage API の監視閾値に用いる」** と定めたが、実装が存在しなかった。`*.workers.dev` は
自ゾーンに属さず WAF レート制限を適用できず、アプリ内 `RATE_LIMITER` は Worker 起動後にしか
効かない（＝リクエスト数課金そのものは止められない）ため、**検知が唯一の防御**である。

【2 軸判定（Issue #247 対応方針）】
  ① 月内累計が `--threshold-usd`（既定 10.0 = `D-19` の撤退ライン）を超えたか
  ② 直近日が **その前日** と比べて `--surge-ratio`（既定 3.0）倍以上に急増したか
日次ポーリングは最大 24 時間の検知ラグがあるため、月末に一発で閾値へ到達するパターンを ② で拾う。
①・② は **どちらも独立に評価する**（片方が真でも他方の評価を飛ばさない・#725 の干渉検証対象）。

🔴 **② は「日次集計」で比較する**（PR #937 Layer 1 セルフレビュー CRITICAL-2）。billable-usage は
製品別内訳で **1 日に複数行** が返りうるため、レコード配列の末尾 2 要素を比べると内訳 1 行同士を
比較して真の急増を取りこぼす（fail-open）。`date -> sum(usd)` へ畳んでから直近 2 日を比べ、
**暦日として隣接していなければ倍率を出さない**（欠測日をまたいだ「前日比」を名乗らない）。

【フェイルセーフ（fail-closed）】
現行の `CLOUDFLARE_API_TOKEN` には Billing 系 Read 権限が無く、課金系エンドポイントは
`Authentication error` を返す（Issue #247「前提（ユーザー作業）」）。この状態を
**`auth_missing: true` + exit 2** として明確に区別する。「権限が無いから正常」と `0` に丸めない
（`docs/rules/check-tool-design-rules.md` §1）。以下も **すべて exit 2** に倒す:

  - 取得できたレコードが 0 件（同 §2「対象 0 件は fail-closed」）
  - **対象月のレコードが 0 件**（API が UTC 基準で前月分しか返さない等。$0.00 と読んで緑にしない）
  - **1 件でも解釈できないレコードがあった**（部分的な取りこぼしは過少集計＝fail-open になる）
  - 1 レコード内に **値の異なる金額キーが 2 つ以上**（どちらが USD か決められない）
  - `result_info` が無いまま **満杯ページ**（`CF_PAGE_SIZE` 件）で打ち切られた（見えない残りがある）
  - **想定外の例外**（`main()` を包括的に捕捉する。Python 既定の exit 1 ＝「閾値超過」に化けさせない）

【応答形式について（未検証・重要）】
本アカウントは Billing Read 権限が未付与のため、`GET /accounts/{id}/billable-usage` の実応答を
**実測できていない**（CP-2 の観点で、記憶に基づく決め打ちのパースはしない）。そのため
`extract_records()` は「日付らしいキー」「金額らしいキー」の候補集合から拾う。金額キーは
**USD が明示されたキーだけ**（`amount` / `cost` のような単位不明キーは採用しない・使用量を金額と
読み違えると誤報にも見逃しにもなる）。採用したキー名は `--json` の `amount_keys` に出すので、
権限付与後の実測（フォローアップ Issue #939）で候補を 1 つへ絞ること。

【終了コード】
  0 = 閾値内（正常）。月内累計が閾値以下で、前日比の急増も検知しなかった
      （`--gate-daily` の同日スキップ時は、**その日に記録した判定の終了コードを再現する**）
  1 = 要対応。閾値超過 **または** 前日比急増を検知した（どちらか一方でも真なら 1）
  2 = 判定不能（fail-closed）。上記フェイルセーフの各条件。呼び出し側はこれを「異常なし」にしない

【実行場所（`check-tool-design-rules.md` §5.2 に従い本判定と self-test を別々に決めている）】
  本判定: `.claude/hooks/stop-slack-notify.sh` が `--gate-daily` 付きで起動する（JST 当日 1 回・
    `tools/commit_cost_telemetry.py` と同じ流儀。終了コードは stderr へ出すが Stop はブロックしない）。
    **`tools/run_checks.sh` には本判定を配線しない** — Cloudflare Billing API への実疎通が必要で、
    外部要因で全 PR が赤くなるため（`check_prod_drift.py` と同じ扱い）。
  `--self-test`: `tools/run_checks.sh` に配線済み（ネットワーク非依存なので PR ごとに走らせる）。

【Issue 起票をしない理由】
超過時の記録は stdout の 1 行のみで、GitHub API は叩かない。起票は呼び出し側（親セッション /
Stop hook 配線）の責務で、本スクリプトは読み取り専用の検知器に徹する。出力する 1 行は
`tools/triage_notification.py classify` が **A 区分（A-6: 課金設定）** と判定する文面にしてある
（self-test が `triage_notification` を実際に import して固定する）。

【トークンと最小権限】
`CLOUDFLARE_BILLING_API_TOKEN`（`Account -> Billing -> Read` だけを持つ専用トークン）があれば
それを使い、無ければ従来の `CLOUDFLARE_API_TOKEN`（デプロイ権限を持つ）へフォールバックする。
リダイレクト応答で `Authorization` ヘッダが別ホストへ再送されるのを防ぐため、既定 opener は
**リダイレクトを追跡しない**（`_NoRedirectHandler`）。

日時の扱い: `docs/rules/datetime-rules.md` に従い、表示・記録用（`checked_at`）は JST。
月の決定も「JST の今日」基準（請求月は人間が読む単位のため）。API へ渡す値・内部比較は文字列日付。

使い方:
    python3 tools/check_cloudflare_cost.py
    python3 tools/check_cloudflare_cost.py --json
    python3 tools/check_cloudflare_cost.py --gate-daily        # JST 当日に実行済みなら記録を再現
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
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloudflare_api import CF_PAGE_SIZE, should_fetch_next_page  # noqa: E402
from mask_secrets import mask_text  # noqa: E402

# `_http_json`（HTTPError + 非 JSON ボディのマスク処理を含む）は `trigger_workers_build.py` の
# 実装をそのまま使う。同じ処理を書き写すと `cloudflare_api.py` 新設（#476）で解消したはずの
# 「同一ロジックの独立したコピー」を再生産することになるため、本 PR では複製せず再利用する。
# 公開名化（`cloudflare_api.py` への移設）とリダイレクト非追跡の共通化は Issue #940。
from trigger_workers_build import ApiError, _http_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))

CF_API_BASE = "https://api.cloudflare.com/client/v4"
BILLABLE_USAGE_PATH = "billable-usage"

DEFAULT_THRESHOLD_USD = 10.0  # D-19 の撤退ライン（月額 $10）
DEFAULT_SURGE_RATIO = 3.0

# 急増判定の下限。$0.00 -> $0.02 のような微小な立ち上がりで A-6 通知を撃たないための床。
# これが無いと月初 1 日目や前日 0 円の日に毎回 surge が真になり、通知が信用されなくなる。
SURGE_MIN_ABS_USD = 1.0

MARKER_REL = "content/pipeline-state/.cloudflare_cost_check_date"
# 同日スキップ時に「評価していない」と「評価して正常だった」を同じ 0 に丸めないため、
# 判定結果をマーカーの隣へ保存し、スキップ時はそれを再現する（PR #937 レビュー WARNING）。
RESULT_REL = "content/pipeline-state/.cloudflare_cost_check_result.json"

# 応答形式が未実測（docstring 参照）のため候補で拾う。実測できたら 1 つに絞ること（#939）。
DATE_KEYS = ("date", "day", "usage_date", "period_start", "occurred_at")
# 🔴 単位が USD だと **明示されているキーだけ** を採用する。`amount` / `cost` は使用量・割引後
# クレジット等が入りうるため候補から外した（PR #937 レビュー WARNING: $1,250,000 の誤報と
# $0.00 の見逃しがどちらも起こりうる）。
AMOUNT_KEYS = ("billable_usd", "amount_usd", "cost_usd", "total_usd")
# `result` が配列でなくオブジェクトで返る場合に、日次配列が入りうるキー。
RESULT_LIST_KEYS = ("daily", "usage", "billable_usage", "items", "records")

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
# Cloudflare のアカウント ID は 32 桁の小文字 16 進数。URL へ埋め込む前に形式検証する
# （改行等が混入すると `InvalidURL` の文言に要求パスがそのまま載る）。
_ACCOUNT_ID_RE = re.compile(r"[0-9a-f]{32}")

# Cloudflare が権限不足で返す代表的なシグナル。裸の `permission` / `forbidden` は
# 「see permissions documentation」のような無関係な文言まで拾って A-6 通知を誤爆させるため、
# 固有表現だけに絞る（PR #937 レビュー WARNING・実測済みの誤爆ケース）。
_AUTH_ERROR_RE = re.compile(
    r"authentication\s+error|not\s+authorized|unauthorized|invalid\s+api\s+token|"
    r"permission\s+denied|insufficient\s+permissions?",
    re.IGNORECASE,
)
# コード一致は **HTTP 401/403 との AND** でのみ採用する（`1000` のような汎用値の単独一致を避ける）。
_AUTH_ERROR_CODES = {1000, 9106, 9109, 10000}
_AUTH_HTTP_STATUSES = (401, 403)


class AuthMissingError(ApiError):
    """Billing Read 権限の欠落（`auth_missing: true` + exit 2 として区別する・Issue #247）。"""


# ──────────────────────────────────────────────
# 日時（表示・記録は JST）
# ──────────────────────────────────────────────


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械比較には使わない（datetime-rules.md）。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def current_month_jst(now: datetime | None = None) -> str:
    """判定対象の請求月（JST 基準の `YYYY-MM`）。

    `now` は self-test 用の注入口（UTC 基準へ変異させたときに決定論的に落とすため・PR #937 レビュー）。
    UTC 基準にすると **JST の月替わり直後 9 時間**（00:00-09:00 JST）だけ前月を指し、当月レコードが
    全て落ちて `billable_usd = 0.00` になる（毎月 1 回、閾値監視の軸 ① が 9 時間まるごと無効になる）。
    """
    moment = now if now is not None else datetime.now(JST)
    return moment.astimezone(JST).strftime("%Y-%m")


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


# ──────────────────────────────────────────────
# 日次ゲート（commit_cost_telemetry.py と同じ流儀）
# ──────────────────────────────────────────────


def project_dir() -> Path:
    # フォールバックは `tools/commit_cost_telemetry.py` の同名関数と **同じ** `os.getcwd()` にする
    # （片方だけ `REPO_ROOT` だと 2 つのマーカーが別ディレクトリに書かれる・PR #937 レビュー）。
    # 共通モジュールへの 1 本化は Issue #940。
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def marker_path() -> Path:
    return project_dir() / MARKER_REL


def result_path() -> Path:
    return project_dir() / RESULT_REL


def already_ran_today() -> bool:
    try:
        return marker_path().read_text(encoding="utf-8").strip() == today_jst()
    except OSError:
        return False


def load_cached_result() -> tuple[dict[str, Any], int] | None:
    """当日 stamp 済みなら、その日に記録した `(payload, exit_code)` を返す。

    記録が読めない・日付がずれている場合は `None` を返し、**スキップせず実判定へ進む**
    （「評価していない」を 0 に丸めないため）。
    """
    if not already_ran_today():
        return None
    try:
        stored = json.loads(result_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(stored, dict) or stored.get("date") != today_jst():
        return None
    payload = stored.get("payload")
    code = stored.get("exit_code")
    if not isinstance(payload, dict) or not isinstance(code, int) or code not in (0, 1, 2):
        return None
    return payload, code


def stamp_today(payload: dict[str, Any], exit_code: int) -> None:
    """マーカーは **判定できた後** に打つ（失敗日は同日中に再試行できる・#243 と同じ設計）。

    🔴 **超過（exit 1）だった日は stamp しない**（当日中に再通知できなくなるため・PR #937 レビュー）。
    """
    if exit_code != 0:
        return
    today = today_jst()
    marker = marker_path()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        result_path().write_text(
            json.dumps({"date": today, "exit_code": exit_code, "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
        marker.write_text(today + "\n", encoding="utf-8")
    except OSError:
        pass


# ──────────────────────────────────────────────
# 判定ロジック（純関数・--self-test の対象）
# ──────────────────────────────────────────────


def is_auth_error(payload: dict[str, Any], *, http_status: int | None = None) -> bool:
    """Cloudflare の `success: false` 応答が「権限不足」を意味するか判定する。

    権限不足を単なる API 失敗と混ぜると、ユーザーだけが解決できる A-6（トークンへ Billing Read を
    付与する）が埋もれる。逆に何でも権限不足と読むと A-6 通知が誤爆するため、
    ① 固有表現の文言一致、② `errors[].code` の一致 **かつ HTTP 401/403** の 2 経路だけを認める。
    """
    errors = payload.get("errors")
    if not isinstance(errors, list):
        errors = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        message = error.get("message")
        if isinstance(message, str) and _AUTH_ERROR_RE.search(message):
            return True
        code = error.get("code")
        if (
            isinstance(code, int)
            and not isinstance(code, bool)
            and code in _AUTH_ERROR_CODES
            and http_status in _AUTH_HTTP_STATUSES
        ):
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


def coerce_usd(value: Any) -> float | None:
    """金額を float へ正規化する。解釈できない値は `None`（＝そのレコードを捨てずに fail-closed へ）。

    弾くもの: bool（`float(True)` が $1.00 に化ける）・非数値型・数値化できない文字列・
    **非有限値**（`NaN` / `Infinity`。`json.loads` は既定でこれらのリテラルを受理する)・**負値**
    （`nan > threshold` は常に False になり、負値は累計を押し下げてどちらも exit 0 へ倒れる）。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        usd = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(usd) or usd < 0:
        return None
    return usd


def pick_amount(record: dict[str, Any]) -> tuple[str | None, float | None, bool]:
    """金額キーを 1 つ選ぶ。Returns `(key, usd, ambiguous)`。

    1 レコード内に **値の異なる候補キーが 2 つ以上** あればどちらが USD か決められないため
    `ambiguous=True` を返す（→ 判定不能・exit 2）。値が一致していれば先頭候補を採用する。
    """
    found = [(key, record[key]) for key in AMOUNT_KEYS if key in record and record[key] is not None]
    if not found:
        return None, None, False
    coerced = [coerce_usd(raw) for _, raw in found]
    distinct: list[float | None] = []
    for value in coerced:
        if value not in distinct:
            distinct.append(value)
    if len(distinct) > 1:
        return found[0][0], None, True
    return found[0][0], coerced[0], False


def extract_records(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    """生レコードから `{"date": "YYYY-MM-DD", "usd": float}` の列を作る（純関数）。

    Returns `(records, error_reason, stats)`。

    🔴 **1 件でも解釈できないレコードがあれば error を返す**（PR #937 レビュー CRITICAL）。
    「1 件でも解釈できれば成功」だと、一部の行だけ別キー・`null`・`NaN`・負値で返るだけで
    累計が撤退ライン以下に見え続ける（過少集計＝fail-open）。
    """
    records: list[dict[str, Any]] = []
    amount_keys: set[str] = set()
    dropped = 0
    ambiguous = 0

    for item in items:
        raw_date = _pick(item, DATE_KEYS)
        if not isinstance(raw_date, str):
            dropped += 1
            continue
        matched = _DATE_RE.match(raw_date.strip())
        if not matched:
            dropped += 1
            continue
        key, usd, is_ambiguous = pick_amount(item)
        if is_ambiguous:
            ambiguous += 1
            continue
        if key is None or usd is None:
            dropped += 1
            continue
        amount_keys.add(key)
        records.append({"date": "-".join(matched.groups()), "usd": usd})

    stats = {
        "dropped_records": dropped,
        "ambiguous_records": ambiguous,
        "amount_keys": sorted(amount_keys),
    }

    if ambiguous:
        return [], (
            f"金額キーが曖昧なレコードが {ambiguous} 件あります"
            f"（1 レコード内に値の異なる候補キーが 2 つ以上。候補: {', '.join(AMOUNT_KEYS)}）。"
            "どちらが USD か決められないため判定できません"
        ), stats
    if dropped:
        return [], (
            f"billable-usage の応答に解釈できないレコードが {dropped} 件ありました"
            f"（解釈できたのは {len(records)} 件）。過少集計のまま「閾値内」と報告しないため"
            "判定不能として扱います（応答形式・金額キーを確認してください）"
        ), stats
    if not records:
        return [], (
            "billable-usage の応答から日次レコードを 1 件も解釈できませんでした"
            "（応答形式の変更、または対象期間にデータが無い可能性があります。"
            "対象の選択が意図どおりか確認してください）"
        ), stats

    records.sort(key=lambda r: r["date"])
    return records, None, stats


def aggregate_daily(records: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """`date -> sum(usd)` へ畳んで日付昇順で返す（純関数）。

    billable-usage は 1 日に複数行（製品別内訳）を返しうる。月内累計は内訳を合算する前提なので、
    前日比も **同じ粒度** で比較しないと 2 軸が別々のデータを見ることになる（内部矛盾・fail-open）。
    """
    daily: dict[str, float] = {}
    for record in records:
        daily[record["date"]] = daily.get(record["date"], 0.0) + record["usd"]
    return [(day, round(daily[day], 6)) for day in sorted(daily)]


def _is_previous_day(prev_day: str, latest_day: str) -> bool:
    """`prev_day` が `latest_day` の暦上の前日か（欠測日をまたいだ比較を「前日比」と呼ばないため）。"""
    try:
        prev = date_cls.fromisoformat(prev_day)
        latest = date_cls.fromisoformat(latest_day)
    except ValueError:
        return False
    return latest - prev == timedelta(days=1)


def evaluate(
    records: list[dict[str, Any]],
    month: str,
    threshold_usd: float,
    surge_ratio: float,
) -> dict[str, Any] | None:
    """2 軸判定（純関数）。①閾値超過 と ②急増 は **互いに独立** に評価する。

    🔴 早期 return を置かない（#725 の干渉）。急増が算出不能でも閾値超過の評価は必ず行い、
    閾値内でも急増の評価は必ず行う。

    🔴 **対象月のレコードが 0 件なら `None`（判定不能）を返す**（PR #937 レビュー CRITICAL）。
    `sum([]) = 0.0` を「月内累計 $0.00 で閾値内」と報告すると、当月課金を一度も観測していないのに
    監視が緑になる（API が UTC 基準で前月分しか返さない等で起こりうる）。
    """
    monthly = [r for r in records if r["date"].startswith(month + "-")]
    if not monthly:
        return None

    # ① 月内累計
    billable_usd = round(sum(r["usd"] for r in monthly), 6)
    exceeded = billable_usd > threshold_usd

    # ② 前日比。月境界をまたぐ比較を成立させるため、**月フィルタ前の全レコード** を日次集計する
    #    （月初 1 日目に「前日が無い」として毎月 1 回検知不能になるのを避ける）。
    daily = aggregate_daily(records)
    latest_date, latest_day_usd = daily[-1] if daily else (None, None)
    prev_date, prev_day_usd = daily[-2] if len(daily) >= 2 else (None, None)

    ratio: float | None = None
    surge_detected = False
    adjacent = (
        latest_date is not None
        and prev_date is not None
        and _is_previous_day(prev_date, latest_date)
    )
    if adjacent and latest_day_usd is not None and prev_day_usd is not None:
        if prev_day_usd > 0:
            ratio = round(latest_day_usd / prev_day_usd, 6)
            surge_detected = (
                latest_day_usd >= SURGE_MIN_ABS_USD and latest_day_usd >= prev_day_usd * surge_ratio
            )
        elif prev_day_usd == 0:
            # 前日 0 円は倍率を算出できない（ratio は null のまま）が、急増そのものは起こりうる。
            # 微小な立ち上がりでの誤爆を避けるため SURGE_MIN_ABS_USD の床を併用する。
            surge_detected = latest_day_usd >= SURGE_MIN_ABS_USD
        else:
            # 前日が負（クレジット・返金調整）。倍率も「$0 からの立ち上がり」も事実に反するので
            # 急増判定そのものを行わない。
            surge_detected = False

    return {
        "month": month,
        "billable_usd": billable_usd,
        "threshold_usd": threshold_usd,
        "exceeded": exceeded,
        "latest_date": latest_date,
        "latest_day_usd": latest_day_usd,
        "prev_date": prev_date,
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
        prev = result.get("prev_day_usd")
        latest = result.get("latest_day_usd")
        if isinstance(ratio, (int, float)):
            ratio_text = f" {ratio:.2f} 倍"
        elif prev == 0:
            ratio_text = "（前日 $0.00 からの立ち上がり）"
        else:
            ratio_text = "（前日比は算出できません）"
        prev_text = f"${prev:.2f}" if isinstance(prev, (int, float)) else "（前日データなし）"
        latest_text = f"${latest:.2f}" if isinstance(latest, (int, float)) else "（データなし）"
        reasons.append(f"直近日 {latest_text} が前日 {prev_text} 比で{ratio_text}に急増")
    return (
        f"⚠️ Cloudflare の課金額が要対応水準です（{result['month']}）: "
        + " / ".join(reasons)
        + "。Cloudflare ダッシュボードの課金設定で請求上限とプランを確認してください"
        "（A-6: 課金設定はアカウント権限が物理的に必要）。未対応だと請求額が増え続けます。"
    )


# ──────────────────────────────────────────────
# 取得系（実 I/O。opener 差し替えで self-test から検証できる）
# ──────────────────────────────────────────────


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """リダイレクトを追跡しないハンドラ。

    CPython の `HTTPRedirectHandler.redirect_request` は `content-length` / `content-type` 以外の
    全ヘッダを引き継ぎ、**同一ホスト検査を行わない**。つまり 302 を追跡すると
    `Authorization: Bearer <token>` がリダイレクト先ホストへ再送される（PR #937 レビュー WARNING）。
    本ツールのトークンには Billing Read を足す前提なので、追跡せずエラーにする。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102, ANN001, ANN201
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"リダイレクト（{code}）は追跡しません（Authorization ヘッダの再送を防ぐため）",
            headers,
            fp,
        )


_REDIRECT_SAFE_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def default_opener(request: Any, timeout: int = 30) -> Any:
    """既定 opener（リダイレクト非追跡）。`urllib.request.urlopen` を直接使わない。"""
    return _REDIRECT_SAFE_OPENER.open(request, timeout=timeout)


class _StatusCapturingOpener:
    """`_http_json` が握り潰す HTTP ステータスを記録するラッパ。

    `_http_json` は 4xx でも JSON ボディを返せた場合は dict を返すためステータスが失われる。
    「コード一致 AND HTTP 401/403」の判定と、「非 JSON ボディの 401/403 を `auth_missing` へ昇格」
    のどちらにもステータスが要るので、ここで捕まえる。
    """

    def __init__(self, inner: Callable[..., Any]) -> None:
        self._inner = inner
        self.last_status: int | None = None

    def __call__(self, request: Any, timeout: int = 30) -> Any:
        try:
            response = self._inner(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            self.last_status = error.code
            raise
        self.last_status = getattr(response, "status", None)
        return response


def fetch_billable_usage(
    account_id: str,
    token: str,
    *,
    opener: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """`GET /accounts/{id}/billable-usage` を全ページ取得する。

    ページングの継続判定は `cloudflare_api.should_fetch_next_page()` を再利用する
    （同じロジックを再実装しない・#476）。ただし同関数は `result_info.total_count` が無い応答で
    **無条件に打ち切る** ため（`workers/scripts` で実測済み）、本ツールでは
    「`result_info` 無し **かつ** 満杯ページ」を **打ち切りの見逃し** として `ApiError` に倒す。
    """
    capturing = _StatusCapturingOpener(opener if opener is not None else default_opener)
    page = 1
    items: list[dict[str, Any]] = []
    quoted_account = urllib.parse.quote(account_id, safe="")
    while True:
        url = (
            f"{CF_API_BASE}/accounts/{quoted_account}/{BILLABLE_USAGE_PATH}"
            f"?per_page={CF_PAGE_SIZE}&page={page}"
        )
        try:
            payload = _http_json(url, {"Authorization": f"Bearer {token}"}, opener=capturing)
        except ApiError as error:
            # 非 JSON ボディの 401/403（エッジが HTML を返す等）も権限不足として扱う。
            # ここで昇格させないと `auth_missing: false` に落ち、A-6 の切り分けができない。
            if capturing.last_status in _AUTH_HTTP_STATUSES:
                raise AuthMissingError(str(error)) from error
            raise
        if not isinstance(payload, dict):
            raise ApiError("billable-usage の応答形式が想定外です（オブジェクトでない）")
        if not payload.get("success"):
            message = mask_text(f"billable-usage の取得に失敗しました: {payload.get('errors')}")
            if is_auth_error(payload, http_status=capturing.last_status):
                raise AuthMissingError(message)
            raise ApiError(message)
        page_items = normalize_result(payload.get("result"))
        if page_items is None:
            raise ApiError("billable-usage の応答に日次レコードの配列が含まれていません")
        items.extend(page_items)

        result_info = payload.get("result_info")
        if not isinstance(result_info, dict):
            result_info = {}
        if result_info.get("total_count") is None and len(page_items) >= CF_PAGE_SIZE:
            raise ApiError(
                f"billable-usage の応答に result_info がなく、page={page} が満杯"
                f"（{len(page_items)} 件 = per_page 上限）でした。取得漏れがあるかを判定できないため"
                "判定不能として扱います（過少集計のまま「閾値内」と報告しない）"
            )
        if not should_fetch_next_page(result_info, len(items), len(page_items)):
            break
        page += 1
    return items


# ──────────────────────────────────────────────
# 出力
# ──────────────────────────────────────────────


def empty_payload() -> dict[str, Any]:
    """`--json` の出力キー集合（判定不能時も同じキーを過不足なく出す）。"""
    return {
        "month": None,
        "billable_usd": None,
        "threshold_usd": None,
        "exceeded": None,
        "latest_date": None,
        "latest_day_usd": None,
        "prev_date": None,
        "prev_day_usd": None,
        "surge_ratio": None,
        "surge_detected": None,
        "dropped_records": 0,
        "amount_keys": [],
        "skipped": False,
        "checked_at": now_jst_str(),
        "error": None,
        "auth_missing": False,
    }


def build_payload(
    result: dict[str, Any],
    *,
    dropped_records: int = 0,
    amount_keys: list[str] | None = None,
) -> dict[str, Any]:
    payload = empty_payload()
    payload.update(result)
    payload["dropped_records"] = dropped_records
    payload["amount_keys"] = list(amount_keys or [])
    payload["error"] = None
    payload["auth_missing"] = False
    return payload


def emit_error(
    message: str,
    as_json: bool,
    *,
    auth_missing: bool = False,
    dropped_records: int = 0,
    amount_keys: list[str] | None = None,
) -> None:
    message = mask_text(message) or message
    if as_json:
        payload = empty_payload()
        payload["error"] = message
        payload["auth_missing"] = auth_missing
        payload["dropped_records"] = dropped_records
        payload["amount_keys"] = list(amount_keys or [])
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"ERROR: 判定不能: {message}", file=sys.stderr)


def human_line(payload: dict[str, Any]) -> str:
    if payload.get("exceeded") or payload.get("surge_detected"):
        return alert_line(payload)
    return (
        f"閾値内: {payload['month']} の月内累計 ${payload['billable_usd']:.2f} "
        f"（撤退ライン ${payload['threshold_usd']:.2f}）。前日比の急増も検知していません。"
    )


def emit_payload(payload: dict[str, Any], as_json: bool, *, dry_run: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    line = human_line(payload)
    prefixes = []
    if dry_run:
        prefixes.append("[dry-run]")
    if payload.get("skipped"):
        prefixes.append("[本日実行済み・記録した判定を再掲]")
    print(" ".join(prefixes + [line]) if prefixes else line)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def resolve_token() -> str:
    """最小権限の専用トークンを優先する（無ければ従来のデプロイ用トークンへフォールバック）。"""
    billing = os.environ.get("CLOUDFLARE_BILLING_API_TOKEN", "").strip()
    if billing:
        return billing
    return os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()


def run_check(args: argparse.Namespace, opener: Callable[..., Any]) -> int:
    """実 I/O を伴う本判定（例外は `main()` が包括的に捕捉して exit 2 へ倒す）。"""
    if args.gate_daily:
        cached = load_cached_result()
        if cached is not None:
            payload, code = cached
            payload = dict(payload)
            payload["skipped"] = True
            emit_payload(payload, args.json, dry_run=args.dry_run)
            return code

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = resolve_token()
    if not account_id or not token:
        emit_error(
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_BILLING_API_TOKEN（無ければ CLOUDFLARE_API_TOKEN）が"
            "セッション環境にありません",
            args.json,
            auth_missing=True,
        )
        return 2
    if not _ACCOUNT_ID_RE.fullmatch(account_id):
        emit_error(
            "CLOUDFLARE_ACCOUNT_ID の形式が想定外です（32 桁の小文字 16 進数ではありません）",
            args.json,
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

    records, rerr, stats = extract_records(items)
    if rerr is not None:
        emit_error(
            rerr,
            args.json,
            dropped_records=stats["dropped_records"],
            amount_keys=stats["amount_keys"],
        )
        return 2

    month = current_month_jst()
    result = evaluate(records, month, args.threshold_usd, args.surge_ratio)
    if result is None:
        emit_error(
            f"対象月 {month}（JST 基準）のレコードが 1 件も見つかりませんでした"
            f"（解釈できたのは {len(records)} 件・別月分のみ）。当月の課金を一度も観測していない状態を"
            "「月内累計 $0.00 で閾値内」と報告しないため判定不能として扱います",
            args.json,
            dropped_records=stats["dropped_records"],
            amount_keys=stats["amount_keys"],
        )
        return 2

    payload = build_payload(
        result,
        dropped_records=stats["dropped_records"],
        amount_keys=stats["amount_keys"],
    )
    emit_payload(payload, args.json, dry_run=args.dry_run)
    code = exit_code_for(result)

    # マーカーは判定できた後にだけ打つ（exit 2 の日は同日中に再試行できる）。
    # 超過（exit 1）の日も stamp しない（`stamp_today()` が守る）。
    if args.gate_daily and not args.dry_run:
        stamp_today(payload, code)

    return code


def main(argv: list[str] | None = None, *, opener: Callable[..., Any] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cloudflare の課金額（Billable Usage）を監視する。"
                     "0=閾値内 / 1=閾値超過または急増 / 2=判定不能（fail-closed）。",
    )
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument("--gate-daily", action="store_true",
                        help="JST 当日に既に実行済みなら記録した判定を再現（Stop hook から毎回呼ぶ用）")
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

    try:
        return run_check(args, opener if opener is not None else default_opener)
    except Exception as error:  # noqa: BLE001 — 想定外の例外を exit 1（＝閾値超過）に化けさせない
        emit_error(
            f"想定外のエラーで判定できませんでした（{type(error).__name__}: {error}）",
            args.json,
        )
        return 2


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────

# 形式検証（32 桁小文字 16 進）を通るダミー。self-test でも実形式を使う。
_TEST_ACCOUNT_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


class _FakeHttpResponse:
    """`urllib.request.urlopen` の戻り値（context manager + `.read()`）を模倣する。"""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.status = 200

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class _RecordingOpener:
    """呼び出し URL・ヘッダ・メソッドを **記録する** fake opener（#710）。

    終了コードだけを差し替える fake は「判定結果を固定値へ潰す変異」を見逃すため、
    ① 意図したエンドポイントを叩いているか ② 使ったトークンはどれか ③ `main()` から実際に
    呼ばれたか、を assert できる形にする。
    """

    def __init__(self, pages: list[Any]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: int = 30) -> _FakeHttpResponse:  # noqa: ARG002
        auth = request.get_header("Authorization") or ""
        self.calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "has_auth_header": any(k.lower() == "authorization" for k in request.headers),
            "auth_token": auth[len("Bearer "):] if auth.startswith("Bearer ") else auth,
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


class _BoomOpener:
    """想定外の例外（`_http_json` が捕捉しない型）を送出する fake opener。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, request: Any, timeout: int = 30) -> Any:  # noqa: ARG002
        self.calls.append(request.full_url)
        raise RuntimeError("想定外の内部エラー")


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


@contextlib.contextmanager
def _patched(name: str, value: Any):
    """モジュールグローバルを差し替える（`main()` が **どの関数を呼んでいるか** を固定するため）。"""
    original = globals()[name]
    globals()[name] = value
    try:
        yield
    finally:
        globals()[name] = original


def _run_main(
    argv: list[str],
    opener: Any,
    *,
    creds: bool = True,
    account_id: str = _TEST_ACCOUNT_ID,
    billing_token: str | None = None,
) -> tuple[int, str]:
    """`main()` を通して終了コードと stdout を得る（内部関数の直呼びで済ませない）。"""
    buffer = io.StringIO()
    env: dict[str, str | None] = (
        {"CLOUDFLARE_ACCOUNT_ID": account_id, "CLOUDFLARE_API_TOKEN": "tok-deploy"}
        if creds
        else {"CLOUDFLARE_ACCOUNT_ID": None, "CLOUDFLARE_API_TOKEN": None}
    )
    env["CLOUDFLARE_BILLING_API_TOKEN"] = billing_token
    with _env(**env), contextlib.redirect_stdout(buffer):
        code = main(argv, opener=opener)
    return code, buffer.getvalue()


def _prev_month_last_day() -> str:
    """「対象月ではない日付」を実行日に依存せず作る（前月末）。"""
    first = datetime.now(JST).date().replace(day=1)
    return (first - timedelta(days=1)).strftime("%Y-%m-%d")


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

    # 🔴 対象月のレコードが 0 件 → 判定不能（$0.00 と読んで緑にしない・PR #937 CRITICAL）
    no_month = evaluate([{"date": "2026-08-31", "usd": 99.0}], "2026-09", 10.0, 3.0)
    if no_month is not None:
        failures.append(f"対象月 0 件は判定不能（None）にする: {no_month}")
    if exit_code_for(no_month) != 2:
        failures.append("対象月 0 件は exit 2（0 に丸めない）")
    return failures


# ── グループ 2: 前日比の急増（② 単体・日次集計・入力バリアント） ──────────────────


def _self_test_surge() -> list[str]:
    failures: list[str] = []

    # int / float 混在（実応答の型ゆれ）
    surge = evaluate(
        [{"date": "2026-09-10", "usd": 1}, {"date": "2026-09-11", "usd": 6.0}],
        "2026-09", 1000.0, 3.0,
    )
    if not surge["surge_detected"]:
        failures.append(f"1 -> 6（6 倍）は急増のはず: {surge}")
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

    # 🔴 同一日の複数行（製品別内訳）は **日次集計してから** 比較する（PR #937 CRITICAL）
    per_product = evaluate(
        [
            {"date": "2026-09-10", "usd": 9.5},
            {"date": "2026-09-10", "usd": 0.5},
            {"date": "2026-09-11", "usd": 30.0},
        ],
        "2026-09", 1000.0, 3.0,
    )
    if per_product["prev_day_usd"] != 10.0:
        failures.append(f"同一日の内訳が合算されていない（前日）: {per_product['prev_day_usd']}")
    if per_product["latest_day_usd"] != 30.0:
        failures.append(f"直近日の値が想定外: {per_product['latest_day_usd']}")
    if not per_product["surge_detected"]:
        failures.append(f"日次集計後 10 -> 30（3 倍）は急増のはず: {per_product}")

    # 内訳行の並び順で「急増を取りこぼす」旧実装（records[-1] / [-2]）を落とす回帰
    same_day_only = evaluate(
        [{"date": "2026-09-11", "usd": 9.5}, {"date": "2026-09-11", "usd": 0.5}],
        "2026-09", 1000.0, 3.0,
    )
    if same_day_only["surge_ratio"] is not None or same_day_only["surge_detected"]:
        failures.append(f"同一日の内訳 2 行だけで前日比を出してはいけない: {same_day_only}")
    if same_day_only["prev_date"] is not None:
        failures.append(f"前日が存在しないのに prev_date が入っている: {same_day_only['prev_date']}")

    # 欠測日をまたぐ比較は「前日比」ではない（倍率を出さない）
    gap = evaluate(
        [{"date": "2026-09-01", "usd": 1.0}, {"date": "2026-09-03", "usd": 30.0}],
        "2026-09", 1000.0, 3.0,
    )
    if gap["surge_ratio"] is not None or gap["surge_detected"]:
        failures.append(f"暦日が隣接しない比較で急増を断定してはいけない: {gap}")
    if gap["prev_date"] != "2026-09-01" or gap["latest_date"] != "2026-09-03":
        failures.append(f"比較対象の日付が記録されていない: {gap}")

    # 前日 0 円（ゼロ除算）: 倍率は算出不能（null）だが、床を超える立ち上がりは急増とみなす
    from_zero = evaluate(
        [{"date": "2026-09-10", "usd": 0.0}, {"date": "2026-09-11", "usd": 5.0}],
        "2026-09", 1000.0, 3.0,
    )
    if from_zero["surge_ratio"] is not None:
        failures.append(f"前日 0 円で surge_ratio が null でない: {from_zero['surge_ratio']}")
    if not from_zero["surge_detected"]:
        failures.append("前日 0 円 -> $5.00 は急増として拾う")

    # 前日が負値（クレジット・返金調整）: 急増判定そのものを行わない（3 分岐の 3 つ目）
    from_negative = evaluate(
        [{"date": "2026-09-10", "usd": -5.0}, {"date": "2026-09-11", "usd": 9.0}],
        "2026-09", 1000.0, 3.0,
    )
    if from_negative["surge_ratio"] is not None or from_negative["surge_detected"]:
        failures.append(f"前日が負値のときは急増判定しない: {from_negative}")

    # 微小な立ち上がりは床（SURGE_MIN_ABS_USD）で抑止する（通知の誤爆防止）
    tiny = evaluate(
        [{"date": "2026-09-10", "usd": 0.0}, {"date": "2026-09-11", "usd": 0.02}],
        "2026-09", 1000.0, 3.0,
    )
    if tiny["surge_detected"]:
        failures.append("$0.02 の立ち上がりは急増として扱わない（床で抑止）")

    # 倍率は満たすが絶対額が床未満（$0.20 -> $0.80 の 4 倍）→ 急増としない
    tiny_ratio = evaluate(
        [{"date": "2026-09-10", "usd": 0.2}, {"date": "2026-09-11", "usd": 0.8}],
        "2026-09", 1000.0, 3.0,
    )
    if tiny_ratio["surge_detected"]:
        failures.append("直近日が $1.00 未満なら倍率を満たしても急増としない（床）")

    # 月境界をまたぐ前日比（月初 1 日目でも判定できる・8/31 -> 9/1 は隣接）
    boundary = evaluate(
        [{"date": "2026-08-31", "usd": 1.0}, {"date": "2026-09-01", "usd": 9.0}],
        "2026-09", 1000.0, 3.0,
    )
    if not boundary["surge_detected"]:
        failures.append(f"月境界をまたぐ 1 -> 9 は急増のはず: {boundary}")
    if boundary["prev_day_usd"] != 1.0:
        failures.append(f"前日が前月のレコードから取れていない: {boundary['prev_day_usd']}")

    # 前日データが無い（レコード 1 件）→ 倍率も検知も出せないが、閾値評価は生きている
    single = evaluate([{"date": "2026-09-01", "usd": 50.0}], "2026-09", 10.0, 3.0)
    if single["surge_ratio"] is not None or single["surge_detected"]:
        failures.append(f"1 件だけで急増を断定してはいけない: {single}")
    if not single["exceeded"]:
        failures.append("前日が無くても閾値超過の評価は行う")

    # aggregate_daily 単体（日次集計そのものの回帰）
    daily = aggregate_daily([
        {"date": "2026-09-02", "usd": 1.0},
        {"date": "2026-09-01", "usd": 2.0},
        {"date": "2026-09-01", "usd": 3.0},
    ])
    if daily != [("2026-09-01", 5.0), ("2026-09-02", 1.0)]:
        failures.append(f"日次集計の結果が想定外: {daily}")
    return failures


# ── グループ 3: 干渉検証（#725・複数の fail-closed が互いを無効化していない） ──────────────────


def _self_test_interference() -> list[str]:
    """①閾値超過 と ②急増、および複数の fail-closed 条件が同じ入力・同じ変数を通る順序で
    互いの前提を壊していないことを示す（両方向を確認する）。"""
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
    if exit_code_for(None) != 2:
        failures.append("判定不能は exit 2（0 に丸めない）")

    # E: 「部分解釈失敗 -> exit 2」が「対象月 0 件 -> exit 2」を隠していない。
    #    全件解釈できる（dropped=0）が対象月に 1 件も無い入力で、**対象月由来のメッセージ** が出る。
    other_month = _prev_month_last_day()
    opener_other = _RecordingOpener([_ok_page([{"date": other_month, "billable_usd": 1.0}])])
    code, out = _run_main(["--json"], opener_other)
    payload = json.loads(out or "{}")
    if code != 2:
        failures.append(f"対象月 0 件は main() 経由でも exit 2 のはずが {code}")
    if payload.get("dropped_records") != 0:
        failures.append(f"解釈できているのに dropped_records が 0 でない: {payload.get('dropped_records')}")
    if "対象月" not in (payload.get("error") or ""):
        failures.append(f"対象月 0 件のメッセージが出ていない（別の fail-closed に吸われている）: {payload.get('error')}")

    # F: 逆向き。解釈失敗が混ざる入力では **解釈失敗のメッセージ** が出る（対象月判定に吸われない）
    month = current_month_jst()
    opener_mixed = _RecordingOpener([_ok_page([
        {"date": f"{month}-01", "billable_usd": 4.0},
        {"date": f"{month}-02", "unknown_key": 900.0},
    ])])
    code, out = _run_main(["--json"], opener_mixed)
    payload = json.loads(out or "{}")
    if code != 2:
        failures.append(f"部分解釈失敗は exit 2 のはずが {code}")
    if payload.get("dropped_records") != 1:
        failures.append(f"dropped_records が 1 でない: {payload.get('dropped_records')}")
    if "解釈できない" not in (payload.get("error") or ""):
        failures.append(f"解釈失敗のメッセージが出ていない: {payload.get('error')}")

    # G: 「負値・非有限値を解釈不能として弾く」が正常系の累計を壊していない
    records, err, stats = extract_records([
        {"date": "2026-09-01", "billable_usd": 4.0},
        {"date": "2026-09-01", "billable_usd": 0.0},
        {"date": "2026-09-02", "billable_usd": 3.0},
    ])
    if err is not None or stats["dropped_records"] != 0:
        failures.append(f"$0.00 を含む正常系を弾いてしまっている: {err} / {stats}")
    result = evaluate(records, "2026-09", 10.0, 3.0)
    if result is None or result["billable_usd"] != 7.0:
        failures.append(f"正常系の累計が壊れている: {result}")

    # H: 日次集計（②のため）が月内累計（①）の粒度を壊していない
    same_day = evaluate(
        [{"date": "2026-09-01", "usd": 2.0}, {"date": "2026-09-01", "usd": 3.0}],
        "2026-09", 10.0, 3.0,
    )
    if same_day["billable_usd"] != 5.0:
        failures.append(f"同一日の内訳が月内累計で合算されていない: {same_day['billable_usd']}")
    if same_day["latest_day_usd"] != 5.0:
        failures.append(f"同一日の内訳が日次集計で合算されていない: {same_day['latest_day_usd']}")
    return failures


# ── グループ 4: 応答パース（必須欠落・0 件・部分失敗・値域） ──────────────────


def _self_test_extract_records() -> list[str]:
    failures: list[str] = []

    records, err, stats = extract_records([
        {"date": "2026-09-02", "billable_usd": "3.5"},
        {"date": "2026-09-01", "billable_usd": 1},
    ])
    if err is not None:
        failures.append(f"正常系でエラーになった: {err}")
    elif [r["date"] for r in records] != ["2026-09-01", "2026-09-02"]:
        failures.append(f"日付昇順にソートされていない: {records}")
    elif records[1]["usd"] != 3.5:
        failures.append(f"文字列金額を float に変換できていない: {records}")
    if stats["amount_keys"] != ["billable_usd"]:
        failures.append(f"採用した金額キーが記録されていない: {stats['amount_keys']}")

    _, err_empty, _ = extract_records([])
    if err_empty is None:
        failures.append("対象 0 件は fail-closed（エラーを返す）")

    _, err_missing, stats_missing = extract_records([{"date": "2026-09-01"}, {"billable_usd": 1.0}])
    if err_missing is None:
        failures.append("必須フィールド欠落のみのレコード群はエラーにする")
    if stats_missing["dropped_records"] != 2:
        failures.append(f"dropped_records の計数が想定外: {stats_missing['dropped_records']}")

    _, err_bad_date, _ = extract_records([{"date": "not-a-date", "billable_usd": 1.0}])
    if err_bad_date is None:
        failures.append("日付として解釈できないレコードのみならエラーにする")

    # 🔴 部分的な解釈失敗（3 件中 1 件だけ金額キー不明）は過少集計になるので fail-closed
    partial, err_partial, stats_partial = extract_records([
        {"date": "2026-09-01", "billable_usd": 4.0},
        {"date": "2026-09-02", "billable_usd": 4.0},
        {"date": "2026-09-03", "unknown_key": 900.0},
    ])
    if err_partial is None:
        failures.append("1 件でも解釈できないレコードがあれば判定不能にする（過少集計の fail-open 防止）")
    if partial:
        failures.append("解釈失敗があるのにレコードを返している（部分結果で判定させない）")
    if stats_partial["dropped_records"] != 1:
        failures.append(f"解釈できなかった件数が 1 でない: {stats_partial['dropped_records']}")

    # 金額の値域・型（bool / null / NaN / Infinity / 負値）は解釈不能として扱う
    for label, item in [
        ("bool", {"date": "2026-09-01", "billable_usd": True}),
        ("NaN", {"date": "2026-09-01", "billable_usd": float("nan")}),
        ("Infinity", {"date": "2026-09-01", "billable_usd": float("inf")}),
        ("負値", {"date": "2026-09-01", "billable_usd": -1000.0}),
        ("数値でない文字列", {"date": "2026-09-01", "billable_usd": "N/A"}),
        ("配列", {"date": "2026-09-01", "billable_usd": [1.0]}),
    ]:
        _, err_value, stats_value = extract_records([item])
        if err_value is None or stats_value["dropped_records"] != 1:
            failures.append(f"金額が {label} のレコードを解釈不能として扱えていない: {stats_value}")

    # `null` は候補キーとして採用されない（キー自体が無いのと同じ扱い）
    _, err_null, stats_null = extract_records([{"date": "2026-09-01", "billable_usd": None}])
    if err_null is None or stats_null["dropped_records"] != 1:
        failures.append(f"金額が null のレコードを解釈不能として扱えていない: {stats_null}")

    # 単位不明キー（amount / cost）は採用しない = 解釈不能（使用量を金額と読み違えない）
    _, err_ambiguous_unit, _ = extract_records([{"date": "2026-09-01", "amount": 1250000}])
    if err_ambiguous_unit is None:
        failures.append("単位不明キー `amount` を金額として採用してしまっている")
    if "amount" in AMOUNT_KEYS or "cost" in AMOUNT_KEYS:
        failures.append("AMOUNT_KEYS に単位不明キーが残っている")

    # 値の異なる候補キーが 2 つ -> 曖昧として判定不能
    _, err_conflict, stats_conflict = extract_records([
        {"date": "2026-09-01", "amount_usd": 1.0, "total_usd": 2.0}
    ])
    if err_conflict is None or "曖昧" not in err_conflict:
        failures.append(f"値の異なる金額キーの併存を曖昧として扱えていない: {err_conflict}")
    if stats_conflict["ambiguous_records"] != 1:
        failures.append(f"ambiguous_records の計数が想定外: {stats_conflict}")

    # 値が一致していれば曖昧ではない（先頭候補を採用する）
    same_value, err_same, stats_same = extract_records([
        {"date": "2026-09-01", "amount_usd": 2.0, "total_usd": 2.0}
    ])
    if err_same is not None or not same_value:
        failures.append(f"値が一致する併存キーを曖昧扱いしている: {err_same}")
    elif stats_same["amount_keys"] != ["amount_usd"]:
        failures.append(f"先頭候補が採用されていない: {stats_same['amount_keys']}")

    if normalize_result({"daily": [{"date": "2026-09-01"}]}) is None:
        failures.append("result がオブジェクトでも日次配列を取り出せるべき")
    if normalize_result("nope") is not None:
        failures.append("result が想定外の型なら None（判定不能へ倒す）")
    return failures


def _self_test_auth_detection() -> list[str]:
    failures: list[str] = []
    if not is_auth_error({"errors": [{"code": 10000, "message": "Authentication error"}]}):
        failures.append("Authentication error を権限不足と判定できていない")
    if not is_auth_error({"errors": [{"code": 1234, "message": "You are not authorized"}]}):
        failures.append("文言ベースの権限不足を検出できていない")
    if not is_auth_error({"errors": [{"code": 1234, "message": "Permission denied for billing"}]}):
        failures.append("`permission denied` を権限不足と判定できていない")

    # 🔴 誤爆の回帰（実測済み）: `see permissions documentation` は権限不足ではない
    routing = {"errors": [{
        "code": 7003,
        "message": "Could not route to /accounts/x/billable-usage; see permissions documentation",
    }]}
    if is_auth_error(routing):
        failures.append("`permissions` を含む無関係な文言を権限不足と誤判定している（A-6 通知の誤爆）")
    if is_auth_error(routing, http_status=403):
        failures.append("403 でもコード非該当・文言非該当なら権限不足にしない")

    # コード一致は HTTP 401/403 との AND（汎用コード 1000 の単独一致で誤爆しない）
    generic = {"errors": [{"code": 1000, "message": "API error"}]}
    if is_auth_error(generic):
        failures.append("汎用コード 1000 の単独一致で権限不足と誤判定している")
    if not is_auth_error(generic, http_status=403):
        failures.append("コード一致 + HTTP 403 は権限不足と判定する")
    if is_auth_error(generic, http_status=500):
        failures.append("HTTP 500 でコード一致だけなら権限不足にしない")

    if is_auth_error({"errors": "broken"}):
        failures.append("errors が想定外の型でも例外にせず False を返すべき")
    return failures


# ── グループ 5: main() を通した終了コード経路 + fake の URL / トークン検証 ──────────────────


def _self_test_main_paths() -> list[str]:
    failures: list[str] = []
    month = current_month_jst()

    # 正常系（閾値内 -> exit 0）。fake は URL を記録し、main() から実際に呼ばれたことを assert する。
    opener_ok = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.5}])])
    code, out = _run_main(["--json"], opener_ok)
    if code != 0:
        failures.append(f"閾値内なのに main() が exit {code}")
    if not opener_ok.calls:
        failures.append("main() から HTTP opener が一度も呼ばれていない（判定が固定値に潰れている）")
    else:
        url = opener_ok.calls[0]["url"]
        if f"/accounts/{_TEST_ACCOUNT_ID}/{BILLABLE_USAGE_PATH}" not in url:
            failures.append(f"意図したエンドポイントを叩いていない: {url}")
        if "per_page=" not in url or "page=1" not in url:
            failures.append(f"ページングパラメータが付いていない: {url}")
        if opener_ok.calls[0]["method"] != "GET":
            failures.append(f"読み取り専用のはずが {opener_ok.calls[0]['method']}")
        if not opener_ok.calls[0]["has_auth_header"]:
            failures.append("Authorization ヘッダを付けていない")
        if opener_ok.calls[0]["auth_token"] != "tok-deploy":
            failures.append(f"既定トークンが使われていない: {opener_ok.calls[0]['auth_token']}")
    try:
        payload = json.loads(out)
    except ValueError:
        payload = {}
        failures.append(f"--json の出力が JSON でない: {out!r}")
    expected_keys = set(empty_payload())
    if payload and set(payload) != expected_keys:
        failures.append(f"--json のキー集合が契約と不一致: {sorted(set(payload) ^ expected_keys)}")
    if payload.get("checked_at", "").endswith("JST") is False:
        failures.append(f"checked_at が JST 表記でない: {payload.get('checked_at')}")
    # 🔴 引数配線の固定（第 3・第 4 引数の入れ替え変異を落とす）
    if payload.get("threshold_usd") != DEFAULT_THRESHOLD_USD:
        failures.append(
            f"既定の閾値が {DEFAULT_THRESHOLD_USD} として使われていない: {payload.get('threshold_usd')}"
        )
    if payload.get("billable_usd") != 0.5 or payload.get("exceeded") is not False:
        failures.append(f"正常系の --json の値が想定外: {payload}")
    if payload.get("amount_keys") != ["billable_usd"]:
        failures.append(f"採用した金額キーが --json に出ていない: {payload.get('amount_keys')}")
    if payload.get("skipped") is not False or payload.get("dropped_records") != 0:
        failures.append(f"skipped / dropped_records の既定値が想定外: {payload}")

    # 閾値超過 -> exit 1（main() 経由）。値そのものも固定する（payload.update({}) の変異を落とす）
    opener_over = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
    code, out = _run_main(["--json"], opener_over)
    payload = json.loads(out or "{}")
    if code != 1:
        failures.append(f"閾値超過なのに main() が exit {code}")
    if payload.get("exceeded") is not True:
        failures.append(f"超過なのに --json の exceeded が True でない: {payload.get('exceeded')}")
    if payload.get("billable_usd") != 99.0:
        failures.append(f"--json の billable_usd が想定外: {payload.get('billable_usd')}")
    if payload.get("auth_missing") is not False:
        failures.append(f"正常判定なのに auth_missing が立っている: {payload.get('auth_missing')}")
    if payload.get("month") != month:
        failures.append(f"--json の month が JST 当月でない: {payload.get('month')}")

    opener_over_text = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
    code, out = _run_main([], opener_over_text)
    if code != 1 or "課金" not in out:
        failures.append(f"超過時の 1 行に A-6 判定用の文言が無い: exit={code} out={out!r}")

    # 🔴 --surge-ratio の配線（閾値と入れ替わっていれば exceeded/surge の組み合わせが変わる）
    surge_records = [
        {"date": f"{month}-10", "billable_usd": 1.0},
        {"date": f"{month}-11", "billable_usd": 6.0},
    ]
    opener_ratio_low = _RecordingOpener([_ok_page(surge_records)])
    code, out = _run_main(["--json", "--threshold-usd", "1000", "--surge-ratio", "2"], opener_ratio_low)
    payload = json.loads(out or "{}")
    if code != 1:
        failures.append(f"--surge-ratio 2 で 6 倍の跳ねを検知できていない: exit={code}")
    if payload.get("exceeded") is not False or payload.get("surge_detected") is not True:
        failures.append(f"閾値と急増倍率の配線が入れ替わっている疑い: {payload}")
    if payload.get("threshold_usd") != 1000.0:
        failures.append(f"--threshold-usd が反映されていない: {payload.get('threshold_usd')}")

    opener_ratio_high = _RecordingOpener([_ok_page(surge_records)])
    code, out = _run_main(["--json", "--threshold-usd", "1000", "--surge-ratio", "100"], opener_ratio_high)
    payload = json.loads(out or "{}")
    if code != 0:
        failures.append(f"--surge-ratio 100 なら 6 倍の跳ねは急増としない: exit={code}")
    if payload.get("surge_detected") is not False:
        failures.append(f"--surge-ratio 100 で surge_detected が立っている: {payload}")

    # 🔴 判定に使う月は `current_month_jst()` の戻り値であることを固定する
    #    （UTC 基準へのインライン変異は、この差し替えが効かなくなるので必ず落ちる）
    with _patched("current_month_jst", lambda now=None: "2026-03"):
        opener_month = _RecordingOpener([_ok_page([
            {"date": "2026-02-28", "billable_usd": 99.0},
            {"date": "2026-03-01", "billable_usd": 1.0},
        ])])
        code, out = _run_main(["--json"], opener_month)
        payload = json.loads(out or "{}")
    if payload.get("month") != "2026-03":
        failures.append(f"main() が current_month_jst() の戻り値を使っていない: {payload.get('month')}")
    if payload.get("billable_usd") != 1.0:
        failures.append(f"対象月以外が月内累計へ混ざっている: {payload.get('billable_usd')}")
    if code != 0:
        failures.append(f"当月 $1.00 は閾値内のはずが exit {code}")

    # --dry-run でも判定内容は出るが、終了コードは同じ（副作用のみ抑止）
    opener_dry = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
    code, out = _run_main(["--dry-run"], opener_dry)
    if code != 1 or "dry-run" not in out:
        failures.append(f"--dry-run の挙動が想定外: exit={code} out={out!r}")

    # 専用トークン（最小権限）が優先される
    opener_billing = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.1}])])
    _run_main([], opener_billing, billing_token="tok-billing")
    if not opener_billing.calls:
        failures.append("専用トークン経路で API が呼ばれていない")
    elif opener_billing.calls[0]["auth_token"] != "tok-billing":
        failures.append(
            f"CLOUDFLARE_BILLING_API_TOKEN が優先されていない: {opener_billing.calls[0]['auth_token']}"
        )

    # 認証情報の欠落 -> exit 2 + auth_missing
    opener_unused = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 1.0}])])
    code, out = _run_main(["--json"], opener_unused, creds=False)
    if code != 2:
        failures.append(f"認証情報欠落は exit 2 のはずが {code}")
    if opener_unused.calls:
        failures.append("認証情報が無いのに API を叩いている")
    if json.loads(out).get("auth_missing") is not True:
        failures.append(f"認証情報欠落で auth_missing=true になっていない: {out!r}")

    # アカウント ID の形式検証（URL へ埋め込む前に落とす）
    opener_badid = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 1.0}])])
    code, out = _run_main(["--json"], opener_badid, account_id="acct-test")
    if code != 2:
        failures.append(f"不正な account_id は exit 2 のはずが {code}")
    if opener_badid.calls:
        failures.append("不正な account_id なのに API を叩いている")
    opener_newline = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 1.0}])])
    code, _ = _run_main(["--json"], opener_newline, account_id=_TEST_ACCOUNT_ID + "\nX")
    if code != 2 or opener_newline.calls:
        failures.append("改行混入の account_id を弾けていない")

    # Billing 権限不足（success:false + Authentication error）-> exit 2 + auth_missing
    opener_denied = _RecordingOpener([
        {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}], "result": None}
    ])
    code, out = _run_main(["--json"], opener_denied)
    if code != 2:
        failures.append(f"権限不足は exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not True:
        failures.append(f"権限不足で auth_missing=true になっていない: {out!r}")

    # HTTP エラー（非 JSON ボディ・5xx）-> exit 2（auth_missing は立てない）
    opener_http = _RaisingOpener(500, b"upstream exploded")
    code, out = _run_main(["--json"], opener_http)
    if code != 2:
        failures.append(f"HTTP エラーは exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not False:
        failures.append("HTTP エラーを権限不足と混同している")
    if not opener_http.calls:
        failures.append("HTTP エラー経路でも opener は呼ばれるはず")

    # 🔴 非 JSON ボディの 401/403 は auth_missing へ昇格させる（A-6 の切り分けができるように）
    for status in (401, 403):
        opener_html = _RaisingOpener(status, b"<html><body>Forbidden</body></html>")
        code, out = _run_main(["--json"], opener_html)
        if code != 2:
            failures.append(f"HTTP {status}（非 JSON）は exit 2 のはずが {code}")
        if json.loads(out).get("auth_missing") is not True:
            failures.append(f"HTTP {status}（非 JSON）で auth_missing=true になっていない: {out!r}")

    # 403 + JSON ボディだが権限とは無関係なコード -> auth_missing は立てない
    opener_403_route = _RaisingOpener(403, json.dumps({
        "success": False,
        "errors": [{"code": 7003, "message": "Could not route; see permissions documentation"}],
    }).encode("utf-8"))
    code, out = _run_main(["--json"], opener_403_route)
    if code != 2:
        failures.append(f"403 + 無関係エラーは exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not False:
        failures.append("403 でも文言・コードが非該当なら auth_missing は立てない")

    # success:false（権限とは無関係）-> exit 2
    opener_fail = _RecordingOpener([{"success": False, "errors": [{"code": 7003, "message": "no route"}]}])
    code, out = _run_main(["--json"], opener_fail)
    if code != 2:
        failures.append(f"success:false は exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not False:
        failures.append("無関係な API 失敗で auth_missing を立てている")

    # トップレベルが JSON 配列 -> exit 2（AttributeError で exit 1 に化けない）
    opener_array = _RecordingOpener([[{"date": f"{month}-01", "billable_usd": 1.0}]])
    code, out = _run_main(["--json"], opener_array)
    if code != 2:
        failures.append(f"トップレベル配列は exit 2 のはずが {code}")
    if json.loads(out).get("auth_missing") is not False:
        failures.append("応答形式エラーで auth_missing を立てている")

    # 🔴 想定外の例外 -> exit 2（Python 既定の exit 1 = 「閾値超過」に化けさせない）
    opener_boom = _BoomOpener()
    code, out = _run_main(["--json"], opener_boom)
    if code != 2:
        failures.append(f"想定外の例外は exit 2 のはずが {code}")
    if "想定外" not in (json.loads(out or "{}").get("error") or ""):
        failures.append(f"想定外の例外のメッセージが出ていない: {out!r}")
    if not opener_boom.calls:
        failures.append("例外経路でも opener は呼ばれるはず")

    # 日次データ 0 件 -> exit 2（fail-closed。0 に丸めない）
    opener_empty = _RecordingOpener([_ok_page([])])
    code, out = _run_main(["--json"], opener_empty)
    if code != 2:
        failures.append(f"対象 0 件は exit 2 のはずが {code}")
    if not json.loads(out).get("error"):
        failures.append("対象 0 件で error が空")

    # 必須フィールド欠落 -> exit 2
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

    # 🔴 result_info 無し + 満杯ページ -> 打ち切りの見逃しとして exit 2
    full_page = [{"date": f"{month}-01", "billable_usd": 0.01} for _ in range(CF_PAGE_SIZE)]
    opener_truncated = _RecordingOpener([_ok_page(full_page)])
    code, out = _run_main(["--json"], opener_truncated)
    if code != 2:
        failures.append(f"result_info 無し + 満杯ページは exit 2 のはずが {code}")
    if "result_info" not in (json.loads(out or "{}").get("error") or ""):
        failures.append(f"打ち切り見逃しのメッセージが出ていない: {out!r}")

    # 対照: result_info 無しでも満杯でなければ通常判定（過剰な fail-closed になっていない）
    opener_partial_page = _RecordingOpener([_ok_page(full_page[:-1])])
    code, _ = _run_main(["--threshold-usd", "1000"], opener_partial_page)
    if code != 0:
        failures.append(f"result_info 無し + 満杯でないページは通常判定のはずが exit {code}")

    return failures


# ── グループ 6: --gate-daily（日次収束・記録の再現・stamp のタイミング） ──────────────────


def _self_test_gate_daily() -> list[str]:
    """`--gate-daily` が JST 当日 1 回に収束し、stamp が **成功後（かつ閾値内）** に行われること、
    スキップ時に「評価していない」を 0 へ丸めず **記録した判定を再現** することを確認する。"""
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
            if marker_path().exists() or result_path().exists():
                failures.append("判定不能の日に stamp している（再試行できなくなる）")

            # 🔴 超過（exit 1）の日も stamp しない（当日中に再通知できるように）
            opener_over = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
            code, _ = _run_main(["--gate-daily"], opener_over)
            if code != 1:
                failures.append(f"超過なのに exit {code}")
            if marker_path().exists() or result_path().exists():
                failures.append("超過した日に stamp している（当日中に再通知できなくなる）")

            # 成功（閾値内）したら stamp する
            opener_ok = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.1}])])
            code, _ = _run_main(["--gate-daily"], opener_ok)
            if code != 0 or not marker_path().exists():
                failures.append(f"成功後に stamp されていない: exit={code}")
            if not result_path().exists():
                failures.append("判定結果が保存されていない（スキップ時に再現できない）")
            if not already_ran_today():
                failures.append("stamp 直後に already_ran_today() が False")

            # 2 回目は API を叩かずスキップし、記録した判定を再現する（--json は空にしない）
            opener_second = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 99.0}])])
            code, out = _run_main(["--gate-daily", "--json"], opener_second)
            if code != 0 or opener_second.calls:
                failures.append(f"同日 2 回目がスキップされていない: exit={code} calls={len(opener_second.calls)}")
            if not out.strip():
                failures.append("スキップ時に --json が空出力になっている（jq が落ちる）")
            else:
                payload = json.loads(out)
                if payload.get("skipped") is not True:
                    failures.append(f"スキップ時に skipped=true が出ていない: {payload}")
                if payload.get("billable_usd") != 0.1:
                    failures.append(f"記録した判定を再現できていない: {payload}")
                if set(payload) != set(empty_payload()):
                    failures.append("スキップ時の --json のキー集合が契約と不一致")

            # 記録した終了コードが 1 なら、スキップでも 1 を返す（0 に丸めない）
            result_path().write_text(json.dumps({
                "date": today_jst(),
                "exit_code": 1,
                "payload": {**empty_payload(), "month": month, "billable_usd": 42.0,
                            "threshold_usd": 10.0, "exceeded": True, "surge_detected": False},
            }, ensure_ascii=False), encoding="utf-8")
            opener_skip = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.1}])])
            code, out = _run_main(["--gate-daily"], opener_skip)
            if code != 1:
                failures.append(f"記録した exit 1 を再現できていない: exit={code}")
            if opener_skip.calls:
                failures.append("スキップのはずが API を叩いている")
            if "課金" not in out:
                failures.append(f"再現時に超過の 1 行が出ていない: {out!r}")

            # マーカーはあるが記録が壊れている -> スキップせず実判定へ進む（0 に丸めない）
            result_path().unlink()
            opener_recover = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.2}])])
            code, _ = _run_main(["--gate-daily"], opener_recover)
            if not opener_recover.calls:
                failures.append("記録が無いのにスキップしている（評価していないのに 0 を返す）")
            if code != 0:
                failures.append(f"再判定の終了コードが想定外: {code}")

            # --dry-run は stamp しない
            marker_path().unlink(missing_ok=True)
            result_path().unlink(missing_ok=True)
            opener_dry = _RecordingOpener([_ok_page([{"date": f"{month}-01", "billable_usd": 0.1}])])
            _run_main(["--gate-daily", "--dry-run"], opener_dry)
            if marker_path().exists() or result_path().exists():
                failures.append("--dry-run で副作用（stamp）が起きている")
    return failures


# ── グループ 7: 通知 1 行が本当に A-6 と分類されるか（実呼び出し） ──────────────────


def _self_test_alert_line() -> list[str]:
    """超過時の 1 行を `triage_notification.classify_item()` に **実際に通して** A-6 を固定する。

    文字列包含（「課金」を含むか）だけでは、分類器側の語彙が変わったときに黙って
    B 区分（@mention 抑制）へ落ちる。分類器を実呼びして `action_class == "A"` を assert する。
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
    if "前日 $0.00 からの立ち上がり" not in zero_prev:
        failures.append(f"前日 0 円の文面が想定外: {zero_prev!r}")

    # 前日が負値のときは「$0.00 からの立ち上がり」と書かない（事実に反する）
    negative_prev = alert_line({
        "month": "2026-09", "billable_usd": 20.0, "threshold_usd": 10.0,
        "exceeded": True, "latest_day_usd": 5.0, "prev_day_usd": -3.0,
        "surge_ratio": None, "surge_detected": True,
    })
    if "$0.00 からの立ち上がり" in negative_prev:
        failures.append(f"前日が負値なのに $0.00 からの立ち上がりと書いている: {negative_prev!r}")

    try:
        import triage_notification
    except ImportError as error:  # pragma: no cover — tools/ は sys.path に入っている
        failures.append(f"triage_notification を import できない: {error}")
        return failures
    for label, text in (("超過", line), ("前日 0 円の急増", zero_prev)):
        verdict = triage_notification.classify_item(text)
        if verdict.get("action_class") != "A" or verdict.get("boundary") != "A-6":
            failures.append(
                f"{label} の 1 行が A-6 と分類されない: "
                f"class={verdict.get('action_class')} boundary={verdict.get('boundary')}"
            )
        if verdict.get("mention") is not True:
            failures.append(f"{label} の 1 行で @mention が発火しない: {verdict}")
    return failures


# ── グループ 8: JST 月の決定（UTC 変異を決定論的に落とす） ──────────────────


def _self_test_month_jst() -> list[str]:
    failures: list[str] = []
    # UTC 21:00（= JST 翌日 06:00）。UTC 基準の実装なら前月を返す。
    boundary = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
    if current_month_jst(boundary) != "2026-10":
        failures.append(
            f"JST の月替わり直後（UTC {boundary:%Y-%m-%d %H:%M}）に当月を返していない: "
            f"{current_month_jst(boundary)}"
        )
    # 逆向き: JST 月末 23:00（= UTC 翌月 14:00）は JST の当月を返す
    reverse = datetime(2026, 10, 31, 14, 0, tzinfo=timezone.utc)
    if current_month_jst(reverse) != "2026-10":
        failures.append(f"JST 月末に翌月を返している: {current_month_jst(reverse)}")
    # 引数なしの既定は「JST の今」
    if current_month_jst() != datetime.now(JST).strftime("%Y-%m"):
        failures.append("引数なしの current_month_jst() が JST 当月でない")
    if now_jst_str()[-3:] != "JST":
        failures.append(f"checked_at の表記が JST でない: {now_jst_str()}")
    return failures


# ── グループ 9: リダイレクト時のトークン再送防止 ──────────────────


def _self_test_redirect_safety() -> list[str]:
    failures: list[str] = []
    if not any(isinstance(h, _NoRedirectHandler) for h in _REDIRECT_SAFE_OPENER.handlers):
        failures.append("既定 opener にリダイレクト非追跡ハンドラが組み込まれていない")
    handler = _NoRedirectHandler()
    request = urllib.request.Request(
        f"{CF_API_BASE}/accounts/{_TEST_ACCOUNT_ID}/{BILLABLE_USAGE_PATH}",
        headers={"Authorization": "Bearer tok-secret"},
    )
    try:
        handler.redirect_request(
            request, io.BytesIO(b""), 302, "Found", {}, "https://evil.example/steal"
        )
    except urllib.error.HTTPError:
        pass  # 期待どおり: 追跡せずエラーにする
    else:
        failures.append("リダイレクトを追跡している（Authorization ヘッダが別ホストへ再送される）")
    return failures


def run_self_test() -> int:
    groups = [
        ("① 閾値超過の判定（対象月 0 件は判定不能）", _self_test_threshold),
        ("② 前日比の急増（日次集計・欠測日・型ゆれ・値域）", _self_test_surge),
        ("複数の fail-closed の干渉検証（#725）", _self_test_interference),
        ("応答パース（部分失敗・値域・金額キーの曖昧性）", _self_test_extract_records),
        ("権限不足の判別（A-6 の切り分け・誤爆の回帰）", _self_test_auth_detection),
        ("main() を通した終了コード経路 + fake の URL / トークン検証", _self_test_main_paths),
        ("--gate-daily の日次収束・記録の再現・stamp のタイミング", _self_test_gate_daily),
        ("超過通知 1 行の A-6 分類（triage_notification 実呼び出し）", _self_test_alert_line),
        ("請求月の決定が JST 基準であること", _self_test_month_jst),
        ("リダイレクト時のトークン再送防止", _self_test_redirect_safety),
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
