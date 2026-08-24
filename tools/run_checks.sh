#!/usr/bin/env bash
# 品質チェックの二層構成のうち「層 2（セッション実行）」を担う（Issue #72 / #543・決定ログ D-41）。
# 層 1（高速ゲート）は .github/workflows/quality-checks.yml が Prettier / ESLint / tsc / Vitest を自動実行する。
# 本スクリプトはそれに加えて E2E・Lighthouse a11y ゲートなど CI に載せない重いチェックまで通し、
# PR 作成前の証跡（PR 本文へ貼る Markdown サマリー）を生成する。
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

# 1.5. フォーマッタ
if [ "$HAS_NODE_PROJECT" -eq 1 ]; then
  run_check "Format (prettier --check)" npx prettier --check .
else
  skip_check "Format (prettier --check)" "package.json が無い（アプリコード導入前）"
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
  # 3.55. OpenNext アセット鮮度チェック（Issue #454 / #455 / #457 の再発防止）。
  #       E2E は `next build && next start`（Node.js ランタイム）でアプリを起動するが、
  #       `getCloudflareContext({ async: true })` は NEXT_RUNTIME=nodejs でも wrangler の
  #       `getPlatformProxy()` を実際に呼び出し、`wrangler.jsonc` の `assets.directory`
  #       （`.open-next/assets`）を指す `env.ASSETS` を用意してしまう。`opennextjs-cloudflare build`
  #       を未実行だとこのディレクトリが無く、Gem Index の読み取りが 404 のまま静かに空になり、
  #       E2E が「実装は正しいのに落ちる」形で失敗する。E2E 本体の直前でここに可視の 1 行として
  #       出す（黙って緑にしない・自動ビルドを挟んだ事実がサマリー表に残る）。
  #       playwright.config.ts の webServer 側にも同じスクリプトを配線済み（run_checks.sh を
  #       経由しない直接の `npx playwright test` 実行でも同じ安全網が効く・ロジックは二重実装しない）。
  #       ここで先に鮮度を揃えておけば、webServer 側の呼び出しは再チェックするだけで即終わる。
  OPEN_NEXT_ASSETS_TIMEOUT_SEC="${RUN_CHECKS_OPEN_NEXT_ASSETS_TIMEOUT:-180}"
  if [ ! -d "$REPO_ROOT/node_modules/@opennextjs/cloudflare" ]; then
    echo "[run_checks] FAIL: OpenNext アセット鮮度チェック（@opennextjs/cloudflare が未インストールのため実行できません。'npm ci' を実行してください）"
    RESULTS+=("OpenNext アセット鮮度チェック (ensure_open_next_assets.mjs)|FAIL|0")
    OVERALL_EXIT=1
  else
    run_check_timeout "OpenNext アセット鮮度チェック (ensure_open_next_assets.mjs)" \
      "$OPEN_NEXT_ASSETS_TIMEOUT_SEC" node tools/ensure_open_next_assets.mjs
  fi

  run_check_timeout "E2E (playwright test)" "$E2E_TIMEOUT_SEC" npx playwright test
fi

# 3.6. Lighthouse（Accessibility ゲート・SP-10 / Issue #181）
# 🔴 Accessibility = 100 は blocking、Performance は記録のみ（run_checks.sh 内で判定に使わない）。
#    E2E とは別ステップ・別タイムアウト（RUN_CHECKS_TIMEOUT を流用すると Lint/型/vitest と取り合いになる
#    E2E と同じ理由）。実測 build 5 秒 + start 数秒 + 2 画面 12 秒/回 ≒ 40 秒台のため既定 180 秒で十分な余裕。
LIGHTHOUSE_TIMEOUT_SEC="${RUN_CHECKS_LIGHTHOUSE_TIMEOUT:-180}"
if [ "${SKIP_LIGHTHOUSE:-0}" = "1" ]; then
  skip_check "Lighthouse (Accessibility gate)" "SKIP_LIGHTHOUSE=1 が指定されたためスキップしました。黙って緑にしないための明示表示"
elif [ "$HAS_NODE_PROJECT" -eq 0 ]; then
  skip_check "Lighthouse (Accessibility gate)" "package.json が無い（アプリコード導入前）"
elif [ ! -f "$REPO_ROOT/node_modules/.bin/lighthouse" ]; then
  echo "[run_checks] FAIL: Lighthouse (Accessibility gate)（lighthouse が未インストールのため実行できません。'npm ci' を実行してください）"
  RESULTS+=("Lighthouse (Accessibility gate)|FAIL|0")
  OVERALL_EXIT=1
else
  run_check_timeout "Lighthouse (Accessibility gate)" "$LIGHTHOUSE_TIMEOUT_SEC" node tools/run_lighthouse.mjs
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

# 4.65. --tw-prose-* リテラル色混入検査（Issue #339・書式トークンの gray スケールへの
#       静かなフォールバックを検知する）。まだ --tw-prose-* が 1 つも無くても PASS を返す設計
#       （typography プラグイン導入前でも run_checks.sh を壊さない）。
if [ -f "$REPO_ROOT/tools/check_prose_tokens.py" ]; then
  run_check "Prose トークン検査 (check_prose_tokens.py)" python3 tools/check_prose_tokens.py
  run_check "Prose トークン検査 self-test (check_prose_tokens.py --self-test)" python3 tools/check_prose_tokens.py --self-test
else
  skip_check "Prose トークン検査 (check_prose_tokens.py)" "スクリプトが見つかりません"
fi

# 4.65. ランディングページ（site/）の静的検査（Issue #360）
#       site/ はアプリ本体の検査のどれにも掛からないため、参照切れ・寸法不一致・アンカー切れ・
#       ADR 本数のドリフトをここで止める（ネットワーク不要・決定論的）。
if [ -f "$REPO_ROOT/tools/check_site.py" ]; then
  run_check "LP 静的検査 (check_site.py)" python3 tools/check_site.py
  run_check "LP 静的検査 self-test (check_site.py --self-test)" python3 tools/check_site.py --self-test
else
  skip_check "LP 静的検査 (check_site.py)" "スクリプトが見つかりません"
fi

# 4.7. ADR 記録と README 必須記載のゲート（E-18 / E-19 / NFR-29〜NFR-32 / AC-11）
if [ -f "$REPO_ROOT/tools/check_adr_coverage.py" ]; then
  run_check "ADR / README 記載検査 (check_adr_coverage.py)" python3 tools/check_adr_coverage.py
  run_check "ADR / README 記載検査 self-test (check_adr_coverage.py --self-test)" python3 tools/check_adr_coverage.py --self-test
else
  skip_check "ADR / README 記載検査 (check_adr_coverage.py)" "スクリプトが見つかりません"
fi

# 4.75. レート制限の配線検査（Issue #442 の再発防止）。
#       Cloudflare Rate Limiting は binding 宣言だけでは何も起きず、しかもフェイルオープン設計のため
#       「配線し忘れ」と「正常」が実行時に区別できない。cloudflare-infrastructure.md の適用経路表
#       （<!-- rate-limit-wiring --> マーカー）と実コードを双方向に突き合わせ、app/ 配下の
#       エントリポイント網羅性まで見る。ローカルのファイルしか読まないためネットワーク非依存。
if [ -f "$REPO_ROOT/tools/check_rate_limit_wiring.py" ]; then
  run_check "レート制限配線検査 (check_rate_limit_wiring.py)" python3 tools/check_rate_limit_wiring.py
  run_check "レート制限配線検査 self-test (check_rate_limit_wiring.py --self-test)" python3 tools/check_rate_limit_wiring.py --self-test
else
  skip_check "レート制限配線検査 (check_rate_limit_wiring.py)" "スクリプトが見つかりません"
fi

# 4.8. 副作用のある API ルートのプリフェッチ検査（#145 の再発防止）
if [ -f "$REPO_ROOT/tools/check_prefetchable_side_effects.py" ]; then
  run_check "副作用 GET のプリフェッチ検査 (check_prefetchable_side_effects.py)" python3 tools/check_prefetchable_side_effects.py
else
  skip_check "副作用 GET のプリフェッチ検査 (check_prefetchable_side_effects.py)" "スクリプトが見つかりません"
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

# 7. 運用ツール self-test（ネットワーク不要・PR #235 WARNING）

# OpenNext アセット鮮度チェック self-test（Issue #454 / #455 / #457）。
# 鮮度判定の純関数（checkStaleness / newestMtimeMs）だけを一時ディレクトリで検証し、
# 実ビルド・ネットワークには依存しない（本判定は上の 3.55 で E2E 直前に配線済み）。
if [ -f "$REPO_ROOT/tools/ensure_open_next_assets.mjs" ]; then
  run_check "OpenNext アセット鮮度チェック self-test (ensure_open_next_assets.mjs --self-test)" \
    node tools/ensure_open_next_assets.mjs --self-test
else
  skip_check "OpenNext アセット鮮度チェック self-test (ensure_open_next_assets.mjs --self-test)" "スクリプトが見つかりません"
fi

# wrangler.jsonc 共有パーサ self-test（Layer 1 セルフレビュー WARNING-6・PR #460）。
# trigger_workers_build.py / retire_preview_aliases.py が共有する Worker 名パースの実体。
if [ -f "$REPO_ROOT/tools/wrangler_config.py" ]; then
  run_check "wrangler 設定パーサ self-test (wrangler_config.py --self-test)" python3 tools/wrangler_config.py --self-test
else
  skip_check "wrangler 設定パーサ self-test (wrangler_config.py --self-test)" "スクリプトが見つかりません"
fi

if [ -f "$REPO_ROOT/tools/retire_preview_aliases.py" ]; then
  run_check "退役スクリプト self-test (retire_preview_aliases.py --self-test)" python3 tools/retire_preview_aliases.py --self-test
else
  skip_check "退役スクリプト self-test (retire_preview_aliases.py --self-test)" "スクリプトが見つかりません"
fi

if [ -f "$REPO_ROOT/tools/check_deploy_gate.py" ]; then
  run_check "デプロイゲート self-test (check_deploy_gate.py --self-test)" python3 tools/check_deploy_gate.py --self-test
else
  skip_check "デプロイゲート self-test (check_deploy_gate.py --self-test)" "スクリプトが見つかりません"
fi

if [ -f "$REPO_ROOT/tools/workers_build_deploy.sh" ]; then
  run_check "Workers Builds デプロイ入口 self-test (workers_build_deploy.sh --self-test)" bash tools/workers_build_deploy.sh --self-test
else
  skip_check "Workers Builds デプロイ入口 self-test (workers_build_deploy.sh --self-test)" "スクリプトが見つかりません"
fi

# install スクリプト方針の検査（Issue #497 の再発防止）。
# 本番ビルド環境（npm 12）は install スクリプトを既定でブロックし、巻き上げ頼みの optional peer も
# 入れないため、ローカルの node_modules では動くのに本番ビルドだけ落ちる。allowScripts の網羅と
# 必須の直接依存を lockfile と突き合わせる（ローカルの JSON しか読まないためネットワーク非依存）。
if [ -f "$REPO_ROOT/tools/check_install_scripts_policy.py" ]; then
  run_check "install スクリプト方針検査 (check_install_scripts_policy.py)" python3 tools/check_install_scripts_policy.py
  run_check "install スクリプト方針検査 self-test (check_install_scripts_policy.py --self-test)" python3 tools/check_install_scripts_policy.py --self-test
else
  skip_check "install スクリプト方針検査 (check_install_scripts_policy.py)" "スクリプトが見つかりません"
fi

if [ -f "$REPO_ROOT/tools/check_digest_freshness.py" ]; then
  run_check "ダイジェスト鮮度 self-test (check_digest_freshness.py --self-test)" python3 tools/check_digest_freshness.py --self-test
else
  skip_check "ダイジェスト鮮度 self-test (check_digest_freshness.py --self-test)" "スクリプトが見つかりません"
fi

# 配信シャード（public/data/gem-index/）の静的検査（SP-17・PR #416 セルフレビュー指摘）。
# 索引整合・列定義・行の型・gemIndex 昇順・サイズ予算（D-38 の cold start CPU 予算の保険）を見る。
# ローカルの生成物しか読まないためネットワーク非依存（本判定も self-test も両方配線する）。
if [ -f "$REPO_ROOT/tools/check_gem_shards.py" ]; then
  run_check "Gem シャード検査 (check_gem_shards.py)" python3 tools/check_gem_shards.py
  run_check "Gem シャード検査 self-test (check_gem_shards.py --self-test)" python3 tools/check_gem_shards.py --self-test
else
  skip_check "Gem シャード検査 (check_gem_shards.py)" "スクリプトが見つかりません"
fi

# Gem 候補プール QA / no-op 判定（Issue #458）の self-test。ネットワーク・実データ非依存の
# 純関数だけを検証する（本判定 --check / --no-op は gem-pool-refresh.yml ワークフロー内で実行する）。
if [ -f "$REPO_ROOT/tools/gem_pool_qa.mjs" ]; then
  run_check "Gem 候補プール QA self-test (gem_pool_qa.mjs --self-test)" node tools/gem_pool_qa.mjs --self-test
else
  skip_check "Gem 候補プール QA self-test (gem_pool_qa.mjs --self-test)" "スクリプトが見つかりません"
fi

# GitHub Actions workflow YAML の構文検査（Issue #458）。週次 cron だけだと構文崩れに最大 1 週間
# 気づけないため、PyYAML でパースできるかだけを見る軽量チェック（actionlint 導入は YAGNI・見送り）。
# PyYAML が無い環境・workflow が無い環境では skip_check にする（既存の作法に合わせる）。
if python3 -c "import yaml" >/dev/null 2>&1; then
  if compgen -G "$REPO_ROOT/.github/workflows/*.yml" >/dev/null 2>&1 || compgen -G "$REPO_ROOT/.github/workflows/*.yaml" >/dev/null 2>&1; then
    run_check "GitHub Actions workflow YAML 構文検査" python3 -c '
import glob
import sys

import yaml

paths = sorted(glob.glob(".github/workflows/*.yml") + glob.glob(".github/workflows/*.yaml"))
failed = False
for p in paths:
    try:
        with open(p, encoding="utf-8") as f:
            yaml.safe_load(f)
    except Exception as e:
        print(f"YAML parse error: {p}: {e}")
        failed = True
sys.exit(1 if failed else 0)
'
  else
    skip_check "GitHub Actions workflow YAML 構文検査" ".github/workflows/ 配下に *.yml/*.yaml がありません"
  fi
else
  skip_check "GitHub Actions workflow YAML 構文検査" "PyYAML が未インストール"
fi

# 被覆率測定（SP-17・D-36 / D-37）も --self-test だけを配線する。本測定は GitHub 検索 API を
# 叩くためネットワーク非依存を保てない（run_checks.sh はオフラインで完走できることを保つ）。
if [ -f "$REPO_ROOT/tools/measure_gem_coverage.py" ]; then
  run_check "Gem 被覆率測定 self-test (measure_gem_coverage.py --self-test)" python3 tools/measure_gem_coverage.py --self-test
else
  skip_check "Gem 被覆率測定 self-test (measure_gem_coverage.py --self-test)" "スクリプトが見つかりません"
fi

# 本番乖離検知は「--self-test だけ」を配線する（判定ロジックの退行を機械で守るため）。
# 本判定（`check_prod_drift.py` を引数なしで実行）は本番疎通に依存するので配線しない
# （本番側の一時的な事情で PR が赤くなるのを避ける・Issue #288）。
if [ -f "$REPO_ROOT/tools/check_prod_drift.py" ]; then
  run_check "本番乖離検知 self-test (check_prod_drift.py --self-test)" python3 tools/check_prod_drift.py --self-test
else
  skip_check "本番乖離検知 self-test (check_prod_drift.py --self-test)" "スクリプトが見つかりません"
fi

# Workers Builds 再トリガーの self-test（Issue #451）。本判定（引数なし実行）は Cloudflare API への
# 実疎通とデプロイゲート判定に依存するため配線しない（本番乖離検知 self-test と同じ理由・Issue #288）。
if [ -f "$REPO_ROOT/tools/trigger_workers_build.py" ]; then
  run_check "Workers Builds 再トリガー self-test (trigger_workers_build.py --self-test)" python3 tools/trigger_workers_build.py --self-test
else
  skip_check "Workers Builds 再トリガー self-test (trigger_workers_build.py --self-test)" "スクリプトが見つかりません"
fi

# レーン定義のスキルが実装（決定木・他スキルの手順・hooks）から到達可能かの検査（Issue #377）。
# 本判定（引数なし実行）も文書だけで完結しネットワークに出ないため、self-test と両方を配線する。
# これが赤いときは「レーンマップに書いてあるのに誰も呼ばない」断絶が生まれている。
if [ -f "$REPO_ROOT/tools/check_lane_reachability.py" ]; then
  run_check "レーン到達可能性 (check_lane_reachability.py)" python3 tools/check_lane_reachability.py
  run_check "レーン到達可能性 self-test (check_lane_reachability.py --self-test)" python3 tools/check_lane_reachability.py --self-test
else
  skip_check "レーン到達可能性 (check_lane_reachability.py)" "スクリプトが見つかりません"
fi

# 棚卸しの判定規則（priority 補完の if-then・重複統合の keep 選択・high 比率の上限）の
# self-test だけを配線する（Issue #385）。本判定（引数なし実行）は GitHub API に依存するので
# 配線しない。規則の SSOT はコード側であり、議論記録はその由来を残すだけにする。
if [ -f "$REPO_ROOT/tools/triage_improvements.py" ]; then
  run_check "棚卸し判定規則 self-test (triage_improvements.py --self-test)" python3 tools/triage_improvements.py --self-test
else
  skip_check "棚卸し判定規則 self-test (triage_improvements.py --self-test)" "スクリプトが見つかりません"
fi

# WIP 自動コミット抑止ガードの回帰テスト（Issue #304 / L-131）。
# 隔離した一時 git リポジトリでフックを実行し、変異テスト中の一時改変が拾われないこと・
# マーカーが無ければ従来どおり保全されること・置き忘れが TTL で失効することを実測する。
if [ -f "$REPO_ROOT/tools/test_wip_commit_guard.sh" ]; then
  run_check "WIP 抑止ガード回帰テスト (test_wip_commit_guard.sh)" bash tools/test_wip_commit_guard.sh
else
  skip_check "WIP 抑止ガード回帰テスト (test_wip_commit_guard.sh)" "スクリプトが見つかりません"
fi

# ファイルツール経由の .env アクセスガード self-test（Issue #401 / PR #487）。
# permissions.deny をひな形（.env.example）のために具体名の列挙へ狭めた分、列挙外の変種名
# （.env.prod / .env.ci 等）を本フックが塞いでいることを判定関数の単位で実測する。
if [ -f "$REPO_ROOT/.claude/hooks/pre-file-tool-env-guard.sh" ]; then
  run_check "env ファイルツールガード self-test (pre-file-tool-env-guard.sh --self-test)" \
    bash .claude/hooks/pre-file-tool-env-guard.sh --self-test
else
  skip_check "env ファイルツールガード self-test (pre-file-tool-env-guard.sh --self-test)" "スクリプトが見つかりません"
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
