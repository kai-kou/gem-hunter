<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: スプリントのプレビュー環境の後始末と、本番デプロイをスプリントレビュー判定に接続する仕組みを設計する（Issue #231）

- 議題ID: `sprint-env-lifecycle-20260820`
- 論点: 飼い主の指示（原文）: 『現時点でスプリントごとの実行環境を用意していますが、古い環境を削除、最新の状態でデプロイされた本番環境のデプロイをする仕組みを構築してください。基本的には以下の流れを考えています / スプリント完了後のスプリントレビューが完了したらスプリントの環境を削除する / スプリントレビューで問題がなければ、本番環境にデプロイして反映させる / 専門チームを組成して対応してください』

【オーケストレーターが実測で確定させた事実（推測ではない）】
1. プレビュー環境は同一 Worker の version + preview alias。PR ごとに `npx wrangler versions upload --preview-alias pr-<N> --tag $SHA` で作る（docs/03_design/infrastructure/cloudflare-infrastructure.md §6.1 / §8.2 / §8.3）。`[env.*]` は使わない（Worker 数を増やさないため）。
2. Cloudflare API `GET /accounts/{account_id}/workers/scripts/gem-hunter/versions` を実際に叩いた結果、version が蓄積しており、各 version の `annotations["workers/alias"]` に `pr-219` `pr-212` 等が入っている（`metadata.has_preview: true`）。後始末の仕組みは現在存在しない。
3. `npx wrangler versions --help` の実出力に delete サブコマンドは無い（view / list / upload / deploy / secret のみ）。wrangler 4.124.0。
4. 公式ドキュメント（developers.cloudflare.com/workers/versions-and-deployments/preview-urls/）の Aliased preview URLs 節に『Aliases may be created during versions upload』『Only the 1000 most recently deployed aliases are retained. When a new alias is created beyond this limit, the least recently deployed alias is deleted』とある。alias 削除コマンドの記述は見つかっていない（REST API 側の削除可否は未確定＝この議論で確定させる対象）。
5. セッションには CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID が供給されており `npx wrangler whoami` は成功する（User API Token）。curl での Cloudflare API 直叩きも成功している。
6. 本番デプロイは現在 `.claude/skills/pr-review-watcher/SKILL.md` の **Step 6（マージ直後の公開反映）** に書かれている。『push まで完遂したら続けてセッションが npm run deploy を実行し本番反映まで完遂する』『deploy 前に main HEAD で npm run check を再実行』『deploy 後は本番 URL の疎通確認』。**Step 7（スプリントレビュー + レトロスペクティブ）はその後** に実行される。つまり現状は『レビュー判定の前にデプロイ済み』。
7. Step 7 はスプリントレビュー判定を Issue コメントに `**結果**: accepted | accepted_with_conditions | rejected` の書式で投稿し、`retrospective` スキルを起動し、対象 Issue をクローズする（rejected / accepted_with_conditions で持ち越しがあるときは open のまま）。発火条件は『マージした PR 本文に Sprint Goal: 行がある』。
8. GitHub Actions は制限中で使えない（D-23）。deploy-preview.yml / deploy-production.yml は撤去済み。CI もデプロイもセッションが直接実行する。`.claude/settings.json` の permissions.allow に wrangler の deploy 系が登録済み（飼い主の明示指示 2026-08-19）。
9. ADR 0004（docs/adr/0004-release-cycle-trunk-based.md・承認済み）は『trunk-based を維持。作業ブランチ → PR（プレビュー）→ main（本番）の 1 ホップ。常設 dev 環境を持たない』と決めており、受け入れた代償として『main 上の合成状態が本番で初めて動く』を挙げ、緩和策を『main マージ後のテストゲート』（Issue #39）としている。preview alias を使った固定 dev 環境案は『シークレットが Worker 1 本の版チェーン全体で線形継承されるため dev 専用シークレットを分離できない』として却下されている。
10. 既存の関連 Issue: #187『プレビュー version に secret が渡っておらず、認証とレート制限がプレビューで動作しない』が open。

【この議論で決めること（争点）】
A. プレビュー環境（version / preview alias）の後始末として **技術的に実行可能な手段は何か**。wrangler CLI・Cloudflare REST API・代替（無害化・alias 命名の変更・放置して LRU に任せる）を、公式ドキュメントと実 API の応答という一次情報で切り分ける。『できるはず』で書かない。
B. 本番デプロイの発火点を、現在の Step 6（マージ直後）から Step 7（スプリントレビューが accepted）へ移すべきか。ADR 0004 の trunk-based（main = 本番）との整合、非スプリント PR（改善 Issue・retro-try・docs）の扱い、レビュー判定までの間 main と本番がずれることのリスクを含めて判断する。
C. 判定が accepted_with_conditions / rejected のとき、本番デプロイと環境削除をそれぞれどうするか（fail-closed の設計）。Step 7 が中断したときに後始末が永久に実施されない経路を塞ぐ方法。
D. 上記を **どこに実装するか**。SSOT を増やさないこと（同じ規則の実体を 2 箇所に書かない）。候補: `.claude/skills/pr-review-watcher/SKILL.md`（Step 6 / Step 7）・`docs/03_design/infrastructure/cloudflare-infrastructure.md` §8・新規 `tools/*.py`（後始末・棚卸し）・`.claude/hooks/`・`sprint-cycle-router` の決定木。実装コストと実効性（本当に守られるか）で評価し、費用対効果が合わないものは『入れない』と明言する。
- 参加者: `cf_platform`, `release_eng`, `harness_ops`, `docs_trace`
- 投稿数: 10
- 更新: 2026-08-20T16:42:00+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `release_eng` — 主張
<sub>2026-08-20T16:33:04+09:00</sub>

## release_eng（争点 B / C）結論: B は条件付き賛成、C は「rejected のみ非デプロイ」

### B: デプロイ発火点を Step 7（accepted 後）へ移すことについて

**ADR 0004 と矛盾しない。** ADR 0004 §3.3 は「本番直結のリスクは main マージ後のテストゲートで塞ぐ」を
既に緩和策として採用済み（`npm run check` を main HEAD で再実行してから deploy・SKILL.md Step 6 実装済み）。
Sprint Review をデプロイ前に挟むのは、この既存の「マージ後・デプロイ前ゲート」パターンを
テスト判定から人格化された判定（受け入れ判定役 fan-out）へ拡張するだけであり、ADR が禁じた
「常設 dev 環境」（§3.4 却下）とは別物。ADR の再判定は不要と判断する。

**ただし移すのは `Sprint Goal:` 行のある PR（Step 7 が発火する PR）に限定すべき。** 非スプリント PR
（改善 Issue・retro-try・docs）には Step 7 が存在しない（SKILL.md Step 7 冒頭「発火条件: `Sprint Goal:` 行
がある。無い場合は本ステップをスキップ」）。ここにもデプロイゲートを要求すると、判定者が存在しない
PR が **永久に未デプロイのまま main に積み上がる**（在庫リーク）。飼い主の指示原文も「スプリント完了後の
スプリントレビュー」と明示しており、非スプリント PR は射程外（`D-12` のスコープ厳守にも合致）。
→ **非スプリント PR は現行どおり Step 6 で即デプロイ**（変更なし）。

**「main マージ済み・未デプロイ」の窓は実害が小さい。** Step 6/7 は同一セッション内で連続実行される
自動処理であり（`SKILL.md` Step 6→Step 7 は同一セッションの逐次ステップ、人間の判断待ちではない）、
数分〜十数分の窓に留まる。さらに実デプロイ手順（`cloudflare-infrastructure.md` §8.2）は常に
「`git checkout origin/main` → `npm run check` → `npm run deploy`」という **その時点の main HEAD** を
対象にしており、Step 6 の時点のコミットではなく最新 HEAD を毎回検証してからデプロイする設計。
したがって Step 7 実行中に後続 PR が別セッションでマージされても、デプロイ時点で再度合成状態が
検証される（既存の仕組みがそのまま使える。追加変更不要）。

### C: 判定別のデプロイ可否（fail-closed 設計）

| 判定 | デプロイ | 理由 |
|---|---|---|
| `accepted` | 実行する | 無条件 OK |
| `accepted_with_conditions` | **原則実行する** | 「条件」は既存テンプレの `次 firing 必須` / `後続スプリントへ送る項目` で表現される **プロセス・スコープ上の残課題**（例: 編成が単独実行だった、UI tier 推奨行の逸脱）であり、コード自体の欠陥ではない。ブロックすると「テストは通っているのに永久に出せない」状態を量産する |
| `rejected` | **実行しない** | fail-closed。コードは main に残るが本番には一切触れない |

**rejected を「本番へ出す前」に止められることが、この設計の最大の利点。** 現行（Step 6 で即デプロイ）は
rejected 判定が出た時点で **既に本番稼働中**であり、復旧には `wrangler rollback` の実行・結果検証という
追加アクションが要る。Step 7 後にデプロイへ倒す設計では、rejected の場合デプロイ自体が発生しないため
**復旧アクションがゼロ**（ロールバックコマンドを打つ必要がない・失敗の可能性がある操作が 1 つ減る）。
これは brief 事実 4 の `wrangler rollback` / `versions deploy <id>@100` という実在手段と比較しても
「まだ出していない」の方が明確に安全側であり、B の結論を後押しする。

⚠️ **例外があるとすれば `accepted_with_conditions` の中で受け入れ判定役が明示的に「本番影響あり」と
書いたケース**。現行テンプレ（Step 7-3 の書式）にはこの区別がないため、**受け入れ判定役の役割定義に
1 行追加**することを推奨する: 「`accepted_with_conditions` を選ぶ場合、デプロイ可否（`deploy: yes/no`）を
明示する」。デフォルトは `yes`。追加コストは Step 7 の fan-out プロンプト 1 行のみ（新規ファイル・新規
ラベル不要、SKILL.md 本文の SSOT を増やさない）。

### 見落としてはいけない失敗モード: Step 7 が完走しないまま firing が尽きる

デプロイを Step 7 accepted へ紐付けると、**Step 7 が中断した場合デプロイも永久に起きない**リスクが
生まれる（現行は Step 6 で即実行なので中断リスクがそもそも無い）。`sprint-cycle-router` Step 3 の
stale 再開（4 時間超）が Sprint Review の再開を拾う設計は既にあるが（`進捗:` マーカー行）、
**再開後に「判定は出ていたが deploy コマンドは未実行」というサブケースを明示的に扱う分岐が今は無い**。
実装時は Step 7 の手順内に「判定投稿 → デプロイ実行 → retrospective 起動」の順で **デプロイを
判定直後の明示ステップとして独立させる**（Step 6 の本文に埋め込んだままにしない）ことを推奨する。
これにより Step 3 の再開ロジックが「判定済みだがデプロイ未実行」を正しく検出・再試行できる
（デプロイコマンド自体は idempotent なので再実行しても安全）。

---
post 済み。結論: B は条件付き賛成（Sprint Goal PR のみ対象・非スプリント PR は現行 Step 6 維持）、
C は rejected のみデプロイ停止・accepted / accepted_with_conditions は原則デプロイ、Step 7 中断時の
再試行導線を実装に含めることを必須条件とする。

### `cf_platform` — 主張
<sub>2026-08-20T16:33:09+09:00</sub>

## cf_platform: 争点A（Cloudflare プラットフォーム事実確認）

### 結論（先出し）
**version / preview alias を個別に削除する CLI・REST API は存在しない。** 確認できた「後始末」レバーは
以下の3つのみで、いずれも「PR単位で狙って削除する」という要求には応えられない。

1. **1000-alias LRU 自動失効**（受動的・呼び出し不可）
2. **Worker 全体の preview_urls 一括無効化**（能動的だが全PR一括・選択不可）
3. **Worker 自体の削除**（該当外・破壊的すぎる）

---

### 1. preview alias を明示的に削除する CLI / API は存在するか → **無い（確認済み）**

**wrangler CLI**:
```
$ npx wrangler versions --help
COMMANDS
  wrangler versions view <version-id>
  wrangler versions list
  wrangler versions upload [path]
  wrangler versions deploy [version-specs..]
  wrangler versions secret
```
delete サブコマンドなし（wrangler 4.124.0 実測）。

`wrangler --help` トップレベルには `wrangler delete [name]` があるが、これは **Worker スクリプト全体の削除**（1本しかない Worker を消せば本番も消える・該当外）。`wrangler deployments --help` にも delete 系はない。

**REST API**: 公式ドキュメント（developers.cloudflare.com/workers/versions-and-deployments/preview-urls/）に明記:
> "Aliases may only be created during version upload."
alias の更新・削除に関する API 記述は存在しない（作成専用のライフサイクル）。API リファレンスページ（`/api/resources/workers/subresources/scripts/subresources/versions/`）は SPA でWebFetch から中身が取得できなかったが、`workers/platform/infrastructure-as-code` ページに掲載されている DELETE の実例は
```
DELETE /accounts/{account_id}/workers/workers/{worker_id}
```
のみで、**Worker 全体**を消す新 API（scripts ではなく workers リソース）。version 単位・alias 単位の DELETE エンドポイントはドキュメント中に一切見つからない。

実測（GET のみ・破壊操作なし）: `GET /accounts/{account}/workers/scripts/gem-hunter/versions` → `result_info.total_count: 35`（version が蓄積し続けている実データを確認）。

### 2. version 自体を削除できるか。保持上限・自動失効は？

- **削除は不可**（上記と同じ理由）。
- **Rollback 対象としての保持上限は 100**（"You can only roll back to the 100 most recently published versions"）だが、これは *rollback 候補として選べる数* の制限であり、101 番目以降の version が **削除されるとは書かれていない**（実際に消える保証がない＝確認できていないので断定しない）。
- version 数そのものへのアカウント/プラン上限は `workers/platform/limits/` に記載なし（"Number of Workers" は 100〜500 だが、これは Worker の数であって version の数ではない）。version 数への課金・上限影響は **未確認**（ここは断定しない）。

### 3. alias を別の version へ張り替えられるか

- **不可（upload 時のみ）**: 公式ドキュメント "Aliases may only be created during version upload."
- 現行運用（`--preview-alias pr-<N>` を同一 PR の push のたびに再実行）は、同じ alias 文字列で **新しい alias を都度作り直している**（= ルーティング上は同名 alias が新 version を指すよう見えるが、実体は「新規作成」であって「既存 alias の更新」ではない）。この結果、**alias 文字列は 1 個でも version オブジェクトは push のたびに増え続ける**（今回実測の 35 version・`pr-219` 系だけで複数存在）。

### 4. `preview_urls` 設定 / Worker subdomain API で一括無効化できるか。副作用は？

**できる（実測・GET のみ）**:
```
GET /accounts/{account}/workers/scripts/gem-hunter/subdomain
→ {"result": {"enabled": true, "previews_enabled": true}, "success": true}
```
`enabled`（workers.dev ルート = 本番）と `previews_enabled`（プレビュー URL 全体）は**独立したフィールド**。公式ドキュメント（Preview URLs ページ「Toggle Preview URLs」節）:
> "Disabling Preview URLs will disable routing to both versioned and aliased preview URLs."
> "Preview URLs are enabled by default when `workers_dev` is enabled... disabled by default when `workers_dev` is disabled" — しかし独立設定も可能

**副作用**: `previews_enabled: false` にしても `enabled`（本番 workers.dev ルート）は変わらない設計 → **本番は落ちない**（このリポジトリの本番は現在 workers.dev 上で稼働・custom domain 未決定 = `cloudflare-infrastructure.md` 348 行目・`M-4` 未決）。ただし **全 PR のプレビューが同時に無効化される**（PR 単位の選択削除は不可能。ON/OFF の 2 値のみ）。

このフィールドを書き換える PATCH は本タスクでは**実行していない**（破壊的変更を避ける指示のため GET のみで存在確認に留めた）。書き換え自体が可能かどうかの API 権限（トークンスコープ）は未検証。

---

### 争点A まとめ（3〜5行）
- **PR 単位でプレビュー環境（version / alias）を狙って削除する API・CLI 手段は存在しない**（wrangler にも REST API にも delete 系エンドポイントなし・一次情報で確認済み）。
- 唯一の自動的な後始末は **1000 alias を超えた分の LRU 自動失効**（受動的・現状 35 version なので当分発動しない）。
- **能動的にできるのは「全プレビューを一括で止める」`previews_enabled` トグルのみ**（本番の `enabled` とは独立フィールドなので本番非破壊）。PR ごとの選択的無効化はできない。
- したがって「スプリントレビュー完了後にそのスプリントの環境だけ削除する」という原指示は **Cloudflare のプラットフォーム機能だけでは文字通りには実装不可能**。実装するなら「削除」ではなく「放置してもコスト・実害がないことの確認」または「全体トグルでの一括停止」のどちらかに設計を寄せる必要がある（争点C/Dの設計判断に引き継ぐ）。

### `docs_trace` — 主張
<sub>2026-08-20T16:33:19+09:00</sub>

# ドキュメント整合調査：スプリント環境ライフサイクルと本番デプロイ順序の改訂

## 争点 D: ドキュメント整合 — 表形式で要変更箇所を列挙

| パス | 節 | 現在の記述の要旨 | 必要な変更の要旨 | 既存の矛盾 |
|------|-----|----------------|--------------|----------|
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | §8.2 本番デプロイ | 本番（マージ後）: `git fetch origin/main ... npm run check ... npm run deploy ... curl 疎通確認`. セッションがマージ直後に実行する。実行結果は Issue / PR コメントに記録 | `npm run deploy` の発火点をスプリントレビューの accepted 判定後に遅延させる。判定までは本番へ進まない |  矛盾あり（§8.2 の「セッションがマージした直後に実行」はスプリントレビュー判定前） |
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | §8.3 プレビュー URL は fail-closed | プレビュー URL の抽出・疎通確認はされているが、PR マージ後の **後始末（URL 削除・version 削除）は言及なし** | プレビュー版（version + preview alias `pr-<N>`）の後始末タイミングと手段を明記する: ① スプリントレビュー accepted ならクリーンアップ ② rejected / accepted_with_conditions なら保持 | 欠落（現在は削除手段の記述が無い） |
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | §6.1 3 環境 | プレビューは「同一 Worker の version（`wrangler versions upload --preview-alias pr-<N>`）」. 後始末手順は未記載 | プレビューのライフサイクルを明示: 作成タイミング（PR 作成前）、保持期間（スプリントレビュー まで）、削除タイミング（reviewed & accepted / rejected） | 欠落（削除手段がない） |
| `docs/adr/0004-release-cycle-trunk-based.md` | § 2. 決定 | 「作業ブランチ → PR（プレビュー）→ `main`（本番）の 1 ホップ構成」「本番直結のリスクは main マージ後のテストゲートで塞ぐ」 | 新しい判定点「スプリントレビュー accepted」を explicit にし、本番デプロイはそこまで待つ。**main マージ = 本番デプロイではなく、review accepted = 本番デプロイ** に改訂 | 矛盾あり（現在は main マージ直後の自動デプロイとなっているが、レビュー判定を経由していない） |
| `.claude/skills/pr-review-watcher/SKILL.md` | Step 6 マージ直後の公開反映 | 「マージで生まれた差分をこのセッション内で反映まで完遂 ... deploy 前に main HEAD で npm run check 再実行 ... deploy 後は本番 URL の疎通確認」。**デプロイは公開反映と同一セッション内に実行** | Step 6 と Step 7 の順序を逆転: ① Step 6: 公開反映のみ（push） ② Step 7: スプリントレビュー + レトロ ③ Step 7a: レビュー結果に応じてデプロイ or クリーンアップ | 矛盾あり（現在 Step 7 より Step 6 が先に実行される） |
| `.claude/skills/pr-review-watcher/SKILL.md` | Step 7 スプリント review + retro | 「マージ + 公開反映の直後・完了報告の前」。発火条件は `Sprint Goal:` 行のある PR | Step 6/7 の順序改訂後、「受け入れ判定役の判定結果に基づくデプロイ判定」を明示。本番デプロイはここで発火する | 順序矛盾による結果の整合性なし |
| `.claude/skills/pr-review-watcher/SKILL.md` | Step 6 リビジョン: 後始末（新規） | 現在は記述なし | 新規追加: スプリントレビュー判定の結果に応じた環境クリーンアップ処理を Step 7 または step 7a に挿入 ① accepted: `wrangler versions list --json \| jq '.versions[] | select(.metadata.has_preview) | select(.annotations.workers/alias | startswith("pr-"))' で対象 version を特定し、REST API で削除（方式は #231 で決定待ち） ② rejected: クリーンアップを延期（デバッグ用に保持） | 欠落（削除 API がない可能性・白書で検証待ち） |
| `docs/rules/sprint-development-rules.md` | SD-1 動作確認できる状態で終わる | 「PR 本文に開けるプレビュー URL がある」。回帰の目視確認を兼ねる | SD-1 の完了条件にプレビュー後始末を追加: プレビューはスプリントレビュー accepted 時点で削除されることと、その際のユーザー体験（URL 403 になる）を明確にする | 矛盾なし（SD-1 はプレビュー URL 貼付まで・後始末は別の規律） |
| `docs/rules/pr-review-flow-summary.md` | 全体 | 「マージ直後: Layer 1 セルフレビュー ... 指摘対応 ... 即マージ」「マージ直後: 公開反映」として本番デプロイを記載 | 本番デプロイの発火点を「スプリント review accepted」に改訂。非スプリント PR（改善 Issue・retro-try）への対応も明記 | 矛盾あり（review 判定が無視されている） |
| `docs/adr/0004-release-cycle-trunk-based.md` | § 4. 結果 代償 | 「`main` 上の合成状態が本番で初めて動く」「緩和策: `main` マージ後のテストゲート」 | 緩和策にスプリント review ゲート（テストゲート + review accepted） を追加。テストゲート単独ではなく、review ゲート **も** トリガーになることを明示 | 矛盾あり（テストゲートのみが記載され、review ゲートが抜けている） |
| `docs/02_requirements/open-questions.md` | D-23 | 「GitHub Actions が制限中のため CI とデプロイをセッション実行へ切り替える」。本番デプロイはマージ直後 | 本番デプロイの順序改訂に伴い、「デプロイはスプリント review accepted 後」に追記 | 矛盾なし（D-23 は CI/デプロイ経路の変更であり、発火条件の改訂ではない） |

---

## 要変更ファイル（優先度順）

### 最優先 2 件（デプロイ順序の構造に影響）

1. **`.claude/skills/pr-review-watcher/SKILL.md` Step 6/7/7a の順序改訂**
   - 現在: Step 6（デプロイ） → Step 7（review）
   - 変更: Step 6（公開反映・push のみ） → Step 7（review） → Step 7a（デプロイ or 後始末）
   - 影響: 実装フロー全体が変わる

2. **`docs/adr/0004-release-cycle-trunk-based.md` §4 代償・緩和策の改訂**
   - 「テストゲート」だけでなく「review ゲート」もトリガーであることを明示
   - trunk-based の下での「いつ本番へ進むか」の定義を更新
   - 影響: リリースサイクルの形式的な再定義

### 次点 3 件（手段と詳細）

3. `docs/03_design/infrastructure/cloudflare-infrastructure.md` §8.2・§8.3・§6.1
   - 本番デプロイの発火タイミング を Step 6/7 の順序に合わせて修正
   - プレビュー環境のクリーンアップ手段（API 経路など）を明記

4. `docs/rules/pr-review-flow-summary.md` 全体
   - PR マージ後の流れを「公開反映 → review → デプロイ」に改訂

5. `docs/02_requirements/open-questions.md` D-23
   - デプロイ発火点を「review accepted」に追記

---

## 既存の矛盾の有無・深刻度

| 区分 | 件数 | 事象 |
|-----|------|------|
| **順序矛盾**（step 6 と 7 が逆） | 2 件 | `.claude/skills/pr-review-watcher/SKILL.md` / `docs/rules/pr-review-flow-summary.md` — 実装フロー全体に影響 |
| **欠落**（削除手段がない） | 3 件 | 環境クリーンアップ API パス・タイミング・条件 |
| **トリガー条件の不備**（review ゲートが抜けている） | 2 件 | `docs/adr/0004-release-cycle-trunk-based.md` / `docs/02_requirements/open-questions.md` |

深刻度: **高** — 現在の実装フロー（マージ → デプロイ） が飼い主の指示（review ゲート）と乖離している

### `harness_ops` — 主張
<sub>2026-08-20T16:35:06+09:00</sub>

## harness_ops: 争点 C/D（実装先・機械強制）— 結論から

**核心の設計判断: `sprint-cycle-router` の 9 分岐は変更しない。新しいラベル・state ファイル・ブロッキング hook も作らない。** 既存の「Issue は open+in-progress のまま残る → Step 3 の stale 再開が拾う」という仕組み（SKILL.md Step 7 の `Sprint Goal:` PR に `Closes #N` を書かない理由と同型）に、後始末・整合性チェックの両方を **無料で乗せる**。新規に作るのは読み取り専用スクリプト 2 本と、既存 hook と同型の PostToolUse hook 1 本だけ。

---

### 1. プレビュー環境の後始末（争点 A の受け皿）

**まず前提の訂正**: `search_cloudflare_documentation` を実際に叩いた（推測ではない）。`preview-urls/` の Aliased preview URLs 節には alias の **作成手順のみ** が書かれ、削除 API・削除コマンドの記述は無い。書かれている唯一の「消える」条件は `Only the 1000 most recently deployed aliases are retained.`（LRU 自動失効）。wrangler CLI にも delete サブコマンドが無いことは brief 事実 3 のとおり。**つまり「個別 alias を明示的に削除する」一次情報の裏付けは現時点でゼロ**。cf_platform が REST API 側で別の削除エンドポイント（version 自体の削除等）を見つけない限り、「削除」を実装対象にするのは時期尚早。

→ **提案: 『削除』ではなく『検出』だけを作る。実削除は cf_platform の一次情報確認待ちとし、確認できなければこの案自体を『入れない』。**

- 新規 `tools/check_preview_env_drift.py`（読み取り専用・`check_publish_drift.py` / `check_pending_pr_reviews.py` と同じ流儀で書く）:
  - Cloudflare `GET /accounts/{account}/workers/scripts/gem-hunter/versions` を叩き `annotations["workers/alias"]` が `pr-<N>` 形式のものを抽出（brief 事実 2 で実測済みのフィールド）
  - 各 `<N>` の PR 状態を `gh pr view <N> --json state`（403 なら `check_pending_pr_reviews.py` と同じ `GH_UNAVAILABLE` exit 3 パターンで呼び出し元に MCP 代替を促す）
  - closed/merged 済みなのに alias が残っている version を「孤児」として `--json` で列挙。exit 0=孤児なし / 1=孤児あり / 3=GH 不能
  - 認証は `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`（brief 事実 5 でセッション env に供給済み・実 curl 成功済み）
- **置き場所は新規 hook ではなく `project-sync` スキルの既存 Step 3.5（Orphan PR 検出）の隣**。project-sync は既に「Abandoned ブランチ検出」を持っており、孤児 preview alias は概念的にその Cloudflare 版。既存の週次/日次衛生スロットにもう 1 検査を足すだけで、新しい実行トリガーを作らずに済む。
- 見つかった孤児は Issue コメントか project-sync の既存レポート形式に載せるだけ（新規ラベルは作らない）。削除アクション自体は無い（上記の理由）ので、これは **Warning 相当**（レポートのみ・何もブロックしない）。
- **費用対効果判定**: 検出スクリプトは安い（既存パターンの複製）。実削除の実装はいま作れる材料が無い（API が無い）ので **見送り**。1000 alias の LRU が実質的な最終防衛線であり、本リポジトリの PR 数のペースでは当面枯渇しない。→ 「削除の自動化」は **入れない**。「検出だけを project-sync に足す」は **入れる**（低コスト・実効性は診断用途止まりだが Issue #187 の切り分けにも使えるため無駄にならない）。

---

### 2. レビュー/デプロイの不整合検知（争点 B/C と直結）

「review accepted なのに未デプロイ」「デプロイ済みなのに未レビュー」を **別のスキャナーで事後検知する** 設計は避ける（既存の stale 4h 判定と機能が重複し、二重の真実の源になる）。代わりに **`post-merge-publish-check.sh` と全く同じ形の PostToolUse hook** を 1 本追加する:

- `post-sprint-review-deploy-check.sh`（matcher: `mcp__github__add_issue_comment` / `mcp__github__issue_write`）
  - tool_input の body に `## 🔍 Sprint Review 判定` と `**結果**: accepted` を検知したら発火（`post-merge-publish-check.sh` の `detect_merge()` と同じ純粋関数で自己テスト可能に書く）
  - `tools/check_deploy_matches_merge.py`（新規・読み取り専用）を呼ぶ: `npx wrangler deployments list`（**`permissions.allow` に既に登録済み・追加コスト無し**）で本番の現在バージョンの `tag`（= merge commit SHA。`cloudflare-infrastructure.md` §8.2 の deploy 手順で `--tag $SHA` を付けている前提。cf_platform に §8.2 の実際の付与有無を確認してもらいたい）と、対象 Issue に紐づく merge commit SHA を突合
  - 一致していれば exit 0（無言）。不一致なら `post-merge-publish-check.sh` と同じ `additionalContext` パターンで「本番デプロイが未反映です。deploy を実行してください」と指示するだけ（hook 自身はデプロイしない・既存方針を踏襲）
- **これで新しい状態管理は要らない**: 「accepted と判定したのに session がデプロイ前に力尽きた」場合も、Step 7 の最終アクションである Issue クローズ（Step 5）が実行されない限り Issue は open + in-progress のまま残るので、**既存の Step 3（4h stale 再開）がそのまま拾う**。新ラベル・新 state ファイルは不要（SKILL.md Step 7 の既存禁止事項をそのまま満たす）。

**なぜ hook で event-bound にする価値があるか**（プレビュー alias 検出との違いを明確化): プレビュー alias の孤児化は「見た目が汚い」程度の実害（LRU が最終的に片付ける）。一方デプロイ/レビューの不整合は「reject されたコードが本番に残る」「accepted なのに本番が古いまま」という **実害が業務に直結する** 論点なので、周期スキャン任せ（次の project-sync 実行まで気づかない＝最大 24h+ 放置）ではなく、イベント直後に検知する価値がある。コスト（hook 1 本 + script 1 本、`post-merge-publish-check.sh` の複製に近い）に見合う。

---

### 3. 無人ルーティンを止めない設計

- 上記 2 種とも **`sprint-cycle-router` の決定木には一切手を入れない**（新分岐を作らない）。新設した hook はどちらも `additionalContext` で指示を注入するだけで `exit 2` の Stop ブロックはしない（`post-merge-publish-check.sh` のコメント『マージは既に成功しており、ブロックすべき事象ではないため（知らせるだけで止めない）』を踏襲）。ルーターが次の firing で新規スプリントに進むこと自体は妨げない。
- 唯一 **Error 相当（完了報告を止める）** にしてよいのは、Step 7 自身の完了条件（SKILL.md 「🔴 上記 1〜5 が未実施のまま完了報告しない」）に「本番デプロイが merge commit と一致していること」を 1 行足すだけ。これは新しい機構ではなく **既存の完了条件リストへの追記**。

### 費用対効果まとめ

| 案 | 実装コスト | 誤検知率 | 本当に守られるか | 判定 |
|---|---|---|---|---|
| Cloudflare alias 明示削除の自動化 | 高（削除 API 未確認 = 実装不能かもしれない） | ー | ー | **入れない**（cf_platform の一次情報待ち） |
| Cloudflare alias 孤児検出（project-sync 追加） | 低（既存パターン複製） | 低（PR state と alias の突合は決定論的） | 診断用途では守られる（削除は伴わない） | **入れる** |
| デプロイ/レビュー不整合 hook（Step7 コメント bound） | 中（新規 hook+script 1 本ずつ） | 低（`post-merge-publish-check` と同型で自己テスト可） | 高い（イベント直後・Step3 が中断時のバックストップ） | **入れる** |
| router 決定木への新分岐追加 | ー | ー | ー | **入れない**（Step7 完了条件への追記で代替可能・新分岐は無人運用のコストに見合わない） |

post 予定。

## ラウンド 2

### `docs_trace` — 反論
<sub>2026-08-20T16:37:47+09:00</sub>

# Round 2: ドキュメント整合応答（cf_platform・release_eng 結論を踏まえた改訂方針）

## 争点 1: プレビュー環境後始末（cf_platform 結論対応）

cf_platform の実測確認：**版削除 API が存在しない**。「削除」ではなく「検出 + 放置 + LRU」が実態。

| パス | 節 | 現在の記述 | 必要な変更 | 実体/参照 |
|-----|-----|---------|----------|---------|
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | §6.1 3 環境 | 「preview は同一 Worker の version + preview alias `pr-<N>`」。後始末手順は未記載 | **削除ではなく検出・報告に改訂**: 「孤児 version の検出は `project-sync` スキルが定期実行」とし、削除不可・LRU 依存を明記 | **実体** |
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | §8.3 プレビュー URL fail-closed | 「URL 抽出・疎通確認」のみ。後始末が無い | **「後始末は project-sync の孤児検出に委譲」と参照追加**。削除 API 不在を補足 | 参照（実体は §6.1） |
| `docs/rules/pr-review-flow-summary.md` | プレビュー削除 | （記述なし） | **新規追記**: 「プレビュー alias は review 結果に関わらず保持され、1000-alias LRU で自動失効する」 | 参照（実体は cloudflare-infrastructure.md） |

## 争点 2: デプロイ/レビュー順序（release_eng 結論対応）

release_eng 結論：**スプリント PR のみ Step 7 後へ移す。非スプリント PR は Step 6 で即デプロイ**。

| パス | 節 | 現在の記述 | 必要な変更 | 実体/参照 |
|-----|-----|---------|----------|---------|
| `.claude/skills/pr-review-watcher/SKILL.md` | Step 6 | 「マージ直後デプロイ」。スプリント PR も非スプリント PR も同じ流れ | **条件分岐を追加**: `if (PR.Sprint Goal 行あり) { skip deployment → Step 7 へ } else { deploy now }` | **実体** |
| `.claude/skills/pr-review-watcher/SKILL.md` | Step 7 | 「スプリント review + retro」。発火条件は `Sprint Goal:` 行のある PR | **新規 Step 7a を追加**: review 判定後にデプロイ/クリーンアップ分岐 ① accepted: deploy ② accepted_with_conditions: deploy ③ rejected: deploy なし | **実体** |
| `docs/adr/0004-release-cycle-trunk-based.md` | §4 代償・緩和策 | 「テストゲート」のみ | **「スプリント review ゲート」を追加**: 「スプリント PR は review ゲート（+ テストゲート）を経て本番へ進む。非スプリント PR は test ゲートで十分」と明示 | **実体** |
| `docs/rules/pr-review-flow-summary.md` | デプロイ発火 | 「マージ直後 review → デプロイ」 | **条件分岐を追加**: 「スプリント PR: マージ → 公開反映 → review → デプロイ。非スプリント PR: マージ → デプロイ（review 後）」 | 参照（実体は SKILL.md） |
| `docs/02_requirements/open-questions.md` | D-23 | 「セッション実行へ切り替える」。発火タイミングは「マージ直後」 | **「スプリント PR のみ Step 7 後」に追記**。非スプリント PR はマージ直後（従来）を併記 | 参照（実体は SKILL.md） |

## 両立性の確認

**release_eng 結論との両立**: ✅ 成立

- **同一ルールの実体**: `.claude/skills/pr-review-watcher/SKILL.md` Step 6/7a（スプリント PR vs 非スプリント PR の分岐・デプロイ判定）
- **参照先**: `docs/adr/0004-release-cycle-trunk-based.md` §4（「なぜこの分岐が要るか」の背景）+ `docs/rules/pr-review-flow-summary.md`（「どう見えるか」のフロー図）
- **矛盾の消し方**: cf_platform の「削除 API 不在」を background として、「削除ではなく検出」と記述を張り替える。SKILL.md の Step 6/7a では「後始末」を呼ばず「検出は project-sync」と参照に限定。

### `harness_ops` — 反論
<sub>2026-08-20T16:38:56+09:00</sub>

## harness_ops: round 2 rebuttal / concession（争点 C/D）

### Q1（孤児検出は削除できない世界で何の役に立つのか）— **concede: 入れない**

cf_platform の確定事実（個別 alias/version の選択削除手段が CLI にも REST API にも存在しない）を受けて自分の r1 案を再検討した結果、**具体的アクションを 1 つも示せない**。検討した候補と却下理由:

- 「見つけたら消す」→ 消す手段が無い（cf_platform 確定）
- 「見つけたら Issue に記録する」→ 記録した後に人間・セッションが取れる次のアクションが無い（消せない事実を確認するだけの記録は行動に繋がらない＝自分が r1 で立てた基準「費用対効果が合わないものは入れないと明言する」に照らして不合格）
- 「1000-alias LRU に任せる」→ これは検出ではなく **何もしないこと自体が正しい設計**（cf_platform 確定: 現状 35 version、当分枯渇しない）

唯一 cf_platform が見つけた能動的レバーは `previews_enabled` の **全体トグル**（PR 単位ではなく全プレビュー一括 ON/OFF、本番 `enabled` とは独立）。これは「孤児掃除」の代替にならない（狙い撃ちできない）が、**緊急時（例: Issue #187 系のシークレット露出インシデントでプレビュー全体を即座に止めたい場合）の手動 killswitch としてなら具体的アクションになる**。ただし全 PR のプレビューを同時に落とす操作は他セッションの進行中レビューを巻き込むため、**自動検出→自動実行ではなく、`cloudflare-infrastructure.md` に手順を明文化するだけの手動緊急手順**（A-6 相当ではないが人間判断が要る操作）に留めるべき。

→ **r1 の撤回: `tools/check_preview_env_drift.py` は作らない。project-sync への追加もしない。** 代わりに docs_trace の表（§8.3 行）に 1 点だけ提案する: 「削除は不可能。1000-alias LRU が唯一の自動失効機構。緊急時は `previews_enabled` トグル（手動・全体停止）」という **期待値を下げる記述**を書く。ドキュメント更新のみでコストほぼゼロ、かつ「守られるか」の問いに対して「何もしないことが正しい」という答えが常に真であり続ける（壊れようがない）。

---

### Q2（PostToolUse matcher は tool_name にしか掛からないのでは）— **一部 concede + 具体化**

確認結果: `docs/rules/hook-events-reference.md` と `post-merge-publish-check.sh` の実装により、**matcher は tool_name のみで掛かる**という指摘は正しい。だが `post-merge-publish-check.sh` 自体も同じ構造（matcher は `mcp__github__merge_pull_request` という tool_name のみ＝あらゆる PR のマージで発火し、`detect_merge()` が `tool_input.owner`/`.tool_input.repo`/`.tool_response.merged` を **jq で本文相当のフィールドを読んで** 絞り込んでいる）。**PostToolUse の stdin JSON には呼び出し時の tool_input 全パラメータが含まれる**ことは、いま `ToolSearch` で取得した実スキーマで裏取りできた: `mcp__github__add_issue_comment` の `body` はトップレベルの必須級パラメータ（コメント本文そのもの）であり、`.tool_input.body` として hook の stdin JSON に載る。よって `detect_merge()` と同じ関数形で:

```bash
# detect_review_verdict(): stdin JSON → match / skip:<reason>
body=$(printf '%s' "$input" | jq -r '.tool_input.body // ""')
if [[ "$body" != *"## 🔍 Sprint Review 判定"* ]]; then echo "skip:not-verdict"; return; fi
if [[ "$body" != *"**結果**: accepted"* ]]; then echo "skip:not-accepted"; return; fi
# owner/repo チェックは detect_merge と同じ
```
という判別は **実行可能**。「あらゆる Issue コメント投稿で発火する」自体は事実だが、それは `pre-tool-use-router.sh` の matcher `Bash|mcp__github__create_pull_request`（Bash 全件に発火して中で絞り込む）と同型であり、jq 1 回のコスト増は無視できる。**誤検知の懸念は的中しない**（発火は広いが判定は絞られる）。

**訂正（concede）**: r1 で書いた matcher 候補 `mcp__github__issue_write` は誤り。`issue_write` の `body` は **Issue 本体の説明文**（`method: create/update` で Issue を書き換えるときの本文）であり、コメント投稿には使わない（SKILL.md Step 7-3 は「対象 Issue のコメントとして投稿」と明記＝コメントAPIは `add_issue_comment` のみ）。**matcher は `mcp__github__add_issue_comment` 単独に絞る。**

---

### Q3（Step 7 中断時のバックストップは十分か）— **concede: 不十分、進捗マーカーで解ける**

`sprint-cycle-router` の Step 3 が実際に読むのは「Issue コメント本文の **`進捗:` 1 行マーカー**」（brief 表内: 「進捗: {SD ステップ名 **または Sprint Review**}まで完了。次は{次にやること}」）。現行の Step 7-3 テンプレは:
```
進捗: Sprint Review まで完了。次は retrospective スキル起動
```
これは **デプロイの有無を一切表現していない**。release_eng の指摘どおり、自分の r1（「Issue が open+in-progress のまま残るから大丈夫」）は **粒度が粗すぎる** — Step 3 が「再開すべき」と判定はできても、「デプロイ済みかどうか」を区別する情報が本文に無いため、再開したセッションは判定コメントを見ても **デプロイ実行を再試行すべきかを本文から判別できない**（もう一度 wrangler deployments list で本番の tag を突合する追加調査が要る＝新規スクリプトへの依存が生まれる）。

**解決策（新規 state ファイル・新規ラベルなし・マーカー文言の拡張のみ）**: Step 7 の判定投稿とデプロイ実行を **2 つの別コメント** に分け、`進捗:` の中身自体にデプロイ状態を持たせる（Step 3 が既に読んでいる場所にそのまま情報を足すだけ）:

```
① 判定投稿直後:
進捗: Sprint Review まで完了（結果: accepted）。次はデプロイ実行 → retrospective スキル起動

② デプロイ成功直後（同一セッション内で追加コメント）:
進捗: デプロイ完了（tag: <merge commit SHA>）。次は retrospective スキル起動
```

Step 3 は「最新の `進捗:` 行」を読むので、①のまま session が力尽きれば次 firing は「次はデプロイ実行」を読んでそのまま再試行できる（`wrangler deploy` は idempotent・release_eng が既に指摘済み）。②まで到達していれば「次は retrospective」からそのまま先へ進む。**これは Q2 の hook より安価かつ確実**なので、優先順位を訂正する:

- **主防御 = 進捗マーカーの文言拡張**（コスト: SKILL.md Step 7 テンプレ 1 箇所の書き換えのみ・新規ファイルゼロ）→ **入れる（最優先）**
- **副防御 = Q2 の PostToolUse hook**（`post-sprint-review-deploy-check.sh`）→ 主防御が「セッションのクラッシュ」を既にカバーするため、残る守備範囲は「session が生きているのに SKILL.md の手順を誤って読み飛ばした（ロジックミス）」というより小さいリスクのみ。**優先度を下げて任意実装とする**（r1 の「入れる」を「入れてもよいが必須ではない・主防御で十分なら見送ってよい」に修正）。

---

### 争点C/D 更新後の結論（3〜5行）
- Q1: 孤児 alias 検出ツールは**撤回**（消せないものを検出しても行動に繋がらない＝自分の基準で不合格）。ドキュメントに期待値（削除不可・LRU 任せ・緊急時のみ手動 `previews_enabled` トグル）を書くだけに留める。
- Q2: matcher 誤検知の指摘は妥当だが `post-merge-publish-check.sh` と同型の jq 絞り込みで解決可能（実スキーマで `tool_input.body` の存在を確認済み）。ただし matcher 候補の `issue_write` は誤りで `add_issue_comment` のみに訂正。
- Q3: 「Issue が open のまま残る」だけでは不十分という指摘を受け入れる。`進捗:` マーカーの文言にデプロイ状態を持たせる（新規ファイル・ラベル無し）のが主防御。Q2 の hook は副防御へ格下げ。

### `release_eng` — 反論
<sub>2026-08-20T16:39:15+09:00</sub>

## release_eng ラウンド2: rebuttal + concession

### lead の穴への回答: 選択肢 1（デプロイの直列化）を採る。ラウンド1の C は過大な安全性を主張していたと認める

**concede**: ラウンド1で「rejected なら復旧アクションがゼロ」と書いたが、これは非スプリント PR の
Step 6 が独立に走ることを考慮していなかった。CP-6 の「複数セッション並行が前提」（CP-4）を踏まえると、
非スプリント PR（改善 Issue・retro-try・docs）が Step 6 で `main` HEAD をまるごとデプロイする限り、
未レビューのスプリント成果物は **他パイプライン経由で本番へ漏れる**。選択肢 2（穴を受け入れる）は
「rejected の発生頻度が低いから許容する」という発生確率論であり、本プロジェクトが一貫して採用する
fail-closed 思想（§8.3 プレビュー URL・A-3 致命的 NG 時の続行禁止）と整合しない。**確率論での妥協は
この設計原則の一貫性を壊す。** → **選択肢 1 を採る。**

**直列化の実装は「PR マージのブロック」ではなく「`npm run deploy` 呼び出し 1 点のブロック」に限定する。**
マージ・push・公開反映（Step 6 の前半）は全パイプラインで従来どおり自由に進めてよい（CP-4 が守る
Issue/PR レベルの排他はそのまま）。止めるのは **デプロイコマンドの実行だけ**:

```
Step 6（どのパイプラインの PR でも共通）:
  1. 公開反映（push）は常に実行
  2. deploy 前に「ゲート判定」を実行:
     open かつ status:in-progress かつタイトルが ^SP-\d+ の Issue のうち、
     Sprint Planning コメントがあり、対応 PR がマージ済み（Step 6 実施済み）で、
     かつ「Sprint Review 判定」コメントがまだ無い、または直近の判定が
     rejected かつそれを覆す新しい判定がまだ無い Issue が 1 件でも存在するか？
       ├─ 存在する → npm run deploy を実行せず「デプロイ保留: 理由は #N の Sprint Review 未確定/rejected」
       │              と Issue/PR コメントに記録して Step 6 を終える（push 済みなので公開反映自体は完了）
       └─ 存在しない → npm run deploy を実行（現行どおり main HEAD 全体を検証してデプロイ）
```

**rejected 後にどうやってゲートが解ける議論**: 現行 Step 7 は rejected/accepted_with_conditions で
持ち越しがある場合 Issue を open のまま残し、次 firing で同一 `SP-n` の修正 PR が出る設計
（brief 事実 7）。修正 PR がマージされ、その Step 7 で改めて `accepted`（または `accepted_with_conditions`
かつ `deploy: yes`）の判定が出た時点で、ゲートは自然に解除される。**main を巻き戻す・rejected コミットを
revert する運用は導入しない**（trunk-based の 1 ホップ構成を維持。ADR 0004 の再判定は revert 手順の
追加ではなく「デプロイの発火点」の追記で足りる）。

**代償として明示すべきこと**: rejected 判定が続く間、**その rejected 修正待ちのスプリントと無関係な
非スプリント PR のデプロイも足止めされる**（main が 1 本の Worker である以上、部分的デプロイはできない
ため不可避）。これは新しい受け入れる代償であり、`docs_trace` が指摘した ADR 0004 §4「代償」表への
追記が必要（次段で `docs_trace` に返す）。足止めの実害は「反映が遅れる」であり「壊れたコードが出る」
より明確に軽いので、trunk-based の 1 ホップ原則は維持できると判断する。

**実装先はゲート判定関数 1 つを共有し、新規ファイルを増やさない**: `harness_ops` が提案した
`post-sprint-review-deploy-check.sh` の対象を「Sprint Review 判定コメント検知時」だけでなく
**既存の `post-merge-publish-check.sh`（全マージで既に発火するフック）に同じゲート判定を追加**する形に
広げることを推奨する（新規 hook を増やさず、既存 hook の判定ロジックを 1 関数追加）。

---

### cf_platform への concession: C の「環境削除」半分は撤回する

cf_platform の実測（PR 単位で version/alias を削除する CLI・REST API は存在しない）を受けて、
ラウンド1の C 表は **デプロイ可否についてのみ有効** であり、「判定に応じて環境を削除する」という
飼い主原文の後半には適用できない。**C を 2 系統に分割して再提示する**:

| 対象 | 判定に応じて変わるか | 理由 |
|---|---|---|
| **本番デプロイ**（`npm run deploy`） | 変わる（accepted/accepted_with_conditions(deploy:yes)=実行、rejected=保留・上記ゲート） | セッションが完全に制御できるコマンド |
| **プレビュー環境の後始末**（version/alias） | **変わらない**（判定に関わらず「削除」というアクションが存在しない） | cf_platform 確認済み。能動的にできるのは全 PR 一括の `previews_enabled` トグルのみで PR 単位選択不可 |

→ harness*ops の「削除ではなく検出だけを project-sync に足す」案に **同意**。判定別の後始末という
飼い主原文の字面は文字通りには実装不可能であり、これは B/C の設計選択の問題ではなく **A の技術的制約**
（cf_platform の一次情報）が上位を規定する。この点は次のユーザー報告で「原指示のうち環境削除の字面は
Cloudflare の制約で実装できず、検出のみに落とす」ことを明記すべき事項として lead に引き継ぐ。

---

### harness_ops への検証: Warning 相当フックだけでは「判定済み・デプロイ未実行」の再試行は担保されない

**検証結果: 不足している。** `post-sprint-review-deploy-check.sh` は Sprint Review 判定コメントを
投稿した **同一セッション・同一ターン直後**にしか発火しない（PostToolUse は当該ツール呼び出しへの
反応であり、セッションが判定投稿の直後に力尽きた場合、injected `additionalContext` を読むターンが
そもそも来ない）。harness_ops 自身が「Issue は open+in-progress のまま残るので Step 3 の stale 再開が
拾う」とバックストップを主張しているが、**`sprint-cycle-router` Step 3 の再開手順（brief に引用されている
文言）は「git log と Sprint Planning コメントから続きを判定し再開」という汎用記述に留まり、
『直近コメントが Sprint Review 判定で、かつそれに続くデプロイ完了コメントが無い場合はまず deploy を
実行してから次に進む』という判定を明示的に含んでいない**。汎用の「続きを判定」に賭けるのは、
まさにラウンド1で自分が指摘した失敗モード（判定済みだがデプロイ未実行のサブケースが再開ロジックに
存在しない）そのものであり、harness_ops の hook だけでは解消されない。

**具体的な補い（新規ファイルなし・既存テキストへの追記のみ）**:
1. `sprint-cycle-router` §3 決定木 Step 3 の再開手順に 1 行追加: 「対象 Issue の最新コメントが
   `## 🔍 Sprint Review 判定`（`accepted` または `accepted_with_conditions` かつ `deploy: yes`）で、
   かつそれ以降に `wrangler deployments list` のタグが一致する旨のコメントが無い場合、
   retrospective 起動より先に `npm run deploy`（上記ゲート判定込み）を実行する」。
2. `harness_ops` の hook 検知条件を `**結果**: accepted` だけでなく **`accepted_with_conditions` かつ
   `deploy: yes` も一致させる**（ラウンド1で自分が追加提案した書式と揃える。これを漏らすと
   accepted_with_conditions 経路だけ検知されない）。

この 2 点を満たして初めて「デプロイは verdict に紐づくが、verdict 後のデプロイ実行が失われない」が
成立する。同一セッション内のフックだけでは firing 跨ぎの障害に対して脆弱。

### `cf_platform` — 反論
<sub>2026-08-20T16:39:42+09:00</sub>

## cf_platform round 2: 争点E 回答 + 他者への rebuttal/concession

### harness_ops への concession（--tag $SHA の確認依頼に回答）
確認した。`docs/03_design/infrastructure/cloudflare-infrastructure.md` 424・503・528 行目、実行コマンドは
一貫して `wrangler versions upload --preview-alias "pr-<N>" --tag "$SHA"` — **`--tag` は毎回付与されている**。
`check_deploy_matches_merge.py`（harness_ops 提案）の「本番 version の `tag` と merge commit SHA を突合」は
このドキュメント記述と矛盾しない。harness_ops の争点A受け皿（検出のみ・project-sync 追加）にも同意する。

### docs_trace への rebuttal（表の 187 行目・訂正が必要）
`.claude/skills/pr-review-watcher/SKILL.md` の提案行に
> ① accepted: ... 対象 version を特定し、**REST API で削除**（方式は #231 で決定待ち）
とあるが、争点A・および本ラウンドの (b) 調査の結果、**version・alias を「削除」する REST API は存在しない**
（一次情報で確認済み・#231 で決定を待っても出てこない）。実装するなら「削除」ではなく後述 (b) の
**「同名 alias へのスタブ再アップロードによる無害化（tombstone）」**に書き換えるべき。「決定待ち」という
書き方は「いずれ delete API が見つかる」という誤った期待を生むため、この表現は次版で修正を推奨する。

---

## 争点E: 代替 (b) の可否判定

### (b) 同名 alias への張り替え → **可能。しかも仮説ではなく、このリポジトリで既に実運用中**

**根拠1（wrangler 実装・ソース確認）**: `node_modules/wrangler/wrangler-dist/cli.js` を grep。
```
"workers/alias": props.previewAlias
```
alias は **version アップロード POST のペイロードに乗る annotation の1つ**として実装されている。
alias 専用の登録・更新エンドポイントは別に存在しない（= alias は「version に貼るラベル」であり、
同じラベルを新しい version に貼れば、そのラベルの実効ルーティング対象は新しい version に移る、という
設計になっている）。`cli.js` 内に alias 重複エラーのメッセージも見つからない（`already|exist|duplicate|conflict`
+ alias の組み合わせで grep したが該当なし）。

**根拠2（本アカウントの実データ・非破壊 GET のみ）**: `GET .../versions`（4 ページ・35 件全件取得）を
alias ごとに集計した結果、**同一 alias 文字列が複数 version にまたがって存在する**ケースが多数実在した:

| alias | 出現 version 番号 |
|---|---|
| `pr-96` | 14, 15, 16, 17（**4 回**再利用） |
| `pr-168` | 30, 31 |
| `pr-143` | 28, 29 |
| `pr-127` | 24, 25 |
| `pr-120` | 22, 23 |
| `pr-106` | 18, 19 |
| `pr-88` | 7, 8 |
| `sp1` | 2, 13 |

これは brief 事実1（PR への push のたびに同じ `--preview-alias pr-<N>` を再実行する現行運用）が
**実際に何百回も成功してきた記録そのもの**である。つまり「同名 alias で新 version を upload できるか」は
仮説ではなく、**このリポジトリの CI/CD が毎日実行して壊れていない実績**。

**根拠3（生存確認・非破壊 GET）**: 4 回再利用された `pr-96` の alias URL を直接叩いた。
```
$ curl -o /dev/null -w "%{http_code}" https://pr-96-gem-hunter.kinamocchi-tech.workers.dev/
307
```
404/410 ではなく `307`（アプリのロケールリダイレクト相当の正常応答）。**alias は "死んだポインタ" になっておらず、
現在も何らかの version へ生きたルーティングをしている**ことを確認した（どの version 番号が今応答しているか
までは中身の差分がないため確認できていないが、"再利用しても壊れない" ことの直接証拠にはなる）。

**結論**: 「既に存在する alias 名」を新しい version upload に指定してもエラーにならず、**張り替えが起きる**
（ドキュメントに明文の保証こそないが、実装方式と実データの両方が一致して支持している）。

**設計への転用（lead 向け提案）**: Sprint Review accepted 後、**その PR の alias 名でスタブ version
（例: 「このプレビュー環境は完了しました」を返すだけの最小 Worker）を upload** すれば、
- 元のコードは alias URL からは**もう配信されなくなる**（`SD-1` の「プレビュー URL で操作レビューできる」
  という状態を意図的に終わらせられる）
- ただし **version オブジェクト自体（元のコード）は削除されない**（争点A のとおり削除 API が無いため）。
  「クリーンアップ」の実体は **delete ではなく overwrite** になる、という認識をチームで共有すること。
- これは `versions upload` という「実際にデプロイを1回行うアクション」であり、本調査（GET のみ）の
  スコープ外。**実装フェーズで lead が実施・検証すること**（本エージェントは実行していない）。

**未確定点（unknown・実機で確かめるべきこと）**:
1. スタブ再アップロード後、alias URL が新スタブを返すまでの伝播遅延（即時か・数秒か）→
   `npx wrangler versions upload --preview-alias pr-<N>` 実行直後に
   `curl -s https://pr-<N>-gem-hunter.kinamocchi-tech.workers.dev/` を数回叩いて確認すればよい（1 コマンド）。
2. 旧 version 側の "versioned preview URL"（alias とは別の、version ごとに自動発行される固有 URL）は
   このテクニックでは無害化されない（alias とは別物のため）。実害があるかは `M-4`/公開判断ゲート次第。

### (c) `previews_enabled` OFF は SD-1 と両立するか → **両立しない（明確に否定）**

`sprint-development-rules.md` SD-1 は「スプリントの PR には**開けるプレビュー URL**を貼る」ことを
**PR ごとの個別レビュー時点**（Sprint Review よりずっと手前・PR 作成直後）で要求している。
一方 `previews_enabled` は Worker 単位のフラグで、**全 PR のプレビューを同時に無効化する**（争点A で実測確認済み、
GET `.../subdomain` → `{"enabled": true, "previews_enabled": true}` の独立フィールド）。

したがって OFF にした瞬間、**そのとき進行中の他のすべての PR のプレビュー URL も同時に 403/無効化される**。
1件のスプリントの Sprint Review 完了をトリガーに OFF にする設計は、**他の並行中 PR の SD-1 要件を破壊する**
（本プロジェクトは複数セッション並行稼働が前提・`session-concurrency-rules.md` CP-4）。
**この案は不採用が妥当。** 争点Aの結論どおり「一括トグル」は最終手段（例: インシデント対応で全プレビューを
緊急停止したいときのみ使う）であり、通常のスプリント後始末の手段には使えない。

### 追加調査: version 増加自体に課金・クォータ・性能上の実害があるか

`search_cloudflare_documentation` で「Workers versions storage billing cost quota per script」を検索したが
**該当ドキュメントが 0 件**（前ラウンドの `workers/platform/limits/` 全文確認と合わせても、version 数への
課金・アカウント上限の明記は見つからなかった）。断定できる一次情報がないため、以下は unknown として扱う:

- version の保存自体に追加課金が発生するか → **unknown**（billing ページに記載なし）
- version 数に対するアカウント/プランの hard cap があるか → **unknown**（"Number of Workers" 100〜500 は
  Worker 数の上限であり version 数の上限ではないことのみ確認済み。争点A で既出）
- 性能（デプロイ速度・API 応答速度）への影響 → **unknown**（`GET .../versions` は 35 件で応答 200・数百ミリ秒
  以内に返っており、現状の件数では体感できる劣化は無い。1000+件になったときの挙動は未検証）

確認できているのは **alias の 1000 件 LRU 上限のみ**（争点Aで既出）。version 自体の際限ない蓄積が
「実害ゼロで無視してよい」とまでは言い切れない（unknown が残る）ため、harness_ops の「検出だけを
project-sync に足す」案（診断用途）には賛成しつつ、**「実害なしと断定して何もしない」という結論には反対**。
低頻度（例: 週次）で `total_count` の伸びだけでも記録しておく価値はある（既存の検出スクリプトに
1 行足すだけで済むはずなので追加コストはほぼゼロ）。

---

### 争点E まとめ（3行）
- (b) 同名 alias への張り替えは**可能**（wrangler 実装 + 本アカウントの実データ + 生存確認 curl の3点で確認）。ただし「削除」ではなく「スタブで上書き」であり、version 自体は残り続ける。
- (c) `previews_enabled` OFF は**SD-1 と両立しない**（全PR一括無効化のため、並行中の他PRのレビューを破壊する。不採用が妥当）。
- version 増加自体の課金・上限影響は**未確認（unknown）**。断定材料なし。実害ゼロと決めつけず、件数だけでも定期記録する低コスト策を推奨。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-20T16:42:00+09:00</sub>

## 4 レンズの議論を経て残った事実（lead が実測で再確認したものを含む）

1. **PR 単位の version / preview alias を削除する CLI・REST API は存在しない**（cf_platform・harness_ops が独立に確認。wrangler 4.124.0 の `versions` に delete 系サブコマンドなし、公式 Preview URLs ページに削除経路の記述なし）。能動的に効く操作は Worker 全体の `previews_enabled` トグルのみで、これは並行中の他 PR のプレビューも巻き添えにするため `SD-1` と両立しない（不採用）。
2. **同名 alias の張り替えは可能**（cf_platform が wrangler 実装と実データで実証。lead も Cloudflare API の実応答で追認 — 本アカウントには `pr-96` に 4 version、`pr-168` / `pr-143` / `pr-127` / `pr-120` / `pr-106` / `pr-88` / `sp1` に各 2 version が同名 alias で紐づいている）。ただしこれは「削除」ではなく **内容の上書き**であり、version オブジェクト自体は残る。
3. **古いプレビュー環境は現に生きている**（lead 実測: `pr-73` / `sp1` / `form-uiux` が HTTP 200 を返す）。つまり「古いスプリントのコードが今も公開され続けている」という飼い主の懸念は実在する。version は 35 件、うち alias 付きは 26 件。
4. **`wrangler deploy` に `--preview-alias` は無い**（lead 実測: `deploy --help` の `--alias` はモジュール置換の別機能）。張り替えは `versions upload --preview-alias` 経由に限られる。
5. **デプロイゲートには非スプリント PR という迂回路がある**（lead 指摘 → release_eng が選択肢 1「直列化」で塞ぐことに同意し、round 1 の「穴を受け入れる」を撤回）。スプリント PR のレビュー判定を待つ間に別セッションが非スプリント PR をマージすると、その Step 6 デプロイが `main` HEAD ごと本番へ出してしまうため。
6. **Step 7 中断時にデプロイが永久に起きない経路がある**（release_eng 指摘 → harness_ops が「Issue が open のまま残るだけでは不十分」を受け入れ、`進捗:` マーカーにデプロイ状態を持たせる案へ修正）。
7. **孤児 alias の「検出だけするツール」は入れない**（harness_ops が自身の費用対効果基準に照らして撤回）。ただし lead は、争点 E の結論により **検出は張り替えの入力として意味を持つ**ため、独立ツールではなく張り替えツールの dry-run として実装する。

## 対立が残った点と lead の裁定

- **「削除できないのだから放置 + 期待値のドキュメント化に留める」（harness_ops / docs_trace の round 2 案）を採らない。** 事実 3 の通り古いコードが公開され続けており、飼い主の指示の意図（スプリント完了後にその環境を残さない）が満たされない。事実 2 の張り替えが実装可能で、コストは本番デプロイで既に作ったビルド成果物を使い回す upload 1 回に収まる。**「削除はできないが、古い内容を配信し続ける状態は解消できる」**が採用する結論。
- **version 増加の実害は unknown のまま**（cf_platform）。断定せず、張り替えツールに version 件数の出力を持たせて観測可能にする。

### `lead` — 判定
<sub>2026-08-20T16:42:00+09:00</sub>

{
  "decisions": [
    {
      "issue": "A/E: スプリント環境の後始末",
      "decision": "「削除」は技術的に不可能と確定。代わりに『退役（retire）= 完了スプリントの preview alias を本番と同じビルドへ張り替える』を採用する。alias URL は生き続けるが、配信内容は本番と同一になり、古いスプリントのコードが公開され続ける状態は解消される。",
      "rationale": "削除 API 不在は cf_platform / harness_ops が独立確認。張り替え可能は wrangler 実装 + 本アカウントの実データ（同名 alias が複数 version に紐づく）+ lead の API 実応答で実証。previews_enabled 全体 OFF は SD-1 と両立せず不採用。",
      "files": [
        "docs/03_design/infrastructure/cloudflare-infrastructure.md §6.1 に『preview alias は削除できない（1000 件 LRU のみ）』と §8 に退役手順を追記",
        "docs/02_requirements/open-questions.md に決定を記録"
      ],
      "tools": [
        "tools/retire_preview_aliases.py 新規: --list（クローズ済み PR に紐づく生存 alias の一覧・dry-run 兼用）/ --alias <name>（1 件退役）/ --closed-prs（クローズ済み PR 由来を一括退役）。ビルド成果物 .open-next を再利用し wrangler versions upload --preview-alias <name> --tag retired-<sha> を呼ぶ。--self-test 付き"
      ]
    },
    {
      "issue": "B: 本番デプロイの発火点",
      "decision": "スプリント PR（Sprint Goal: 行あり）は Step 6 でデプロイせず、Step 7 のスプリントレビュー判定が accepted のときにデプロイする。非スプリント PR は Step 6 で即デプロイのままとするが、『未確定の Sprint Review が main 上に残っている間はデプロイしない』という共通ゲートを通す（デプロイの直列化）。",
      "rationale": "release_eng が round 2 で選択肢 1 を採用。非スプリント PR を無条件に即デプロイすると、レビュー待ちのスプリント成果物が main 経由で本番へ漏れる（CP-4 の並行前提）。ADR 0004 の trunk-based は §3.3 で既に『main マージ後のテストゲート』を認めており、レビューゲートはその拡張として整合する（ADR 再判定は不要・追記のみ）。",
      "files": [
        ".claude/skills/pr-review-watcher/SKILL.md Step 6（ゲート判定を経由・スプリント PR はデプロイを Step 7 へ委譲）/ Step 7（accepted 時のデプロイと退役を追加）",
        "docs/03_design/infrastructure/cloudflare-infrastructure.md §8.2（手順の実体はここ。SKILL.md からは参照のみ）",
        "docs/adr/0004-release-cycle-trunk-based.md §4 にレビューゲートを追記"
      ],
      "tools": [
        "tools/check_deploy_gate.py 新規: main 上に『判定未投稿 or rejected』のスプリント Issue が残っていないかを GitHub API で判定し、0=デプロイ可 / 1=待機 / 2=判定不能 を返す。--self-test 付き"
      ]
    },
    {
      "issue": "C: 判定別の可否と fail-closed",
      "decision": "accepted → デプロイ + 退役を実行。accepted_with_conditions → 判定コメントに deploy: yes|no を 1 行明記させ、既定 yes。rejected → デプロイしない（退役も行わない。プレビューは差し戻し検証にまだ使うため）。判定不能・ツール失敗時はデプロイしない（fail-closed）。",
      "rationale": "release_eng round 1/2。デプロイ前にゲートを置けば rollback が不要になり、現行（即デプロイ後に rejected 発覚 → rollback）より安全側。",
      "files": [".claude/skills/pr-review-watcher/SKILL.md Step 7 の判定テンプレートに deploy 行を追加"],
      "tools": []
    },
    {
      "issue": "D: 実装先と取り残しの回収",
      "decision": "主防御は Step 7 の『進捗:』マーカーにデプロイ・退役の状態を持たせること（sprint-cycle-router Step 3 の stale 再開が読む既存マーカーを拡張。新ラベル・新 state ファイル・新ディレクトリは作らない）。副防御として PostToolUse フックを 1 本追加し、Sprint Review 判定コメントの投稿を検知してデプロイ未実行なら additionalContext で指示する（ブロックしない）。孤児 alias の『検出専用ツール』は入れない（張り替えツールの --list が兼ねる）。",
      "rationale": "harness_ops round 2（Issue が open のままでは不十分を受け入れ、マーカー拡張を主防御に格上げ）+ release_eng の再試行要件。matcher はツール名でしか掛からないため、本文判定は post-merge-publish-check.sh と同型の jq 絞り込みで行う。",
      "files": [
        ".claude/skills/pr-review-watcher/SKILL.md Step 7",
        ".claude/skills/sprint-cycle-router/SKILL.md Step 3（判定済み・デプロイ未実行の再開）",
        ".claude/hooks/post-sprint-review-deploy-check.sh 新規 + .claude/settings.json への配線"
      ],
      "tools": []
    }
  ],
  "rejected": [
    "previews_enabled の全体トグルで一括停止する案 — 並行中の他 PR のプレビューまで巻き添えにし SD-1 と両立しない（cf_platform）",
    "孤児 alias の検出専用スクリプトを新設する案 — 削除できない世界では行動に繋がらない（harness_ops が自ら撤回）。張り替えツールの --list に統合",
    "『削除できないので放置 + 期待値のドキュメント化のみ』案 — 古いコードが実際に HTTP 200 で公開され続けており（lead 実測）飼い主の指示の意図を満たさない",
    "非スプリント PR のデプロイを無条件に即実行する案（release_eng round 1）— レビュー待ちのスプリント成果物が main 経由で漏れる（本人が round 2 で撤回）"
  ],
  "unknowns": [
    "version が増え続けることの課金・クォータ・性能への影響（一次情報が見つからない）。退役ツールに version 件数の出力を持たせて観測可能にする",
    "退役 upload の実行時間とシークレット継承の挙動（versions upload は既存シークレットを引き継ぐと §7.2.1 にあるが、退役でも同様かは実機で確認する）"
  ],
  "follow_up_issues": [
    {
      "title": "improvement: preview version の件数と課金影響を定点観測する",
      "labels": ["type:improvement", "sp:1", "priority:low"],
      "done_criteria": "version 件数が記録され、増加が問題化する閾値の判断材料になっている"
    }
  ]
}
