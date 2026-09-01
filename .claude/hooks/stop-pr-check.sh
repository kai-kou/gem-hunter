#!/bin/bash
# Stop hook: PR作成フロー未実行チェック
# push済みブランチにPRがなければClaude に通知する
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"

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
# 同一セッション・同一ブランチで PR 確認済みなら、確認依頼を繰り返し出さない。
# マーカーは `.git/` 配下に置き（追跡対象を汚さない）、TTL で自動失効。
# 次セッションではマーカーが消えるため安全側へ倒れる。
if [[ "${CLAUDE_CODE_REMOTE:-}" == "true" ]]; then
  MARKER_DIR=".git/pr-check-confirmed"
  # branch 名に / が含まれる場合、ファイル名として使えないので - に置換
  MARKER_FILE="${MARKER_DIR}/${current_branch//\//-}"

  # TTL は環境変数で上書き可（既定 30 分：バックグラウンドタスク fan-out の
  # 多ターン化に対応。セッション内の重複は防ぎ、セッション跨ぎでは再出現）
  TTL_MINUTES="${PR_CHECK_CONFIRMATION_TTL_MINUTES:-30}"

  # マーカーが存在し TTL 内なら、既に確認済みと判定して抑制
  if [[ -f "$MARKER_FILE" ]]; then
    # marker_time を stat で取得（BSD `stat -f%m` と GNU `stat -c%Y` に対応）
    marker_time=$(stat -f%m "$MARKER_FILE" 2>/dev/null || stat -c%Y "$MARKER_FILE" 2>/dev/null || echo 0)
    now=$(date +%s)
    age_minutes=$(( (now - marker_time) / 60 ))
    if [[ $age_minutes -lt $TTL_MINUTES ]]; then
      # 確認済みなので確認依頼を出さずに終了（同一セッション・同一ブランチの重複抑制）
      exit 0
    fi
  fi

  # マーカーなし or TTL 経過 → 確認依頼を出す。
  # リマインドを出した時点でマーカーを置き、TTL 内の再掲を抑制する（Issue #478）。
  # hook_block は stderr 出力後に exit 2 する（lib/hook_block.sh）ため、必ずその「前」に置く。
  # 作成に失敗しても（権限・読み取り専用 .git 等）握りつぶして必ずリマインドへ進む＝安全側に倒れる
  # （マーカーが無い状態＝毎ターン従来どおりリマインドが出るだけで、見逃しは発生しない）。
  # 既存マーカーへの touch は mtime を更新するので、TTL 経過後の再掲でも計測が正しく巻き直る。
  mkdir -p "$MARKER_DIR" 2>/dev/null || true
  touch "$MARKER_FILE" 2>/dev/null || true

  hook_block "📋 PR 存在確認をお願いします（クラウドではハーネスから判定できない仕様。gh の導入では解決しません）: ${VERIFY_HINT}
- PR が既にある場合: 確認結果（PR 番号・state）を踏まえてそのまま終了してよい
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
