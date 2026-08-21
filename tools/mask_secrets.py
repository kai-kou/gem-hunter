#!/usr/bin/env python3
"""
mask_secrets.py — 秘匿情報マスクユーティリティ（P-12）

print / log 出力時に環境変数の値を印字側でマスクする。
Claude Code のコンテキストやターミナルへの秘匿情報流出を防ぐ。

NOTE: GitHub Variables の一覧表示には必ず以下のいずれかを使うこと:
  - python3 tools/setup_github_variables.py --list  （マスク表示）
  - python3 tools/gh_vars.py --json                 （キー一覧のみ・値は *** ）
  ❌ gh variable list を直接実行すると全ての値が平文でターミナルに流れる
"""

import os
import re

# 秘匿性の高い変数名に含まれるキーワードパターン（大文字小文字不問）
_SENSITIVE_PATTERNS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "KEY",
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "PRIVATE",
    "ACCESS",
)

_SENSITIVE_RE = re.compile(
    "|".join(_SENSITIVE_PATTERNS),
    re.IGNORECASE,
)


def is_sensitive_var(name: str) -> bool:
    """変数名が機密パターンに一致するか判定する。"""
    return bool(_SENSITIVE_RE.search(name))


def mask_value(value: str, keep_start: int = 4, keep_end: int = 4) -> str:
    """値をマスク表示する（先頭/末尾を数文字残して中間を **** に置換）。

    Args:
        value: マスク対象の値（None・空文字も安全に処理する）
        keep_start: 先頭に残す文字数
        keep_end: 末尾に残す文字数

    Returns:
        マスクされた文字列。None・空文字・短い値は "****" のみ返す。

    Examples:
        mask_value("xoxb-abc123def456")    -> "xoxb****f456"
        mask_value("short")               -> "****"
        mask_value("")                    -> "****"
        mask_value(None)                  -> "****"
    """
    if value is None:
        return "****"
    value = str(value)
    if not value:
        return "****"
    if len(value) <= keep_start + keep_end:
        return "****"
    return value[:keep_start] + "****" + value[-keep_end:]


def mask_if_sensitive(name: str, value: str) -> str:
    """変数名が機密パターンに一致する場合のみマスクして返す。

    Args:
        name: 環境変数名
        value: 環境変数の値（None・空文字も安全に処理する）

    Returns:
        機密パターン一致 → mask_value(value) の結果
        非一致 → value をそのまま返す
        None / 空文字 → "" を返す
    """
    if not value:
        return ""
    if is_sensitive_var(name):
        return mask_value(value)
    return value


_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)

# 任意テキストへのマスク適用で既定の対象にするセッション環境変数
DEFAULT_SECRET_VARS = ("CLOUDFLARE_API_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def mask_text(text: str, secrets: dict[str, str] | None = None) -> str:
    """任意テキスト（外部コマンドの stdout/stderr 等）から既知の秘匿値を除去する。

    上の `mask_value()` は「値そのもの」を、`mask_if_sensitive()` は「変数名と値の対」を
    扱うのに対し、本関数は **秘匿値がどこに埋まっているか分からないテキスト全体** を対象にする。
    外部コマンドの出力を Issue / PR コメントへ転記する経路（`retire_preview_aliases.py` /
    `check_prod_drift.py`）が共通で使う（PR #235 の `mask_output` をここへ集約した）。

    `secrets` 省略時は `DEFAULT_SECRET_VARS` の実値を対象にする。純粋関数として使いたい場合は
    `secrets={}` を明示的に渡す（環境変数を読まなくなる）。
    """
    if not text:
        return text
    if secrets is None:
        secrets = {name: os.environ.get(name, "") for name in DEFAULT_SECRET_VARS}
    masked = text
    for value in secrets.values():
        if value:
            masked = masked.replace(value, mask_value(value))
    return _BEARER_RE.sub("Bearer ****", masked)
