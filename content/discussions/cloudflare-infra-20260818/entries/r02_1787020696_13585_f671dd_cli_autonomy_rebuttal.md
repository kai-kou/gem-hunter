<!--entry
author: cli_autonomy
round: 2
kind: rebuttal
ts: 2026-08-18T11:38:16+09:00
-->

## Round 2: rebuttal（`cli_autonomy`）

### 1. `privacy_lockin` の R2 + D1/DO incremental cache — CLI 手順の実測とINF-4判定

**結論: ステップは増えるが一時的（bootstrap）で完結し、`INF-4`（定常運用ゼロ）は破れない。ただし `privacy_lockin` に 1 点、重要な見落としを指摘する。**

前提として round 1 で私が示した「preview は per-PR で別 Worker を作らず、1 つの共有 preview Worker のバージョン群として扱う」設計を維持する限り、R2/D1/DO の bootstrap は **PR 数に比例しない**。増える具体コマンドは以下（すべて非対話・一度きり）:

```bash
npx wrangler r2 bucket create gem-hunter-cache-preview
npx wrangler r2 bucket create gem-hunter-cache-production
npx wrangler d1 create gem-hunter-tagcache-preview --json
npx wrangler d1 create gem-hunter-tagcache-production --json
npx wrangler d1 migrations apply gem-hunter-tagcache-preview --remote
npx wrangler d1 migrations apply gem-hunter-tagcache-production --remote
```
→ **+6 コマンド、+2 環境ぶんの `wrangler.jsonc` バインディング追記（1 回コミット）**。`DOShardedTagCache` を選ぶ場合は D1 の create/migrate 4 行が不要になり（DO namespace は `wrangler.jsonc` の `durable_objects` バインディング定義だけで初回デプロイ時に自動生成される）、**むしろ D1 案より CLI ステップは少ない**。ここは cost/design 側の判断材料として投げる。

定常運用（`INF-4` の射程）で人手が要る場面は探した限りゼロ: D1 のスキーマ変更（OpenNext のバージョンアップ時のみ発生・稀）は `wrangler d1 migrations apply` を **CI ジョブに 1 行入れておけば** デプロイのたびに自動追従する。R2 バケットは保守レス。よって `INF-4` は守れる、という round 1 の私の立場を維持する。

**ただし `privacy_lockin` への指摘（見落とし 1 点）**: 研究メモ §3.1 に **「R2 は有効化に支払い方法の登録が必要」**（🔴）とある。これは Free プラン内の話であり、CPU ms とは無関係。つまり **R2 + D1/DO 案を採用した瞬間、`cost_guard` の CPU 実測ゲートを待たずに `A-6`（カード登録）が発生する**。「Workers Caching + Cache-Control のみ」（round 1 §5 の 1 行構成）なら A-6 はゼロのまま `SP-1` に進める。この非対称性は `privacy_lockin` の主張には明記されていなかったので、`§14` の A-6 依頼事項に **「R2 有効化」を独立した 3 件目の A-6 として追加** することを提案する（`cost_guard` の 2 件と束ねて一度にユーザーへ確認するのが CP-6 上も効率的）。

### 2. `cost_guard` の Free→Paid 判定式 — CLI 側で何が変わるか

**support（大筋で支持）+ 1 点訂正。** `cost_guard` の「実測ゲート → 判定基準に従い確認なしで切り替え」は CLI/自律運用の観点からもそのまま成立する。**訂正点**: Free→Paid の切り替えそのものは **wrangler / API に「プラン変更」コマンドが存在しない**（研究メモにも記載なし。既知の Cloudflare API にも billing plan upgrade のエンドポイントはなく、Dashboard の課金画面が唯一の経路）。つまり Claude 側が「自律的に切り替える」とは正確には **「切り替えの前提条件を先に全部整えておき、人間のカード登録クリック 1 回だけを残す」** という意味になる。

Claude が非対話で完結できること:
- `wrangler.jsonc` に **安全キャップとして** `"limits": {"cpu_ms": N}` を追加する（Paid化で Free の構造的ハードキャップ = HTTP 1027 停止が消えるため、`cost_guard` が指摘した「denial-of-wallet 対策」を **Paid切替と同じコミットで即座に埋める**。これは switch の *必須条件* ではなく Claude が能動的に足す残余リスク対策）
- デプロイコマンド（`versions upload` / `versions deploy`）は Free/Paid で **一切変わらない**
- APIトークンのスコープも Free/Paid で変わらない（再発行不要）— `whoami` 疎通確認だけで Paid 移行後も継続動作を確認できる

Claude が完結できないこと（`A-6` として残る）:
- 支払い方法の登録そのもの（Dashboard 操作）
- 「Free → Paid」への切替ボタン押下自体（API 経路が存在しないため CLI では代行不可。ここは `cost_guard` の想定より不可分な人間作業）

→ **`cost_guard` の①番の依頼文言を微修正することを提案する**: 「確認なしで切り替えを進めてよいか」ではなく、「実測 NG が確定したら、Claude は `limits.cpu_ms` 設定・監視体制を確認なしで先に整え、**カード登録の実行だけ** を A-6 として即時通知する（それまでの準備作業に承認は不要）」という書き方の方が、CP-6 の「判断は自律・操作だけが人間」という原則に忠実になる。

### 3. 自分の round 1 主張の補強: stdout 正規表現抽出の失敗検知

`SD-1`（PR に開けるプレビュー URL があること）を **サイレントに欠落させない** ため、抽出失敗を CI の赤 X として扱う具体形を出す。

```bash
URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\.workers\.dev' wrangler-out.log | head -1)
if [ -z "$URL" ]; then
  echo "::error::wrangler versions upload did not emit a *.workers.dev URL (stdout format may have changed) — see wrangler-out.log"
  exit 1   # ジョブを fail-closed にする。空URLのままPRコメントへ進ませない
fi

# 到達性チェック（プロパゲーションのラグを許容する軽いリトライ）
for i in 1 2 3; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$URL") && [ "$code" -lt 500 ] && break
  sleep 5
done
[ "$code" -ge 500 ] && { echo "::error::preview URL returned $code after retries: $URL"; exit 1; }

echo "url=$URL" >> "$GITHUB_OUTPUT"
```

さらに **投稿後の自己検証** を追加する（コメント/本文更新そのものの失敗も拾うため）:
```bash
gh pr comment "$PR_NUMBER" --body "Preview: $URL"
gh pr view "$PR_NUMBER" --json comments -q '.comments[].body' | grep -qF "$URL" \
  || { echo "::error::posted comment did not persist the preview URL"; exit 1; }
```

round 1 で「ND-JSON は監査用に並置」と書いたが、これを **一次シグナルではなく検証専用** へ格下げし直す: ND-JSON のパース成功可否は warning のみで exit しない（フィールド名が不確定なため false negative でジョブを落とすリスクの方が大きい）。**fail-closed にするのは正規表現抽出（主経路）と URL 到達性・PR 反映確認（後段）だけ**、というのが round 2 での精緻化。これにより「URL が取れなかったのに緑で通る」経路は構造的に塞がる。
