#!/bin/bash
# pre-pr-create-check.sh の run_checks 結果表判定（4.5節）の回帰テスト（Issue #405 / PR #456）
#
# 背景: PR #391/#400 のレトロで「結果表を貼ったのに見出し文字列が期待値と違いブロックされる」
# 事故が判明（Issue #405）。修正の過程で Layer 1 セルフレビュー（PR #456）が以下の穴を
# 敵対的検証で実測した:
#   1. grep -n | head -1 で最初の見出ししか見ないため、見出しが複数回出ると
#      「後から正しく貼り直した」PR まで誤ブロックされる
#   2. フェンスドコードブロック内の見出し+表（手順書の例示）で素通りできる
#   3. 全角スペースの見出しが認識されず、理由不明のままブロックされる
#
# 本テストは、実際のフック（.claude/hooks/pre-pr-create-check.sh）を隔離した一時 git
# リポジトリで実起動し、BLOCK / ALLOW の期待値を固定する（bash -n 以上の実測・#194 方式）。
#
# 使い方: bash tools/test_pr_create_check_guard.sh
#
# 🔴 tools/run_checks.sh への配線は別セッションが並行編集中のため本 PR では行わない
#    （テスト本体の追加までがスコープ。配線は別 Issue で行う）。
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/.claude/hooks/pre-pr-create-check.sh"
pass=0
fail=0

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT" 2>/dev/null || true' EXIT

report() { # $1 = ok/ng, $2 = ケース名, $3 = 補足
  if [ "$1" = "ok" ]; then
    pass=$((pass + 1))
    echo "  ok   $2"
  else
    fail=$((fail + 1))
    echo "  NG   $2"
    [ -n "${3:-}" ] && echo "       $3"
  fi
}

# 隔離リポジトリ: 未コミット・未push チェック（1〜4節）を通過させるため、
# クリーンな状態で origin へ push 済みのブランチを用意する。
setup_repo() {
  local root="$1"
  git init --quiet "$root/work"
  git -C "$root/work" config user.email test@example.com
  git -C "$root/work" config user.name test
  git -C "$root/work" config commit.gpgsign false
  echo hello >"$root/work/README.md"
  git -C "$root/work" add README.md
  git -C "$root/work" commit --quiet -m init
  git init --quiet --bare "$root/bare.git"
  git -C "$root/work" remote add origin "$root/bare.git"
  git -C "$root/work" checkout --quiet -b feat/test-hook
  git -C "$root/work" push --quiet -u origin feat/test-hook
}

# $1 = 作業ディレクトリ, $2 = PR 本文, 標準出力に exit code
run_hook() {
  local workdir="$1" body="$2" json
  json=$(jq -n --arg body "$body" \
    '{tool_name:"mcp__github__create_pull_request", tool_input:{body:$body, head:"feat/test-hook", base:"main"}}')
  (cd "$workdir" && printf '%s' "$json" | bash "$HOOK" >/dev/null 2>&1)
  echo $?
}

new_repo() {
  local root
  root=$(mktemp -d "$TMP_ROOT/case.XXXXXX")
  setup_repo "$root"
  echo "$root/work"
}

check_exit() { # $1 = 期待exit, $2 = 実exit, $3 = ケース名
  if [ "$1" = "$2" ]; then
    report ok "$3"
  else
    report ng "$3" "期待 exit=$1 実際 exit=$2"
  fi
}

echo "== ケース群 A: 許容 4 表記 + 直後の表 → 通過（exit 0） =="
work=$(new_repo)
check_exit 0 "$(run_hook "$work" '## run_checks 結果
| a | b |
|---|---|')" "## run_checks 結果"
check_exit 0 "$(run_hook "$work" '## `run_checks` 結果
| a | b |
|---|---|')" '## `run_checks` 結果（バッククォート付き）'
check_exit 0 "$(run_hook "$work" '## npm run check 結果
| a | b |
|---|---|')" "## npm run check 結果"
check_exit 0 "$(run_hook "$work" '## `npm run check` 結果
| a | b |
|---|---|')" '## `npm run check` 結果（バッククォート付き）'

echo "== ケース群 B: PR #456 で修正した 3 件 =="
check_exit 0 "$(run_hook "$work" '## run_checks 結果
（これから貼ります、まだ準備中）

## run_checks 結果
| check | status |
|---|---|
| lint | pass |')" "見出し重複（1つ目は表なし・2つ目に表あり）→ 通過"

check_exit 2 "$(run_hook "$work" '手順書の例:
```
## run_checks 結果
| check | status |
|---|---|
```')" "コードフェンス内の見出し+表のみ → ブロック"

check_exit 0 "$(run_hook "$work" '## run_checks　結果
| check | status |
|---|---|')" "全角スペースの見出し → 通過"

echo "== ケース群 C: 既存の正しいブロックケース（回帰なきこと） =="
check_exit 2 "$(run_hook "$work" '## run_checks 結果
Ran locally, all green, no time to paste full table now.

## Unrelated section about UI mockups
| Screen | Status |
|---|---|
| Login | Done |')" "無関係な別セクションの表 → ブロック"

check_exit 2 "$(run_hook "$work" '## run_checks 結果
問題ありませんでした。')" "見出しのみで表なし → ブロック"

check_exit 2 "$(run_hook "$work" 'よろしくお願いします。')" "見出しも表もなし → ブロック"

echo "== ケース群 D: 未コミット・未push 検知（1〜4節）に回帰がないこと =="
echo dirty >>"$work/README.md"
check_exit 2 "$(run_hook "$work" '## run_checks 結果
| a | b |
|---|---|')" "未ステージの変更がある PR は結果表があってもブロック"
git -C "$work" checkout --quiet -- README.md

echo ""
echo "結果: PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
