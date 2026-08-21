#!/usr/bin/env bash
# workers_build_deploy.sh — Workers Builds の Deploy command 用エントリポイント（D-26 ゲートを移行後も維持する）
#
# 【背景・設計の正本】
# `docs/03_design/infrastructure/cloudflare-infrastructure.md` §8.2.3（P-1 の決定）。
# 議論記録: `content/discussions/prod-deploy-gate-20260821/whiteboard.md`（Issue #288 / #300）。
#
# Workers Builds は main への push をトリガーにするため、そのままでは
# `D-26`（スプリント PR は Sprint Review 判定が accepted になるまでデプロイしない）が
# 呼ばれずに素通りする。本スクリプトを Deploy command に指定することで、
# ビルド環境の中でゲート判定を実行し、通過したときだけ実デプロイへ進む。
#
# 【🔴 ゲートが閉じているときは非ゼロで終了する（fail-closed）】
# 「デプロイをスキップして exit 0 で終える」経路は採らない。Workers Builds が
# 「Deploy command が exit 0 でデプロイしなかった場合にビルドを成功扱いにするか」を
# 公式ドキュメントに明記していないため（2026-08-21 時点で未確認）、その未文書の挙動に
# 依存しない設計にしている。ビルドが赤くなるのは「デプロイ保留中」の可視化であって故障ではない。
#
# 【終了コード】
#   0 = ゲート通過 + デプロイ成功
#   1 = ゲート待機（判定未確定 or rejected のスプリント Issue が残っている）またはデプロイ失敗
#   2 = ゲート判定不能（GitHub API 到達不可等・fail-closed）
#
# 使い方:
#     bash tools/workers_build_deploy.sh
#     bash tools/workers_build_deploy.sh --self-test   # ネットワーク不要のユニットテスト

set -euo pipefail

# テスト時に差し替えるためのフック（既定は実コマンド）
GATE_CMD=${GATE_CMD:-"python3 tools/check_deploy_gate.py"}
DEPLOY_CMD=${DEPLOY_CMD:-"npm run deploy"}

run_gated_deploy() {
  local gate_status=0
  # shellcheck disable=SC2086
  ${GATE_CMD} || gate_status=$?

  if [ "${gate_status}" -ne 0 ]; then
    echo "[workers-build-deploy] デプロイを実行しません（ゲート終了コード: ${gate_status}）。" >&2
    echo "[workers-build-deploy] 1=待機（Sprint Review 未確定 or rejected）/ 2=判定不能（fail-closed）。" >&2
    echo "[workers-build-deploy] ビルドが赤くなるのは想定どおりの挙動です（本番は更新されていません）。" >&2
    return "${gate_status}"
  fi

  echo "[workers-build-deploy] ゲート通過。デプロイを実行します。"
  # shellcheck disable=SC2086
  ${DEPLOY_CMD}
}

self_test() {
  local failures=0

  assert_status() {
    local label="$1" expected="$2" actual="$3"
    if [ "${expected}" = "${actual}" ]; then
      echo "  ok   ${label}（exit ${actual}）"
    else
      echo "  FAIL ${label}: expected exit ${expected}, got ${actual}"
      failures=$((failures + 1))
    fi
  }

  echo "self-test: workers_build_deploy.sh"

  local tmpdir
  tmpdir=$(mktemp -d)
  local marker="${tmpdir}/deployed"

  # 終了コードを固定で返すスタブ（GATE_CMD/DEPLOY_CMD は空白区切りで語分割されるため、
  # スタブは 1 語のパスで渡す）
  make_stub() {
    local path="$1" code="$2"
    printf '#!/usr/bin/env bash\nexit %s\n' "${code}" > "${path}"
    chmod +x "${path}"
  }
  make_stub "${tmpdir}/gate_wait" 1
  make_stub "${tmpdir}/gate_unknown" 2
  make_stub "${tmpdir}/deploy_fail" 1
  printf '#!/usr/bin/env bash\ntouch "%s"\n' "${marker}" > "${tmpdir}/deploy_ok"
  chmod +x "${tmpdir}/deploy_ok"

  # 1. ゲート通過（exit 0）ならデプロイを実行し 0 で終わる
  local status=0
  GATE_CMD="true" DEPLOY_CMD="${tmpdir}/deploy_ok" run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "ゲート通過ならデプロイする" 0 "${status}"
  if [ -f "${marker}" ]; then
    echo "  ok   デプロイコマンドが実行された"
    rm -f "${marker}"
  else
    echo "  FAIL デプロイコマンドが実行されていない"
    failures=$((failures + 1))
  fi

  # 2. ゲート待機（exit 1）ならデプロイせず 1 で終わる
  status=0
  GATE_CMD="${tmpdir}/gate_wait" DEPLOY_CMD="${tmpdir}/deploy_ok" run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "ゲート待機なら 1 を伝播する" 1 "${status}"
  if [ -f "${marker}" ]; then
    echo "  FAIL 待機なのにデプロイコマンドが実行された"
    failures=$((failures + 1))
    rm -f "${marker}"
  else
    echo "  ok   待機時はデプロイコマンドを実行しない"
  fi

  # 3. ゲート判定不能（exit 2）ならデプロイせず 2 で終わる（fail-closed）
  status=0
  GATE_CMD="${tmpdir}/gate_unknown" DEPLOY_CMD="${tmpdir}/deploy_ok" run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "判定不能なら 2 を伝播する（fail-closed）" 2 "${status}"
  if [ -f "${marker}" ]; then
    echo "  FAIL 判定不能なのにデプロイコマンドが実行された"
    failures=$((failures + 1))
    rm -f "${marker}"
  else
    echo "  ok   判定不能時はデプロイコマンドを実行しない"
  fi

  # 4. デプロイ自体が失敗したら非ゼロで終わる
  status=0
  GATE_CMD="true" DEPLOY_CMD="${tmpdir}/deploy_fail" run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "デプロイ失敗を握り潰さない" 1 "${status}"

  rm -rf "${tmpdir}"

  if [ "${failures}" -eq 0 ]; then
    echo "self-test: PASS"
    return 0
  fi
  echo "self-test: FAIL（${failures} 件）"
  return 1
}

main() {
  if [ "${1:-}" = "--self-test" ]; then
    self_test
    return $?
  fi
  run_gated_deploy
}

main "$@"
