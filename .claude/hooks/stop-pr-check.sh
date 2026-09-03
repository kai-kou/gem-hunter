#!/bin/bash
# Stop hook: PR作成フロー未実行チェック
# push済みブランチにPRがなければClaude に通知する
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"
# shellcheck source=lib/hook_layer1_common.sh
# ベース由来の PostToolUse 観測マーカー（post-pr-confirm-mark.sh）を読むための共通関数。
source "$HOOK_DIR/lib/hook_layer1_common.sh"

# `.git` 共通ディレクトリの解決と stat の GNU/BSD フォールバックは
# lib/wip_guard.sh が既に解いている（同じ「.git 配下の TTL マーカー」という目的）。
# 重複コピーを作らず再利用する（無い環境では下のフォールバックへ落ちる）。
# shellcheck source=lib/wip_guard.sh
[[ -f "$HOOK_DIR/lib/wip_guard.sh" ]] && source "$HOOK_DIR/lib/wip_guard.sh"

# ── PR 確認済みマーカー（Issue #478）─────────────────────────────────────────
#
# 目的: 同一セッション・同一ブランチ・同一 HEAD で PR の実在を確認済みなら、Stop のたびに
#       同じ確認依頼を出さない。
#
# 🔴 マーカーは「リマインドを出したとき」ではなく「Claude が list_pull_requests で PR の実在を
#    確認したとき」にだけ立てる（Issue #478 の明示指定）。設置経路は
#    `bash .claude/hooks/stop-pr-check.sh --mark-confirmed <PR番号>` のみで、フック本体は
#    マーカーを **作らない**。これにより「PR を作ったつもりで作れていなかった」ケースでは
#    Claude がマークできない＝リマインドが従来どおり出続ける（安全側）。
#
# 置き場所: `--git-common-dir`（絶対パス）配下。cwd 相対の `.git/` を使うと
#   ① worktree では `.git` がファイルなので mkdir -p が "Not a directory" で失敗し抑制が効かない
#   ② cwd がサブディレクトリだと偽の `.git/` ディレクトリを作ってしまう（以後その配下が
#      親リポジトリの git status に現れなくなる）
#   の 2 つの実害が出る（PR #772 Layer 1 セルフレビューで実測）。
#
# 寿命: `.git/` 配下は `git clean -fd` の対象外（.claude/hooks/session-start.sh 参照）なので
#   作業コピーが残る限りセッションを跨いで生き残る。よってマーカーのキーに
#   **セッション ID + ブランチ + HEAD sha** を含め、別セッション・追加コミット後には
#   マッチしないようにする（TTL と `find -mtime +1 -delete` で残骸も掃除する）。

# 数値バリデーション済みの TTL（分）を返す。
# 🔴 環境変数を検証せずに算術評価（`[[ $a -lt $TTL ]]` / `(( ))`）へ流すと任意コマンド実行になる
#    （実測: TTL='x[$(touch /tmp/pwn)]' でファイルが生成された）。必ずここを通す。
pr_check_ttl_minutes() {
  local ttl="${PR_CHECK_CONFIRMATION_TTL_MINUTES:-30}"
  [[ "$ttl" =~ ^[0-9]+$ ]] || ttl=30
  printf '%s\n' "$ttl"
}

# ファイル名に使える文字だけに落とす（パス区切り・記号を除去し、長さも制限する）
pr_check_sanitize() {
  printf '%s' "${1:-}" | tr -c 'A-Za-z0-9_-' '-' | cut -c1-80
}

# マーカー格納ディレクトリ（絶対パス）。git リポジトリでなければ非 0
pr_check_marker_dir() {
  local common marker
  if declare -F wip_guard_marker_path >/dev/null 2>&1; then
    marker=$(wip_guard_marker_path ".") || return 1
    common=$(dirname "$marker")
  else
    common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) \
      || common=$(git rev-parse --absolute-git-dir 2>/dev/null) || return 1
  fi
  [[ -n "$common" ]] || return 1
  printf '%s/pr-check-confirmed\n' "$common"
}

# 現在の HEAD（短縮 sha）。コミットが無ければ "nohead"
pr_check_head() {
  git rev-parse --short=12 HEAD 2>/dev/null || printf 'nohead\n'
}

# マーカーのファイル名（セッション ID + ブランチ + HEAD sha）
pr_check_marker_key() { # $1=session id, $2=branch, $3=head sha
  printf '%s__%s__%s\n' \
    "$(pr_check_sanitize "${1:-none}")" "$(pr_check_sanitize "${2:-none}")" "$(pr_check_sanitize "${3:-none}")"
}

# マーカーの mtime（エポック秒）。stat の GNU/BSD 差異は wip_guard 側の実装に寄せる
pr_check_marker_mtime() { # $1 = マーカーパス
  if declare -F wip_guard_marker_mtime >/dev/null 2>&1; then
    wip_guard_marker_mtime "$1"
  else
    stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
  fi
}

# 環境変数側のセッション ID（--mark-confirmed 実行時の既定キー）
pr_check_env_session_id() {
  local sid="${CLAUDE_CODE_SESSION_ID:-}"
  [[ -n "$sid" ]] || sid="nosession"
  printf '%s\n' "$sid"
}

# 確認済みなら 0、未確認（＝リマインドを出すべき）なら 1。
# $1=ブランチ, $2.. = 突き合わせるセッション ID の候補（stdin JSON 由来 / 環境変数由来）
pr_check_is_confirmed() {
  local branch="$1"; shift
  local dir head ttl now sid file content mtime age
  dir=$(pr_check_marker_dir) || return 1
  head=$(pr_check_head)
  ttl=$(pr_check_ttl_minutes)
  now=$(date +%s)
  for sid in "$@"; do
    [[ -n "$sid" ]] || continue
    file="$dir/$(pr_check_marker_key "$sid" "$branch" "$head")"
    [[ -f "$file" ]] || continue
    # 中身が PR 番号でない（空・ゴミ）マーカーは「未確認」とみなす。
    # touch だけで立った空マーカーを確認済みと誤認しないための下限（Issue #478）。
    content=$(head -c 64 "$file" 2>/dev/null | tr -d '[:space:]' || echo "")
    [[ "$content" =~ ^[0-9]+$ ]] || continue
    mtime=$(pr_check_marker_mtime "$file")
    # 算術評価へ流す前に必ず数値検証する（stat 失敗時の文字列混入を遮断）
    [[ "$mtime" =~ ^[0-9]+$ ]] || continue
    age=$(( (now - mtime) / 60 ))
    (( age < 0 )) && age=0
    if (( age < ttl )); then return 0; fi
  done
  return 1
}

# ── ベース由来の PostToolUse 観測マーカー（base#543）─────────────────────────
# post-pr-confirm-mark.sh が「現在ブランチの PR が実在すると確認できた」ツール呼び出しを
# PostToolUse で観測して立てるマーカー。本リポジトリ独自の `--mark-confirmed`（Issue #478）と
# **併存** させる（ベースの移行ノートが下流に求める「置き換えるか両立させるか」の判断結果）。
#   - #478 側: Claude が明示的にコマンドを打つ。セッション + ブランチ + HEAD sha + TTL で厳格に判定
#   - base#543 側: ツール応答の観測で自動。セッション + ブランチ（HEAD・TTL は持たない）
# どちらも「PR の実在を確認できたとき」にしか立たないため、L-103 防御（PR 未作成なら
# リマインドが出続ける）は両経路とも維持される。
pr_check_is_confirmed_by_observation() { # $1=ブランチ, $2.. = セッション ID 候補
  local branch="$1"; shift
  local dir sid
  declare -F hook_pr_confirm_marker_path >/dev/null 2>&1 || return 1
  dir="${CLAUDE_HOOK_PR_MARKER_DIR:-$(git rev-parse --git-dir 2>/dev/null || echo "")}"
  [[ -n "$dir" ]] || return 1
  for sid in "$@"; do
    [[ -n "$sid" ]] || continue
    [[ -f "$(hook_pr_confirm_marker_path "$sid" "$branch" "$dir")" ]] && return 0
  done
  return 1
}

# `--mark-confirmed <PR番号>`: PR の実在を確認できた Claude だけが呼ぶ設置経路
pr_check_mark_confirmed() { # $1 = PR 番号
  local pr="${1:-}" branch dir head file
  if [[ ! "$pr" =~ ^[0-9]+$ ]]; then
    echo "[stop-pr-check] --mark-confirmed には PR 番号（数字のみ）を渡してください: 受け取った値=[${pr}]" >&2
    return 1
  fi
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "[stop-pr-check] git リポジトリ外のためマーカーを設置できません" >&2
    return 1
  fi
  branch=$(git branch --show-current 2>/dev/null || echo "")
  if [[ -z "$branch" ]]; then
    echo "[stop-pr-check] ブランチを特定できないためマーカーを設置できません（detached HEAD）" >&2
    return 1
  fi
  dir=$(pr_check_marker_dir) || { echo "[stop-pr-check] .git 共通ディレクトリを解決できませんでした" >&2; return 1; }
  if ! mkdir -p "$dir" 2>/dev/null; then
    echo "[stop-pr-check] マーカーディレクトリを作成できませんでした: $dir" >&2
    return 1
  fi
  # 古い残骸の掃除（.git 配下に溜め続けない）
  find "$dir" -maxdepth 1 -type f -mtime +1 -delete 2>/dev/null || true
  head=$(pr_check_head)
  file="$dir/$(pr_check_marker_key "$(pr_check_env_session_id)" "$branch" "$head")"
  if ! printf '%s\n' "$pr" >"$file" 2>/dev/null; then
    echo "[stop-pr-check] マーカーを書き込めませんでした: $file" >&2
    return 1
  fi
  echo "[stop-pr-check] PR #${pr} 確認済みマーカーを設置しました（ブランチ ${branch} / HEAD ${head} / TTL $(pr_check_ttl_minutes) 分）: ${file}"
}

if [[ "${1:-}" == "--mark-confirmed" ]]; then
  pr_check_mark_confirmed "${2:-}"
  exit $?
fi

if [[ "${1:-}" == "--self-test" ]]; then
  # 使い捨ての git リポジトリ（ローカル bare を origin にする＝ネットワーク不要）で
  # フック本体を実際に起動し、終了コードを実測する。実リポジトリには一切触れない。
  self_test_fail=0
  ok() { echo "  ok   $1"; }
  ng() { echo "  NG   $1${2:+ / $2}"; self_test_fail=1; }
  expect_rc() { # $1=期待 rc, $2=実 rc, $3=ケース名
    if [[ "$2" == "$1" ]]; then ok "$3"; else ng "$3" "expected rc=$1 got rc=$2"; fi
  }

  HOOK_PATH="$HOOK_DIR/$(basename "${BASH_SOURCE[0]}")"
  REAL_STAT="$(command -v stat || echo /usr/bin/stat)"
  TMP_ROOT="$(mktemp -d)"
  trap 'rm -rf "$TMP_ROOT" 2>/dev/null || true' EXIT

  git init -q --bare "$TMP_ROOT/origin.git"
  git init -q -b feat/selftest "$TMP_ROOT/work" 2>/dev/null || {
    git init -q "$TMP_ROOT/work"; git -C "$TMP_ROOT/work" checkout -q -b feat/selftest; }
  cd "$TMP_ROOT/work"
  git config user.email selftest@example.com
  git config user.name selftest
  git config commit.gpgsign false
  git remote add origin "$TMP_ROOT/origin.git"
  echo one >a.txt && git add a.txt && git commit -q -m one
  git push -q -u origin feat/selftest
  git checkout -q -b feat/other && echo two >b.txt && git add b.txt && git commit -q -m two
  git push -q -u origin feat/other
  git checkout -q feat/selftest

  run_hook() { # $1=stdin session id, $2=env session id → rc を stdout に出す
    local rc
    set +e
    printf '{"stop_hook_active":false,"session_id":"%s"}' "$1" \
      | CLAUDE_CODE_REMOTE=true GITHUB_REPOSITORY=owner/repo \
        CLAUDE_CODE_SESSION_ID="${2:-}" bash "$HOOK_PATH" >/dev/null 2>&1
    rc=$?
    set -e
    printf '%s' "$rc"
  }
  mark() { # $1=PR 番号, $2=env session id → rc を stdout に出す
    local rc
    set +e
    CLAUDE_CODE_SESSION_ID="${2:-}" bash "$HOOK_PATH" --mark-confirmed "$1" >/dev/null 2>&1
    rc=$?
    set -e
    printf '%s' "$rc"
  }
  marker_of() { # $1=session id, $2=branch → マーカーの絶対パス
    printf '%s/%s\n' "$(pr_check_marker_dir)" "$(pr_check_marker_key "$1" "$2" "$(pr_check_head)")"
  }

  MARKER_DIR="$(pr_check_marker_dir)"

  # 1. マーカー無し → リマインド発火（exit 2）。かつリマインドはマーカーを作らない（Issue #478）
  expect_rc 2 "$(run_hook S1 S1)" "マーカー無し → リマインド発火"
  if [[ -d "$MARKER_DIR" ]] && [[ -n "$(ls -A "$MARKER_DIR" 2>/dev/null)" ]]; then
    ng "リマインド発火時にマーカーを作らない" "$MARKER_DIR にファイルが作られた"
  else
    ok "リマインド発火時にマーカーを作らない"
  fi

  # 2. --mark-confirmed 後・TTL 内 → 抑制（exit 0）
  expect_rc 0 "$(mark 772 S1)" "--mark-confirmed 772 が成功する"
  expect_rc 0 "$(run_hook S1 S1)" "確認済み・TTL 内 → 抑制"

  # 3. stdin の session_id が別でも環境変数側が一致すれば抑制（取り違え耐性）
  expect_rc 0 "$(run_hook OTHER S1)" "stdin 不一致・env 一致 → 抑制"
  # 3b. どちらのセッション ID も一致しない → 抑制しない
  expect_rc 2 "$(run_hook S2 S2)" "別セッション → 抑制しない"

  # 3c. ベース由来の PostToolUse 観測マーカー（base#543）でも抑制される（併存経路）
  OBS_MARKER=$(hook_pr_confirm_marker_path S3 feat/selftest "$TMP_ROOT/work/.git")
  expect_rc 2 "$(run_hook S3 S3)" "観測マーカー無しの別セッション → 抑制しない"
  : >"$OBS_MARKER"
  expect_rc 0 "$(run_hook S3 S3)" "観測マーカーあり → 抑制する（base#543 併存）"
  expect_rc 2 "$(run_hook S4 S4)" "他セッションの観測マーカーでは抑制しない"
  rm -f "$OBS_MARKER"
  expect_rc 2 "$(run_hook S3 S3)" "観測マーカー削除後 → 再び抑制しない"

  # 4. マーカーの中身が PR 番号でない → 未確認扱い
  MK="$(marker_of S1 feat/selftest)"
  : >"$MK"
  expect_rc 2 "$(run_hook S1 S1)" "空マーカー → 抑制しない"
  echo "abc" >"$MK"
  expect_rc 2 "$(run_hook S1 S1)" "PR 番号でないマーカー → 抑制しない"
  echo "772" >"$MK"
  expect_rc 0 "$(run_hook S1 S1)" "PR 番号を書き戻すと再び抑制"

  # 5. TTL 超過 → 再リマインド
  touch -d "@$(( $(date +%s) - 7200 ))" "$MK"
  expect_rc 2 "$(run_hook S1 S1)" "TTL 超過（既定 30 分・2 時間前）→ 再リマインド"
  export PR_CHECK_CONFIRMATION_TTL_MINUTES=240
  expect_rc 0 "$(run_hook S1 S1)" "TTL を 240 分に延ばすと同じマーカーで抑制"
  unset PR_CHECK_CONFIRMATION_TTL_MINUTES

  # 6. TTL の不正値 → 既定 30 分へフォールバックし、コマンドが実行されない（算術評価インジェクション）
  # ペイロードは 2 種類試す。`x[...]` は set -u 下では "unbound variable" でフックごと落ちる
  # （リマインドが静かに消える別の実害）。`age[...]` は set -u 下でも実際にコマンドが走る
  # （実測済み）ので、遮断できていることの検証にはこちらが要る。
  for payload_idx in 1 2; do
    PWN="$TMP_ROOT/pwn_selftest_${payload_idx}"
    if [[ "$payload_idx" == "1" ]]; then
      export PR_CHECK_CONFIRMATION_TTL_MINUTES="x[\$(touch $PWN)]"
    else
      export PR_CHECK_CONFIRMATION_TTL_MINUTES="age[\$(touch $PWN)]"
    fi
    expect_rc 2 "$(run_hook S1 S1)" "TTL が不正値（payload ${payload_idx}）でも既定 30 分（2 時間前のマーカー）→ 再リマインド"
    if [[ -e "$PWN" ]]; then
      ng "TTL 経由の算術評価インジェクションを遮断（payload ${payload_idx}）" "$PWN が作られた"
    else
      ok "TTL 経由の算術評価インジェクションを遮断（payload ${payload_idx}）"
    fi
  done
  export PR_CHECK_CONFIRMATION_TTL_MINUTES=abc
  expect_rc 0 "$(mark 772 S1)" "不正 TTL でも --mark-confirmed は成功"
  expect_rc 0 "$(run_hook S1 S1)" "TTL=abc → 既定 30 分で抑制"
  unset PR_CHECK_CONFIRMATION_TTL_MINUTES

  # 7. HEAD が変わった（確認後に追加コミット）→ 再リマインド
  echo more >>a.txt && git add a.txt && git commit -q -m more
  expect_rc 2 "$(run_hook S1 S1)" "HEAD 変更後 → 再リマインド"
  expect_rc 0 "$(mark 772 S1)" "新 HEAD で再マーク"
  expect_rc 0 "$(run_hook S1 S1)" "新 HEAD のマーカーで抑制"

  # 8. 別ブランチ → 抑制されない（feat/other も push 済みなので not_found スキップではない）
  git checkout -q feat/other
  expect_rc 2 "$(run_hook S1 S1)" "別ブランチ → 抑制されない"
  git checkout -q feat/selftest

  # 9. stat の GNU/BSD 両形式で mtime が取れる
  SHIM="$TMP_ROOT/shim"; mkdir -p "$SHIM"
  cat >"$SHIM/stat" <<SHIM_GNU
#!/bin/bash
# GNU 形式のみ対応（BSD 形式 -f は失敗させる）
[[ "\$1" == "-c" ]] || exit 1
exec "$REAL_STAT" "\$@"
SHIM_GNU
  chmod +x "$SHIM/stat"
  ORIG_PATH="$PATH"; export PATH="$SHIM:$PATH"
  expect_rc 0 "$(run_hook S1 S1)" "stat が GNU 形式のみでも抑制が効く"
  cat >"$SHIM/stat" <<SHIM_BSD
#!/bin/bash
# BSD 形式のみ対応（GNU 形式 -c は失敗させる）
[[ "\$1" == "-f" ]] || exit 1
exec "$REAL_STAT" -c %Y "\$3"
SHIM_BSD
  chmod +x "$SHIM/stat"
  expect_rc 0 "$(run_hook S1 S1)" "stat が BSD 形式のみでも抑制が効く"
  export PATH="$ORIG_PATH"; rm -rf "$SHIM"

  # 10. worktree（.git がファイル）でもマーカーが共通 .git 配下に作られる
  git worktree add -q "$TMP_ROOT/wt" -b feat/wt >/dev/null 2>&1
  git -C "$TMP_ROOT/wt" push -q -u origin feat/wt
  MAIN_GIT_DIR="$TMP_ROOT/work/.git"
  (
    cd "$TMP_ROOT/wt"
    [[ -f "$TMP_ROOT/wt/.git" ]] || echo "  NG   worktree の .git がファイルでない（前提崩れ）"
    exit 0
  )
  wt_rc=$(cd "$TMP_ROOT/wt" && mark 772 S1)
  expect_rc 0 "$wt_rc" "worktree で --mark-confirmed が成功"
  wt_head=$(git -C "$TMP_ROOT/wt" rev-parse --short=12 HEAD)
  wt_marker="$MAIN_GIT_DIR/pr-check-confirmed/$(pr_check_marker_key S1 feat/wt "$wt_head")"
  if [[ -f "$wt_marker" ]]; then ok "worktree のマーカーが共通 .git 配下に作られる"; else ng "worktree のマーカーが共通 .git 配下に作られる" "$wt_marker が無い"; fi
  if [[ -d "$TMP_ROOT/wt/.git" ]]; then ng "worktree 配下に偽の .git ディレクトリを作らない" "$TMP_ROOT/wt/.git がディレクトリ化した"; else ok "worktree 配下に偽の .git ディレクトリを作らない"; fi
  wt_rc=$(cd "$TMP_ROOT/wt" && run_hook S1 S1)
  expect_rc 0 "$wt_rc" "worktree でも抑制が効く"

  # 11. --mark-confirmed の入力検証
  expect_rc 1 "$(mark 'abc' S1)" "--mark-confirmed に非数値 → 失敗"
  expect_rc 1 "$(mark '' S1)" "--mark-confirmed に空文字 → 失敗"

  cd "$HOOK_DIR"
  if [[ $self_test_fail -eq 0 ]]; then echo "stop-pr-check: self-test PASS"; fi
  exit $self_test_fail
fi

input=$(cat)

# 再帰防止
stop_hook_active=$(echo "$input" | jq -r '.stop_hook_active // "false"')
if [[ "$stop_hook_active" == "true" ]]; then exit 0; fi

# git リポジトリでなければスキップ
if ! git rev-parse --git-dir >/dev/null 2>&1; then exit 0; fi

current_branch=$(git branch --show-current)

# main / 空 はスキップ（slug 導出より前に判定し、main では slug 警告を出さない）
if [[ -z "$current_branch" ]] || [[ "$current_branch" == "main" ]]; then exit 0; fi

# リポジトリ slug（owner/repo）を動的に導出する。
# 雛形プレースホルダ kai-kou/gem-hunter をハードコードすると、bootstrap で置換し忘れた
# プロジェクトで PR チェックが機能しない（実際に発生・L-103 再発の温床）。
# 優先順: GITHUB_REPOSITORY → gh repo view → origin URL パース。
REPO_SLUG="${GITHUB_REPOSITORY:-}"
# クラウドでは gh repo view が 403（GraphQL・L-114）のため試行せず origin URL パースへ進む
if [[ -z "$REPO_SLUG" ]] && [[ "${CLAUDE_CODE_REMOTE:-}" != "true" ]] && command -v gh >/dev/null 2>&1; then
  REPO_SLUG=$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || echo "")
fi
if [[ -z "$REPO_SLUG" ]]; then
  origin_url=$(git remote get-url origin 2>/dev/null || echo "")
  if [[ -n "$origin_url" ]]; then
    # http(s)://.../<owner>/<repo>(.git) / git@host:<owner>/<repo>(.git) の両形式に対応
    REPO_SLUG=$(printf '%s' "$origin_url" | sed -E 's#(\.git)?/?$##; s#.*[:/]([^/]+/[^/]+)$#\1#')
  fi
fi
# owner/repo 形式に解決できなければ、断定せず「判定不能」警告で明示停止する（不正 API パス
# repos//pulls を組み立てない・サイレント素通りも防ぐ）。
# owner にドットを含むものも弾く（GitHub の owner 名にドットは不可。`host/repo` の単一セグメント
# URL を `github.com/single` 等と誤パースした場合を検知する）。
if [[ -z "$REPO_SLUG" || "$REPO_SLUG" != */* || "${REPO_SLUG%%/*}" == *.* ]]; then
  hook_block "⚠️ PR確認できません: リポジトリ名（owner/repo）を自動検出できませんでした（GITHUB_REPOSITORY 未設定・origin 不正のいずれか）。\`git remote -v\` で origin を確認したうえで、mcp__github__list_pull_requests（クラウド一次経路）または \`gh pr list --head ${current_branch} --state all\`（ローカル）で PR が作成されているか確認してください。"
fi
REPO_OWNER="${REPO_SLUG%%/*}"

# 検証手段の案内文を環境で切り替える。クラウド（CLAUDE_CODE_REMOTE=true）では gh の repo スコープ
# 操作が egress プロキシに 403 でブロックされるため、`gh pr list` を案内しても機能しない（L-114）。
# 公式 MCP（mcp__github__list_pull_requests）を案内する。
if [[ "${CLAUDE_CODE_REMOTE:-}" == "true" ]]; then
  VERIFY_HINT="mcp__github__list_pull_requests(owner=\"${REPO_OWNER}\", repo=\"${REPO_SLUG#*/}\", head=\"${REPO_OWNER}:${current_branch}\", state=\"all\") で PR を確認してください（クラウドでは gh の repo 操作が 403 でブロックされます・L-114）"
else
  VERIFY_HINT="\`gh pr list --head ${current_branch} --state all -R ${REPO_SLUG}\` を手動実行して PR が作成されているか確認してください"
fi

# リモートブランチの存在確認
# branch_check_status: "exists" | "not_found" | "unknown"
# "unknown" = timeout/認証/ネットワーク等で判定不能 → PR チェックに進む（サイレントスキップしない）
branch_check_status="unknown"

git_ls_exit=0
timeout 10s git ls-remote --exit-code --heads origin -- "$current_branch" >/dev/null 2>&1 \
  || git_ls_exit=$?

if [[ $git_ls_exit -eq 0 ]]; then
  branch_check_status="exists"
elif [[ $git_ls_exit -eq 2 ]]; then
  # --exit-code: exit 2 = マッチする ref なし = ブランチが存在しない（ネットワークは正常）
  branch_check_status="not_found"
else
  # 判定不能（timeout/認証/ネットワーク等） → gh api フォールバック（ローカル実行専用）
  # ブランチ名に / を含む場合のためURL エンコードを適用。
  # クラウドでは gh 自体が未導入で repo スコープ REST も 403 のため試行しない（L-114 / #342）。
  if [[ "${CLAUDE_CODE_REMOTE:-}" != "true" ]] && command -v gh >/dev/null 2>&1; then
    branch_api_result=$(timeout 10s gh api \
      "repos/${REPO_SLUG}/branches/$(printf -- '%s' "$current_branch" | jq -Rr @uri)" \
      --jq '.name' 2>/dev/null || echo "")
    if [[ "$branch_api_result" == "$current_branch" ]]; then
      branch_check_status="exists"
    fi
  fi
  # gh 未導入・gh api が空を返した場合（404/timeout/認証エラー）→ unknown のまま
  # PR チェック側に判断を委ねる
fi

# ブランチが存在しないことが確定した場合のみスキップ
# unknown（両方失敗）はサイレントスキップせず PR チェックに進む（L-050 対策）
if [[ "$branch_check_status" == "not_found" ]]; then exit 0; fi

# --- クラウド: PR 確認済みマーカーによる重複抑制（Issue #478）---
# 判定ロジックとマーカー設計はファイル冒頭の pr_check_* 関数群を参照。
# 🔴 ここではマーカーを **作らない**。設置は Claude が PR の実在を確認したあとに
#    `--mark-confirmed <PR番号>` を実行したときだけ行う（Issue #478 の明示指定）。
#    したがって PR が未作成のとき（本来の発火ケース）は従来どおり毎回リマインドが出る。
if [[ "${CLAUDE_CODE_REMOTE:-}" == "true" ]]; then
  # セッション ID は stdin JSON（フックの正）と環境変数（--mark-confirmed 実行時の正）の
  # 両方を候補にする。両者が食い違っても抑制が黙って効かなくなることを防ぐ。
  session_id_stdin=$(printf '%s' "$input" | jq -r '.session_id // ""' 2>/dev/null || echo "")
  session_id_env=$(pr_check_env_session_id)

  if pr_check_is_confirmed "$current_branch" "$session_id_stdin" "$session_id_env"; then
    # 同一セッション・同一ブランチ・同一 HEAD で PR 実在を確認済み → 確認依頼を出さない
    exit 0
  fi

  # ベース由来の PostToolUse 観測マーカー（base#543）でも抑制する（併存・上の関数コメント参照）
  if pr_check_is_confirmed_by_observation "$current_branch" "$session_id_stdin" "$session_id_env"; then
    exit 0
  fi

  hook_block "📋 PR 存在確認をお願いします（クラウドではハーネスから判定できない仕様。gh の導入では解決しません）: ${VERIFY_HINT}
- PR が既にある場合: 確認結果（PR 番号・state）を踏まえてそのまま終了してよい。あわせて \`bash .claude/hooks/stop-pr-check.sh --mark-confirmed <PR番号>\` を実行すると、同じブランチ・同じコミットの間はこの確認依頼を $(pr_check_ttl_minutes) 分抑制します（Issue #478）
- PR が無い場合: pr-review-flow.md に従いセルフレビュー → PR 作成まで進める"
fi

# --- 以下はローカル実行専用（gh が GitHub に直接到達できる環境）---
# PR存在チェック: gh api で確認（timeout付き・リトライ付き）
# --method GET を明示指定（-f フラグ使用時のデフォルト POST を回避）
# state=all + jq フィルタ: open PR と merged PR のみカウント（closed/abandoned PR は除外）

# ローカルで gh が未導入の場合は実行可能な代替手段を案内して終了。
# 固定文言「gh をインストールしてください」だけでは実行不能なため GitHub UI も併記する（#313 / #318）。
if ! command -v gh >/dev/null 2>&1; then
  hook_block "⚠️ PR確認できません: gh が未導入のため PR 存在確認ができません。gh をインストールするか GitHub UI（https://github.com/${REPO_SLUG}/pulls）でブランチ ${current_branch} の PR を確認してください。作成されていない場合はpr-review-flow.mdに従いPRを作成してください。"
fi

total="unknown"
# ローカル実行では gh が GitHub に直接到達できるため repo スコープ REST で実確認する。
# 失敗時は結果が空になり unknown 分岐へ落ちる（サイレント素通りしない・安全側維持）。
for attempt in 1 2; do
  gh_err=$(mktemp)
  result=$(timeout 15s gh api --method GET "repos/${REPO_SLUG}/pulls" \
    -f head="${REPO_OWNER}:${current_branch}" -f state=all -f per_page=100 \
    --jq '[.[] | select(.state == "open" or .merged_at != null)] | length' 2>"$gh_err" || echo "")
  if [[ "$result" =~ ^[0-9]+$ ]]; then
    rm -f "$gh_err"
    total="$result"
    break
  fi
  # 4xx（プロキシ 403 回帰・権限不足等）は決定的失敗なのでリトライしない（即 unknown 分岐へ）
  if grep -qE 'HTTP 4[0-9][0-9]' "$gh_err" 2>/dev/null; then
    rm -f "$gh_err"
    break
  fi
  rm -f "$gh_err"
  [[ $attempt -lt 2 ]] && sleep 2
done

if [[ "$total" == "0" ]]; then
  if [[ "$branch_check_status" == "exists" ]]; then
    # ブランチの存在が確定している場合のみ "push済み" と断定する
    hook_block "⚠️ PR未作成警告: ブランチ ${current_branch} はリモートにpush済みですが、PRがまだ作成されていません。pr-review-flow.md に従い、セルフレビュー → PR作成 → AIレビュー依頼 → レビュー監視を実行してください。

【根本原因対策 L-050】PR作成を報告する前に必ずPR URLを確認してください。"
  else
    # branch_check_status == "unknown": ブランチpush状態が確認できないため断定を避ける
    hook_block "⚠️ PR確認できません: ブランチ ${current_branch} のブランチ存在確認でエラー（timeout/認証/ネットワーク等）が発生したため、PR未作成かどうか断定できません。${VERIFY_HINT}。作成されていない場合はpr-review-flow.mdに従いPRを作成してください。"
  fi
elif [[ "$total" == "unknown" ]]; then
  # 判定不能時（timeout/認証/レート制限/ネットワーク等）はサイレントスキップせず警告を出す（L-050 対策）
  hook_block "⚠️ PR確認できません: ブランチ ${current_branch} のPR存在確認でエラー（timeout/認証/レート制限/ネットワーク等）が発生しました。${VERIFY_HINT}。作成されていない場合はpr-review-flow.mdに従いPRを作成してください。"
fi

exit 0
