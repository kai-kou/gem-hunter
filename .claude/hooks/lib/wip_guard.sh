#!/bin/bash
# WIP 自動コミット抑止ガード（Issue #304）
#
# 背景: L-100 の防御として入れた WIP 自動コミット（Stop / PreCompact / PostCompact）は、
# 「未コミット作業が消える」ことは防ぐが、逆方向の事故 —— **コミットすべきでない一時状態を
# 取り込んでしまう** —— を想定していなかった。変異テスト（実装をわざと壊してテストが FAIL に
# 変わるかを確認する検証手法）の最中に別セッションの Stop フックが走り、符号を反転させた
# 実装がそのまま push された実例がある（2026-08-21・PR #303 / L-131）。
#
# 仕組み: `$GIT_DIR/MUTATION_IN_PROGRESS` が存在する間、WIP 自動コミットを抑止する。
#   - `.git/` 配下に置くのでコミット対象にならず、`git clean -fd` でも消えない
#   - 置き忘れると L-100 の防御が恒久的に無効化されるため **TTL（既定 2 時間）で自動失効** する
#     （失効後は警告を出しつつ通常どおり WIP コミットする＝ fail-safe 側に倒す）
#   - 設置・解除は `tools/mutation_guard.sh begin` / `end` を使う（手で作らない）
#
# 使い方: source "$(dirname "$0")/lib/wip_guard.sh" してから
#   if wip_guard_active "$REPO_ROOT" "PreCompact"; then ... 抑止 ... fi

WIP_GUARD_MARKER_NAME="MUTATION_IN_PROGRESS"
WIP_GUARD_TTL_SECONDS_DEFAULT=7200

# マーカーの絶対パスを出力する（git リポジトリでなければ非 0 を返す）
# マーカーは **全 worktree 共通の** git ディレクトリ（--git-common-dir）配下に置く。
# linked worktree では --git-dir が `.git/worktrees/<name>` を指すため、そこに置くと
# 「worktree 側で begin したのにメイン側のフックからは見えない」という非対称が生まれる
# （PR #307 Layer 1 セルフレビュー指摘）。変異テストはリポジトリ単位で 1 つ動いていれば
# 十分なので、共通ディレクトリを正本にする。
wip_guard_marker_path() { # $1 = リポジトリルート
  local repo_root="${1:-.}" git_dir
  git_dir=$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || git_dir=""
  if [ -z "$git_dir" ]; then
    # 古い git（--path-format 非対応）向けのフォールバック
    git_dir=$(git -C "$repo_root" rev-parse --git-common-dir 2>/dev/null) \
      || git_dir=$(git -C "$repo_root" rev-parse --git-dir 2>/dev/null) || return 1
    case "$git_dir" in
      /*) ;;
      *) git_dir="$repo_root/$git_dir" ;;
    esac
  fi
  printf '%s/%s\n' "$git_dir" "$WIP_GUARD_MARKER_NAME"
}

# マーカーの更新時刻（エポック秒）を出力する。取得できなければ 0
wip_guard_marker_mtime() { # $1 = マーカーパス
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
}

# 抑止すべきなら 0、通常どおり WIP コミットしてよいなら 1 を返す。
# 抑止時・失効時はいずれも理由を stderr に出す（サイレントに挙動を変えない）。
wip_guard_active() { # $1 = リポジトリルート, $2 = ログ用ラベル
  local repo_root="${1:-.}" label="${2:-wip-guard}" marker ttl age now mtime
  marker=$(wip_guard_marker_path "$repo_root") || return 1
  [ -f "$marker" ] || return 1

  ttl="${WIP_GUARD_TTL_SECONDS:-$WIP_GUARD_TTL_SECONDS_DEFAULT}"
  now=$(date +%s)
  mtime=$(wip_guard_marker_mtime "$marker")
  age=$((now - mtime))

  if [ "$age" -ge "$ttl" ]; then
    echo "[$label] ⚠️ 変異テストマーカー（${marker}）が TTL ${ttl} 秒を超過しているため失効させ、通常どおり WIP 自動コミットします。作業中なら 'tools/mutation_guard.sh begin' で置き直し、終わっているなら 'end' で外してください（Issue #304 / L-131）" >&2
    return 1
  fi

  echo "[$label] 変異テスト等の一時改変中（マーカー: ${marker}・経過 ${age} 秒）のため WIP 自動コミットを抑止しました。作業ツリーはそのまま保持しています（Issue #304 / L-131）" >&2
  return 0
}

# フックからの定型呼び出し（存在確認・リポジトリルート解決を含む）。
# 各フックが同じ 5 行をコピペすると、引数や解決方法の差異が静かに混入するため
# （PR #307 Layer 1 セルフレビュー指摘）、呼び出し側は本関数だけを使う。
wip_guard_active_here() { # $1 = ログ用ラベル, $2 = リポジトリルート（省略時は cwd から解決）
  local repo_root="${2:-}"
  if [ -z "$repo_root" ]; then
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || return 1
  fi
  wip_guard_active "$repo_root" "${1:-wip-guard}"
}
