#!/usr/bin/env bash
# GitHub Actions が制限中のため、CI をセッション実行の自前チェックへ切り替える（Issue #72）。
# 常に末尾に「PR 本文に貼れる Markdown サマリー」を出力する（--markdown オプションは設けない）。
# 各チェックはタイムアウト付きで実行し、タイムアウトは「チェッカー自体が落ちた」失敗として扱う。
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

TIMEOUT_SEC="${RUN_CHECKS_TIMEOUT:-300}"

# 集計用配列（"name|status|seconds"）
declare -a RESULTS=()
OVERALL_EXIT=0

has_timeout_cmd() {
  command -v timeout >/dev/null 2>&1
}

# run_check <name> <command...>
# 戻り値: RESULTS に記録するだけ（呼び出し元では判定しない）
run_check() {
  local name="$1"
  shift
  local start_ts end_ts elapsed exit_code output

  start_ts=$(date +%s)
  if has_timeout_cmd; then
    output=$(timeout "$TIMEOUT_SEC" "$@" 2>&1)
    exit_code=$?
  else
    output=$("$@" 2>&1)
    exit_code=$?
  fi
  end_ts=$(date +%s)
  elapsed=$((end_ts - start_ts))

  if [ "$exit_code" -eq 124 ]; then
    echo "[run_checks] FAIL: ${name}（${TIMEOUT_SEC}秒でタイムアウト。チェッカー自体が完走できませんでした）"
    echo "${output}"
    RESULTS+=("${name}|FAIL(timeout)|${elapsed}")
    OVERALL_EXIT=1
  elif [ "$exit_code" -ne 0 ]; then
    echo "[run_checks] FAIL: ${name}（exit ${exit_code}）"
    echo "${output}"
    RESULTS+=("${name}|FAIL|${elapsed}")
    OVERALL_EXIT=1
  else
    echo "[run_checks] PASS: ${name}（${elapsed}秒）"
    RESULTS+=("${name}|PASS|${elapsed}")
  fi
}

skip_check() {
  local name="$1"
  local reason="$2"
  echo "[run_checks] SKIP: ${name}（${reason}）"
  RESULTS+=("${name}|SKIP|0")
}

# --- アプリコードの有無を先に判定 ---
# 🔴 SKIP してよいのは「アプリがまだ無い（package.json 自体が無い）」ときだけ。
#    package.json があるのに node_modules が無いのは **依存未インストール = 検査できていない** 状態なので
#    FAIL 扱いにする（未実行と合格が終了コードで区別できないと、CI 不在の今この結果を信用できない）。
HAS_NODE_PROJECT=1
DEPS_MISSING=0
if [ ! -f "$REPO_ROOT/package.json" ]; then
  HAS_NODE_PROJECT=0
elif [ ! -d "$REPO_ROOT/node_modules" ]; then
  HAS_NODE_PROJECT=0
  DEPS_MISSING=1
fi

# 依存未インストールは主要 3 チェックを実行不能にするため、その事実を 1 件の FAIL として記録する
if [ "$DEPS_MISSING" -eq 1 ]; then
  echo "[run_checks] FAIL: 依存関係が未インストール（node_modules が無いため Lint / 型チェック / テストを実行できません。'npm ci' を実行してください）"
  RESULTS+=("依存関係のインストール状態|FAIL|0")
  OVERALL_EXIT=1
fi

# 1. Lint
if [ "$HAS_NODE_PROJECT" -eq 1 ]; then
  run_check "Lint (eslint)" npx eslint
else
  skip_check "Lint (eslint)" "package.json が無い（アプリコード導入前）"
fi

# 2. 型チェック
if [ "$HAS_NODE_PROJECT" -eq 1 ]; then
  run_check "型チェック (tsc --noEmit)" npx tsc --noEmit
else
  skip_check "型チェック (tsc --noEmit)" "package.json が無い（アプリコード導入前）"
fi

# 3. ユニット・結合テスト
if [ "$HAS_NODE_PROJECT" -eq 1 ]; then
  run_check "テスト (vitest run)" npx vitest run
else
  skip_check "テスト (vitest run)" "package.json が無い（アプリコード導入前）"
fi

# 4. 依存規則（クリーンアーキテクチャ）
if [ -f "$REPO_ROOT/tools/check_architecture_boundaries.py" ]; then
  run_check "依存規則 (check_architecture_boundaries.py)" python3 tools/check_architecture_boundaries.py
else
  skip_check "依存規則 (check_architecture_boundaries.py)" "スクリプトが見つかりません"
fi

# 4.5. UI 寸法検査（コントロールサイズ・フォントサイズのトークン化ゲート）
if [ -f "$REPO_ROOT/tools/check_ui_dimensions.py" ]; then
  run_check "UI 寸法検査 (check_ui_dimensions.py)" python3 tools/check_ui_dimensions.py
else
  skip_check "UI 寸法検査 (check_ui_dimensions.py)" "スクリプトが見つかりません"
fi

# 5. CJK Markdown 整形
if [ -f "$REPO_ROOT/tools/check_cjk_markdown.py" ]; then
  run_check "CJK Markdown (check_cjk_markdown.py --changed)" python3 tools/check_cjk_markdown.py --changed
else
  skip_check "CJK Markdown (check_cjk_markdown.py --changed)" "スクリプトが見つかりません"
fi

# 6. セルフレビュー機械チェック
if [ -f "$REPO_ROOT/tools/self_review_check.py" ]; then
  run_check "セルフレビュー機械チェック (self_review_check.py)" python3 tools/self_review_check.py
else
  skip_check "セルフレビュー機械チェック (self_review_check.py)" "スクリプトが見つかりません"
fi

# --- サマリー表 ---
echo ""
echo "===================== run_checks サマリー ====================="
printf "%-45s %-14s %s\n" "チェック" "結果" "所要秒数"
for row in "${RESULTS[@]}"; do
  IFS='|' read -r r_name r_status r_sec <<< "$row"
  printf "%-45s %-14s %s秒\n" "$r_name" "$r_status" "$r_sec"
done
echo "================================================================"

# --- PR 本文に貼れる Markdown サマリー（常に末尾に出力） ---
echo ""
echo "## run_checks 結果"
echo ""
echo "| チェック | 結果 | 所要秒数 |"
echo "|---|---|---|"
for row in "${RESULTS[@]}"; do
  IFS='|' read -r r_name r_status r_sec <<< "$row"
  echo "| ${r_name} | ${r_status} | ${r_sec}秒 |"
done

exit "$OVERALL_EXIT"
