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
# docs/03_design/infrastructure/cloudflare-infrastructure.md §7.4 の表（「読み取り（許可）」行に
# 行アンカー＋ヘッダ列の動的解決で特定した「ツール」列のバッククォート区切りツール名）から
# 機械的に読み取る。本スクリプトは正本を複製しない。
# 表を解釈できない場合（ファイル不在・該当行が見つからない/曖昧・列を解決できない・
# 書式変更等）は **fail-closed**（全 Cloudflare MCP ツールをブロック）にする。
#
# 使い方: bash .claude/hooks/pre-cloudflare-mcp-allowlist-check.sh <tool_name>
# self-test: bash .claude/hooks/pre-cloudflare-mcp-allowlist-check.sh --self-test

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"

TOOL_PREFIX="mcp__Cloudflare_Developer_Platform__"

# SSOT ドキュメントのパス（固定・上書き不可）。
# 🔴 WARNING 3（Layer 1 セルフレビュー指摘）: 以前は `CF_MCP_ALLOWLIST_DOC_PATH` 環境変数で
# 本番実行でも無条件に上書きできる設計だった（`.claude/settings.json` の `env` に 1 行足す
# だけで許可集合の正本を任意ファイルへ差し替え可能になる、実効的なセキュリティホール）。
# self-test 側は元々 `classify_cloudflare_mcp_tool` にフィクスチャの doc パスを**引数として
# 直接渡す**設計になっており、この環境変数は self-test からも参照されていなかった
# （used-nowhere の攻撃面だけが存在していた）。よって環境変数オーバーライド自体を廃止し、
# 常にリポジトリ内の固定パスだけを見る。
CF_MCP_DOC_PATH="$REPO_ROOT/docs/03_design/infrastructure/cloudflare-infrastructure.md"

# ドキュメントの §7.4 表から「読み取り（許可）」行のツール名セルだけを取り出す。
# 見つかれば 1 行のテキスト（バッククォート区切りのツール名を含むセル本文）を返す。
# 見つからない・曖昧・列を解決できない場合は何も出力しない（呼び出し側が fail-closed 判定）。
#
# 🔴 CRITICAL 1 対策（Layer 1 セルフレビュー指摘・行アンカー）: 以前は `grep -F` で文書全体から
# 「読み取り（許可）」という**文字列を含む行**を拾っており、表の行かどうかを見ていなかった。
# ① 同じ文言を含む散文が表より前に来ると、その散文行がヒットして `cut` が空を返し
# 全 Cloudflare MCP ツールが原因不明のまま fail-closed で全面ブロックされる
# ② その散文に英数字のみのバッククォート語（`` `d1_database_get` `` 等）があると、
# それが許可ツール名として許可集合に混入する fail-open のどちらも起こりうる
# （しかも本ドキュメント自身がこの節でその文言・バッククォート語を含んでいるため、
# 表が散文より後に来る書き方に変わった瞬間に発火しうる）。
# 対策: 行頭が `|` で区分セルが「読み取り（許可）」に**完全一致**する行だけを候補にする
# （`grep -E '^\| *読み取り（許可） *\|'`）。散文はどこにあっても行頭が `|` でないため
# 候補に入らない。さらに候補が 0 件でも 2 件以上（曖昧）でも fail-closed にする
# （複数ヒットのときどちらが正か決め打ちしない）。
#
# 🔴 CRITICAL 2 対策（Layer 1 セルフレビュー指摘・列位置の動的解決）: 以前は
# `cut -d'|' -f3`（決め打ちの第3フィールド）でツール名列を取っており、表に列が
# 1 つ増減・並び替えされると別の列（例: 区分と可否の間に列が増えるとツール名の
# はずが破壊的操作の列を拾う）を許可集合として読み込んでしまう最悪の組み合わせに
# なりうった。対策: ヘッダ行（同じ表の連続ブロック内で、セルが「ツール」に完全一致する
# 行）から列番号を動的に解決し、その列番号をデータ行に適用する。表の外（先頭が `|`
# でない行）に出たらヘッダ追跡をリセットし、無関係な別テーブルのヘッダを誤って
# 引き継がない。ヘッダが見つからない（= 列番号を解決できない）場合も fail-closed にする。
# 🔵 設計選択（コーディネーターが提示した二択のうち採用した方）: 「区分セルの次のセル」
# ではなく「ヘッダの列名解決」を選んだ。理由: 上記の実測攻撃フィクスチャ（区分列とツール列の
# 間に新しい列が挿入されるケース）は「次のセル」方式では防げない（挿入された列が
# そのまま「次のセル」になってしまう）ため、列の意味（ヘッダ名）で解決する方式でなければ
# この攻撃を防げない。制約として「区分」列は表の先頭列のままであることを前提にする
# （区分列自体の位置がずれるケースは対象外・現行表の構造と一致）。
_cf_mcp_extract_tool_cell() {
  local doc="$1" anchor_lines anchor_count
  [ -f "$doc" ] || return 0

  # 行アンカー: 行頭 `|` + 区分セルが「読み取り（許可）」に完全一致する行のみを候補にする
  anchor_lines=$(grep -E '^\| *読み取り（許可） *\|' "$doc" || true)
  [ -n "$anchor_lines" ] || return 0

  anchor_count=$(printf '%s\n' "$anchor_lines" | grep -c '.' || true)
  if [ "$anchor_count" -ne 1 ]; then
    # 曖昧（同じ表行文言が複数箇所にある）。どちらが正か決め打ちしない → fail-closed
    return 0
  fi

  # ヘッダ行から「ツール」列の位置を動的解決し、同じ表ブロック内のデータ行（区分セルが
  # 「読み取り（許可）」に完全一致する行）のその列を出力する。表の外に出たらリセットする。
  awk -F'|' '
    {
      if ($0 !~ /^\|/) { header_idx = 0; next }
      for (i = 1; i <= NF; i++) {
        cell = $i
        gsub(/^[ \t]+|[ \t]+$/, "", cell)
        if (cell == "ツール") { header_idx = i }
      }
      cell1 = $2
      gsub(/^[ \t]+|[ \t]+$/, "", cell1)
      if (cell1 == "読み取り（許可）") {
        if (header_idx > 0) { print $(header_idx) }
        exit
      }
    }
  ' "$doc"
}

# `_cf_mcp_extract_tool_cell` が返したセル本文からバッククォート区切りツール名を抜き出す。
# 抽出できたら "search_cloudflare_documentation workers_list ..." のように空白区切りで返す。
# 抽出できない場合は何も出力せず、呼び出し側が fail-closed 判定する。
_cf_mcp_extract_allowed_short_names() {
  local doc="$1" col2
  col2=$(_cf_mcp_extract_tool_cell "$doc")
  [ -n "$col2" ] || return 0

  # バッククォートで囲まれたトークンを全て抜き出す（例: `search_cloudflare_documentation`）
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
# ⚪ NIT（Layer 1 セルフレビュー指摘）: 空文字列分岐（「（取得できませんでした）」）は、
# 現在の呼び出し経路（block:not-in-allowlist ケースのみで呼ばれる。抽出が失敗していれば
# その前に block:doc-unparseable に分岐して本関数へは到達しない）からは**到達不能**。
# 純粋関数として「空を渡されても壊れない」防御的な分岐として意図的に残す（削除より
# 安全側に倒す。呼び出し経路が将来変わってもメッセージが空文字列になる事故を防ぐ）。
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

  echo "== CRITICAL 1 回帰防止: 表の行だけを候補にする（散文中の同一文言に反応しない） ==" >&2
  # Layer 1 セルフレビュー指摘の実測フィクスチャ: 「読み取り（許可）」という文言を含む散文が
  # 表より前に来ても、① その散文行を表の行と誤認して fail-closed に落ちない
  # （散文の直後に本物の表があれば、そちらを正しく見つける）② 散文中のバッククォート語
  # （`d1_database_get` / `PreToolUse` 等）が許可集合に混入しない（fail-open しない）の
  # 両方を同時に確認する。
  local prose_before_table_doc="$tmpdir/prose-before-table.md"
  printf '（散文）読み取り（許可）というツール区分の話をする。ここでは `d1_database_get` や `PreToolUse` には一切触れない。\n\n| 区分 | ツール | 可否 |\n|---|---|---|\n| 読み取り（許可） | `search_cloudflare_documentation` / `workers_list` / `workers_get_worker` / `workers_get_worker_code` | 🟢 使ってよい |\n' > "$prose_before_table_doc"
  check "散文中のバッククォート語 d1_database_get は許可集合に混入しない（fail-open しない）" \
    "${TOOL_PREFIX}d1_database_get" "$prose_before_table_doc" "block:not-in-allowlist"
  check "散文中のバッククォート語 PreToolUse も混入しない" \
    "${TOOL_PREFIX}PreToolUse" "$prose_before_table_doc" "block:not-in-allowlist"
  check "散文の後にある本物の表は正しく解析され workers_list は allow（fail-closed しない）" \
    "${TOOL_PREFIX}workers_list" "$prose_before_table_doc" "allow"

  echo "== CRITICAL 1 回帰防止: 候補行が複数（曖昧）なら fail-closed ==" >&2
  local ambiguous_doc="$tmpdir/ambiguous-two-tables.md"
  printf '| 区分 | ツール | 可否 |\n|---|---|---|\n| 読み取り（許可） | `workers_list` | 🟢 |\n\n（別の表）\n\n| 区分 | ツール | 可否 |\n|---|---|---|\n| 読み取り（許可） | `workers_get_worker` | 🟢 |\n' > "$ambiguous_doc"
  check "候補行が2件（曖昧）→ どちらが正か決め打ちせず fail-closed" \
    "${TOOL_PREFIX}workers_list" "$ambiguous_doc" "block:doc-unparseable"

  echo "== CRITICAL 2 回帰防止: 列位置をヘッダから動的解決する（決め打ちしない） ==" >&2
  # Layer 1 セルフレビュー指摘の実測フィクスチャ: 区分列とツール列の間に新しい列
  # （優先度）が挿入されると、位置決め打ち（旧実装の `cut -d'|' -f3`）は誤って
  # 「優先度」列の内容（deny 済みの破壊的操作ツール名）を許可集合として読み込む
  # 最悪の組み合わせになる。ヘッダの列名（「ツール」）で動的解決していれば、
  # 列が増えても正しい列を追随できることを実測する。
  local column_reorder_doc="$tmpdir/column-reorder.md"
  printf '| 区分 | 優先度 | ツール | 可否 |\n|---|---|---|---|\n| 読み取り（許可） | `d1_database_create` | `search_cloudflare_documentation` / `workers_list` | 🟢 |\n' > "$column_reorder_doc"
  check "挿入列の内容（d1_database_create）が誤って許可集合に入らない（本 fail-open 修正の核心ケース）" \
    "${TOOL_PREFIX}d1_database_create" "$column_reorder_doc" "block:not-in-allowlist"
  check "列が増えても正しいツール列（workers_list）を追随して allow できる" \
    "${TOOL_PREFIX}workers_list" "$column_reorder_doc" "allow"
  check "同フィクスチャの search_cloudflare_documentation も allow" \
    "${TOOL_PREFIX}search_cloudflare_documentation" "$column_reorder_doc" "allow"

  echo "== WARNING 4: プレフィックスちょうど（サフィックス空）はブロック ==" >&2
  check "プレフィックスのみ（サフィックス空）はブロック" \
    "${TOOL_PREFIX}" "$real_doc" "block:not-in-allowlist"

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
