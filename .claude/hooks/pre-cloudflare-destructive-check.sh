#!/bin/bash
set -euo pipefail
# PreToolUse hook: Cloudflare Workers スクリプトへの破壊的操作をブロック（ハードコンストレイント Lv3）
#
# 【背景（Issue #613 / #615）】
# preview alias の削除手段を実 API で裏取りする過程で、探索目的の
#   DELETE /accounts/{account_id}/workers/scripts/gem-hunter/<存在しないサブリソース>
# を送信したところ、Cloudflare API は **パス末尾の未知セグメントを黙って切り捨てて**
# `DELETE /accounts/{account_id}/workers/scripts/gem-hunter`（Worker 本体の削除）として処理し
# HTTP 200 を返した。結果、本番 Worker・version 165 件・preview alias 46 件・シークレット全てが
# 消失した（復旧はできたが version/alias 履歴は失われた）。
#
# 【対策】
# Cloudflare Workers スクリプト（`workers/scripts/<name>` 配下・any subpath）に対する
# DELETE リクエスト、および Worker 本体を削除する `wrangler delete` を機械的にブロックする。
# 個別 version・preview alias の削除 API・CLI コマンドは存在しない（実測確認済み・
# docs/03_design/infrastructure/cloudflare-infrastructure.md §6.1）ため、
# このパターンの DELETE は「意図した個別削除」ではなく「誤ってスクリプト全体を消す」
# ケースにほぼ限られる。
#
# 検証: `bash .claude/hooks/pre-cloudflare-destructive-check.sh --self-test`

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"

BLOCK_MESSAGE_DELETE_API="[pre-cloudflare-destructive-check] ❌ Cloudflare Workers スクリプトへの DELETE リクエストをブロックしました。

Cloudflare API は workers/scripts/<name> 配下の **末尾に未知のサブリソース名を付けても 404 にならず、
親リソース（Worker 本体）への DELETE として処理される**（実測・Issue #615 で本番 Worker を誤削除）。

version / preview alias を個別削除する API・CLI コマンドは存在しない
（docs/03_design/infrastructure/cloudflare-infrastructure.md §6.1）。
後始末は削除ではなく「退役」（本番と同じビルドへの張り替え）で行う:
  python3 tools/retire_preview_aliases.py --list
  python3 tools/retire_preview_aliases.py --alias pr-<N>

Worker 本体を意図して削除する場合のみ、ユーザーに確認してから実行すること（A-1〜A-6 相当の不可逆操作）。"

BLOCK_MESSAGE_WRANGLER_DELETE="[pre-cloudflare-destructive-check] ❌ 'wrangler delete' をブロックしました。

このコマンドは Worker 本体を削除し、version 履歴・preview alias を全て道連れにする不可逆操作。
プレビュー環境の後始末は退役スクリプトを使うこと:
  python3 tools/retire_preview_aliases.py --alias pr-<N>

Worker 本体の削除が本当に必要な場合は、ユーザーに確認してから実行すること。"

# heredoc の本文（コミットメッセージ・PR 本文・ドキュメント等を `cat <<'EOF' ... EOF` や
# `cat > file <<'EOF' ... EOF` で組み立てる箇所）を取り除く。本文中に「wrangler delete」
# 「DELETE ... workers/scripts」という **文字列としての言及**（この教訓自体を記録する
# コミットメッセージ・スクラッチファイルへの書き出し等）が実行コマンドと誤認されるのを防ぐ
# （実際に self-test 追加時点でこのコミットメッセージ自身が誤検知した・回帰防止）。
#
# 🔴 対象は **その heredoc を起こしているのが `cat`（直前にリダイレクト先を挟んでもよい）の
# ときだけ**に絞る（`bash`/`sh`/`python3`/`node` 等、heredoc を実際に実行するコマンドへの
# heredoc は対象外のまま残す）。汎用的に全ての `<<DELIM` を剥がすと、
# `bash <<'EOF'\ncurl -X DELETE .../workers/scripts/gem-hunter\nEOF` のように **heredoc 経由で
# 危険なコマンドを実行しているのに本文扱いされて素通りする** 抜け道になる（`cat` は標準出力・
# ファイルへ書き出すだけで実行しないため、`cat` 起点なら安全に剥がせる）。判定は「`<<` の直前の
# コマンド区切り（`;` `|` `&` `` ` `` `(` `{`）より後ろの先頭語が `cat` か」で行う（`cat > file <<EOF`
# のように途中にリダイレクト先を挟む形も拾う）。
strip_heredocs() {
  awk '
    BEGIN { in_hd = 0; delim = ""; strip_tabs = 0 }
    {
      line = $0
      if (in_hd) {
        cmp = line
        if (strip_tabs) { gsub(/^\t+/, "", cmp) }
        if (cmp == delim) { in_hd = 0 }
        next
      }
      if (match(line, /<<-?[ \t]*("[^"]*"|'"'"'[^'"'"']*'"'"'|[A-Za-z_][A-Za-z0-9_]*)/)) {
        prefix = substr(line, 1, RSTART - 1)
        seg = prefix
        cut = 0
        for (i = length(seg); i >= 1; i--) {
          c = substr(seg, i, 1)
          if (c == ";" || c == "|" || c == "&" || c == "`" || c == "(" || c == "{") { cut = i; break }
        }
        seg = substr(seg, cut + 1)
        gsub(/^[ \t]+/, "", seg)
        if (seg ~ /^cat([ \t]|$|>)/) {
          tok = substr(line, RSTART, RLENGTH)
          strip_tabs = (tok ~ /^<<-/) ? 1 : 0
          gsub(/^<<-?[ \t]*/, "", tok)
          gsub(/^["'"'"']|["'"'"']$/, "", tok)
          delim = tok
          in_hd = 1
          print line
          next
        }
      }
      print line
    }
  '
}

# コマンド文字列から Cloudflare Workers スクリプトへの DELETE を検出する（純粋関数・self-test 対象）
# 引数: $1 = コマンド文字列
# 戻り値（echo）: "block:api" / "block:wrangler-delete" / "allow"
classify_command() {
  local cmd
  cmd="$(printf '%s' "$1" | strip_heredocs)"

  # --- ① HTTP クライアントによる DELETE ---
  # -X DELETE / --request DELETE（大文字小文字を問わない）が、workers/scripts を含む URL と
  # 同一コマンド文字列中に共存するかを見る。curl（`-X` / `--request`）と wget（`--method`）の
  # どちらの流儀も拾うため特定コマンド名には依存しない。フラグと値の間は空白・`=`・引用符
  # （`'`/`"`）のどの組み合わせも許容する（`-X DELETE` / `-XDELETE` / `-X "DELETE"` /
  # `--request=DELETE` / `--request='DELETE'` / `--method=DELETE` いずれも同じ意味の呼び出しであり、
  # 引用符付き・`--method` だけ素通りしては再発防止にならない）。
  if printf '%s' "$cmd" | grep -qiE -- '(-X|--request|--method)[[:space:]=]*["'"'"']?DELETE["'"'"']?' \
    && printf '%s' "$cmd" | grep -qE 'workers/scripts'; then
    echo "block:api"
    return
  fi

  # --- ② `wrangler delete`（Worker 本体を削除するサブコマンド） ---
  # `npx wrangler delete` / `wrangler delete --name x` / `wrangler "delete"` 等。サブコマンド名を
  # 引用符で囲んでも同じ意味なので許容する。`wrangler d1 delete` や `wrangler kv:namespace delete`
  # のような他リソースの削除コマンドは対象外にする（Workers スクリプト削除とは別の操作であり、
  # 誤ブロックは避ける）。
  if printf '%s' "$cmd" | grep -qE '(^|[[:space:];|&(`{])wrangler[[:space:]]+["'"'"']?delete["'"'"']?([[:space:]]|$)'; then
    echo "block:wrangler-delete"
    return
  fi

  echo "allow"
}

main() {
  local input tool_name command decision
  input=$(cat)

  tool_name=$(printf '%s' "$input" | jq -r '.tool_name // ""')
  if [ "$tool_name" != "Bash" ]; then exit 0; fi

  command=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

  # 安価な早期リターン: DELETE も wrangler も含まなければ対象外
  if ! printf '%s' "$command" | grep -qiE 'delete'; then exit 0; fi

  decision=$(classify_command "$command")
  case "$decision" in
    block:api) hook_block "$BLOCK_MESSAGE_DELETE_API" ;;
    block:wrangler-delete) hook_block "$BLOCK_MESSAGE_WRANGLER_DELETE" ;;
  esac

  exit 0
}

run_self_test() {
  local failures=0 total=0

  check() {
    local label="$1" cmd="$2" expected="$3" actual
    total=$((total + 1))
    actual=$(classify_command "$cmd")
    if [[ "$actual" != "$expected" ]]; then
      echo "  FAIL: $label — expected=$expected actual=$actual cmd=$cmd" >&2
      failures=$((failures + 1))
    fi
  }

  check "実際の事故コマンド（末尾サブリソース付き DELETE）" \
    'curl -s -X DELETE -H "Authorization: Bearer $TOK" "https://api.cloudflare.com/client/v4/accounts/$ACC/workers/scripts/gem-hunter/totally-bogus-subresource"' \
    "block:api"
  check "スクリプト本体への直接 DELETE" \
    'curl -X DELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter' \
    "block:api"
  check "--request DELETE 形式" \
    'curl --request DELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter/versions/abc' \
    "block:api"
  check "workers/scripts を含まない DELETE は対象外" \
    'curl -X DELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/kv/namespaces/ns/values/key' \
    "allow"
  check "GET は対象外" \
    'curl -X GET https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter/versions' \
    "allow"
  check "npx wrangler delete をブロック" \
    'npx wrangler delete' \
    "block:wrangler-delete"
  check "wrangler delete --name をブロック" \
    'wrangler delete --name gem-hunter' \
    "block:wrangler-delete"
  check "wrangler d1 delete は対象外（別リソース）" \
    'npx wrangler d1 delete my-db' \
    "allow"
  check "wrangler versions upload は対象外" \
    'npx wrangler versions upload --preview-alias pr-212' \
    "allow"
  check "retire_preview_aliases.py の実行は対象外" \
    'python3 tools/retire_preview_aliases.py --alias pr-212' \
    "allow"

  # --- 引用符付き / `=` 形式の DELETE も同じ意味の呼び出しとして検知する（回帰: 初版は素通りした） ---
  check '二重引用符 -X "DELETE" をブロック' \
    'curl -X "DELETE" https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter' \
    "block:api"
  check "単一引用符 -X 'DELETE' をブロック" \
    "curl -X 'DELETE' https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter" \
    "block:api"
  check "--request=DELETE（等号形式）をブロック" \
    'curl --request=DELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter' \
    "block:api"
  check "wget --method=DELETE をブロック" \
    'wget --method=DELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter' \
    "block:api"
  check '引用符付き wrangler "delete" をブロック' \
    'npx wrangler "delete"' \
    "block:wrangler-delete"

  # --- heredoc 本文中の言及を実コマンドと誤認しない（回帰: このコミット自身が誤検知した） ---
  local heredoc_commit_msg
  heredoc_commit_msg=$'git commit -m "$(cat <<\'EOF\'\nimprovement: wrangler delete \xe3\x82\x92\xe6\xa9\x9f\xe6\xa2\xb0\xe7\x9a\x84\xe3\x81\xab\xe3\x83\x96\xe3\x83\xad\xe3\x83\x83\xe3\x82\xaf\xe3\x81\x99\xe3\x82\x8b\nEOF\n)"'
  check "コミットメッセージ heredoc 内の『wrangler delete』は対象外" \
    "$heredoc_commit_msg" \
    "allow"

  local heredoc_delete_api_msg
  heredoc_delete_api_msg=$'git commit -m "$(cat <<\'EOF\'\nDELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter への対策\nEOF\n)"'
  check "コミットメッセージ heredoc 内の DELETE API 言及は対象外" \
    "$heredoc_delete_api_msg" \
    "allow"

  # `cat` と `<<` の間にリダイレクト先を挟む形（`cat > file <<EOF`）も本文として剥がす
  # （回帰: この self-test を書き足す作業そのものが、この形で一度誤検知した）
  local heredoc_cat_redirect_msg
  heredoc_cat_redirect_msg=$'cat > "/tmp/out.sh" <<\'SCRIPT\'\ncurl -X DELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter\nSCRIPT'
  check "cat > file <<EOF 形式の heredoc 本文中の言及は対象外" \
    "$heredoc_cat_redirect_msg" \
    "allow"

  local heredoc_with_real_delete_before
  heredoc_with_real_delete_before=$'npx wrangler delete && git commit -m "$(cat <<\'EOF\'\nnote\nEOF\n)"'
  check "heredoc の外にある実コマンドの wrangler delete は引き続きブロックする" \
    "$heredoc_with_real_delete_before" \
    "block:wrangler-delete"

  # --- heredoc を「本文」ではなく実際に実行するコマンド（bash/sh 等）は剥がさない ---
  # `cat` 限定にする前は、`bash <<EOF ... EOF` に包むだけで危険なコマンドが本文扱いされ
  # 素通りする抜け道になっていた（発見・修正）。
  local bash_heredoc_with_delete
  bash_heredoc_with_delete=$'bash <<\'HEREDOC\'\ncurl -X DELETE https://api.cloudflare.com/client/v4/accounts/ACC/workers/scripts/gem-hunter\nHEREDOC'
  check "bash <<EOF 経由で実行される DELETE は heredoc でも剥がさずブロックする" \
    "$bash_heredoc_with_delete" \
    "block:api"

  echo "" >&2
  echo "[pre-cloudflare-destructive-check] self-test: $((total - failures)) passed / ${failures} failed (total ${total})" >&2
  [[ "$failures" -eq 0 ]]
}

if [[ "${1:-}" == "--self-test" ]]; then
  run_self_test
  exit $?
fi

main
