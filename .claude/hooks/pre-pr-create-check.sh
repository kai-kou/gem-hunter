#!/bin/bash
set -euo pipefail
# PreToolUse hook: PR作成前の未コミットファイルチェック（ハードコンストレイント Lv3）
#
# Bash ツールで gh pr create が実行される前に自動チェック。
# 未コミット・未push のファイルがあれば PR 作成をブロックする。

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"

input=$(cat)

# ツール名を取得（printf を使い、バックスラッシュを含む入力でも echo のエスケープ解釈に依存しない）
tool_name=$(printf '%s\n' "$input" | jq -r '.tool_name // ""')

# is_pr_create=1 のときだけ後段のゲート（git-clean + self_review_check + Layer 1 リマインダー）を実行する
is_pr_create=0
command=""

if [ "$tool_name" = "mcp__github__create_pull_request" ]; then
  # MCP 経由の PR 作成（クラウド主経路。gh pr create は proxy 403 で失敗するため）。
  # コマンド文字列を持たないため直接ゲートへ。
  is_pr_create=1
elif [ "$tool_name" = "Bash" ]; then
  command=$(printf '%s\n' "$input" | jq -r '.tool_input.command // ""')
  # 行頭アンカーのみだと `git commit && gh pr create` のような複合コマンドで
  # gh pr create がバイパスされる（pre-tool-use-router.sh のルーティング判定はアンカーなし
  # のため両者がズレる）。区切り文字（空白・;・|・&）の直後も許容する。
  if printf '%s\n' "$command" | grep -qE '(^|[[:space:];|&])gh\s+pr\s+create(\s|$)'; then
    is_pr_create=1
  fi
else
  # Bash / MCP PR 作成以外のツールは対象外
  exit 0
fi

# --- poll_pr_reviews.sh 引数バリデーション（Lv3 ハードコンストレイント・Bash 経路のみ） ---
# poll_pr_reviews.sh が呼び出される場合、引数の順序を事前チェック
# 実行位置アンカー付き（bash/sh 経由の起動のみ）。アンカーなしだと
# `git diff -- tools/poll_pr_reviews.sh HEAD~1` のような無関係コマンドの
# パス引数にも誤反応し、ブロックしてしまう（Issue #158 候補3）。
if [ "$tool_name" = "Bash" ] && printf '%s\n' "$command" | grep -qE '(^|[[:space:];|&])(bash|sh)[[:space:]]+\S*poll_pr_reviews\.sh([[:space:]]|$)'; then
  # 引数を抽出（bash tools/poll_pr_reviews.sh arg1 arg2 arg3）
  arg1=$(echo "$command" | sed -E 's/.*poll_pr_reviews\.sh\s+//' | awk '{print $1}')
  arg2=$(echo "$command" | sed -E 's/.*poll_pr_reviews\.sh\s+//' | awk '{print $2}')
  arg3=$(echo "$command" | sed -E 's/.*poll_pr_reviews\.sh\s+//' | awk '{print $3}')

  errors=""

  # 第1引数が owner/repo 形式でなければエラー
  if [ -n "$arg1" ] && ! echo "$arg1" | grep -qE '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$'; then
    errors="${errors}第1引数 '${arg1}' が owner/repo 形式ではありません。\n"
  fi

  # 第2引数が正の整数でなければエラー
  if [ -n "$arg2" ] && ! echo "$arg2" | grep -qE '^[0-9]+$'; then
    errors="${errors}第2引数 '${arg2}' がPR番号（正の整数）ではありません。\n"
  fi

  # 第3引数にパス区切りがなければエラー（リポジトリ汚染防止）
  if [ -n "$arg3" ] && ! echo "$arg3" | grep -qE '/'; then
    errors="${errors}第3引数 '${arg3}' に / が含まれていません。リポジトリルートに状態ファイルが作成されます。\n"
  fi

  if [ -n "$errors" ]; then
    correct_usage="正しい形式: bash tools/poll_pr_reviews.sh {owner}/{repo} {pr_number} /tmp/pr_review_{pr_number}.json"
    hook_block "[pre-tool-use-validate] poll_pr_reviews.sh の引数が不正です。

${errors}
${correct_usage}"
  fi

  exit 0
fi

# PR 作成（gh pr create / MCP create_pull_request）でなければスキップ
if [ "$is_pr_create" -ne 1 ]; then exit 0; fi

# git リポジトリでなければスキップ
if ! git rev-parse --git-dir >/dev/null 2>&1; then exit 0; fi

# pathspec は cwd 相対のため、リポジトリルートへ固定する（#243 レビュー）
cd "$(git rev-parse --show-toplevel)" || exit 0

# 月次コストテレメトリは PR 前チェックから除外する（#242・stop-git-check.sh と同一方針）。
# 旧ブランチで追跡されたまま --flush 更新されると、WIP コミット除外と衝突して
# PR 作成が恒久ブロックされるデッドロックになるため（#243 レビュー）。
TELEMETRY_EXCLUDE=':(exclude)content/analytics/cost_monthly/'

errors=""

# 1. 未ステージの変更チェック
if ! git diff --quiet -- . "$TELEMETRY_EXCLUDE" 2>/dev/null; then
  changed_files=$(git diff --name-only -- . "$TELEMETRY_EXCLUDE" 2>/dev/null | head -10)
  errors="${errors}未ステージの変更があります:
${changed_files}

"
fi

# 2. ステージ済み未コミットの変更チェック
if ! git diff --cached --quiet -- . "$TELEMETRY_EXCLUDE" 2>/dev/null; then
  staged_files=$(git diff --cached --name-only -- . "$TELEMETRY_EXCLUDE" 2>/dev/null | head -10)
  errors="${errors}ステージ済み未コミットの変更があります:
${staged_files}

"
fi

# 3. 未追跡ファイルチェック
untracked=$(git ls-files --others --exclude-standard -- . "$TELEMETRY_EXCLUDE" 2>/dev/null | head -10)
if [ -n "$untracked" ]; then
  errors="${errors}未追跡ファイルがあります:
${untracked}

"
fi

# 4. 未pushコミットチェック
current_branch=$(git branch --show-current 2>/dev/null)
if [ -n "$current_branch" ]; then
  if git rev-parse "origin/$current_branch" >/dev/null 2>&1; then
    unpushed=$(git rev-list "origin/$current_branch..HEAD" --count 2>/dev/null || echo "0")
    if [ "$unpushed" -gt 0 ]; then
      errors="${errors}未pushのコミットが ${unpushed} 件あります。git push してください。

"
    fi
  else
    # リモートにブランチが存在しない場合、ブランチ自体が未push
    local_commits=$(git rev-list HEAD --count 2>/dev/null || echo "0")
    if [ "$local_commits" -gt 0 ]; then
      errors="${errors}ブランチ '${current_branch}' がリモートに存在しません。git push -u origin ${current_branch} してください。

"
    fi
  fi
fi

if [ -n "$errors" ]; then
  hook_block "[pre-pr-create-check] PR作成をブロックしました。未コミット・未pushの変更があります。

${errors}先にすべての変更をコミット＆pushしてから PR 作成（gh pr create / mcp__github__create_pull_request）を再実行してください。
手順: git add <ファイル> → git commit → git push -u origin <ブランチ名>"
fi

# 4.5. run_checks サマリーの貼付検査（Lv3・Actions 制限中の CI 代替・#72）
# GitHub Actions が制限中で CI が存在しないため、`tools/run_checks.sh` の実行結果を PR 本文へ貼ることが
# 唯一の機械的証跡になる。貼付が無い PR は「lint / 型 / テストを誰も実行していない」可能性があるためブロックする。
# 🔴 ここをブロックにする理由: 満たす条件が「本文に結果表を貼る」だけで決定論的（誤検知が構造的に起きない）。
#    チェッカーの異常終了を fail-open にしたのとは性質が違う（あちらは環境要因、これは手順の省略）。
#    Actions が復帰しワークフローが CI を担うようになったら本ブロックは撤去する（cloudflare-infrastructure.md §8.4）。
if [ "$tool_name" = "mcp__github__create_pull_request" ]; then
  pr_body=$(printf '%s\n' "$input" | jq -r '.tool_input.body // ""')
  # 許容する見出しパターン（Issue #405・PR #456 Layer 1 指摘で強化）: 見出しレベルは `##` 固定
  # ＝ docs/rules/pr-review-flow-summary.md の例示と一致させる。キーワードは run_checks /
  # npm run check のどちらでもよく、各キーワードはバッククォートで囲んでも囲まなくても良い
  # （SSOT は本ファイルの実装を正とし、docs 側はそれに合わせて記述する）。
  #   - ## run_checks 結果         ── `## `run_checks` 結果`
  #   - ## npm run check 結果  ── `## `npm run check` 結果`
  #
  # 判定は awk で単一パスで行い、以下 3 点のすり抜けを塞ぐ（PR #456 敵対的検証で実測）:
  #   1. 見出しが複数回出現する場合、最初の 1 個だけでなく全見出しを走査し、
  #      いずれか 1 つのセクションに表があれば合格にする（1 個目だけ見ると
  #      「後から正しく貼り直した」PR が誤ブロックされていた）
  #   2. フェンスドコードブロック（``` / ~~~）内の見出し・表は判定対象から除外する
  #      （手順書やテンプレートの例示だけで素通りしていた）
  #   3. 全角スペース（U+3000）を半角に正規化してから判定する（IME 由来の全角スペース
  #      1 つで見出しが認識できず、理由不明のままブロックされていた）
  # awk の POSIX 文字クラス依存を避けるため半角スペース/タブのみを空白として扱う。
  pr_body_norm=$(printf '%s\n' "$pr_body" | sed 's/　/ /g')
  has_run_checks_result=$(printf '%s\n' "$pr_body_norm" | awk '
    {
      line = $0
      stripped = line
      sub(/^[ \t]+/, "", stripped)
      if (stripped ~ /^(```+|~~~+)/) { infence = !infence; next }
      if (infence) next
      if (line ~ /^##[ \t]*`?(run_checks|npm run check)`?[ \t]*結果/) { trying = 1; next }
      if (trying) {
        if (line ~ /^[ \t]*\|/) { found = 1; exit }
        if (line ~ /^##[ \t]/) { trying = 0 }
      }
    }
    END { print found + 0 }
  ') || true
  if [ "$has_run_checks_result" -ne 1 ]; then
    hook_block "[pre-pr-create-check] PR 作成をブロックしました。PR 本文に run_checks の結果表が見つかりません。

GitHub Actions が制限中で CI が無いため、\`npm run check\`（= tools/run_checks.sh）の結果が唯一の機械的証跡です。
1. \`npm run check\` を実行する
2. 出力末尾の Markdown サマリー表を、\`## run_checks 結果\` または \`## npm run check 結果\` という見出しを付けて PR 本文に貼る（run_checks / npm run check の部分はバッククォートで囲んでも囲まなくても可。表記ゆれ・意訳は不可）
3. 見出しから次の見出し（##）までの間に表（| 区切りの行）を置く（無関係な別セクションの表・コードフェンス内の例示は不可）
4. PR 作成を再実行する

手順の正本: docs/rules/pr-review-flow-summary.md「PR 作成時の必須事項」項目 0"
  fi
fi

# 5. セルフレビュー機械チェック（docs/rules/self-review-checklist.md・Lv3）
# Error 検出時のみブロック。チェッカー自体の異常（python 不在等・exit>1）ではブロックしない。
# サブディレクトリから gh pr create が実行されてもスキップされないようリポジトリルートで実行する
repo_root=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
check_output=""
if [ -f "$repo_root/tools/self_review_check.py" ]; then
  cd "$repo_root" || exit 0
  check_exit=0
  if command -v timeout >/dev/null 2>&1; then
    check_output=$(timeout 60 python3 tools/self_review_check.py 2>&1) || check_exit=$?
  else
    # macOS 等 timeout 不在環境のフォールバック
    check_output=$(python3 tools/self_review_check.py 2>&1) || check_exit=$?
  fi
  if [ "$check_exit" -eq 1 ]; then
    hook_block "[pre-pr-create-check] セルフレビュー機械チェックで Error を検出したため PR 作成をブロックしました。

${check_output}

Error を修正してから PR 作成を再実行してください（チェックシート: docs/rules/self-review-checklist.md）。"
  elif [ "$check_exit" -ne 0 ]; then
    # self_review_check.py 自体の異常終了（内部未捕捉例外 exit=2 / 外側 `timeout 60` による
    # プロセス kill exit=124 等）。ブロックはしない（fail-open・無人ルーティンを止めない）が、
    # 従来は check_output が誰にも表示されず握りつぶされていた（SP-1 で実際に発生した事故・
    # content/discussions/sp1-review-retro-20260819）ため可視化する。
    check_output="${check_output}
[pre-pr-create-check] self_review_check.py が exit ${check_exit} で異常終了しました。セルフレビュー機械チェックが実質未実行のまま PR 作成が続行されています。原因を確認してください（一時的な負荷等でなければ type:bug Issue 化を検討）。"
  fi
fi

# 5.5. WIP コミット残存チェック（非ブロッキング・警告のみ・Issue #94）
# Stop フックの WIP 自動コミット（メッセージ先頭が "[wip] "）がブランチに残っていないか確認する。
# 🔴 自動 squash / fixup はしない（履歴改変は破壊的で、レビュー中の PR に force-with-lease を
# 強いる副作用が Issue #94 のコメントで複数回観測されている）。警告に留め、対応要否（そのまま
# 出す/手動で reset --soft してまとめる）はセッションの判断に委ねる。
wip_commit_warning=""
_merge_base=$(git merge-base HEAD origin/main 2>/dev/null || echo "")
if [ -n "$_merge_base" ]; then
  _wip_commits=$(git log --oneline "${_merge_base}..HEAD" 2>/dev/null | grep -E '^[0-9a-f]+ \[wip\]' || true)
  if [ -n "$_wip_commits" ]; then
    wip_commit_warning="[pre-pr-create-check] 警告: ブランチに Stop フック由来と思われる [wip] コミットが残っています（Issue #94）。履歴が読みにくくなる可能性があります。必要なら PR 作成前に手動で 'git reset --soft ${_merge_base}' 等でまとめ直してから再度コミットしてください（自動 squash はしません）:
${_wip_commits}"
  fi
fi
unset _merge_base _wip_commits

# 6. Layer 1 セルフレビュー リマインダー（FAIR・全PR必須・非ブロッキング）
# Layer 1（フレッシュ文脈レビュー）は PR 作成「後」に実行する必要があるためここではブロックしない。
# 組み込み /code-review は disable-model-invocation で自律起動不可のため、同名 project スキル
# .claude/skills/code-review/（自前実装・bundled を置換・自律起動可）を Skill(code-review) で実行する。
# 詳細は docs/rules/ai-reviewer-strategy.md。
#
# 出力チャネル（Issue #211・#202 同型修正）:
#   systemMessage はユーザー表示専用で Claude には届かない（公式仕様）。Claude に届けたい
#   内容（Layer 1 実行指示 + self_review_check の Warning）は PreToolUse が公式サポートする
#   hookSpecificOutput.additionalContext で注入する（ツール結果の隣に挿入される）。
#   exit 0（Warning のみ）のとき check_output を破棄していた旧実装の配管バグもここで解消。
_ctx="[pre-pr-create-check] Layer 0 機械ゲート通過。PR 作成後に Layer 1 セルフレビュー（FAIR・全PR必須）を必ず実行してください。自前 code-review スキル（.claude/skills/code-review/・組み込みを置換・自律起動可）を Skill(code-review) で起動して PR 差分をレビューし、指摘は全件 PR の行単位インラインコメントで記録してください（指摘ゼロでも event=COMMENT のレビューを1件投稿・#461）。これはブロックではありません（docs/rules/ai-reviewer-strategy.md）。"
if printf '%s' "$check_output" | grep -qE 'Warning|異常終了'; then
  _ctx="${_ctx}
セルフレビュー Warning（非ブロック・対応要否を判断すること）:
${check_output}"
fi
if [ -n "$wip_commit_warning" ]; then
  _ctx="${_ctx}
${wip_commit_warning}"
fi
jq -n --arg ctx "$_ctx" '{
  "systemMessage": "[pre-pr-create-check] Layer 0 機械ゲート通過（Layer 1 リマインダーと Warning は Claude のコンテキストに注入済み）。",
  "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": $ctx}
}'

exit 0
