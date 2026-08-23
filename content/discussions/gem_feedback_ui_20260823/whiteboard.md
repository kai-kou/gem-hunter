<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: Gem 機能フィードバック 3 件（一覧導線の視認性 / Gem 一覧カードの表示項目 / 件数と説明文の不一致）の設計を確定する

- 議題ID: `gem_feedback_ui_20260823`
- 論点: 飼い主フィードバック（実機スクリーンショット付き・2026-08-23）: (F-1) 検索結果上部の「この検索語の Gem 候補を一覧で見る」導線がテキストリンクのままで埋もれている。ボタン風にするか、アプリタイトルで使っているアイコン（public/images/logo.webp）を文言の頭に添えるなどして目立たせてほしい。(F-2) Gem 一覧（/{locale}/gems）の各カードに、検索結果一覧（RepositoryList）で表示している項目も含めてほしい。(F-3) Gem 一覧の件数表示（例「5 件」）と説明文（「検索結果で Gem の印が付いていた候補 4 件を、名前が一致しないものも含めてこの一覧に加えています。」）の件数が一致しておらず、利用者が矛盾と受け取る。

現行実装（すべてリポジトリ絶対パスで実在）: 導線は src/ui/gem-list-link.tsx（text-primary の素のテキストリンク・className は back-link.tsx / repository-list.tsx と同じ意匠）で、呼び出しは app/[locale]/page.tsx の 240〜280 行付近（messages.home.gemBadge.intro の 1 文の直後・結果一覧より前・0 件では出さない）。Gem 一覧カードは src/ui/gem-list.tsx が描画し、1 件あたり repositoryFullName（詳細へのリンク）/ packageName / registry / stars / dependentCount / gemIndex を出す。検索結果カードは src/ui/repository-list.tsx で、avatar 画像 / fullName / Gem バッジ / description / primaryLanguage / stars / lastPushedAt / topics（先頭 5 件）を出す。Gem 一覧のデータ源は静的アセット public/data/gem-index/（src/infrastructure/platform/static-gem-index.ts が読む）で、型は src/domain/model/gem.ts の GemPoolEntry = { packageName, repositoryFullName, dependentCount, stars, gemIndex, registry } のみ。description / 言語 / topics / 最終更新日 / avatar は候補プールに存在しない。件数の算出は src/infrastructure/platform/static-gem-index.ts の mergeIncludedRecords（includedCount = 名前照合 AND に一致しなかったが badged 同伴で新規追加された件数）で、UI 文言は messages/ja.json・messages/en.json の gems.totalCount / gems.includedFromSearch。ページ配線は app/[locale]/gems/page.tsx。

F-3 の実測（スクリーンショット）: 検索語 next.js で総件数 5 件・注記 4 件。tokenizeQuery('next.js') = ['next','js'] の AND に一致したのは vercel/next.js の 1 件のみで、残り 4 件は検索結果でバッジが付いていた候補の同伴（badged・Issue #453 の案3'）による追加。vercel/next.js も badged に含まれるが名前照合で既に一致しているため includedCount には数えない。つまり数値としては破綻していないが、文言が「検索結果で Gem の印が付いていた候補 4 件を…加えています」と読め、実際に印が付いていたのは 5 件なので **説明が事実と食い違う**。

制約: (a) D-29 — Ecosyste.ms の生テキスト（description 等）は再配信しない。候補プールに数値・識別子・自作派生値しか持たないのはこの決定に由来する。(b) クリーンアーキテクチャ依存規則（docs/rules/architecture-rules.md・docs/03_design/architecture/application-architecture.md）: src/ui/ は表示のみ・app/ は infrastructure を直接 import しない・GitHub API に触れてよいのは src/infrastructure/github/ の ACL だけ（NFR-16 / TR-4）。データソースは GET /search/repositories と GET /repos/{owner}/{repo}（+ SP-16 で足した README）に限定という E-2 の宣言がある。(c) INF-2 / NFR-7 — Cloudflare Workers Free の CPU・サブリクエスト上限と低コスト維持。Gem 一覧は GitHub API を 1 回も呼ばずに描ける現行設計が SPOF 回避（D-28）にもなっている。(d) NFR-3 クライアント JS を増やさない。(e) NFR-12 / NFR-13 a11y（ライブリージョンは 1 つ・フォーカスリング太さ・見出し階層・タッチターゲット）と docs/03_design/ui-ux/ui-ux-guidelines.md のデザイントークン（ボタンは src/ui/button.tsx が既存）。(f) D-36 — Gem Index を並び替え軸にしない・印が付かないことは低評価を意味しない注記が必須。(g) SD-2 TDD 主体（テストを先に書く・操作レビュー手順は e2e/sp-19.spec.ts へ写す）。

争点は少なくとも次の 5 つ: A) F-1 の実装形（既存 button.tsx の意匠を流用した「ボタン風リンク」にするのか、リンクのままアイコン + 強調に留めるのか。logo.webp をアイコンとして流用してよいか（ロゴの意味が『アプリ』から『Gem 一覧』へ二重化しないか・alt/装飾扱いの妥当性・24px 以下での視認性・webp 1 枚の再利用 vs 新規アセット生成 vs インライン SVG）。gemBadge.intro の説明文との位置関係・視覚的階層。タッチターゲット 44px・フォーカスリング・ダークモード。検索結果 0 件で出さない現行仕様を維持するか） B) F-2 でカードに足せる項目は何か（候補プールに実在するのは registry / packageName / dependentCount / stars / gemIndex のみ。検索結果と揃えるには description・言語・topics・最終更新日・avatar が要るが、これらは D-29 か GitHub API 追加呼び出しに抵触する。avatar だけは https://github.com/{owner}.png で API を使わず出せるが外部画像リクエストが 20 件増える。GitHub API を最大 20 件分呼ぶ案（GET /repos/{owner}/{repo} × N もしくは GraphQL 一括）は E-2・NFR-7・INF-2・D-28 の SPOF 回避とどう衝突するか。『通常の一覧で表示している項目も含める』という指示を、どこまでが仕様として満たされたと言えるか） C) F-2 を満たす際のカードの構造（検索結果カードと同じレイアウトへ寄せるのか、Gem 一覧固有の項目（Gem Index・レジストリ・利用パッケージ数）を主役に据えたまま不足項目だけ足すのか。共通コンポーネント化すべきか（repository-list.tsx と gem-list.tsx を 1 本にすると型と責務が混ざる懸念）。a11y（リンク領域拡張の ::after とバッジ・画像の関係）） D) F-3 の正しい仕様（① 文言だけ直す＝「この一覧の N 件のうち M 件は、検索結果で Gem の印が付いていた候補です」の形にする ② includedCount の意味を『同伴指定のうち一覧に載っている総数』へ変える＝ポート契約 GemPoolSearchResult.includedCount の意味変更 ③ 両方の数を返して文言で使い分ける。どれがユーザーの誤読を最も減らすか。ポート契約を動かす場合の影響範囲（src/domain/ports/gem-index-port.ts・static-gem-index.test.ts の既存 10 ケース・search-gems.ts・gem-list.tsx・messages 2 言語）。総件数 role=status とのライブリージョン重複規律を壊さないか） E) 上記 3 件を 1 PR にまとめるか分けるか、E2E（e2e/sp-19.spec.ts・e2e/sp-18.spec.ts）と単体テスト（src/ui/*.test.tsx）の追加範囲、docs（docs/02_requirements/user-story-map.md §5.3 SP-19 の操作レビュー手順・prd.md の AC・docs/02_requirements/open-questions.md の D-36/D-37 追補）の更新要否。
- 参加者: `ux_entry`, `data_scope`, `count_truth`, `docs_trace`
- 投稿数: 4
- 更新: 2026-08-23T12:06:11+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `data_scope` — 主張
<sub>2026-08-23T12:04:29+09:00</sub>

## 結論

「検索結果一覧と同じ項目を Gem 一覧カードにも含める」は **一部しか満たせない**。

- **足せる（コスト実質ゼロ）**: avatar 画像（`https://github.com/{owner}.png` を `repositoryFullName` の owner から組み立て。GitHub API 呼び出し不要・認証不要・D-29 の対象外）
- **足せる（既に静的データにある列の見せ方の話）**: stars・dependentCount は既に出ている。primaryLanguage・topics・lastPushedAt・description は **候補プールのシャードに列自体が存在しない**ため、静的データからは一切出せない
- **足せない（D-29 で禁止）**: description（Ecosyste.ms の生テキスト）は仮に取得できたとしても再配信禁止
- **足せない（アーキテクチャ・コスト上不可）**: primaryLanguage・topics・lastPushedAt を GitHub API 1 ページ (20 件) 呼び出しで補う案は、レイテンシ・ACL 層・SPOF 設計のいずれの観点からも却下すべき

## 根拠

### 1. シャードの実データ列（実測・`public/data/gem-index/npmjs-org.json` head）
```
"columns":["repositoryFullName","packageName","dependentCount","stars","gemIndex"]
```
12 シャード全て `index.json`（`/home/user/gem-hunter/public/data/gem-index/index.json`）の `shards[]` から生成されており、columns はこの 5 列で固定（`static-gem-index.ts` の `COLUMN_*` 定数もこの 5 列しか読まない）。**description・primaryLanguage・topics・lastPushedAt・avatarUrl はどのシャードにも存在しない**。型定義（`src/domain/model/gem.ts` の `Gem` / `GemPoolEntry`）もこの 5 フィールド + `registry` のみで、型を見ただけでも実データを見ても結論は同じ。

### 2. `repository-list.tsx` が出す項目のうち、Gem 一覧に追加可能かの仕分け

| 項目 | 出所 | Gem 一覧への追加可否 |
|---|---|---|
| avatar 画像 | `item.owner.avatarUrl`（GitHub API `search/repositories` の `owner.avatar_url`） | **可**。ただし Gem 一覧にはこの値自体が無い。`https://github.com/{owner}.png`（`repositoryFullName.split('/')[0]`）という **GitHub 公式の慣例 URL パターン**で組み立てれば API 呼び出し・認証・ACL 通過が一切不要（`<img>` の `src` に直接 URL を置くだけ。詳細ページ `repository-detail.tsx` も同じ `owner.avatarUrl` を使っているだけで特別な API 呼び出しはしていない）。ただし GitHub 側の非公式仕様への依存（プライベート運用時にレート制限/変更の可能性）は Issue 化して明示すべき |
| description | Ecosyste.ms 由来の生テキスト（Gem の場合）or GitHub API 由来（検索結果の場合） | **不可**。仮に GitHub API から取得しても D-29 の対象外だが、そもそも今回の論点は「候補プールの静的データに無い列を足す」ことなので、取得には GitHub API 呼び出しが要る（下記 3 参照）。かつ Ecosyste.ms 側にも該当データがあるなら D-29「生テキスト再配信禁止」に抵触する |
| primaryLanguage / topics / lastPushedAt | GitHub API 由来（検索結果 API のフィールド） | **静的データに無い。GitHub API 追加呼び出しが必須**（下記 3 参照） |
| stars / (dependentCount 相当) | 両方の一覧に既にある | 追加不要（Gem 一覧は既に stars を表示済み） |

### 3. GitHub API 1 ページ (最大20件) 呼び出し案の定量評価 — **却下すべき**

- **ACL 違反ではない**が層違反リスクが高い: `TR-4`/`NFR-16` は「GitHub API に触れてよいのは `src/infrastructure/github/`（`GithubRepositoryQuery`）だけ」であり、これ自体は守れる（`GithubRepositoryQuery` 経由で呼べば ACL は通る）。しかし現在の `search-gems.ts`（`makeSearchGems`）は `GemIndexPort` にしか依存しておらず、Gem 一覧の描画パスに GitHub API 依存を新規に持ち込むことになる。
- **許可エンドポイント表（prd.md §4.3）に無い**: 表は `GET /search/repositories`・`GET /repos/{owner}/{repo}`・`GET /repos/{owner}/{repo}/readme` の 3 つに **限定**しており「新規エンドポイントの追加は本表への追記を伴う」。20 件分の詳細を 1 回で返すバルクエンドポイントは存在しない（`GET /repos/{owner}/{repo}` は単体取得のみ）ため、20 件を埋めるには **20 回の個別リクエスト**が必要（`GET /search/repositories` を `repo:owner/name` の OR 検索にまとめる手も GitHub 側の検索クエリ長制限とレート枠を別途消費し、実質的にエンドポイント追加相当の設計変更になる）。
- **レート枠 (NFR-7)**: 検索は 30 req/分、詳細取得（Core API）は 5,000 req/h。Gem 一覧はキーワード検索を経由しないページなので Search API の 30 req/分枠を消費する理由がなく、詳細取得 20 回/ページ表示は Core API 枠を 1 ページ表示あたり 20 消費する。同時アクセスが数人でもすぐ律速に達し、`NFR-7` の request coalescing / キャッシュ前提が崩れる。
- **Workers CPU 予算 (D-38 実測)**: 現状 Gem 一覧の初回リクエストは静的アセット処理だけで **237〜277ms**（`limits.cpu_ms=400` に対し実測最大の 44% しか余裕なし、と `D-38` が明記）。ここに 20 件の外部 fetch（ネットワーク I/O は CPU time にはあまり乗らないが、レスポンスの JSON パース・マッピングは乗る）を直列化（`NFR-7`③ が並行実行を非推奨と明記）で足すと、レイテンシは数百 ms〜数秒に跳ね上がる。CPU ms の天井というより **ユーザー体感レイテンシ（NFR-1 LCP 2.5 秒）** を壊す。
- **サブリクエスト上限**: Cloudflare Workers の subrequest 上限は Free 50/invocation・Paid 1000/invocation。20 回程度は数値上は収まるが、`D-38` の shard 取得 (12 subrequests) と合算すると余裕は減る。数値上「収まる」ことと「妥当」は別で、後述のキャッシュ不能・SPOF 問題の方が本質的な却下理由。
- **キャッシュ不能**: Gem 一覧はページ・検索語ごとに異なる 20 件の組み合わせが出る（`gemIndex` 昇順の全量走査結果からのページ切り出し）。GitHub 側データを都度 20 回 fetch する設計はキャッシュヒット率が低く、`NFR-5`（API レスポンスをキャッシュ）の効果を得にくい。
- **D-28 の SPOF 回避方針に反する**: D-28 は「候補プールはバッチ生成 + 静的配信で GitHub/Ecosyste.ms の可用性から独立させる」という設計思想（配信自体は止めず鮮度のみ劣化させる）。Gem 一覧の描画に GitHub API のライブ呼び出しを混ぜると、GitHub API 障害時に Gem 一覧自体が表示できなくなる新しい SPOF を作り込むことになり、D-28 の設計意図と正面から矛盾する。
- **E-2 (データソースの限定宣言)**: 与件が定めるデータソースの限定を Gem 一覧にまで広げる設計変更になり、影響範囲がスコープ外に広がる。

## 採る案

1. **avatar のみ追加**: `https://github.com/{owner}.png` を `repositoryFullName` から組み立てて `<img>` で表示。GitHub API 呼び出し・ACL 変更・SPOF リスクいずれも無し。実装コストは `GemList` に 1 行足すだけ
2. **description / primaryLanguage / topics / lastPushedAt は今回追加しない**: 静的候補プールに列が存在しないため、追加には (a) バッチ生成 (D-28/D-38 のシャード生成パイプライン) 側で GitHub API から新規列を収集して静的 JSON に焼き込む、(b) 実行時に GitHub API を追加呼び出しする、の 2 択しかない。(b) は上記理由で却下。(a) は将来検討に値するが、シャード生成バッチ（Cloudflare 外の cron）・シャードスキーマ・`index.json`/`columns` 契約・型定義（`Gem`/`GemPoolEntry`）・D-29 のライセンス精査を要する **別 Issue 相当の設計変更**であり、今回のフィードバック対応の範囲を超える

## 却下する案と理由

- **「検索と完全一致の項目を全部揃える」**: 型的にもデータ的にも不可能（プールに列が無い）。UI 側の実装では解決できない
- **GitHub API 1 ページ呼び出しでその場で補完**: レイテンシ・レート枠・CPU 予算・SPOF・E-2/TR-4 の設計意図のいずれの観点からも損失が大きく、Gem Index の売り（バッチ生成による低コスト配信）を破壊する
- **Ecosyste.ms の description を再配信**: D-29 が明示的に禁止

### `docs_trace` — 主張
<sub>2026-08-23T12:05:25+09:00</sub>

# docs_trace 分析結果：F-1/F-2/F-3 と既存ドキュメント整合チェック

## 3 件の変更内容
- **F-1**: 検索結果上部の Gem 一覧導線（`src/ui/gem-list-link.tsx`）をボタン風・アイコン付きに強調する
- **F-2**: Gem 一覧（`/{locale}/gems`）のカードに検索結果一覧と同じ表示項目を足す
- **F-3**: Gem 一覧の総件数表示と同伴注記（`gems.totalCount` / `gems.includedFromSearch`）の件数が食い違って見える問題を直す

---

## 矛盾・更新箇所一覧

### F-1 → 矛盾なし（整合確認済み）

| 記述場所 | 確認内容 | 結果 |
|---------|---------|------|
| `user-story-map.md` §5.3 `SP-19` 手順 2 | 「検索結果の上部にある「この検索語の Gem 候補を一覧で見る」導線を押す」 | ✅ F-1 の「導線を強調」と整合 |
| `open-questions.md` `D-36` 追記（2026-08-22） | 「導線ラベルは、実装 `home.gemListLink.label` の逐語に合わせて『Gem 候補を一覧で見る』へ確定」 | ✅ ラベル確定済み。F-1 は UI 強調するだけで逐語は変えない |
| `e2e/sp-19.spec.ts` | テストが「`home.gemListLink.label`」を参照（逐語は「Gem 候補を一覧で見る」）| ✅ E2E テストとの整合維持 |

**判定**: F-1 はドキュメント上の既定と矛盾しない。操作レビュー手順・テスト・D-36 のいずれとも整合。

---

### F-2 → 更新が要る記述あり

| 記述場所 | 現状の記述 | 問題 | 必要な対応 |
|---------|----------|------|-----------|
| `prd.md` §4.2 `AR-1` | 「一覧カードに説明文・主要言語・star 数・最終更新日・topics を表示する」 | `AR-1` は**検索結果**カードを対象としており、Gem 一覧（`/gems`）カードの仕様が記述されていない | Gem 一覧用の新規 `AR-n` を追加するか、既存 `AR-1` に「Gem 一覧でも検索結果と同じ項目を表示」という追記が要る |
| `ui-ux-guidelines.md` §4.2 | 「結果カードの情報設計」として検索結果のみ定義 | Gem 一覧のカード表示設計が記述されていない | Gem 一覧のカード設計を§に追加する（検索結果と同一か異なるか明確化） |
| `user-story-map.md` §5.3 `SP-19` | 手順書に Gem 一覧の**カード表示項目**に関する記述がない | `SP-19` の操作レビューが「一覧の有無・ページングのみ」で、カード内容について触れていない | 手順書または手順の注記に「検索結果と同じ表示項目を含むこと」を明示する必要があるか検討 |

**判定**: F-2 の変更（Gem 一覧にカード項目を足す）は実装上必要だが、その根拠・要件が既存ドキュメントに明記されていない。

---

### F-3 → 意図的な設計差分（明示が必要）

| 記述場所 | 現状の記述 | 事実 | 必要な対応 |
|---------|----------|------|-----------|
| `open-questions.md` `D-36` 本文・Issue #453 追記 | 「バッジと一覧の判定基準が異なる（`lookup` vs `search`）。検索結果にバッジが複数付いても一覧が 1 件に落ちることがある」 | 仕様上意図的な差分（GitHub API の全語 AND と、Gem プールの単語境界一致は別基準） | **ドキュメントに「この差分が意図的であり、バッグではない」という明記が要る** |
| `prd.md` §2.4.1 `from` パラメータの説明 | 「詳細ページでのみ意味を持つ」と記載 | `from=gems` で詳細から戻るリンク先が変わる動作が規定されている | ✅ 既に記載済み |
| UI / E2E テスト | 件数の差分を検証する手順がない | F-3 の変更が「見える問題」を解消する場合、UI での表現の改善（「含む Gem 件数」 vs「検索ヒット後に照合した結果」の区別表示等）が必要か不明 | **F-3 が具体的に「何を直すか」（UI 表示・ラベル・説明テキスト）をドキュメント化する必要がある** |

**判定**: F-3 の「食い違い」は `D-36` Issue #453 で明示的に設計された差分だが、ユーザーにどう説明するか（UI テキスト・注記等）が既存ドキュメントに記述されていない。

---

## 最小限の更新が必要なファイル・行

| ファイル | 行 | 更新内容 |
|---------|----|---------| 
| `prd.md` §4.2 | `AR-1` 直後 | Gem 一覧のカード表示要件を追記するか、`AR-1` の対象範囲を「検索結果 + Gem 一覧」に明確化 |
| `ui-ux-guidelines.md` §4.2 | 「結果カード」後 | Gem 一覧用カード設計（検索結果と同一か異なるか）を追記 |
| `user-story-map.md` §5.3 `SP-19` 操作レビュー | 手順 3 の注記 | 「Gem 一覧のカードに検索結果と同じ表示項目を含むこと」を明示 |
| `open-questions.md` `D-36` 追記部 | 「Issue #453」セクション | UI の表示側で「検索ヒット件数 vs Gem 照合件数」の差分をユーザーに説明する方法を記録 |

---

## 残課題

1. **F-2 の根拠**: Gem 一覧にカード項目を足すという要件が、どの `AC-n` / `GR-n` に由来するか確認が必要
2. **F-3 の UI 改善**: 件数の差分を「意図的な設計」から「ユーザーに理解可能な表現」へ変換する具体方法を定める
3. **SSOT の一本化**: Gem 一覧のカード設計が複数箇所で再掲されていないか確認（`prd.md` `AR-1` と `ui-ux-guidelines.md` の分離が正しいか）

### `count_truth` — 主張
<sub>2026-08-23T12:05:38+09:00</sub>

# F-3: 件数の意味論 — `count_truth` 分析（Round 1）

## 誤読の機序（実データで再現）

`q=next.js` → `tokenizeQuery` = `['next','js']`。名前照合（AND）に一致するのは `vercel/next.js` の
1 件だけ。検索結果ページ側で Gem バッジが付いていた候補（`badged` パラメータ、`includeFullNames`
の生値）は 5 件相当（`vercel/next.js` 自身を含む、実機では少なくとも 5 名分が渡っている）。

`mergeIncludedRecords`（`static-gem-index.ts:449-491`）のロジックを実データで辿ると:

1. `matched` = `{vercel/next.js}`（AND 一致、1 件）
2. `includeFullNames` を順に見る。`vercel/next.js` は `matchedLower.has(lowerName)` が真なので
   **`continue`** — 同伴候補としては数えない（449 行目コメントのとおり「名前照合に既に一致している、
   または同伴指定内の重複」は弾く）
3. 残り 4 件（`chimurai/http-proxy-middleware` 等）が `additions` に入り `includedCount = 4`
4. `merged = matched(1) + additions(4) = 5` 件 → これが `totalCount`

つまり **`totalCount`（5）は「一覧に実際に並ぶ行数」、`includedCount`（4）は「そのうち同伴で
足された行数」であり、両者は最初から異なる母集団を数えている**。矛盾ではなく設計どおりの値。

利用者が誤読する理由は 2 段ある:

- **(a) 引き算が閉じない**: 画面は「5 件」→「4 件を加えた」の 2 文しか見せない。`5 - 4 = 1` を
  利用者が自分で補完しないと、残り 1 件（`vercel/next.js` 自身、名前が一致した分）の存在が
  文言のどこにも書かれていない。「4 件加えた」だけでは「では残り 1 件は何なのか」が説明されず、
  「5 と 4 が食い違っている」という誤った印象になる（本来は食い違いではなく **未説明の差分**）。
- **(b) 「검색語には一致しないものも含めています」という文言の射程が曖昧**: 文言は
  「名前が一致しないものも含めて」と言うが、「含めて」の母数（5 件全体なのか、4 件だけの話なのか）
  が構文上どちらにも読める。「この一覧に加えています」の主語が「4 件」なので、5 件全体との関係が
  読者の推論任せになっている。

**利用者フィードバック「検索結果数と説明にある件数が一致していない」は、この (a)(b) の複合**——
`totalCount` と `includedCount` が別々の数を数えていること自体は妥当な設計だが、**文言がその関係
（5 = 1 + 4）を一言も明示していない**ため、2 つの独立した数値がぶつかって見える。

## 採る案: ① 文言だけ直す

**②（`includedCount` の意味変更）・③（2 数を返す）はいずれも不要と判断する。** 理由は次の3点:

1. `totalCount` と `includedCount` は既に **両方ともビューモデルに存在し、UI に届いている**
   （`GemListViewModel.totalCount` / `.includedCount`）。5 と 4 の関係を文言で説明するのに
   **新しいデータは要らない**。`total - count`（= 名前照合で一致した件数）は算数で出せる。
2. `includedCount` の現行契約（「追加された件数」）は `mergeIncludedRecords` の実装・
   `GemIndexPort` の JSDoc・既存テスト 8 本超（後述）に明示的に固定された意味論であり、
   これを「一覧に載っている同伴指定の総数」に変えると *同じ値の呼び方を変えるだけ* で
   利用者の誤読（(a)(b)）は解決しない——今度は「では検索語に一致した分はどこにあるのか」が
   同じ構造で再発するだけ（数え方を変えても、5 との関係を文言が説明しない限り同じ問題が残る）。
3. YAGNI: 表示に必要なのは「5 件のうち何件が名前不一致か」という **1 つの派生値**
   （`totalCount - includedCount`）であり、ポート契約を割ってまで新しいフィールドを増やす
   必要性が無い。`ui-ux-guidelines.md` §7.2 のライブリージョン制約（後述）も、追加の文言を
   **既存の非ライブリージョン `<p>` に足すだけ** で満たせる。

## 具体的な文言案

**`includedFromSearch` を「加えた件数」単独の告知から「内訳」の告知へ変える。** プレースホルダーを
`{count}`（同伴で加わった件数）のみから **`{count}` + `{total}`（一覧の総件数）** の 2 つへ拡張する
（`formatMessage` は任意キーのプレースホルダーに既に対応済み・置換関数実装のため後方互換）。

### ja（`messages/ja.json` の `gems.includedFromSearch`）

```
現行: "検索結果で Gem の印が付いていた候補 {count} 件を、名前が一致しないものも含めてこの一覧に加えています。"

新案: "この一覧の {total} 件のうち {count} 件は、検索語には一致しませんが、検索結果で Gem の印が
付いていたためこの一覧に加えています。"
```

### en（`messages/en.json` の `gems.includedFromSearch`）

```
現行: "We've added {count} candidate(s) that were marked as Gem in your search results, including
ones whose name doesn't match."

新案: "{count} of the {total} candidates below don't match your search words, but are shown here
because they were marked as Gem in your search results."
```

**設計判断の理由**:

- 「{total} 件のうち {count} 件」という **部分/全体の構文** にすることで、残り `{total}-{count}`
  件（名前照合で一致した分）の存在が読者の推論に頼らず文中に織り込まれる（`5 のうち 4` と言えば
  「残り 1 件は名前が一致した」がほぼ自明に読める。二重に数値を出さなくても閉じる）。
- 母数を明示することで `totalCount` の `<p role="status">`（見出し直後・`{count}` 件）と
  `includedFromSearch` の `<p>`（その直後）が **同じ数字（5）を共有** し、2 つの表示が同じ土台の
  上にあることを示す。現行は「5 件」「4 件」が別々の文に出て関連づけが読者任せだったが、新案では
  1 文目の 5 と 2 文目の 5 が同じ語（{total}）で一致し、視覚的にも紐づく。
- `unmatchableQuery` や `relaxedNotice` の既存文言スタイル（「なぜこの表示になっているか」を
  一文で説明し尽くす）に合わせている。

### `gem-list.tsx` 側の変更点（`formatMessage` 呼び出しに `total` を足すだけ）

```tsx
// 現行（199-203 行目）
{formatMessage(labels.includedFromSearch, {
  count: numberFormat.format(view.includedCount),
})}

// 変更後
{formatMessage(labels.includedFromSearch, {
  count: numberFormat.format(view.includedCount),
  total: numberFormat.format(view.totalCount),
})}
```

`GemListLabels` 型・`GemListViewModel` 型・`GemPoolSearchResult` 契約・`search-gems.ts`・
`static-gem-index.ts` の実装ロジックは **一切変更しない**（`totalCount` と `includedCount` は
既に両方 props に来ている値をそのまま使うだけ）。

## `ui-ux-guidelines.md` §7.2「ライブリージョンは 1 つ」との整合

現行実装は既にこの規律を守っている: `totalCount` の `<p role="status">` の直後に
`includedFromSearch` の `<p>`（`role` 属性なし）を並べ、コメントで明示的に「2 つのライブリージョンが
同時に読み上げられるのを避ける」としている（`gem-list.tsx:192-197`)。**本提案はこの構造を変えない**
——`includedFromSearch` の文言を差し替えるだけで、`role="status"` を新設・移動しない。読み上げは
引き続き `totalCount` の 1 箇所（「5 件」）だけがライブリージョンとして通知し、`includedFromSearch`
は视覚的な補足として非同期に読める(スクリーンリーダーは DOM 順に読むため文脈は保たれる)。
プレースホルダーを増やしても DOM 構造・aria 属性は不変なので、この規律への影響はゼロ。

## 総件数「5 件」の表示自体が正しいか（判定: 正しい。変えるべきは文言のみ）

`totalCount` を「名前照合の一致件数（1）」に変えて「表示件数（5）」と分離する案も検討したが、
**却下する**。理由:

- `clampPage`（`static-gem-index.ts:497-504`）は `merged.length`（= 同伴込みの総数）を母数に
  最終ページをクランプする。ページャの「総件数」表示が `merged.length` と異なる値になると、
  「後ろのページに進んだのに一覧の件数と総件数の関係が合わない」という **別の、より悪い齟齬**
  （ページング契約そのものの破綻）を生む。「5 件のうち 4 件」の文言が実現できるのも、
  `totalCount` が実際に画面に並ぶ行数（5）と一致しているからこそ（一致していなければ
  「{total} 件のうち」の {total} 自体が信用できない数になる）。
- `totalCount` は「絞り込み後にページングされる母集団の件数」という一貫した定義を保っており
  （検索語ヒットだけの母数、同伴込みの母数、を状況によって使い分ける方が二重定義でかえって危険）、
  現行定義（`merged.length`）を変えないことが最小の変更面を保つ。

**結論**: 総件数の値自体は正しい。誤読の原因は「5」と「4」の関係を文言が説明していないことに
尽きるため、文言修正（案①）で完全に解消できる。

## 却下する案（②③）の詳細と却下理由

### ② `includedCount` の意味変更（同伴指定のうち一覧に載っている総数へ）

却下。意味を「追加された件数（4）」から「同伴指定のうち一覧に既にある総数（5、`vercel/next.js`
含む）」に変えると:

- `mergeIncludedRecords` の実装（458-483 行目）を書き換える必要がある。現行は
  `matchedLower.has(lowerName)` で **弾いた** ものを数えない設計だが、変更後は弾いた分も
  数える必要があり、`additions.length` とは別カウンタを持つか、`includeFullNames` を先に
  `matched` との重複ぶんも含めて数え直すロジックが要る。
- `GemIndexPort#search` の JSDoc（`gem-index-port.ts:67-72`）が「**追加された** 件数」と明記して
  おり、契約変更として周知が必要。ポート契約は「複数消費者を持つ境界契約」（`gem-list.tsx` 冒頭の
  コメントが明言）なので、意味変更は影響範囲の特定が必須。
- 既存テスト（`static-gem-index.test.ts`）が **現行の「追加された件数」意味論に基づいた具体的な
  数値** を assert しており、意味変更で以下が **全て失敗する**（挙動は正しいまま、期待値だけ
  ズレる壊れ方をする——テストの意図と実装の意図が乖離する典型例、`intent-gate-rules.md` の対象）:
  - 935-960 行目: `includeFullNames: ['acme/orm-core']` → `includedCount` `toBe(1)`
  - 970-975 行目: 存在しない名前 → `toBe(0)`
  - 980-990 行目: 既に AND 一致した名前 → `toBe(0)`（②ではこのケースの意味が根本から変わる）
  - 1010-1020 行目: 大文字小文字混在 → `toBe(1)`
  - 1025-1038 行目: 重複除去 → `toBe(1)`
  - 1055-1066 行目: プールに無い名前 → `toBe(0)`
  - 1076-1102 行目: 20 件上限 → `toBe(20)`
  - 1107-1119 行目: 未指定・空配列 → `toBe(0)`（2 ケース）
- `includedFromSearch` の文言も「加えています」から「載っています」的な表現に書き換えが要り、
  結局 ① と同じ文言修正作業が **契約変更に加えて** 発生する（① の作業を代替しない、上乗せになる）。

### ③ 2 つの数を返して文言で使い分ける

却下。②ほど破壊的ではないが、**既に両方の数字（`totalCount` / `includedCount`）が UI に届いている**
ため、新しいフィールド（例: `matchedCount` や `badgedTotalCount`）を追加しても算数
（`totalCount - includedCount`）で同じ値が導けるものを重複して持つだけ。YAGNI
（1 箇所しか使わない値のために契約面を増やさない・`CLAUDE.md`「やってはいけないこと」）。
仮に採用する場合の影響ファイルは ② とほぼ同じ（`gem-index-port.ts` の型追加・
`static-gem-index.ts` の返却値追加・テスト全面更新・`search-gems.ts` の中継・
`GemListViewModel` へのフィールド追加）だが、① で同じ UX 結果が算数だけで得られる以上、
その投資に見合うリターンが無い。

## 影響ファイル一覧（採用する ① 案のみ）

| ファイル | 変更内容 |
|---|---|
| `messages/ja.json` | `gems.includedFromSearch` の文言を「{total} 件のうち {count} 件」形式へ差し替え |
| `messages/en.json` | 同上（英語文言） |
| `src/ui/gem-list.tsx` | `formatMessage(labels.includedFromSearch, {...})` 呼び出しに `total: numberFormat.format(view.totalCount)` を追加（1 箇所） |

`src/domain/ports/gem-index-port.ts` / `src/infrastructure/platform/static-gem-index.ts` /
`src/infrastructure/platform/static-gem-index.test.ts` / `src/usecases/search-gems.ts` /
`GemListViewModel` / `GemListLabels` 型定義 — **いずれも変更不要**（契約・ロジック・既存テストは
無傷のまま）。`tools/check_cjk_markdown.py` 相当の CJK 前後スペース規律は `messages/*.json` の
本文値には適用対象外（Markdown ではなく JSON 文字列のため）。

### `ux_entry` — 主張
<sub>2026-08-23T12:05:45+09:00</sub>

# F-1 導線・視覚階層: `GemListLink`（この検索語の Gem 候補を一覧で見る）

## 主張

1. **ghost variant のボタン化が正解**（プレーンリンクの装飾強化ではなく、`buttonVariants({ variant: 'ghost', size: 'default' })` へ置き換える）。
2. **アイコンは付ける**（lucide-react の `Gem`）。過剰ではない。
3. **ロゴ画像（`logo.webp`）の流用は却下**。lucide アイコンで揃える。
4. インライン新規 SVG 生成・Unicode 絵文字も却下。既存の lucide 個別 import 方針のままでよい。
5. サイズは `--size-control-xl`（44px）ではなく `--size-control-md`（32px = `size='default'`）でよい。

---

## 根拠

### 埋もれの原因は「リンクとして正しいが、視覚的な箱を持たない」こと
- `src/ui/gem-list-link.tsx` L17: 現状は `text-primary … underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring` という **素のテキストリンク**。padding もbackground も持たない。
- `app/[locale]/page.tsx` L258-274: 直前に `<p className="text-muted-foreground mt-2 text-sm">{messages.home.gemBadge.intro}</p>` があり、`gemBadge.intro` の本文（`text-sm`・`text-muted-foreground`）とリンク（`text-sm`・`text-primary`）が **同じフォントサイズ・同じインライン形状** で縦に並ぶ。色以外に階層差が無く、本文の続きのように見えて埋もれる。
- 一方、既存コードには「二次的だがアクションであることを示す」ために **既に `buttonVariants` を通した Link** が複数ある: `pagination.tsx` L42（`linkClassName = buttonVariants({ variant: 'ghost', size: 'default' })`）、`login-link.tsx` L34（`buttonVariants({ variant: 'ghost', size: 'sm' })`）。この 2 件は「ページ送り」「ログイン」という **リンクだが操作感を持たせたい導線** で、今回の「Gem 一覧へ行く」も同じ性質（データを変える副作用は無いが、ユーザーの導線として能動的に押させたい）。**新しいパターンを増やさず、既存の ghost button パターンに合流させるのが一貫性上も正しい**。
- `ui-ux-guidelines.md` L142: 「高さとフォントサイズは cva の `size` variant 経由でのみ指定し、呼び出し側の `className` に生の `h-*` / `text-*` を書かない」が 🔴 必須。現状の `gem-list-link.tsx` は `text-sm` を直書きしており、これ自体がこの規約から外れている。ボタン化で cva 経由に是正できる。

### filled primary（`bg-primary`）にはしない
- `search-form.tsx` の検索ボタンが既に `size="xl"`（44px）の `bg-primary` 主要 CTA を持つ（`ui-ux-guidelines.md` L146「主要導線（検索入力欄・検索ボタン）は `--size-control-xl` を使う」）。同じ画面に `bg-primary` の箱をもう一つ置くと、視覚的に「どちらが主役か」が競合し F-1（視覚階層）が逆に悪化する。
- `ghost` は「resting は背景無し、hover で `bg-muted`、focus-visible で `ring-3`」という **箱の形はあるが主張しない** 変化を持つ（`button.tsx` L23-24）。ページ送り・ログインと同じ「二次導線としての箱」を Gem 一覧リンクにも与えれば、埋もれ対策として十分でありやり過ぎでもない。

### アイコン付与は妥当（意味の二重化ではない）
- `repository-detail.tsx` L1, L52-55, L115 に既存パターンがある: `lucide-react` から個別 import → `<Icon aria-hidden="true" className="size-4 shrink-0" />` をラベル文言の直前に置く。`ui-ux-guidelines.md` L31「アイコンは shadcn/ui の既定に従う。個別 import し、アイコンセット全体を bundle に載せない」に合致。
- アイコン + 可視ラベルの並置は「唯一の情報源をアイコンにする」（`ui-ux-guidelines.md` L427 相当）とは別物で、ラベルが常に主でアイコンは装飾的な走査補助（`aria-hidden="true"`）。`gem-badge.tsx` の「色だけで意味を伝えない」原則（L9）とも矛盾しない——ここでは色を意味の担体にしていない。
- **F-1（視覚階層・走査性）の観点で効く**: 検索結果ページの中で「これはページ内リンクではなく、別画面へのナビゲーション」であることを、テキストだけより先に目に入るピクトグラムで示せる。

### ロゴ画像流用は却下（意味の二重化・技術的不整合）
- `site-header.tsx` L41-58 のロゴは **サイトブランド（アプリのトップページ）を表す紋章** として `<h1><Link href={`/${locale}`}>` の中に置かれている。ここに同じ画像を「Gem 一覧へ行く」リンクの頭に付けると、ユーザーは「これもトップページ（ホーム）へのリンクでは」と誤読しかねない——**アイコンは隣接ラベルの行き先を表すべきで、ブランドマークの使い回しはリンクの行き先を誤認させる**。これは飼い主フィードバックが問う「意味の二重化」そのもの。
- `tools/ui-assets/README.md` L13, L114-118: `logo.webp` は `gpt-image-2` で生成した **固定色のラスター画像**（透過 96px→24px 配信）で、`currentColor` に追従する SVG ではない。ダーク/ライト両テーマで同一ファイルを使う設計はヘッダーという特定の背景文脈でのみ検証されている（`ui-ux-guidelines.md` §7.4 の装飾イラスト規定 L431 も「logo / hero-idle / empty-result / not-found の 4 点」に**用途を限定**しており、ghost ボタンの hover 背景（`bg-muted`）上での視認性は未検証)。16-24px 帯での可読性を新たに保証し直す必要が生じる。
- lucide アイコンは `stroke="currentColor"` ベースの SVG で、ライト/ダークどちらのテーマトークンにも自動追従し、追加のネットワーク往復・decode コストも無い（既にバンドル済みの依存）。ロゴ画像の流用はこの利点を放棄して装飾ラスター画像の追加参照を増やすだけで、メリットが無い。

### 却下する代替案
- **新規アイコンをアセット生成**（`tools/ui-assets/` で gpt-image-2 生成）: YAGNI。既存の lucide セットに `Gem` という直接的なピクトグラムが既に存在し、個別 import 方針（L31）にそのまま乗る。生成→変換→レビューのコストに見合わない。
- **Unicode 絵文字（💎 等）**: 却下。OS・フォントでグリフが異なり配色をトークンで制御できない（`--color-accent` 等のセマンティックトークンで着色できるのは SVG のみ）。§2.1 の「生の色をコンポーネントに直接書かない」という運用と相容れない（絵文字の色は環境依存の固定色）。

### サイズは `--size-control-md`（`size='default'`）で十分
- `ui-ux-guidelines.md` L146-147:「主要導線（検索入力欄・検索ボタン）は `--size-control-xl`」「二次的なコントロールは `--size-control-md` 以上」。Gem 一覧リンクは検索結果画面における **二次導線**（検索そのものではない）なので `xl` に引き上げる必然性は無く、`default`（32px）で `--size-control-xs`（24px）のフロアも `--size-control-md` の推奨もどちらも満たす。タッチターゲット的にも 32px は既存のページ送り・ログインと同格で一貫する。

---

## 具体的な実装案

`src/ui/gem-list-link.tsx` を以下へ置き換える（`src/ui/` は表示のみ・文言は props 経由という E-4 を維持、`href` 組み立ての責務は呼び出し側のまま変更なし）。

```tsx
import { Gem } from 'lucide-react'
import Link from 'next/link'
import { buttonVariants } from './components/button'

/**
 * 検索結果から Gem 一覧（`/{locale}/gems`）への導線（`SP-19`）。表示だけを持つ
 * Server Component で、文言は props 経由（`E-4`）。
 *
 * 🔵 F-1（飼い主フィードバック・埋もれ対策）: 素のテキストリンクではなく
 * `buttonVariants({ variant: 'ghost', size: 'default' })` を通す。`pagination.tsx` /
 * `login-link.tsx` と同じ「操作感を持たせたい二次導線」パターンに合流させる
 * （新しい見た目のパターンを増やさない）。`bg-primary`（filled）にしないのは、
 * 検索ボタン（`--size-control-xl`）という既存の主要 CTA と主張を競合させないため。
 *
 * `href` の組み立て（ロケール・検索語のクエリ化）は呼び出し側（`app/` の配線）の責務。
 * ここで URL を組み立てると、検索条件の正本が `app/` と `src/ui/` の 2 箇所に分かれる。
 */
export function GemListLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className={buttonVariants({ variant: 'ghost', size: 'default', className: 'gap-1.5' })}
    >
      {/* 装飾アイコン（走査補助）。ロゴ画像は使わない — ブランドマークの使い回しは
          「ホームへのリンクでは」という誤読を招く（意味の二重化）。lucide は currentColor
          追従で追加ネットワーク往復も無い。 */}
      <Gem aria-hidden="true" className="size-4 shrink-0" />
      {label}
    </Link>
  )
}
```

- `focus-visible:ring-3` / `focus-visible:ring-ring` は `buttonVariants` の共通ベースクラス（`button.tsx` L11）にそのまま含まれるため、既存の `gem-list-link.test.tsx`（`toContain('focus-visible:ring-3')` / `toContain('focus-visible:ring-ring')`、`getByRole('link', { name })`）は **無修正で通る**（アイコンは `aria-hidden` でアクセシブルネームに含まれない）。
- `messages.home.gemBadge.intro` との位置関係・0 件時に出さない現行仕様（`page.tsx` L258, L275）は変更不要。ghost button 化で箱の形が付くこと自体が、直前の `<p>`（本文）とリンク（アクション）の視覚階層を分離する。
