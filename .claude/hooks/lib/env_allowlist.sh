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
  # 大文字小文字を正規化してから判定する（Issue #1031-2）。`.ENV` / `.Env.Local` のような
  # 表記が case のパターンをすり抜けるのを防ぐ（大文字小文字を区別しない FS では実在しうる）。
  # 同一系統の `pre-tool-use-router.sh` の `_sensitive_file_access` と同じ正規化に揃える。
  _heg_base=$(printf '%s' "$_heg_base" | tr '[:upper:]' '[:lower:]')
  case "$_heg_base" in
    # ひな形は固定 4 種の完全一致に限る。
    .env.example|.env.sample|.env.template|.env.dist) return 1 ;;
    # 唯一の例外はロケール変種（2 文字の言語コード。例: .env.example.ja / .env.example.en）。
    # 旧実装の `.env.example.*` は「ひな形を騙る任意の名前」（.env.example.secret /
    # .env.example.prod-actual）を無条件で通していた（Issue #1031-1）。
    .env.example.[a-z][a-z]) return 1 ;;
    .env|.env.*) return 0 ;;
    *) return 1 ;;
  esac
}

# ひな形として明示的に許可する固定名の一覧（ワイルドカードを持たないもののみ）。
# `.env.example.[a-z][a-z]`（例: .env.example.ja）は上の case で個別に扱っており、ここには含めない
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

# --- self-test（デグレ検証: bash .claude/hooks/lib/env_allowlist.sh --self-test）---
# 期待値表（Issue #1031）。`hook_env_guard_verdict` の本番実装をそのまま呼び、
# 「ブロックすべき / 通すべき」の両方向を検証する。
# 形式: "<期待>|<パス>"（block = ブロック対象 / allow = 対象外）
hook_env_guard_self_test_cases() {
  cat <<'EOF'
block|.env
block|.env.local
block|.env.production
block|.env.prod
block|.env.ci
block|.env.qa
block|config/.env.docker
block|/home/user/gem-hunter/.env.staging
block|./.env
block|.env.
block|.ENV
block|.Env.Local
block|.eNv.PRODUCTION
block|path/to/.ENV
block|/abs/path/.ENV.PRODUCTION
block|.env.example.secret
block|.env.example.prod-actual
block|.ENV.EXAMPLE.SECRET
block|.env.example.j
block|.env.example.jpn
block|.env.example.ja.local
block|.env.notes.md
allow|.env.example
allow|.env.sample
allow|.env.template
allow|.env.dist
allow|.env.example.ja
allow|.env.example.en
allow|.ENV.EXAMPLE
allow|.Env.Example.Ja
allow|.environment
allow|.env-notes.md
allow|environment.ts
allow|README.md
allow|docs/rules/env-vars.md
allow|src/infrastructure/github/oauth.ts
allow|
EOF
}

hook_env_guard_self_test() {
  _hegst_fail=0
  _hegst_block=0
  _hegst_allow=0
  while IFS='|' read -r _hegst_want _hegst_path; do
    [ -n "$_hegst_want" ] || continue
    if hook_env_guard_verdict "$_hegst_path"; then
      _hegst_got="block"
    else
      _hegst_got="allow"
    fi
    if [ "$_hegst_want" != "$_hegst_got" ]; then
      echo "[env-allowlist][self-test] FAIL: '$_hegst_path' は $_hegst_want のはずが $_hegst_got" >&2
      _hegst_fail=1
    fi
    if [ "$_hegst_want" = "block" ]; then
      _hegst_block=$((_hegst_block + 1))
    else
      _hegst_allow=$((_hegst_allow + 1))
    fi
  done <<EOF
$(hook_env_guard_self_test_cases)
EOF

  # ひな形一覧（hook_env_guard_template_names）は全件が実際に通ること（定義の自己矛盾検出）
  while IFS= read -r _hegst_tmpl; do
    [ -n "$_hegst_tmpl" ] || continue
    if hook_env_guard_verdict "$_hegst_tmpl"; then
      echo "[env-allowlist][self-test] FAIL: ひな形 '$_hegst_tmpl' がブロック対象になっている" >&2
      _hegst_fail=1
    fi
  done <<EOF
$(hook_env_guard_template_names)
EOF

  if [ "$_hegst_fail" -eq 0 ]; then
    echo "[env-allowlist][self-test] OK（ブロック ${_hegst_block} 件 / 通過 ${_hegst_allow} 件）"
    return 0
  fi
  return 1
}

# 直接実行されたときだけ self-test を走らせる（source 経由では何もしない）。
# `${BASH_SOURCE[0]}` は source 時にこのファイル自身、直接実行時は "$0" と一致する。
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  case "${1:-}" in
    --self-test) hook_env_guard_self_test; exit $? ;;
  esac
fi
