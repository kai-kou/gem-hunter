#!/usr/bin/env python3
"""Workers Builds の構成不備を、複数スクリプトが **同じ言い回し** で報告するための共通診断。

【なぜ必要か（Issue #693）】
`check_prod_drift.py` と `trigger_workers_build.py` は、同一の根本原因（Cloudflare の
build trigger が 0 件 = Workers Builds の Git 連携が外れている）に対して、それぞれの視点から
別々のメッセージを出していた。

| スクリプト | 旧メッセージ | 読み手が受ける印象 |
| --- | --- | --- |
| `check_prod_drift.py` | 本番への実デプロイ実績が見つかりません | デプロイ **履歴** が無いように見える |
| `trigger_workers_build.py` | `branch_includes` に 'main' を含む trigger が見つかりません | **branch 設定のミス** に見える |

そのため毎回「API トークンの権限か？」「wrangler の設定か？」と別方向の仮説から切り分けを
やり直し、一次事実（trigger が 0 件）に到達するまで数セッションを要した（#626 / #640 / #672 / #679）。

**文言はこのモジュールにだけ定義する**（2 箇所へ複製しない）。呼び出し側は
`no_triggers_message()` を呼び、`TriggerNotConfiguredError` を送出・捕捉する。

self-test: `python3 tools/workers_build_diagnostics.py --self-test`
"""

from __future__ import annotations

import sys

# 一次事実（build trigger が 0 件）を名指しする語句。両スクリプトの self-test はこの語句の
# 有無で「0 件」と「branch 不一致」を切り分ける。
NO_TRIGGERS_REGISTERED_HINT = "Cloudflare の build trigger が 0 件です"

# 「次に何をすればよいか」の導線（#693 完了条件）。API 経路が存在しないため、復旧は
# ダッシュボード操作（A-6）に限られる。
RECOVERY_HINT = (
    "Workers Builds の GitHub 連携が未接続、または接続が外れています。"
    "復旧にはダッシュボードでの GitHub App 認可が必要で、API 経路は存在しません"
    "（A-6・docs/03_design/infrastructure/cloudflare-infrastructure.md §8.2.3・Issue #626）"
)


class TriggerNotConfiguredError(Exception):
    """build trigger が 1 件も登録されていない（= 本番デプロイ経路が構成されていない）。

    「判定不能」（検査側が壊れている / 一時的な API エラー）とは区別する（#694）。
    """


def no_triggers_message(worker_name: str | None = None, worker_tag: str | None = None) -> str:
    """trigger 0 件のときの共通診断メッセージ（文言の唯一の定義箇所）。"""
    context = []
    if worker_name:
        context.append(f"worker={worker_name}")
    if worker_tag:
        context.append(f"tag={worker_tag}")
    suffix = f"（{', '.join(context)}）" if context else ""
    return f"{NO_TRIGGERS_REGISTERED_HINT}{suffix}。{RECOVERY_HINT}"


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def _self_test_message() -> list[str]:
    failures: list[str] = []

    message = no_triggers_message("gem-hunter", "tag-1")
    if NO_TRIGGERS_REGISTERED_HINT not in message:
        failures.append(f"一次事実の語句が含まれていない: {message}")
    if "worker=gem-hunter" not in message or "tag=tag-1" not in message:
        failures.append(f"worker / tag のコンテキストが欠落している: {message}")
    if "#626" not in message or "GitHub App" not in message:
        failures.append(f"復旧導線（次に何をすればよいか）が含まれていない: {message}")

    bare = no_triggers_message()
    if NO_TRIGGERS_REGISTERED_HINT not in bare or "（" in bare.split("。")[0]:
        failures.append(f"worker / tag 不明時に空の括弧が出ている: {bare}")

    if not issubclass(TriggerNotConfiguredError, Exception):
        failures.append("TriggerNotConfiguredError が例外クラスでない")

    return failures


def run_self_test() -> int:
    failures = _self_test_message()
    for failure in failures:
        print(f"FAIL[共通診断メッセージ]: {failure}")
    if failures:
        print(f"\nセルフテスト: {len(failures)} 件の不一致")
        return 1
    print("セルフテスト: 全て PASS")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())
    print(no_triggers_message())
