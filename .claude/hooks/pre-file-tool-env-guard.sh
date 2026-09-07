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
  # 🔴 判定関数の直呼びだけでなく、**本番入口**（stdin JSON → jq 抽出 → hook_block → exit code）を
  # 経由して検証する（Issue #1083 経路 3）。判定関数だけを直呼びする self-test は、jq のフィールド名
  # 変異（`file_path` → `filePath`）で TARGETS が空になり while ループが 1 度も走らない退行を
  # 検出できない（判定関数自体は変異の影響を受けないため緑のまま）。
  _egv_fail=0
  _egv_total=0

  # _egv_run <JSON> <期待する終了コード> <説明>
  # 本番入口（このスクリプト自身）へ stdin 経由で JSON を渡し、実際の終了コードを assert する。
  _egv_run() {
    _egv_json="$1" _egv_want="$2" _egv_desc="$3"
    _egv_total=$((_egv_total + 1))
    # `set -e` 環境下でパイプラインの非ゼロ終了がスクリプトごと止まらないよう、
    # 判定は if の条件位置で行う（pipefail により printf 側ではなく本番入口の終了コードが伝播する）。
    if printf '%s' "$_egv_json" | bash "$HOOK_DIR/pre-file-tool-env-guard.sh" >/dev/null 2>/dev/null; then
      _egv_got=0
    else
      _egv_got=$?
    fi
    if [ "$_egv_got" -ne "$_egv_want" ]; then
      echo "[env-guard][self-test] FAIL: ${_egv_desc}（期待 exit ${_egv_want} / 実際 exit ${_egv_got} / JSON: ${_egv_json}）" >&2
      _egv_fail=1
    fi
  }

  # --- file_path フィールド（Read/Write/Edit 経路） ---
  _egv_run '{"tool_name":"Read","tool_input":{"file_path":".env.production"}}' 2 "file_path=.env.production はブロック"
  _egv_run '{"tool_name":"Read","tool_input":{"file_path":".env.example"}}' 0 "file_path=.env.example（ひな形）は通過"

  # --- notebook_path フィールド（NotebookEdit 経路） ---
  _egv_run '{"tool_name":"NotebookEdit","tool_input":{"notebook_path":".env"}}' 2 "notebook_path=.env はブロック"
  _egv_run '{"tool_name":"NotebookEdit","tool_input":{"notebook_path":"analysis.ipynb"}}' 0 "notebook_path=analysis.ipynb は通過"

  # --- path フィールド（Grep/Glob 経路・Issue #1083 経路 2 本体） ---
  _egv_run '{"tool_name":"Grep","tool_input":{"pattern":".","path":".env","output_mode":"content"}}' 2 "Grep(pattern=., path=.env) はブロック"
  _egv_run '{"tool_name":"Glob","tool_input":{"pattern":"**/*","path":".env.local"}}' 2 "Glob(path=.env.local) はブロック"
  _egv_run '{"tool_name":"Grep","tool_input":{"pattern":"TODO","path":"src"}}' 0 "Grep(path=src) は通過"
  _egv_run '{"tool_name":"Grep","tool_input":{"pattern":"secret"}}' 0 "Grep(path 省略) は通過（path 未指定は対象外）"

  # --- 複数フィールド同時（要素間の関係性の負ケース・#896: 個々は妥当でも 1 つでも違反なら全体ブロック） ---
  _egv_run '{"tool_name":"Read","tool_input":{"file_path":"README.md","path":".env"}}' 2 "file_path は無害だが path が .env → ブロック"
  _egv_run '{"tool_name":"Read","tool_input":{"file_path":"README.md","notebook_path":"a.ipynb","path":"src"}}' 0 "全フィールド無害 → 通過"

  # --- jq 不在時の fail-closed（設計基準 §3: 判定不能を合格に丸めない） ---
  # 素の env -i PATH=空 だと dirname/cat 等スクリプトが依存する他コマンドまで消えて
  # 「jq 不在」以外の理由で落ちてしまう（誤検出）。/usr/bin と /bin の全コマンドを
  # jq だけ除いてシンボリックリンクした専用 PATH を作り、「jq だけが無い」状態を再現する。
  _egv_no_jq_dir="$(mktemp -d)"
  for _egv_src_dir in /usr/bin /bin; do
    [ -d "$_egv_src_dir" ] || continue
    for _egv_bin in "$_egv_src_dir"/*; do
      _egv_bin_name="${_egv_bin##*/}"
      [ "$_egv_bin_name" = "jq" ] && continue
      [ -e "$_egv_no_jq_dir/$_egv_bin_name" ] && continue
      ln -s "$_egv_bin" "$_egv_no_jq_dir/$_egv_bin_name" 2>/dev/null || true
    done
  done
  _egv_total=$((_egv_total + 1))
  if printf '%s' '{"tool_name":"Read","tool_input":{"file_path":".env.example"}}' \
    | env -i "PATH=$_egv_no_jq_dir" "$_egv_no_jq_dir/bash" "$HOOK_DIR/pre-file-tool-env-guard.sh" >/dev/null 2>/dev/null; then
    _egv_got=0
  else
    _egv_got=$?
  fi
  rm -rf "$_egv_no_jq_dir" 2>/dev/null || true
  if [ "$_egv_got" -ne 2 ]; then
    echo "[env-guard][self-test] FAIL: jq 不在時は fail-closed（exit 2）のはずが exit ${_egv_got}" >&2
    _egv_fail=1
  fi

  # --- 判定関数（hook_env_guard_verdict）自体の直呼び回帰も引き続き保持 ---
  # （env_allowlist.sh 側の hook_env_guard_self_test が本体を持つため、ここでは二重にしない。
  #   本フック固有の懸念＝本番入口の終了コード経路は上の _egv_run 群が担う）

  if [ "$_egv_fail" -eq 0 ]; then
    echo "[env-guard][self-test] OK（本番入口経由 ${_egv_total} 件）"
    exit 0
  fi
  exit 1
fi

INPUT=$(cat)

# 🔴 fail-closed（設計基準 docs/rules/check-tool-design-rules.md §3）: jq が使えない／
# JSON 解析に失敗する状態を「対象なし（通過）」に丸めない。判定不能を合格にすると、
# 本フックの存在意義（.env 系ファイルの秘密情報保護）そのものが迂回される。
if ! command -v jq >/dev/null 2>&1; then
  hook_block "BLOCK: jq コマンドが見つからないため .env 判定ができません（fail-closed）。
理由: 判定不能を通過扱いにすると .env 保護そのものが迂回されるため、ブロック側に倒しています。
jq を PATH に用意してから再試行してください。
デグレ検証: bash .claude/hooks/pre-file-tool-env-guard.sh --self-test"
fi

# Read / Write / Edit は file_path、NotebookEdit は notebook_path、Grep / Glob は path を持つ。
# 将来のツールで別名が増えても取りこぼさないよう、3 つとも候補にする。
if ! TARGETS=$(printf '%s\n' "$INPUT" \
  | jq -r '[.tool_input.file_path?, .tool_input.notebook_path?, .tool_input.path?]
           | map(select(. != null and . != "")) | .[]' 2>/dev/null); then
  hook_block "BLOCK: PreToolUse 入力の JSON 解析に失敗しました（fail-closed）。
理由: 判定不能を通過扱いにすると .env 保護そのものが迂回されるため、ブロック側に倒しています。
デグレ検証: bash .claude/hooks/pre-file-tool-env-guard.sh --self-test"
fi

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
