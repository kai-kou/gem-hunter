#!/bin/bash
# .env 系ファイルの「何を塞ぎ、何を通すか」の判定を一元化する共有ライブラリ（Issue #493）。
#
# 背景: pre-tool-use-router.sh の `_sfa_env_access`（Bash 経由・第2層）と
# pre-file-tool-env-guard.sh の `_env_guard_verdict`（ファイルツール経由・第2層）が
# 同じ意味論（本物の .env はブロック・ひな形 4 種は通す）を独立した case 文としてコピーしており、
# ひな形の種類を増やすとき片方だけ更新しても各 self-test は自分が持つケース集合しか
# 検証しないため気づけなかった。本ファイルが判定の唯一の実体（SSOT）であり、
# 2 フックはこれを source して使う（意味論は変更しない・純粋なリファクタ）。
#
# tools/check_env_guard_consistency.py がこの関数を実際に bash 経由で呼び出し、
# .claude/settings.json の permissions.deny と矛盾していないか（deny に載っている名前が
# ここでも実際にブロックされるか／ひな形が deny にも紛れ込んでいないか）を検査する。

# hook_env_guard_verdict PATH
# 判定はベース名スコープで行う（サブディレクトリ配置・絶対パス・`./` 付きも捕捉する）。
# 戻り値: 0 = ブロック対象（本物の .env） / 1 = 対象外（ひな形・非 .env）
hook_env_guard_verdict() {
  _heg_base="${1##*/}"
  case "$_heg_base" in
    .env.example|.env.sample|.env.template|.env.dist|.env.example.*) return 1 ;;
    .env|.env.*) return 0 ;;
    *) return 1 ;;
  esac
}

# ひな形として明示的に許可する固定名の一覧（ワイルドカードを持たないもののみ）。
# `.env.example.*`（例: .env.example.ja）は上の case で個別に扱っており、ここには含めない
# （tools/check_env_guard_consistency.py が「settings.json の deny にひな形が紛れていないか」を
# 突き合わせる対象は固定名のみで十分なため）。
hook_env_guard_template_names() {
  cat <<'EOF'
.env.example
.env.sample
.env.template
.env.dist
EOF
}
