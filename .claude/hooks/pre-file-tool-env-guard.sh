#!/bin/bash
set -euo pipefail
# PreToolUse ガード: ファイル系ツール（Read / Write / Edit / NotebookEdit）から
# `.env` 系ファイルへ触れるのをブロックする（Issue #401 / PR #487 のセルフレビュー指摘）。
#
# 🔴 なぜ必要か（射程の穴）:
#   `permissions.deny` の `Read(.env.*)` は Write / Edit にも波及する公式仕様のため、
#   ワイルドカードのままだと **秘密情報を含まないひな形（`.env.example`）すら作成できない**。
#   deny は allow・フック・否定パターンのいずれでも例外化できない（評価順が最優先）ので、
#   ひな形を扱うには deny 側を具体名の列挙へ狭めるしかなかった。
#   その結果 **列挙から漏れた変種名**（`.env.prod` / `.env.ci` / `.env.qa` 等）が
#   ファイル系ツールから素通りになる。既存の `pre-tool-use-router.sh` は matcher が
#   `Bash|mcp__github__create_pull_request` のため **Bash 経由しか塞いでいない**。
#   本フックがファイル系ツール経路の第 2 層としてワイルドカード判定を復元する。
#
# 判定はベース名スコープ（`config/.env.ci` のようなサブディレクトリ配置も捕捉する）。
# `permissions.deny` が cwd アンカーで守れない **cwd 外の絶対パス** も本フックは塞ぐ。
#
# デグレ検証: bash .claude/hooks/pre-file-tool-env-guard.sh --self-test

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"
# shellcheck source=lib/env_allowlist.sh
source "$HOOK_DIR/lib/env_allowlist.sh"

# ひな形・サンプル類（秘密情報を含まない前提のファイル）は許可する。
# 判定の実体は lib/env_allowlist.sh の hook_env_guard_verdict（SSOT・Issue #493）。
# `pre-tool-use-router.sh` の `_sfa_env_access` と同じ関数を source して使う（片方だけ広げない、
# を case 文のコピーではなく共有関数で構造的に保証する）。
_env_guard_verdict() {
  hook_env_guard_verdict "$1"
}

if [ "${1:-}" = "--self-test" ]; then
  _egv_fail=0
  # ブロックされるべきパス
  for p in .env .env.local .env.production .env.prod .env.ci .env.qa \
           /home/user/gem-hunter/.env.staging config/.env.docker ~/.env.secret; do
    if ! _env_guard_verdict "$p"; then
      echo "[env-guard][self-test] FAIL: ブロックされるべきパスが通過した: $p" >&2
      _egv_fail=1
    fi
  done
  # 通過すべきパス
  for p in .env.example .env.sample .env.template .env.dist .env.example.ja \
           README.md src/infrastructure/github/oauth.ts docs/rules/env-vars.md \
           environment.ts .environment; do
    if _env_guard_verdict "$p"; then
      echo "[env-guard][self-test] FAIL: 通過すべきパスがブロックされた: $p" >&2
      _egv_fail=1
    fi
  done
  if [ "$_egv_fail" -eq 0 ]; then
    echo "[env-guard][self-test] OK（ブロック 9 件 / 通過 10 件）"
    exit 0
  fi
  exit 1
fi

INPUT=$(cat)

# Read / Write / Edit は file_path、NotebookEdit は notebook_path を持つ。
# 将来のツールで別名が増えても取りこぼさないよう、両方＋汎用の path を候補にする。
TARGETS=$(printf '%s\n' "$INPUT" \
  | jq -r '[.tool_input.file_path?, .tool_input.notebook_path?, .tool_input.path?]
           | map(select(. != null and . != "")) | .[]' 2>/dev/null || true)

while IFS= read -r _egv_path; do
  [ -n "$_egv_path" ] || continue
  if _env_guard_verdict "$_egv_path"; then
    hook_block "BLOCK: .env 系ファイルへのファイルツール経由のアクセスは禁止されています（対象: $_egv_path）
理由: 実値の秘密情報がコンテキストへ展開されるのを防ぐ第 2 層。permissions.deny は
      ひな形（.env.example）を扱うために具体名の列挙へ狭めており、列挙外の変種名を本フックが塞ぐ。
通過するのは秘密情報を含まないひな形のみ: .env.example / .env.sample / .env.template / .env.dist
デグレ検証: bash .claude/hooks/pre-file-tool-env-guard.sh --self-test"
  fi
done <<EOF
$TARGETS
EOF

exit 0
