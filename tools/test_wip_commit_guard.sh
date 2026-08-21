#!/bin/bash
# WIP 自動コミット抑止ガード（.git/MUTATION_IN_PROGRESS）の回帰テスト（Issue #304）
#
# 事故の実測（2026-08-21・PR #303）: 変異テスト（実装をわざと壊してテストが FAIL に変わるかを
# 確認する検証手法）で実装を壊していた最中に、並行セッションの Stop フックの WIP 自動コミットが
# その一時改変を拾って commit & push した。L-100（未コミット作業が消える）への防御が、逆方向の
# 事故（コミットすべきでない一時状態を取り込む）を生んだ形。
#
# 本テストは「マーカーがあれば抑止し、無ければ従来どおり保全する」ことを、隔離した一時 git
# リポジトリでフックを実際に実行して実測する（bash -n 以上の検証・Issue #194 と同じ方向）。
# 使い方: bash tools/test_wip_commit_guard.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pass=0
fail=0

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

# 隔離リポジトリを作る（作業リポジトリ + そのクローンを origin にする + フック一式のコピー）。
# セットアップでは push しない（フック自身の push だけを観測対象にする）。
make_repo() { # $1 = ルート
  local root="$1"
  git init --quiet "$root/work"
  git -C "$root/work" config user.email test@example.com
  git -C "$root/work" config user.name test
  git -C "$root/work" config commit.gpgsign false
  echo "original" >"$root/work/impl.txt"
  mkdir -p "$root/work/.claude/hooks/lib"
  cp "$REPO_ROOT/.claude/hooks/stop-slack-notify.sh" \
    "$REPO_ROOT/.claude/hooks/pre-compact.sh" \
    "$REPO_ROOT/.claude/hooks/post-compact.sh" "$root/work/.claude/hooks/"
  cp "$REPO_ROOT"/.claude/hooks/lib/*.sh "$root/work/.claude/hooks/lib/" 2>/dev/null || true
  chmod +x "$root/work/.claude/hooks/"*.sh
  git -C "$root/work" add impl.txt .claude
  git -C "$root/work" commit --quiet -m "initial"
  git -C "$root/work" branch -M main
  git clone --quiet --bare "$root/work" "$root/origin"
  git -C "$root/work" remote add origin "$root/origin"
  git -C "$root/work" fetch --quiet origin
  git -C "$root/work" checkout --quiet -b feat/mutation-test
  # 作業ブランチに固有のコミットを 1 つ積む（マージ済み判定でスキップされると
  # 「抑止できた」ように見えてしまい、テストが偽陽性になるため）
  echo "work in progress" >"$root/work/feature.txt"
  git -C "$root/work" add feature.txt
  git -C "$root/work" commit --quiet -m "feature"
  # 変異テスト相当: 追跡ファイルをわざと壊す
  echo "MUTATED" >"$root/work/impl.txt"
}

run_hook() { # $1 = 作業ディレクトリ, $2 = フック名
  (
    cd "$1" && CLAUDE_CODE_REMOTE=true PROJECT_TZ=Asia/Tokyo \
      ./.claude/hooks/"$2" <<<'{"stop_hook_active": false}' >/dev/null 2>&1
  )
  return 0
}

wip_commit_count() { # $1 = 作業ディレクトリ
  git -C "$1" log --oneline | grep -c '\[wip\]' || true
}

age_marker() { # $1 = マーカーパス（TTL 超過状態にする）
  touch -d "3 hours ago" "$1" 2>/dev/null && return 0
  touch -t "$(date -v-3H +%Y%m%d%H%M 2>/dev/null || echo 202001010000)" "$1"
}

HOOKS="stop-slack-notify.sh pre-compact.sh post-compact.sh"

echo "== ケース 1: マーカー無し → 従来どおり WIP 保全される（L-100 の防御を壊さない） =="
for hook in $HOOKS; do
  tmp=$(mktemp -d)
  make_repo "$tmp"
  run_hook "$tmp/work" "$hook"
  if [ "$(wip_commit_count "$tmp/work")" -ge 1 ]; then
    report ok "マーカー無し: $hook が未コミット変更を WIP 保全する"
  else
    report ng "マーカー無し: $hook が未コミット変更を WIP 保全する" "[wip] コミットが作られていない"
  fi
  rm -rf "$tmp"
done

echo "== ケース 2: マーカーあり（新鮮）→ 抑止され、作業ツリーはそのまま残る =="
for hook in $HOOKS; do
  tmp=$(mktemp -d)
  make_repo "$tmp"
  touch "$tmp/work/.git/MUTATION_IN_PROGRESS"
  run_hook "$tmp/work" "$hook"
  count=$(wip_commit_count "$tmp/work")
  dirty=$(git -C "$tmp/work" status --porcelain | wc -l)
  if [ "$count" -eq 0 ] && [ "$dirty" -ge 1 ]; then
    report ok "マーカーあり: $hook が WIP 自動コミットを抑止する"
  else
    report ng "マーカーあり: $hook が WIP 自動コミットを抑止する" "wip コミット=$count / 未コミット=$dirty"
  fi
  rm -rf "$tmp"
done

echo "== ケース 3: マーカーが TTL 超過（置き忘れ）→ 失効し、従来どおり保全される =="
for hook in $HOOKS; do
  tmp=$(mktemp -d)
  make_repo "$tmp"
  touch "$tmp/work/.git/MUTATION_IN_PROGRESS"
  age_marker "$tmp/work/.git/MUTATION_IN_PROGRESS"
  run_hook "$tmp/work" "$hook"
  if [ "$(wip_commit_count "$tmp/work")" -ge 1 ]; then
    report ok "TTL 超過マーカー: $hook が失効して WIP 保全に戻る"
  else
    report ng "TTL 超過マーカー: $hook が失効して WIP 保全に戻る" "置き忘れマーカーが恒久的に保全を無効化している"
  fi
  rm -rf "$tmp"
done

echo "== ケース 5: stop-git-check.sh がマーカー中はコミット要求でブロックしない =="
tmp=$(mktemp -d)
make_repo "$tmp"
cp "$REPO_ROOT/.claude/hooks/stop-git-check.sh" "$tmp/work/.claude/hooks/"
chmod +x "$tmp/work/.claude/hooks/stop-git-check.sh"
git -C "$tmp/work" add .claude >/dev/null 2>&1
git -C "$tmp/work" commit --quiet -m "add stop-git-check"
echo "MUTATED" >"$tmp/work/impl.txt"
(cd "$tmp/work" && ./.claude/hooks/stop-git-check.sh <<<'{"stop_hook_active": false}' >/dev/null 2>&1)
blocked_without_marker=$?
touch "$tmp/work/.git/MUTATION_IN_PROGRESS"
(cd "$tmp/work" && ./.claude/hooks/stop-git-check.sh <<<'{"stop_hook_active": false}' >/dev/null 2>&1)
blocked_with_marker=$?
if [ "$blocked_without_marker" -ne 0 ]; then
  report ok "マーカー無し: 未コミット変更をブロックする（従来動作を維持）"
else
  report ng "マーカー無し: 未コミット変更をブロックする（従来動作を維持）" "exit=$blocked_without_marker"
fi
if [ "$blocked_with_marker" -eq 0 ]; then
  report ok "マーカーあり: コミット要求でブロックしない"
else
  report ng "マーカーあり: コミット要求でブロックしない" "exit=$blocked_with_marker"
fi
rm -rf "$tmp"

echo "== ケース 4: tools/mutation_guard.sh の begin / status / end が往復する =="
tmp=$(mktemp -d)
make_repo "$tmp"
guard="$REPO_ROOT/tools/mutation_guard.sh"
if [ -x "$guard" ]; then
  (cd "$tmp/work" && "$guard" begin >/dev/null 2>&1)
  if [ -f "$tmp/work/.git/MUTATION_IN_PROGRESS" ]; then
    report ok "begin がマーカーを置く"
  else
    report ng "begin がマーカーを置く" "マーカーが作られていない"
  fi
  if (cd "$tmp/work" && "$guard" status >/dev/null 2>&1); then
    report ok "status が有効時に exit 0 を返す"
  else
    report ng "status が有効時に exit 0 を返す" ""
  fi
  (cd "$tmp/work" && "$guard" end >/dev/null 2>&1)
  if [ ! -f "$tmp/work/.git/MUTATION_IN_PROGRESS" ]; then
    report ok "end がマーカーを外す"
  else
    report ng "end がマーカーを外す" "マーカーが残っている"
  fi
  if (cd "$tmp/work" && "$guard" status >/dev/null 2>&1); then
    report ng "status が無効時に exit 1 を返す" "マーカー解除後も有効と判定している"
  else
    report ok "status が無効時に exit 1 を返す"
  fi
else
  report ng "tools/mutation_guard.sh が実行可能である" "ファイルが無い、または実行権限が無い"
fi
rm -rf "$tmp"

echo ""
echo "結果: PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
