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
- 投稿数: 4
- 更新: 2026-08-20T16:35:32+09:00

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
