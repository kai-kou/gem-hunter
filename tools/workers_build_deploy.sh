#!/usr/bin/env bash
# workers_build_deploy.sh — Workers Builds の Deploy command 用エントリポイント（D-26 ゲートを移行後も維持する）
#
# 【背景・設計の正本】
# `docs/03_design/infrastructure/cloudflare-infrastructure.md` §8.2.3（P-1 の決定 = `D-32`）。
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
# 【🔴 実行するコマンドを環境変数から読まない】
# ゲート判定コマンドとデプロイコマンドは下記の配列に固定する。環境変数で上書きできるように
# すると、ビルド変数へ `GATE_CMD=true` を 1 行足すだけで `D-26` のゲートを迂回できてしまう
# （Layer 1 セルフレビューで 3 観点が独立に指摘・PR #311）。差し替えは self-test 内でのみ行う。
#
# 【ログ出力の規約】
# `check_deploy_gate.py` は `GH_TOKEN` の値をログ・エラー出力に出さない規約（同ファイル冒頭コメント）。
# 本スクリプトはその出力をそのままビルドログ（ダッシュボードで閲覧可能）へ流すため、
# ゲート側を変更するときはこの規約を必ず維持すること。
#
# 【終了コード】
#   0   = ゲート通過 + デプロイ成功
#   1   = ゲート待機（判定未確定 or rejected のスプリント Issue が残っている）
#   2   = ゲート判定不能（GitHub API 到達不可等・fail-closed）
#   その他 = ゲートまたはデプロイの異常終了（そのコマンドの終了コードがそのまま出る。
#            例: 127 = コマンドが見つからない / 126 = 実行権限なし）
#
# 使い方:
#     bash tools/workers_build_deploy.sh
#     bash tools/workers_build_deploy.sh --self-test   # ネットワーク不要のユニットテスト

set -euo pipefail

# 🔴 環境変数からは読まない（上記「実行するコマンドを環境変数から読まない」を参照）。
# 配列で持つことで語分割・グロブ展開を経由せずに実行する。
GATE_CMD=(python3 tools/check_deploy_gate.py)
DEPLOY_CMD=(npm run deploy)

run_gated_deploy() {
  local gate_status=0
  "${GATE_CMD[@]}" || gate_status=$?

  if [ "${gate_status}" -ne 0 ]; then
    echo "[workers-build-deploy] デプロイを実行しません（ゲート終了コード: ${gate_status}）。" >&2
    case "${gate_status}" in
      1) echo "[workers-build-deploy] 1 = 待機（Sprint Review 判定が未確定、または rejected のスプリント Issue が残っている）。" >&2 ;;
      2) echo "[workers-build-deploy] 2 = 判定不能（GitHub API へ到達できない等・fail-closed）。" >&2 ;;
      *) echo "[workers-build-deploy] 想定外の終了コードです。ゲートコマンドの実行自体に失敗した可能性があります（コマンド不在・実行権限・インタプリタの異常終了を確認してください）。" >&2 ;;
    esac
    echo "[workers-build-deploy] ビルドが赤くなるのは想定どおりの挙動です（本番は更新されていません）。" >&2
    return "${gate_status}"
  fi

  echo "[workers-build-deploy] ゲート通過。デプロイを実行します。"
  "${DEPLOY_CMD[@]}"
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

  # マーカーの有無で「デプロイコマンドが実行されたか」を判定する。
  assert_deployed() {
    local label="$1" should_exist="$2"
    if [ "${should_exist}" = "yes" ] && [ -f "${marker}" ]; then
      echo "  ok   ${label}"
    elif [ "${should_exist}" = "no" ] && [ ! -f "${marker}" ]; then
      echo "  ok   ${label}"
    else
      echo "  FAIL ${label}"
      failures=$((failures + 1))
    fi
    rm -f "${marker}"
  }

  echo "self-test: workers_build_deploy.sh"

  local tmpdir marker
  tmpdir=$(mktemp -d)
  marker="${tmpdir}/deployed"

  make_stub() {
    printf '#!/usr/bin/env bash\nexit %s\n' "$2" > "$1"
    chmod +x "$1"
  }
  make_stub "${tmpdir}/gate_ok" 0
  make_stub "${tmpdir}/gate_wait" 1
  make_stub "${tmpdir}/gate_unknown" 2
  make_stub "${tmpdir}/deploy_fail" 1
  printf '#!/usr/bin/env bash\ntouch "%s"\n' "${marker}" > "${tmpdir}/deploy_ok"
  chmod +x "${tmpdir}/deploy_ok"
  # 既定値と同じ「実行ファイル + 引数」の 2 要素構成でも動くことを確かめるためのスタブ
  printf '#!/usr/bin/env bash\nexit "$1"\n' > "${tmpdir}/gate_with_arg"
  chmod +x "${tmpdir}/gate_with_arg"

  local status

  # 1. ゲート通過（exit 0）ならデプロイを実行し 0 で終わる
  status=0
  GATE_CMD=("${tmpdir}/gate_ok")
  DEPLOY_CMD=("${tmpdir}/deploy_ok")
  run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "ゲート通過ならデプロイする" 0 "${status}"
  assert_deployed "デプロイコマンドが実行された" yes

  # 2. ゲート待機（exit 1）ならデプロイせず 1 で終わる
  status=0
  GATE_CMD=("${tmpdir}/gate_wait")
  DEPLOY_CMD=("${tmpdir}/deploy_ok")
  run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "ゲート待機なら 1 を伝播する" 1 "${status}"
  assert_deployed "待機時はデプロイコマンドを実行しない" no

  # 3. ゲート判定不能（exit 2）ならデプロイせず 2 で終わる（fail-closed）
  status=0
  GATE_CMD=("${tmpdir}/gate_unknown")
  DEPLOY_CMD=("${tmpdir}/deploy_ok")
  run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "判定不能なら 2 を伝播する（fail-closed）" 2 "${status}"
  assert_deployed "判定不能時はデプロイコマンドを実行しない" no

  # 4. デプロイ自体が失敗したら非ゼロで終わる
  status=0
  GATE_CMD=("${tmpdir}/gate_ok")
  DEPLOY_CMD=("${tmpdir}/deploy_fail")
  run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "デプロイ失敗を握り潰さない" 1 "${status}"

  # 5. ゲートコマンドが存在しない（exit 127 相当）ときもデプロイしない
  status=0
  GATE_CMD=("${tmpdir}/does_not_exist")
  DEPLOY_CMD=("${tmpdir}/deploy_ok")
  run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "ゲートコマンド不在なら 127 を伝播する" 127 "${status}"
  assert_deployed "ゲートコマンド不在時はデプロイコマンドを実行しない" no

  # 6. 既定値と同じ「実行ファイル + 引数」の複数要素構成でも正しく実行できる
  #    （配列展開を誤って 1 語に潰す退行を検知する）
  status=0
  GATE_CMD=("${tmpdir}/gate_with_arg" 1)
  DEPLOY_CMD=("${tmpdir}/deploy_ok")
  run_gated_deploy >/dev/null 2>&1 || status=$?
  assert_status "引数付きゲートコマンドを 1 語に潰さない" 1 "${status}"
  assert_deployed "引数付きゲートが待機を返したらデプロイしない" no

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
