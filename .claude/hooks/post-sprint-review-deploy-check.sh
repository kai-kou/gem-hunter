#!/bin/bash
# post-sprint-review-deploy-check.sh — Sprint Review 判定コメント投稿直後にデプロイ未実行を検知する
# （Issue #231・`content/discussions/sprint-env-lifecycle-20260820/whiteboard.md` lead 判定 D の副防御）
#
# 背景: 本番デプロイの発火点をマージ直後（Step 6）からスプリントレビュー accepted 後（Step 7）へ
# 移した結果、「判定は投稿されたがデプロイ実行の前にセッションが力尽きた」という新しい中断点が生まれた。
# 主防御は `pr-review-watcher` Step 7 の `進捗:` マーカー拡張 + `sprint-cycle-router` Step 3 の再開判定
# （firing を跨いだクラッシュを拾う）。本フックはその **副防御**: 同一セッション・同一ターン直後に
# デプロイ実行を促すだけの軽量リマインダーであり、主防御を代替しない（セッションが判定投稿の直後に
# 力尽きた場合はこの additionalContext を読むターン自体が来ないため、Step 3 側の再開判定が必須）。
#
# 動作: PostToolUse（matcher: mcp__github__add_issue_comment）で Issue コメント投稿を検知したら
#   1. 投稿本文（tool_input.body）に `## 🔍 Sprint Review 判定` が含まれるか判定する
#      （含まれなければ通常のコメント投稿なので何もしない・exit 0）
#   2. 含まれる場合、`**結果**` / `**デプロイ**` 行を読み、デプロイが必要な判定
#      （accepted、または accepted_with_conditions かつ deploy: yes。デフォルトは yes）かどうかを判定する
#   3. デプロイが必要な判定なら additionalContext で
#      「デプロイ → 疎通確認 → 退役 → 進捗マーカー更新」の実行を促す
#   4. デプロイ不要な判定（rejected、または deploy: no）なら何もしない（exit 0）
#
# 出力経路: PostToolUse は stdout JSON の hookSpecificOutput.additionalContext に対応する
# （docs/rules/hook-events-reference.md §2）。exit 2（ブロック）は使わない — 判定コメントの投稿は
# 既に成功しており、ブロックすべき事象ではないため（`post-merge-publish-check.sh` と同じ方針。
# 知らせるだけで止めない）。
#
# 既知の適用範囲: matcher は `mcp__github__add_issue_comment` のみに絞る（`mcp__github__issue_write`
# は Issue 本体の説明文を書き換える別 API であり、コメント投稿には使わない・ラウンド2 concession）。
# あらゆる Issue コメント投稿で発火するが、本文に判定マーカーが無ければ即 skip するため誤検知の懸念は
# 実害を持たない（`post-merge-publish-check.sh` の `detect_merge()` と同型）。
#
# 入力 (stdin JSON): { "tool_name": "...", "tool_input": {...}, "tool_response": {...} }
# 自己テスト: bash .claude/hooks/post-sprint-review-deploy-check.sh --self-test
set -uo pipefail

# 検知ロジックだけを評価して結果を標準出力に出し、additionalContext の生成を行わないモード（--self-test 用）
DETECT_ONLY="${CLAUDE_HOOK_SPRINT_REVIEW_DEPLOY_DETECT_ONLY:-}"

# ── 検知: このツール呼び出しは「Sprint Review 判定コメントの投稿」で、かつデプロイが要るか ──
# 標準出力に judgement（deploy-needed / no-deploy-needed / skip:<理由>）を出す。副作用は持たない。
detect_review_verdict() {
  local input="$1"
  local tool_name body verdict deploy_flag

  tool_name=$(printf '%s' "$input" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
  if [[ "$tool_name" != "mcp__github__add_issue_comment" ]]; then
    echo "skip:not-comment-tool"; return 0
  fi

  body=$(printf '%s' "$input" | jq -r '.tool_input.body // ""' 2>/dev/null || echo "")
  if [[ "$body" != *"## 🔍 Sprint Review 判定"* ]]; then
    echo "skip:not-verdict"; return 0
  fi

  # 結果行: **結果**: accepted | accepted_with_conditions | rejected
  if [[ "$body" == *"**結果**:"*"rejected"* ]]; then
    verdict="rejected"
  elif [[ "$body" == *"**結果**:"*"accepted_with_conditions"* ]]; then
    verdict="accepted_with_conditions"
  elif [[ "$body" == *"**結果**:"*"accepted"* ]]; then
    verdict="accepted"
  else
    echo "skip:no-result-line"; return 0
  fi

  if [[ "$verdict" == "rejected" ]]; then
    echo "no-deploy-needed:rejected"; return 0
  fi

  # デプロイ行: **デプロイ**: yes | no（未記載時は既定 yes・SKILL.md Step 7-3 の既定値と一致させる）
  if [[ "$body" == *"**デプロイ**:"*"no"* ]]; then
    deploy_flag="no"
  else
    deploy_flag="yes"
  fi

  if [[ "$deploy_flag" == "no" ]]; then
    echo "no-deploy-needed:deploy-no"; return 0
  fi

  echo "deploy-needed:${verdict}"
}

# ── 自己テスト（検知ロジックのみ・ネットワーク非依存）──────────────────────
run_self_test() {
  local pass=0 fail=0
  _case() {
    local desc="$1" want="$2" json="$3"
    local got
    got=$(detect_review_verdict "$json")
    if [[ "$got" == "$want" ]]; then
      pass=$((pass + 1))
    else
      fail=$((fail + 1))
      echo "  ✗ $desc: want=$want got=$got"
    fi
  }

  _case "accepted はデプロイ要" "deploy-needed:accepted" \
    '{"tool_name":"mcp__github__add_issue_comment","tool_input":{"body":"## 🔍 Sprint Review 判定\n**結果**: accepted\n**デプロイ**: yes\n進捗: Sprint Review 判定済み"}}'
  _case "accepted_with_conditions + デプロイ未記載は既定 yes" "deploy-needed:accepted_with_conditions" \
    '{"tool_name":"mcp__github__add_issue_comment","tool_input":{"body":"## 🔍 Sprint Review 判定\n**結果**: accepted_with_conditions\n**次 firing 必須**: なし"}}'
  _case "accepted_with_conditions + デプロイ no はデプロイ不要" "no-deploy-needed:deploy-no" \
    '{"tool_name":"mcp__github__add_issue_comment","tool_input":{"body":"## 🔍 Sprint Review 判定\n**結果**: accepted_with_conditions\n**デプロイ**: no"}}'
  _case "rejected はデプロイ不要" "no-deploy-needed:rejected" \
    '{"tool_name":"mcp__github__add_issue_comment","tool_input":{"body":"## 🔍 Sprint Review 判定\n**結果**: rejected\n**デプロイ**: no"}}'
  _case "判定マーカーが無いコメントは対象外" "skip:not-verdict" \
    '{"tool_name":"mcp__github__add_issue_comment","tool_input":{"body":"通常のコメントです"}}'
  _case "issue_write は対象外（body があっても別API）" "skip:not-comment-tool" \
    '{"tool_name":"mcp__github__issue_write","tool_input":{"body":"## 🔍 Sprint Review 判定\n**結果**: accepted"}}'
  _case "マージ等の無関係ツールは対象外" "skip:not-comment-tool" \
    '{"tool_name":"mcp__github__merge_pull_request","tool_input":{"owner":"acme","repo":"widgets"}}'
  _case "壊れた入力でも落ちない" "skip:not-comment-tool" '{'

  echo "[post-sprint-review-deploy-check --self-test] PASS=$pass FAIL=$fail"
  [[ "$fail" -eq 0 ]]
}

if [[ "${1:-}" == "--self-test" ]]; then
  run_self_test
  exit $?
fi

# ── 本体 ─────────────────────────────────────────────────────────────
input=$(cat 2>/dev/null || true)

# トグル（他フックと同じ命名規則。このレーンだけ止めたいときに使う）
if [[ "${CLAUDE_HOOK_SKIP_SPRINT_REVIEW_DEPLOY_CHECK:-}" == "true" ]]; then exit 0; fi

command -v jq >/dev/null 2>&1 || exit 0

verdict=$(detect_review_verdict "$input")
if [[ -n "$DETECT_ONLY" ]]; then echo "$verdict"; exit 0; fi
[[ "$verdict" == deploy-needed:* ]] || exit 0

result="${verdict#deploy-needed:}"

msg="🚀 Sprint Review 判定（結果: ${result}）を検知しました。**デプロイ: yes** のため、完了報告の前に
\`.claude/skills/pr-review-watcher/SKILL.md\` Step 7-3.5 に従って以下を **このセッションの中で** 完遂してください（ユーザー確認は不要）:
1. \`main\` HEAD で \`npm run check\` を再実行してから \`npm run deploy\`（手順の実体は \`cloudflare-infrastructure.md\` §8.2）
2. 本番 URL の疎通確認
3. 該当スプリント PR の preview alias を退役: \`python3 tools/retire_preview_aliases.py --alias pr-<N>\`
4. 対象 Issue に追加コメントで \`進捗: デプロイ完了（tag: <merge commit SHA>）・退役完了（alias: pr-<N>）。次は retrospective スキル起動\` を投稿
セッションがここで終了した場合でも、次回 firing は \`sprint-cycle-router\` Step 3（デプロイ・退役未完了の検出）が
この判定コメントを読んで再試行します（\`npm run deploy\` / \`retire_preview_aliases.py\` は idempotent）。"

jq -n --arg ctx "$msg" \
  '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
exit 0
