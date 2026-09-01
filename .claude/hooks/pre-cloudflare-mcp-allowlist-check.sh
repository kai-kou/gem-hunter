#!/bin/bash
set -euo pipefail
# PreToolUse hook: Cloudflare MCP ツールのアローリスト化（Issue #56）
#
# 【背景】
# `.claude/settings.json` の `permissions.allow` / `deny` はツール名の列挙にすぎない。
# Cloudflare MCP サーバーに新しいツールが増えると、`allow` にも `deny` にも載っていない
# ツールは確認プロンプトなしで素通りする（`deny` にワイルドカードを書くと `allow` の
# 個別許可ごと潰れるため、`permissions` だけでは「この N 個以外は全部ブロック」という
# アローリストを表現できない）。
#
# 【対策】
# このフックが Cloudflare MCP ツール呼び出し（`mcp__Cloudflare_Developer_Platform__*`）を
# 一律ゲートし、許可集合に無いツールを exit code 2 でブロックする。
#
# 【許可集合の正本（SSOT）】
# docs/03_design/infrastructure/cloudflare-infrastructure.md §7.4 の表（「読み取り（許可）」行の
# バッククォート区切りツール名）から機械的に読み取る。本スクリプトは正本を複製しない。
# 表を解釈できない場合（ファイル不在・行が見つからない・書式変更等）は **fail-closed**
# （全 Cloudflare MCP ツールをブロック）にする。
#
# 使い方: bash .claude/hooks/pre-cloudflare-mcp-allowlist-check.sh <tool_name>
# self-test: bash .claude/hooks/pre-cloudflare-mcp-allowlist-check.sh --self-test

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"

TOOL_PREFIX="mcp__Cloudflare_Developer_Platform__"

# SSOT ドキュメントのパス（self-test 時は固定パスの代わりにフィクスチャへ差し替え可能にする
# ため環境変数で上書きできるようにする。通常運用では常に既定値を使う）。
CF_MCP_DOC_PATH="${CF_MCP_ALLOWLIST_DOC_PATH:-$REPO_ROOT/docs/03_design/infrastructure/cloudflare-infrastructure.md}"

# ドキュメントの §7.4 表から「読み取り（許可）」行の**ツール名列（第2列）だけ**から
# バッククォート区切りツール名を抽出する。抽出できたら
# "search_cloudflare_documentation workers_list ..." のように空白区切りで返す。
# 抽出できない（ファイル不在・行が見つからない・バッククォートが 1 個も無い等）場合は
# 何も出力せず、呼び出し側が fail-closed 判定する。
#
# 🔴 fail-open 対策（コーディネーター指摘・回帰防止）: 当初は行全体（3列）から
# バッククォート語を拾っており、第1列（区分）・第3列（可否・注記）に将来
# `` `wrangler` `` のような英数字のみのバッククォート語が混入すると、それが
# **許可ツール名として黙って許可集合に加わる**（セキュリティゲートの fail-open）。
# 実際に §7.4 の第3列には既に `` `CP-2` `` が入っており、ハイフンを含むため
# 偶然 `[A-Za-z0-9_]+` に当たらずセーフだっただけで、英数字のみの語が入れば
# 即座に穴になる状態だった。対策として `cut -d'|' -f3` で**第2列のセルのみ**を
# 取り出してから抽出する（Markdown 表の行は先頭が `|` のため、`|` 区切りの
# フィールド番号は 1: 空文字（行頭より前）/ 2: 第1列（区分）/ 3: 第2列（ツール名）/
# 4: 第3列（可否）/ 5: 空文字（行末より後）となり、目的の列は `-f3`）。
_cf_mcp_extract_allowed_short_names() {
  local doc="$1" line col2
  [ -f "$doc" ] || return 0

  # 「読み取り（許可）」を含む表の行を 1 行取る（複数マッチしても最初の 1 行のみ使う。
  # 表は §7.4 に 1 行しか無い前提だが、複数あっても最初の行を正とすることで挙動を決定的にする）
  line=$(grep -m1 -F '読み取り（許可）' "$doc" || true)
  [ -n "$line" ] || return 0

  # `|` 区切りの第3フィールド（= 表の第2列 = ツール名列）だけを取り出す
  col2=$(printf '%s\n' "$line" | cut -d'|' -f3)
  [ -n "$col2" ] || return 0

  # バッククォートで囲まれたトークンを全て抜き出す（例: `search_cloudflare_documentation`）
  # grep -oE で `...` にマッチさせ、sed でバッククォート自体を剥がす
  printf '%s\n' "$col2" \
    | grep -oE '`[A-Za-z0-9_]+`' \
    | sed -E 's/`//g'
}

# ツール名（フルネーム）が許可集合に入っているかを判定する。
# 戻り値（echo）: "allow" / "block:not-in-allowlist" / "block:doc-unparseable"
classify_cloudflare_mcp_tool() {
  local tool_name="$1" doc="$2" short_names short allowed=1

  # Cloudflare MCP 以外は対象外（呼び出し元で既にプレフィックス判定しているはずだが、
  # 単体テスト・誤呼び出しからの防御として二重に確認する）
  case "$tool_name" in
    "${TOOL_PREFIX}"*) ;;
    *) echo "allow"; return ;;
  esac

  short_names=$(_cf_mcp_extract_allowed_short_names "$doc")
  if [ -z "$short_names" ]; then
    echo "block:doc-unparseable"
    return
  fi

  local tool_short="${tool_name#"$TOOL_PREFIX"}"
  while IFS= read -r short; do
    [ -n "$short" ] || continue
    # 完全一致のみ許可する（前方一致・部分一致で誤って通さない。
    # 例: 許可ツール `workers_list` に対し `workers_list_extra` のような
    # 未知ツールを部分一致で誤許可しない）
    if [ "$tool_short" = "$short" ]; then
      allowed=0
      break
    fi
  done <<EOF
$short_names
EOF

  if [ "$allowed" -eq 0 ]; then
    echo "allow"
  else
    echo "block:not-in-allowlist"
  fi
}

# 許可集合（空白区切り）を「`a` / `b` / `c`」形式の人間向け文字列に整形する。
# 空なら「（取得できませんでした）」を返す（本来 block:doc-unparseable 経路で使うことは
# ないが、防御的にメッセージが空になることを避ける）。
_cf_mcp_format_allowed_list() {
  local short_names="$1" short formatted=""
  [ -n "$short_names" ] || { echo "（取得できませんでした）"; return; }
  while IFS= read -r short; do
    [ -n "$short" ] || continue
    if [ -z "$formatted" ]; then
      formatted="\`${short}\`"
    else
      formatted="${formatted} / \`${short}\`"
    fi
  done <<EOF
$short_names
EOF
  printf '%s\n' "$formatted"
}

main() {
  local tool_name decision
  tool_name="${1:-}"

  if [ -z "$tool_name" ]; then
    # 呼び出し不備。tool_name が取れない場合は何もチェックできないため fail-closed。
    hook_block "[pre-cloudflare-mcp-allowlist-check] ❌ tool_name が取得できませんでした（呼び出し不備・fail-closed でブロック）"
  fi

  decision=$(classify_cloudflare_mcp_tool "$tool_name" "$CF_MCP_DOC_PATH")

  case "$decision" in
    allow) exit 0 ;;
    block:not-in-allowlist)
      # 🔴 SSOT を複製しない: メッセージ中の許可ツール一覧はハードコードせず、
      # §7.4 から抽出した許可集合をその場で整形して埋め込む（コーディネーター指摘・
      # ドリフト対策）。§7.4 が更新されればメッセージも自動的に追随する。
      local allowed_list
      allowed_list=$(_cf_mcp_format_allowed_list "$(_cf_mcp_extract_allowed_short_names "$CF_MCP_DOC_PATH")")
      hook_block "[pre-cloudflare-mcp-allowlist-check] ❌ Cloudflare MCP ツール '${tool_name}' は許可集合に含まれていません。

許可集合の正本: docs/03_design/infrastructure/cloudflare-infrastructure.md §7.4
（現在の許可ツール: ${allowed_list}）

このツールが本当に必要な場合は、まず §7.4 の表と .claude/settings.json の permissions を
同一 PR で更新してから使用すること（Issue #56）。リソース作成・変更・削除は wrangler CLI に
一本化する方針のため、多くの書き込み系 MCP ツールは恒久的に不許可のままになる想定。"
      ;;
    block:doc-unparseable)
      hook_block "[pre-cloudflare-mcp-allowlist-check] ❌ Cloudflare MCP ツール '${tool_name}' をブロックしました（fail-closed）。

理由: 許可集合の正本ドキュメント（docs/03_design/infrastructure/cloudflare-infrastructure.md §7.4）
を解析できませんでした（ファイル不在・該当行『読み取り（許可）』が見つからない・
バッククォート区切りのツール名が 1 個も無い、のいずれか）。

判定できないときはブロック側に倒す方針（fail-closed）のため、ドキュメントを修復するまで
Cloudflare MCP ツールは全てブロックされます。"
      ;;
    *)
      hook_block "[pre-cloudflare-mcp-allowlist-check] ❌ 内部エラー: 未知の判定結果 '${decision}'（fail-closed でブロック）"
      ;;
  esac
}

run_self_test() {
  local failures=0 total=0
  local real_doc="$REPO_ROOT/docs/03_design/infrastructure/cloudflare-infrastructure.md"
  local tmpdir
  tmpdir=$(mktemp -d)
  # trap は関数ローカルの $tmpdir がスコープアウトした後の EXIT でも参照できるよう、
  # 値を展開してから登録する（`local` 変数を未展開のまま trap に渡すと、関数終了後の
  # EXIT トリガー時に「unbound variable」になる・self-test 実施時に実測）
  # shellcheck disable=SC2064
  trap "rm -rf '$tmpdir'" EXIT

  check() {
    local label="$1" tool="$2" doc="$3" expected="$4" actual
    total=$((total + 1))
    actual=$(classify_cloudflare_mcp_tool "$tool" "$doc")
    if [[ "$actual" != "$expected" ]]; then
      echo "  FAIL: $label — expected=$expected actual=$actual tool=$tool doc=$doc" >&2
      failures=$((failures + 1))
    else
      echo "  ok   $label" >&2
    fi
  }

  echo "== 実ドキュメント（§7.4）に対する判定 ==" >&2
  check "許可ツール1: search_cloudflare_documentation" \
    "${TOOL_PREFIX}search_cloudflare_documentation" "$real_doc" "allow"
  check "許可ツール2: workers_list" \
    "${TOOL_PREFIX}workers_list" "$real_doc" "allow"
  check "許可ツール3: workers_get_worker" \
    "${TOOL_PREFIX}workers_get_worker" "$real_doc" "allow"
  check "許可ツール4: workers_get_worker_code" \
    "${TOOL_PREFIX}workers_get_worker_code" "$real_doc" "allow"

  echo "== 既知の deny 列挙済みツール（引き続きブロックされること） ==" >&2
  check "d1_database_create はブロック" \
    "${TOOL_PREFIX}d1_database_create" "$real_doc" "block:not-in-allowlist"
  check "kv_namespace_delete はブロック" \
    "${TOOL_PREFIX}kv_namespace_delete" "$real_doc" "block:not-in-allowlist"
  check "d1_database_get（読み取り系だが未許可）はブロック" \
    "${TOOL_PREFIX}d1_database_get" "$real_doc" "block:not-in-allowlist"

  echo "== Issue #56 の核心: allow にも deny にも無い『新しい』ツール ==" >&2
  check "未知の新規ツール（架空）はブロック（本 Issue の核心）" \
    "${TOOL_PREFIX}totally_new_tool_nobody_listed_yet" "$real_doc" "block:not-in-allowlist"
  check "d1_database_execute_sql のような未列挙の新ツールもブロック" \
    "${TOOL_PREFIX}d1_database_execute_sql" "$real_doc" "block:not-in-allowlist"

  echo "== 入力バリアント: 前方一致・部分一致で誤許可しない ==" >&2
  check "許可ツール名の前方一致（workers_list_extra）は誤許可しない" \
    "${TOOL_PREFIX}workers_list_extra" "$real_doc" "block:not-in-allowlist"
  check "許可ツール名の後方一致（extra_workers_list）は誤許可しない" \
    "${TOOL_PREFIX}extra_workers_list" "$real_doc" "block:not-in-allowlist"
  check "大文字小文字違い（Workers_List）は誤許可しない" \
    "${TOOL_PREFIX}Workers_List" "$real_doc" "block:not-in-allowlist"

  echo "== プレフィックス外のツールは対象外（allow） ==" >&2
  check "Cloudflare MCP 以外のツール名は対象外" \
    "mcp__github__delete_file" "$real_doc" "allow"
  check "空文字列に近いツール名も対象外" \
    "Bash" "$real_doc" "allow"

  echo "== fail-closed: ドキュメントが解析できないとき ==" >&2
  local missing_doc="$tmpdir/does-not-exist.md"
  check "ドキュメント不在 → fail-closed でブロック" \
    "${TOOL_PREFIX}workers_list" "$missing_doc" "block:doc-unparseable"

  local no_row_doc="$tmpdir/no-matching-row.md"
  printf '# dummy\n\nこのドキュメントには該当する表がありません。\n' > "$no_row_doc"
  check "該当行が無い → fail-closed でブロック" \
    "${TOOL_PREFIX}workers_list" "$no_row_doc" "block:doc-unparseable"

  local no_backtick_doc="$tmpdir/row-without-backticks.md"
  printf '| 読み取り（許可） | search_cloudflare_documentation workers_list | 使ってよい |\n' > "$no_backtick_doc"
  check "行はあるがバッククォート無し → fail-closed でブロック（表の書式が崩れた場合）" \
    "${TOOL_PREFIX}workers_list" "$no_backtick_doc" "block:doc-unparseable"

  echo "== fail-open 回帰防止: 第1列・第3列のバッククォート語を許可集合に混入させない ==" >&2
  # コーディネーター指摘: 当初は行全体からバッククォート語を拾っており、区分列（第1列）・
  # 可否/注記列（第3列）に英数字のみのバッククォート語が入ると、それが黙って許可集合に
  # 加わる fail-open だった（§7.4 の実際の第3列は `CP-2` でハイフンを含むため偶然セーフ
  # だっただけ）。第1列・第3列にダミーの英数字バッククォート語を仕込んだフィクスチャで、
  # そのダミー語が許可集合に混入しない（＝ツールとして許可されない）ことを実測する。
  local col1_leak_doc="$tmpdir/col1-leak.md"
  printf '| 読み取り（許可） `evil_tool` | `search_cloudflare_documentation` / `workers_list` / `workers_get_worker` / `workers_get_worker_code` | 🟢 使ってよい |\n' > "$col1_leak_doc"
  check "第1列（区分）に紛れ込んだバッククォート語 evil_tool は許可集合に混入しない" \
    "${TOOL_PREFIX}evil_tool" "$col1_leak_doc" "block:not-in-allowlist"
  check "同フィクスチャで本来の許可ツールは引き続き allow" \
    "${TOOL_PREFIX}workers_list" "$col1_leak_doc" "allow"

  local col3_leak_doc="$tmpdir/col3-leak.md"
  printf '| 読み取り（許可） | `search_cloudflare_documentation` / `workers_list` / `workers_get_worker` / `workers_get_worker_code` | 🟢 使ってよい（`evil_tool` の一次情報確認） |\n' > "$col3_leak_doc"
  check "第3列（可否・注記）に紛れ込んだバッククォート語 evil_tool は許可集合に混入しない（本 fail-open 修正の核心ケース）" \
    "${TOOL_PREFIX}evil_tool" "$col3_leak_doc" "block:not-in-allowlist"
  check "同フィクスチャで本来の許可ツールは引き続き allow（2）" \
    "${TOOL_PREFIX}workers_get_worker" "$col3_leak_doc" "allow"

  echo "== exit code まで貫通しているか（main() 経由） ==" >&2
  local out code
  out=$(main "${TOOL_PREFIX}d1_database_create" 2>&1) || code=$?
  total=$((total + 1))
  if [ "${code:-0}" -eq 2 ]; then
    echo "  ok   main() 経由で未許可ツールが exit 2 になる" >&2
  else
    echo "  FAIL: main() 経由の exit code が 2 ではない（実際: ${code:-0}）" >&2
    failures=$((failures + 1))
  fi
  code=0
  out=$(main "${TOOL_PREFIX}workers_list" 2>&1) || code=$?
  total=$((total + 1))
  if [ "${code:-0}" -eq 0 ]; then
    echo "  ok   main() 経由で許可ツールが exit 0 になる" >&2
  else
    echo "  FAIL: main() 経由で許可ツールがブロックされた（実際: ${code:-0}, out=${out}）" >&2
    failures=$((failures + 1))
  fi
  code=0
  out=$(main "" 2>&1) || code=$?
  total=$((total + 1))
  if [ "${code:-0}" -eq 2 ]; then
    echo "  ok   main() 経由で tool_name 未指定が exit 2 になる（呼び出し不備の fail-closed）" >&2
  else
    echo "  FAIL: tool_name 未指定時の exit code が 2 ではない（実際: ${code:-0}）" >&2
    failures=$((failures + 1))
  fi

  echo "" >&2
  echo "[pre-cloudflare-mcp-allowlist-check] self-test: $((total - failures)) passed / ${failures} failed (total ${total})" >&2
  [[ "$failures" -eq 0 ]]
}

if [[ "${1:-}" == "--self-test" ]]; then
  run_self_test
  exit $?
fi

main "${1:-}"
