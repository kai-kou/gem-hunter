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

# run_check_timeout <name> <timeout_sec> <command...>
# 戻り値: RESULTS に記録するだけ（呼び出し元では判定しない）
run_check_timeout() {
  local name="$1"
  local timeout_sec="$2"
  shift 2
  local start_ts end_ts elapsed exit_code output

  start_ts=$(date +%s)
  if has_timeout_cmd; then
    output=$(timeout "$timeout_sec" "$@" 2>&1)
    exit_code=$?
  else
    output=$("$@" 2>&1)
    exit_code=$?
  fi
  end_ts=$(date +%s)
  elapsed=$((end_ts - start_ts))

  if [ "$exit_code" -eq 124 ]; then
    echo "[run_checks] FAIL: ${name}（${timeout_sec}秒でタイムアウト。チェッカー自体が完走できませんでした）"
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

# run_check <name> <command...>
# 既定タイムアウト（$TIMEOUT_SEC）を使う従来ラッパー。
run_check() {
  local name="$1"
  shift
  run_check_timeout "$name" "$TIMEOUT_SEC" "$@"
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

# 3.5. E2E テスト (Playwright)
# 🔴 ビルドを含み重いため Vitest とは別ステップにし、専用タイムアウトを持つ。
#    RUN_CHECKS_TIMEOUT（既定 300 秒）を流用すると Lint/型/vitest と取り合いになるため個別の env を持つ。
#    既定値の根拠: 内側の webServer（`next build && next start`）の起動上限 180 秒（playwright.config.ts）
#    + テスト実行時間の余裕を足した 600 秒。180 秒ぎりぎりでビルドが終わる遅い環境でも、
#    外側のこのタイムアウトが先に発火してテストの正常進行を FAIL(timeout) と誤報告しないようにする。
E2E_TIMEOUT_SEC="${RUN_CHECKS_E2E_TIMEOUT:-600}"
if [ "${SKIP_E2E:-0}" = "1" ]; then
  skip_check "E2E (playwright test)" "SKIP_E2E=1 が指定されたためスキップしました。黙って緑にしないための明示表示"
elif [ "$HAS_NODE_PROJECT" -eq 0 ]; then
  skip_check "E2E (playwright test)" "package.json が無い（アプリコード導入前）"
elif [ ! -d "$REPO_ROOT/node_modules/@playwright/test" ]; then
  # 🔴 package.json はある = アプリコード導入済みなのに @playwright/test が無いのは
  #    「依存未インストール = 検査できていない」状態（上記 DEPS_MISSING と同じ扱い）。
  #    Lint/型/vitest は同条件で FAIL するのに E2E だけ黙って緑にしない（本ファイル冒頭のポリシー）。
  echo "[run_checks] FAIL: E2E (playwright test)（@playwright/test が未インストールのため実行できません。'npm ci' を実行してください）"
  RESULTS+=("E2E (playwright test)|FAIL|0")
  OVERALL_EXIT=1
else
  run_check_timeout "E2E (playwright test)" "$E2E_TIMEOUT_SEC" npx playwright test
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

# 4.6. カラートークン コントラスト検査（E-9 / NFR-13）
if [ -f "$REPO_ROOT/tools/check_contrast.py" ]; then
  run_check "配色コントラスト検査 (check_contrast.py)" python3 tools/check_contrast.py
else
  skip_check "配色コントラスト検査 (check_contrast.py)" "スクリプトが見つかりません"
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
