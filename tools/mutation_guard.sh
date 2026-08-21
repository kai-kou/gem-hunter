#!/bin/bash
# 変異テストガード: WIP 自動コミットを一時的に抑止するマーカーの操作（Issue #304 / L-131）
#
# 実装をわざと壊す作業（変異テスト・原因切り分けのための一時改変）を始める前に `begin`、
# 終えたら `end` を実行する。マーカーがある間、Stop / PreCompact / PostCompact の
# WIP 自動コミットは作業ツリーを拾わない（`.claude/hooks/lib/wip_guard.sh`）。
#
#   bash tools/mutation_guard.sh begin    # マーカーを置く（既にあれば時刻を更新して延長）
#   bash tools/mutation_guard.sh status   # 有効なら exit 0 / 無効・失効なら exit 1
#   bash tools/mutation_guard.sh end      # マーカーを外す（作業ツリーが汚れていれば警告）
#
# 置き忘れても TTL（既定 2 時間・`WIP_GUARD_TTL_SECONDS` で変更可）で自動失効し、
# L-100 の防御（未コミット作業の保全）が恒久的に無効化されることはない。
set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  echo "[mutation-guard] git リポジトリの中で実行してください" >&2
  exit 1
fi

# shellcheck source=../.claude/hooks/lib/wip_guard.sh
LIB="$REPO_ROOT/.claude/hooks/lib/wip_guard.sh"
if [ ! -f "$LIB" ]; then
  echo "[mutation-guard] ${LIB} が見つかりません" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$LIB"

MARKER="$(wip_guard_marker_path "$REPO_ROOT")" || exit 1
TTL="${WIP_GUARD_TTL_SECONDS:-$WIP_GUARD_TTL_SECONDS_DEFAULT}"

case "${1:-}" in
  begin)
    printf 'created_at=%s\nttl_seconds=%s\nnote=変異テスト等の一時改変中。WIP 自動コミットを抑止する（Issue #304）\n' \
      "$(TZ="${PROJECT_TZ:-Asia/Tokyo}" date '+%Y-%m-%d %H:%M %Z')" "$TTL" >"$MARKER"
    echo "[mutation-guard] マーカーを置きました（${MARKER}・TTL ${TTL} 秒）。終わったら 'bash tools/mutation_guard.sh end' を実行してください"
    ;;
  status)
    if wip_guard_active "$REPO_ROOT" "mutation-guard" 2>/dev/null; then
      echo "[mutation-guard] 有効（WIP 自動コミットは抑止されます）: ${MARKER}"
      exit 0
    fi
    if [ -f "$MARKER" ]; then
      echo "[mutation-guard] マーカーは存在しますが TTL ${TTL} 秒を超過して失効しています: ${MARKER}"
    else
      echo "[mutation-guard] 無効（マーカーなし・WIP 自動コミットは通常どおり動きます）"
    fi
    exit 1
    ;;
  end)
    rm -f "$MARKER"
    echo "[mutation-guard] マーカーを外しました（${MARKER}）"
    if [ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null || true)" ]; then
      echo "[mutation-guard] ⚠️ 作業ツリーに変更が残っています。変異（意図的な破壊）を戻し忘れていないか確認してください:" >&2
      git -C "$REPO_ROOT" status --short >&2
    fi
    ;;
  *)
    echo "usage: bash tools/mutation_guard.sh {begin|status|end}" >&2
    exit 2
    ;;
esac
