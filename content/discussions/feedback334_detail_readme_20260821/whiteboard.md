<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 初見フィードバック 6 件（タイトル導線 / 詳細画面の情報量 + README / RSS 撤去 / 出典リンク化）の設計を確定する

- 議題ID: `feedback334_detail_readme_20260821`
- 論点: 飼い主フィードバック（Issue #334）: (F-1) ツールタイトルをクリックしたら未検索状態の画面へ遷移してほしい (F-2) 詳細画面もトップと同じくツールタイトルを含めて同じ挙動にしてほしい (F-3) 詳細画面にも一覧にある概要（description）と最終更新日を追加してほしい（一覧にあるのに詳細にない状態を解消する） (F-4) 詳細画面で README が読めるようにしてほしい (F-5) トップ末尾の RSS 機能は廃止 (F-6) 出典表示の Ecosyste.ms もリンク化してほしい。現行実装: トップ app/[locale]/page.tsx（h1 = messages.home.title 'gem-hunter' のプレーンテキスト・検索フォーム・キーワード未入力時のみ日次ダイジェスト表示）、詳細 app/[locale]/repos/[owner]/[repo]/page.tsx（h1 = repository.fullName の GitHub 外部リンク・LocaleSwitcher・BackLink・4 つの統計 dl のみ。Suspense/loading.tsx は notFound() の 404 を守るため意図的に置いていない）、出典 src/ui/attribution-notice.tsx（{source} は現在プレーンテキスト・{license} だけリンク）、RSS は src/ui/daily-digest.tsx の購読リンク + app/api/digest/rss/route.ts + src/composition/digest-feed.ts + src/infrastructure/feed/digest-rss.ts + e2e/sp-15.spec.ts + docs（prd.md US-33 / user-story-map.md SP-15 / open-questions.md）。制約: クリーンアーキテクチャ依存規則（app は infrastructure を直接 import しない・ARCH-3、GitHub API に触れてよいのは src/infrastructure/github/ の ACL だけ・NFR-16/TR-4、データソースは GET /search/repositories と GET /repos/{owner}/{repo} に限定という E-2 の既存宣言）、NFR-3（クライアント JS を増やさない方針）、Cloudflare Workers（CPU/バンドル制約・INF-2 の低コスト）、NFR-9（内部エラー文言を画面に出さない）、NFR-12/13（a11y・見出し階層・WCAG）、AC-5（詳細が無ければ HTTP 404）、AC-12/NFR-33（private リポジトリを露出しない）、キャッシュは CachePort（ADR 0005）。争点は少なくとも次の 6 つ: A) F-1/F-2 の実装形（ツールタイトルをどこに置くか＝共有ヘッダー component か各ページか / 詳細ページの見出し階層をどうするか＝h1 が 2 つにならないか・repository.fullName の h1 を h2 に落とすと SetDocumentTitle や route announcer や既存 E2E/a11y テストにどう影響するか / リンク先は /{locale} 固定でよいか・検索条件クエリを落とす挙動が SP-7 の『戻る』と矛盾しないか / LocaleSwitcher・BackLink との配置順） B) F-4 README の取得経路（GET /repos/{o}/{r}/readme を ACL に足す＝E-2 のデータソース限定宣言の更新が要る / RepositoryQueryPort に findReadme を足すか別ポートにするか / findDetail に含めて 1 回で返すか別 fetch にするか・404（README 無し）を null にする契約 / private 露出防止と mapper の扱い / キャッシュ TTL / レート枠の消費が増える影響） C) F-4 README のレンダリング方式（Accept: application/vnd.github.html でサーバー側 HTML を貰って sanitize するか / raw Markdown を貰って Markdown レンダラで描画するか / どのライブラリが Workers ランタイムとバンドルサイズに耐えるか / XSS 対策の具体（dangerouslySetInnerHTML を使うなら sanitizer は何か・許可タグ / 相対リンク・相対画像の解決 / iframe・script・onclick 属性の除去） / 表示量の上限（巨大 README の切り詰め）と『GitHub で全文を読む』導線 / 読み込み失敗時に詳細画面全体を壊さない設計 / Suspense を置けない制約（notFound の 404 保護）との両立） D) F-3 の型・表示（RepositoryDetail に description は既にあるが未表示・lastPushedAt が無い→ドメイン型と mapper と既存テストの更新範囲 / 『最終更新』は pushed_at か updated_at か（一覧は lastPushedAt = pushed_at を『最終更新』として出しているので一致させるべきか） / 日付書式は一覧と同じ Intl + Asia/Tokyo でよいか / messages/*.json のキー追加 detail.description / detail.updatedAt の要否） E) F-5 RSS 撤去の範囲（UI リンクだけ消すのか /api/digest/rss ごと消すのか・digest-rss.ts / digest-feed.ts / DAILY_DIGEST_LIMIT の行き先 / e2e/sp-15.spec.ts の該当ケース / prd.md US-33・user-story-map.md SP-15・open-questions.md の記述をどう書き換えるか＝削除ではなく『撤去した事実と理由』を残す規律 / SeenDigest 等の残存機能を壊さないか） F) F-6 出典リンクの行き先（Ecosyste.ms のリンク URL は何が正しいか・https://ecosyste.ms か API ドメインか / attribution-notice.tsx の {source} プレースホルダ分割の実装 / rel・target と a11y 文言（新しいタブで開く旨）を既存の opensInNewTab 文言と揃えるか）。
- 参加者: `ui_nav`, `readme_render`, `arch_domain`, `removal_impact`, `docs_trace`
- 投稿数: 5
- 更新: 2026-08-21T16:44:48+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `docs_trace` — 主張
<sub>2026-08-21T16:39:27+09:00</sub>

# 変更 F-1〜F-6 に対する既存ドキュメント矛盾・追記・紛らわしい箇所調査

## 【矛盾する記述】ドキュメントが事実と合わなくなるもの

### 1. `prd.md` §4.3・`E-2` の API エンドポイント限定と F-4 の README 取得
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/prd.md` 行 278-279
**現在の記述**: `GET /search/repositories` と `GET /repos/{owner}/{repo}` に限定する

**矛盾**: F-4 で詳細画面に README を表示するには `GET /repos/{owner}/{repo}/readme`（または `/repos/{owner}/{repo}/contents/README.md`）が必須。API エンドポイント限定を撤回または拡張する必要あり。

**更新が要るもの**:
- `prd.md` §4.3「データ取得方式」表に README 取得エンドポイントを追加
- `prd.md` §2.2 技術的制約に README API のレート制限上限を追加（個別呼び出しのため）
- `user-story-map.md` 線 198「`E-2` — GitHub API 呼び出しをデータアクセス層に隔離」に `GET /repos/{owner}/{repo}/readme` の追記
- `TR-4` の定義を拡張（`GET /repos/{owner}/{repo}/readme` を明示的に許可）

---

### 2. `prd.md` §4.1 `FR-4` と `user-story-map.md` SP-6 の詳細ページ表示項目 vs F-3 の description 追加
**ファイル**: 
- `/home/user/gem-hunter/docs/02_requirements/prd.md` 行 220：`FR-4` は「言語・Star 数・Watcher 数・Fork 数・Issue 数」と列挙
- `/home/user/gem-hunter/docs/02_requirements/user-story-map.md` 行 419：SP-6 操作レビューで「**7 項目** が出ている」と明記

**矛盾**: 言語・Star・Watcher・Fork・Issue = 5 項目。user-story-map.md のコメント「7 項目」はオーナーアイコン + リポジトリ名を含めての計数だと推測。F-3 で description を追加するなら、これが 8 項目（またはリポジトリ名を数え直して 7 項目に調整）になる。

**更新が要るもの**:
- `prd.md` §4.1 `FR-4` に「description」を明示的に追加
- `prd.md` §4.2 `AR-1` の説明文の扱い（既に「検索結果に含まれる」と明記）を確認し、詳細ページ版の取扱をも同時に明記
- `user-story-map.md` SP-6 操作レビュー手順を「説明文が出ている」と明記

---

### 3. `prd.md` 及び `user-story-map.md` の「最終更新日」の取扱
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/prd.md` / `/home/user/gem-hunter/docs/02_requirements/user-story-map.md`

**矛盾**: F-3 で「最終更新日」を詳細画面に追加しているが、`FR-4` / `US-18` のどちらにも「最終更新日」が明示的に含まれていない。一覧画面（`AR-1` / `US-12`）には「最終更新日」が含まれることが明記されているが、詳細ページは言及がない。`pushed_at` がそれを意図していたのか、新規追加なのか不明。

**更新が要るもの**:
- `prd.md` §4.1 `FR-4` に「最終更新日（`pushed_at`）」を追加
- `user-story-map.md` SP-6 操作レビュー手順に「最終更新日が出ている」を追加

---

### 4. `user-story-map.md` SP-15 で `US-33`（RSS）が実装されるが F-5 で廃止される矛盾
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/user-story-map.md` 行 516・`user-story-map.md` 線 104-110 
**現在の記述**: SP-15 に `US-33`「ダイジェストを RSS で購読できる」を含む / `A-8` の要件に `US-33` が置かれている

**矛盾**: F-5「トップ末尾の RSS 機能（`US-33`）を廃止」とあるため、`US-33` は削除または段階的に廃止される予定。その場合 `AR-10`（Phase 2・`GR-7` 関連の RSS）も同時に削除対象か不明。

**更新が要るもの**（確認待ち）:
- `US-33` を `user-story-map.md` から削除するか、コメントアウト / 取消し線で表記
- `prd.md` §4.2 `AR-10` を同様に削除または廃止マーク
- `user-story-map.md` line 104-110（A-8 バックボーン）から `US-33` を削除
- `prd.md` の `GR-7`（RSS）関連を確認し、削除対象に含めるか判定

---

## 【追記が要る箇所】新しい要件を明示すべき場所

### 1. `prd.md` §2.4 URL クエリパラメータ契約への README ページング（F-4 関連）
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/prd.md` 行 151-165

**理由**: F-4 で README を表示するなら、長い README の場合のページング戦略（全文表示・最初の N 行・タブ分けなど）を決定する必要があり、これが URL 状態に影響する可能性（`NFR-2` に抵触）がある。

**追記例**: "`E-3` キャッシュ層」の項に README キャッシュの TTL と取得範囲（全文か最初の N 行か）を記載

---

### 2. `prd.md` §4.3 詳細ページの README 取得方式の明文化
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/prd.md` 行 274-286

**理由**: F-1・F-4 の結果、詳細ページでの API 呼び出しが「`GET /repos/{owner}/{repo}` 単独」から「同 + `GET /repos/{owner}/{repo}/readme`」に増える。キャッシュ設計（`E-3` / `NFR-5`）・レート消費・エラーハンドリング（リポジトリなしの 404 vs README なしの 404）に影響。

**追記が要るもの**:
- README 取得時のエラーハンドリング（README が存在しないリポジトリは多数であり、404 時の表示方針）
- README の取得範囲（全文・最初の N バイト等）
- キャッシュキーに README を含めるか（`NFR-18` 関連）

---

### 3. 詳細ページの表示項目確定（F-3・F-4）を `FR-4` / `US-18` に明記
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/prd.md` 行 220・`user-story-map.md` 行 419

**理由**: 現在は「7 項目」という数字だけで具体的に何かが不明。F-3・F-4 の追加で以下となることを明示：オーナーアイコン・リポジトリ名・言語・Star・Watcher・Fork・Issue・description・最終更新日・README。

**追記例**:
```markdown
| **FR-4** | 詳細情報の表示（リポジトリ名・オーナーアイコン・言語・Star 数・Watcher 数・Fork 数・Issue 数・description・最終更新日・README） | `P1-MVP` | ...
```

---

### 4. ツールタイトルのナビゲーション動作（F-1・F-2）をどこかに規定
**ファイル**: `prd.md` / `user-story-map.md` のいずれにも記載なし

**理由**: F-1「トップのツールタイトル「gem-hunter」をクリックで `/{locale}` へ遷移」は UI/UX の一部だが、どの要件（`US-n` / `AR-n` / `E-n`）に属するのか、または新規要件として追記すべきか不明。トップページの「戻る」動線と関連があるはず。

**追記が要るもの**: 新規 `AR-n` または既存 `US-1`（到達する）の拡張として「トップページからの離脱と復帰のナビゲーション」を明記

---

### 5. Ecosyste.ms データの出典表示と CC BY-SA 4.0 ライセンス（F-3・F-6）
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/open-questions.md` 線 254 / `user-story-map.md` 線 185

**理由**: F-3 で description（Ecosyste.ms 由来の可能性）と F-6「出典表示の Ecosyste.ms をリンク化」が追加される場合、どの情報がどこから来たのか、CC BY-SA 4.0 の継承義務をどう果たすかを `E-25` の範囲で明記する必要がある。

**追記が要るもの**: 
- `prd.md` §3.2 / `user-story-map.md` の「Ecosyste.ms データの範囲」を明確化（description だけか、他も含めるか）
- `E-25` / `GR-6` の出典表示ルール（「改変の明示」「CC BY-SA 4.0 ライセンスへのリンク」等）を詳細化

---

## 【触らなくてよいが紛らわしい箇所】読んだ人が誤解しうる、既存の記述

### 1. `user-story-map.md` SP-6 の「7 項目」という数字が曖昧
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/user-story-map.md` 行 419

**理由**: 「オーナーアイコン + リポジトリ名 + 5 項目 = 7」か「5 項目だけ数えて 7」かが不明。読む側が数えても必ず 7 になるよう明示すべき。

**読み替え案**: 「詳細ページでリポジトリ名・オーナーアイコン・言語・Star 数・Watcher 数（`subscribers_count`）・Fork 数・Issue 数が出ている」と明記し、後の追加項目と区別を明確に

### 2. `prd.md` §4.2 `AR-1` の「追加 API 呼び出しは発生しない」という説明が詳細ページ版に及ぶのか不明
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/prd.md` 行 247

**理由**: `AR-1` は一覧カード版で「検索レスポンスに含まれる」と明記されているが、F-3 で詳細ページにも description を表示する場合、それが検索レスポンスに含まれるのか、詳細 API で別取得するのかが不明。

### 3. `user-story-map.md` SP-14 で D-33 の記述が長く、本体との関係が把握しづらい
**ファイル**: `/home/user/gem-hunter/docs/02_requirements/user-story-map.md` 線 529-567

**理由**: SP-16 の撤去理由が詳述されているが、これが「将来再導入のサンク」なのか、「今後メンテしない廃止」なのかが不明。F-5（RSS 廃止）と同じく撤去対象なのか、機能は有効なのか、読む側が判断できない。

---

## 【Summary】

本調査で検出された矛盾 4 件・追記 5 件・紛らわしい 3 件。

**最優先対応（実装着手前に確定必須）**:
1. 矛盾 1：README API エンドポイントの明示（`TR-4` / `E-2` 拡張）
2. 追記 4：ツールタイトルのナビゲーション動作の要件化
3. 矛盾 4：`US-33`（RSS）の削除スコープ確定

**次優先（実装中に対応可）**:
- 矛盾 2-3：詳細ページ表示項目の詳細化・最終更新日の明記
- 追記 2-3：README キャッシュ設計・エラーハンドリングの明文化
- 追記 5：Ecosyste.ms データ範囲と CC BY-SA 4.0 帰属表示ルールの詳細化

### `ui_nav` — 主張
<sub>2026-08-21T16:41:03+09:00</sub>

## 結論サマリー（争点 A 中心・情報設計 / a11y レンズ）

1. ツールタイトルは **`layout.tsx` の共有 `<header>` に 1 箇所だけ**置き、`page.tsx` 自前の `<h1>` は撤去する。
2. `repository.fullName` は **`<h2>` へ降格**して問題ない（既存 E2E の大半は level 未指定）。ただし **`app/[locale]/repos/[owner]/[repo]/page.tsx` のエラー分岐と `not-found.tsx` にもそれぞれ独自の `<h1>` があり、両方とも `<h2>` に揃えないと 1 ページに h1 が 2 つ並ぶ**。エラー分岐側は `e2e/sp-9-errors.spec.ts:216` が `level: 1` を明示しているため、**このテストの修正が必須**（見落としやすい）。
3. `LocaleSwitcher` は **layout.tsx へ移せない**（`searchParams` が layout に渡らない Next.js の制約）。タイトルだけを layout 側へ、`LocaleSwitcher` は現状どおり各 page.tsx に残す。
4. タイトルのリンク先 `/{locale}`（クエリなし）は `BackLink` の「検索状態を保持して戻る」とは **役割が違う**ため矛盾ではない（サイトホームへのリセット導線）。ただし実装は `buildSearchUrl` を経由せず、**素の固定 href** にすべき。
5. F-3（description・最終更新）は一覧の視覚配置は流用しつつ、**sr-only の付け方は詳細画面の既存流儀（可視ラベル + `aria-hidden` アイコン）に合わせる**。「最終更新」は `RepositoryDetail` 型に該当フィールド（`lastPushedAt` 相当）が無く、型・mapper 側の追加が要る（`arch_domain` 領域だが表示設計に影響するため明記）。

---

## 1. ツールタイトルの置き場所とマークアップ

### 現状
- `app/[locale]/page.tsx:292`: `<h1 className="text-2xl font-semibold">{messages.home.title}</h1>`（プレーンテキスト、リンクなし）
- 詳細ページにはツールタイトルが一切存在しない（`repository-detail.tsx` の `<h1>` は `repository.fullName` のみ）
- `<header>` / `role="banner"` はプロジェクト内に **1 箇所も存在しない**（`grep -rn "<header" app/ src/ui/` はヒットなし）

### 判断: 共有ヘッダー component（`layout.tsx` 経由）に一本化する
- `app/[locale]/layout.tsx` はロケール配下の**全ページ**（トップ・詳細成功時・詳細エラー時・`not-found.tsx`）を包む唯一の共通点。ここに `<header>` ランドマークを新設し、中に `<h1><Link href={`/${locale}`}>{messages.home.title}</Link></h1>` を置けば、F-2「詳細画面もトップと同じくツールタイトルを含めて同じ挙動」を**実装を複製せず**満たせる。
- `page.tsx:292` の `<h1>{messages.home.title}</h1>` は**撤去**する（残すと home ページだけ h1 が 2 つになる）。`p.text-muted-foreground`（`messages.home.description`、page.tsx:293）は残し、header 直後・検索フォームの前に来る位置関係は変わらない。
- リンクは内部遷移なので `next/link`（`Link`）を使う（`back-link.tsx:1`・`repository-list.tsx:76`・`locale-switcher.tsx:1` と同じ内部遷移の慣行。外部リンクにのみ素の `<a>` を使っているのは `repository-detail.tsx:72`・`attribution-notice.tsx` のみ）。
- フォーカスリング・下線は既存パターンを流用: `text-primary rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring`（`back-link.tsx:35`, `repository-list.tsx:81`, `repository-detail.tsx:76` と同一クラス構成）。

### 反対されうる点
- 「各ページに書く」案（page.tsx と repos/[owner]/[repo]/page.tsx に個別実装）でも F-2 は満たせるが、コード重複が 2 箇所（将来 3 箇所目=検索エラー画面も個別に持っている）に増え、意匠変更のたびに同期が要る。`back-link.tsx` を共有化した理由（`back-link.tsx:7-8` のコメント「コピペ重複を防ぎ、意匠変更を 1 箇所に集約する」）と同じ論理で layout.tsx 案を推す。

---

## 2. 詳細ページの見出し階層と h1 二重化問題

### 波及範囲（見落とされがちな箇所を含め全て特定）
`repository.fullName` に相当する `<h1>` は実は **3 箇所**に存在する（1 箇所だけ直せば済むわけではない）:

| 箇所 | 現状 | 対応 |
|---|---|---|
| `src/ui/repository-detail.tsx:66` `<h1 className="text-2xl font-semibold break-words">` | 成功時のリポジトリ名（GitHub 外部リンク） | `<h2>` に変更 |
| `app/[locale]/repos/[owner]/[repo]/page.tsx`（`DomainError` catch 分岐内）`<h1 className="mb-4 text-2xl font-semibold">{\`${owner}/${repo}\`}</h1>` | 詳細取得エラー時の見出し | `<h2>` に変更（**これを見落とすと header の h1 と衝突して h1 が 2 つになる**） |
| `app/[locale]/repos/[owner]/[repo]/not-found.tsx:26` `<h1 className="text-2xl font-semibold">{messages.detail.notFound}</h1>` | 404 専用 UI の見出し | `<h2>` に変更（同上） |

### E2E への実波及（実際に読んで確認済み）

- **`e2e/sp-3.spec.ts:37,42,45`**: `page.getByRole('heading', { name: 'octostub/octo-widgets' })` — **level 未指定**。`getByRole('heading', {name})` はレベルを問わず role="heading"（h1〜h6 すべて）にマッチするため、h2 化しても**壊れない**。
- **`e2e/a11y.spec.ts:28`**: 同じく level 未指定の `getByRole('heading', {name: 'octostub/octo-widgets'})` → 壊れない。
- **`e2e/sp-9-errors.spec.ts:216`**: `await expect(page.getByRole('heading', { level: 1 })).toContainText(\`octostub/${repo}\`)` — **`level: 1` を明示している**。これは上表 2 行目（エラー分岐の `<h1>`）を指しており、そこを `<h2>` に変えると `getByRole('heading', {level:1})` が一致するのは header 側の「gem-hunter」だけになり、`toContainText('octostub/...')` は**失敗する**。このテストコード自体を「見出し全体（level 問わず）に `octostub/${repo}` を含む」形へ書き換える必要がある（例: `getByRole('heading', { name: new RegExp(\`octostub/${repo}\`) })` へ変更、または `level: 2` に変更）。**これがこの変更で最も見落としやすいポイント**。
- **`e2e/sp-6-notfound.spec.ts`**: `getByText(ja.detail.notFound, {exact:true})` と `toHaveTitle(...)` のみを検証しており、heading の level は見ていない → `not-found.tsx` の h1→h2 変更でも**壊れない**（が、上表の理由で変更自体は必要）。
- **`e2e/sp-6-idle.spec.ts:30,54`**・**`e2e/sp-7.spec.ts:134`**・**`e2e/sp-10.spec.ts`**・**`e2e/sp-14.spec.ts`**: いずれも `level: 2`（`検索結果` / `今日の Gem`）または level 未指定の別名の見出しを検証しており、詳細ページの h1/h2 変更とは無関係（影響なし）。
- **`e2e/sp-9-loading-empty.spec.ts:41`**: `getByRole('heading', { name: ja.home.title })` — level 未指定。home の `<h1>` を撤去して layout の header 内 `<h1>` に一本化しても、`heading` role・`name` は変わらず**壊れない**（ただし重複マッチしないよう `page.tsx:292` の自前 `<h1>` は必ず削除すること。残すと `getByRole` が 2 件ヒットして strict mode violation で別テストが落ちる）。

### `SetDocumentTitle` / ルートアナウンサーへの影響
- `src/ui/set-document-title.tsx` は `document.title` の設定だけを行い、見出しレベルとは無関係。`ui-ux-guidelines.md:328-341`（§7.1）の「route announcer は document title の変化だけを見る」仕組みも同様に **h1→h2 変更の影響を受けない**。トップ↔詳細のようなフルページ遷移では `generateMetadata`（`page.tsx` 末尾）と `SetDocumentTitle` が引き続きタイトルを制御するため、この観点の変更は不要。
- 一方 `ui-ux-guidelines.md:328-341` の §7.1 パターン（`next/link` クライアント遷移時に `<h2 tabIndex={-1}>` へ focus を移す）は home の `#results-heading` 専用の仕組みであり、詳細ページの h1→h2 化はこの仕組みを流用も破壊もしない（別物）。

### axe（`e2e/a11y.spec.ts` 等）への影響
- `e2e/axe.ts:15` の `withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'])` は **`heading-order` / `page-has-heading-one` を含まない**（両ルールは axe-core 上 `best-practice` タグのみで WCAG タグを持たない）。したがって h1 が 2 つ並んでしまう実装ミスをしても、この e2e の axe 検査では **検出されない**。`ui-ux-guidelines.md` §7 の「機械ゲート三層防御」表にも `heading-order` 系は明記されておらず、**手動チェックリスト（§7.7）への追加を検討すべき見落としリスク**として指摘する。

---

## 3. タイトルリンクの行き先と SP-7 の関係

- `src/ui/url/build-search-url.ts:26-42` の `buildSearchUrl` は検索条件を**保持して**クエリを組み立てる関数であり、`BackLink`（`src/ui/back-link.tsx:16-24` の `href?` props）はこれを使って「検索条件を保持したまま戻る」ことが目的（コメント: `back-link.tsx:19-23`「検索条件…を保持したまま一覧へ戻りたい呼び出し元が…組み立てて渡す」）。
- ツールタイトルの `href` は **`buildSearchUrl` を経由しない固定値 `/${locale}`** にする。これは「検索条件を破棄してホームへ戻る」という F-1 の意図どおりであり、`BackLink` の「条件保持」とは**役割が異なるだけで矛盾ではない**（一般的な「サイトタイトル＝ホームへのリセット導線」という UX 慣行と一致）。
- トップページで検索中（`?q=...` 等）にタイトルをクリックした場合の挙動: `/{locale}` へ遷移しクエリが消える → `hasKeyword` が false になり `page.tsx:207-216` の分岐で idle 表示（検索フォーム＋日次ダイジェストのみ）に戻る。これは F-1 の要求そのもの。
- 注意点: `e2e/sp-7.spec.ts` は「詳細往復で検索条件が保たれる」ことを検証するテストであり、そこで **BackLink**（「一覧へ戻る」リンク、`labels.backLink` 文言）をクリックする前提になっている（`e2e/sp-3.spec.ts:47` 相当のパターン）。ツールタイトルと `BackLink` は文言もリンク先ロジックも別物なので、既存の SP-7 系 E2E は**そのまま壊れない**——ただし実装時に「タイトルリンクが誤って `buildSearchUrl(basePath, searchState)` を使ってしまう」実装ミスをすると、検索中にタイトルをクリックしても検索状態が残り F-1 の意図と食い違う。ここは仕様解釈の分岐ではなく実装レベルのミスなので、レビュー観点として明記するに留める。

---

## 4. `LocaleSwitcher` / `BackLink` / ログインリンクの配置順序とランドマーク構造

### 制約: `LocaleSwitcher` は layout.tsx へ移せない
- `LocaleSwitcher` は `currentPath`（クエリを含む現在パス）を props で要求する（`locale-switcher.tsx:14-18`）。`currentPath` は各 `page.tsx` が `searchParams` から `buildSearchUrl` で組み立てている（`app/[locale]/page.tsx` の `currentPath`、`repos/[owner]/[repo]/page.tsx` の `currentPath`）。
- **Next.js の App Router では `searchParams` は `page.tsx` にのみ渡り、`layout.tsx` には渡らない**（ルートパラメータ用に `next/root-params` を使っている `not-found.tsx` のコメント（`not-found.tsx:11-15`）が示すとおり、`params` ですら特殊経路が要る設計）。`layout.tsx` で `searchParams` 相当を取得するには `headers()` の `referer` を読むような迂回か、`useSearchParams()` を使うクライアントコンポーネント化が要り、後者は **NFR-3**（クライアント JS を検索入力欄・各コントロールのトリガーだけに絞る方針・`ui-ux-guidelines.md:203`「`use client` を付けるのは検索入力欄と各コントロールのトリガーだけ」）に反する。
- 結論: **`LocaleSwitcher` は現状どおり各 page.tsx 側に残す**（3 箇所の個別呼び出しは変更しない）。layout.tsx の共有ヘッダーに入れるのは「クエリに依存しない」タイトルリンクだけにする。

### ランドマーク構造の提案
- 新設: `layout.tsx` の `<body>` 直下に `<header>`（`role="banner"` 相当・暗黙ロール）を 1 つ置き、中身は `<h1><Link href={/${locale}}>...</Link></h1>` のみ（ログインリンクの `div`（`layout.tsx:69-76`）は header の外、`children` の前に残すか、header 内に統合するかは意匠判断——**header 内に統合する場合は banner ランドマーク内にログイン導線が同居しても仕様上問題ない**（banner は 1 ページに 1 つが原則だが、中に複数の子要素を持てる）。
- 既存の懸念点（本 PR のスコープではないが構造確認として記録）: **`LocaleSwitcher` の `<nav>` は現在 `<main>` の内側**（`page.tsx:284`, `repos/.../page.tsx` の `<LocaleSwitcher>` 呼び出し）に置かれている。ランドマーク設計としては `nav` は `main` の外（兄弟）に置くのが望ましいが、これは既存実装からの逸脱であり、今回のタイトル追加とは別軸の指摘なので**別 Issue 化を推奨**（CP-1 のスコープ境界に従う）。今回 header を新設するタイミングで一緒に「nav を header 内または header 直後・main の外」へ動かすなら一石二鳥だが、それは `arch_domain` / lead の判断に委ねる。
- 順序案（推奨）: `header`（tool title h1）→ `main` 内で `LocaleSwitcher`（nav）→ 各ページ固有の見出し（h2 fullName 等）→ 本文。detail 成功時は `BackLink` が `RepositoryDetail` 冒頭にあるので、`main` 内の順序は「LocaleSwitcher → BackLink → h2 fullName → 統計」のまま変わらない。

---

## 5. F-3（概要・最終更新）の配置と一覧との整合

### 一覧側の既存作法（`src/ui/repository-list.tsx`）
- **description**: `item.description` が truthy のときだけ `<p className="text-muted-foreground mt-1 text-sm">{item.description}</p>`（`repository-list.tsx:85-87`）。ラベルなし、可視テキストのみ。sr-only 処理は一切していない（説明文はそれ自体が読み上げ可能なテキストのため不要）。
- **最終更新**: `<span>{labels.updatedAt} {dateFormat.format(item.lastPushedAt)}</span>`（`repository-list.tsx:95-97`）。**可視ラベル（`labels.updatedAt` = "最終更新"）を明示**しており sr-only ではない（star 数だけ `<span aria-hidden="true">★ </span><span className="sr-only">{labels.starCount} </span>` という視覚記号置換パターン（`repository-list.tsx:90-93`）を使っているのとは異なる）。
- 日付フォーマット: `new Intl.DateTimeFormat(localeTag, { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Tokyo' })`（`repository-list.tsx:45-50`）。`ui-ux-guidelines.md:216`（§4.2）が明記する「絶対表記（YYYY-MM-DD）、相対表記は使わない」の実装そのもの。

### 詳細側の既存作法（`src/ui/repository-detail.tsx`）
- 統計（star/watcher/fork/openIssue）は `dl > dt(icon aria-hidden + 可視ラベル) + dd(数値)` の構造（`repository-detail.tsx:94-106`）。**sr-only は使っていない**（`language` だけ `<span className="sr-only">{labels.language}: </span>` を使うが、これはラベルとアイコンを両方持たない唯一の項目だからで、アイコン付き stats とは別パターン）。

### 配置提案
1. **description**: `repository.fullName`（h2 化）＋ `primaryLanguage` のブロック（`repository-detail.tsx:65-91` の `<div className="min-w-0">`）の直後、`dl` 統計の前に、一覧と同じ `<p className="text-muted-foreground mt-1 text-sm">{repository.description}</p>` を `repository.description` が truthy のときだけ描画する。ラベルなし・sr-only なし、一覧の作法をそのまま踏襲すれば整合が取れる。ドメイン型 `RepositoryDetail`（`src/domain/model/repository.ts:34`）には**既に `description: string | null` フィールドがあるため、型追加は不要**——これは表示漏れだけの問題（`arch_domain` 領域の確認: mapper がこの値を落としていないか要確認）。
2. **最終更新**: `RepositoryDetail` 型には `lastPushedAt`（または `pushedAt`）に相当するフィールドが**存在しない**（`src/domain/model/repository.ts:29-45` を確認済み。`RepositorySummary` にはあるが `RepositoryDetail` にはない）。表示するにはドメイン型・mapper・use case への追加が先に必要（`arch_domain`/`docs_trace` 領域）。表示位置としては、詳細側の `dl` 統計と揃えて **5 個目の `dt/dd`**（Calendar アイコン + `labels.updatedAt` + 日付）として追加するのが、詳細ページ内の一貫性（アイコン+ラベル+値のセット・`ui-ux-guidelines.md:290`「統計はアイコン+ラベル+数値のセットで横並び」）に最も合う。日付フォーマットは一覧と**同一コード**（`Intl.DateTimeFormat` + `timeZone: 'Asia/Tokyo'` + `y/m/d 2-digit`）を再利用し、同じ値（例えば同じ `pushed_at`）を一覧と詳細で異なる書式・異なる粒度で出さないようにする。
3. メッセージキー: `messages.home.updatedAt`（"最終更新"）を詳細側でも再利用するか、`messages.detail.updatedAt` を新設するかは実装レベルの判断（値は同じ文言になる想定）。`description` はラベル自体を持たないため新規キー不要。

---

## 6. フォーカスリング・タップ領域・opensInNewTab との整合

- 新設するタイトルリンク（内部遷移）は `target="_blank"` を使わないため `opensInNewTab` sr-only 文言は**不要**（この文言は `repository-detail.tsx:79-82` の GitHub 外部リンクと `attribution-notice.tsx` 専用）。
- フォーカスリングは既存の内部リンク共通クラス（`focus-visible:ring-3 focus-visible:ring-ring` + `outline-none` 対）をそのまま流用すればよく、新規パターンの発明は不要（`ui-ux-guidelines.md:353-355` §7.3 の必須要件に整合）。
- タップ領域: タイトルはテキストリンク（`h1` 内のインラインテキスト）であり、`ui-ux-guidelines.md` §7.5 の **Inline 例外**（「文または文のブロック内にあるターゲットは対象外」）に該当するため `--size-control-xs` の実測は不要と判断できる。ただし見出し全体をクリック領域にする場合（`repository-list.tsx` の `::after` パターンのような拡張）は例外の適用外になるため、**単純なテキストリンクのまま**にすることを推奨（過剰実装を避ける・YAGNI）。

### `removal_impact` — 主張
<sub>2026-08-21T16:41:54+09:00</sub>

# removal_impact r1: F-5（RSS 撤去）・F-6（出典リンク化）

## F-5: RSS 撤去の物理範囲

### 削除するファイル（4 ファイル）

1. `app/api/digest/rss/route.ts`（全 39 行）
2. `app/api/digest/rss/route.test.ts`（全体。`route.ts` 削除に伴い対象消失）
3. `src/infrastructure/feed/digest-rss.ts`（全 110 行。`renderDigestRss` 純粋関数）
4. `src/infrastructure/feed/digest-rss.test.ts`（全体）

`grep -rln "digest-rss\|renderDigestRss\|renderDailyDigestRss"` で確認済み。4 ファイル外に
`digest-rss.ts` の実装（`renderDigestRss` / `escapeXml` 等）を参照する箇所はゼロ。
`src/infrastructure/feed/` ディレクトリはこの 2 ファイルのみなのでディレクトリごと消える。

### 削除する `src/composition/digest-feed.ts` と、そこに同居している共有資産の行き先

`src/composition/digest-feed.ts`（39 行）は **RSS 専用の composition** として書かれているが
（冒頭コメント「RSS 配信（`US-33`）の composition」）、`DAILY_DIGEST_LIMIT`（20 行目）だけは
トップページ（`app/[locale]/page.tsx` 6 行目 `import { DAILY_DIGEST_LIMIT } from
'@/src/composition/digest-feed'`、280 行目で使用）からも import されている。RSS と無関係にトップ
の表示件数（5 件）を決める値なので、ファイルごと消すと **トップページが壊れる**。

**結論**: `DAILY_DIGEST_LIMIT = 5` を `app/[locale]/page.tsx` 内のローカル定数へ引っ越す
（消費者がトップページ 1 箇所だけになるため、composition を跨いで共有する理由が RSS 撤去で
消滅する＝ YAGNI に照らして「1 箇所しか使わない共有ファイル」を残さない）。`digest-feed.ts` は
ファイルごと削除する。

- `app/[locale]/page.tsx` 6 行目の import 文を削除し、280 行目付近に
  `const DAILY_DIGEST_LIMIT = 5`（コメントは「トップの表示件数（`ADR 0014` §2.1 の既定 5 件）」
  へ差し替え、RSS 同期の話は書かない）をローカル定義として追加する。

### `FALLBACK_META` は撤去不要（RSS 専用ではない）

`src/infrastructure/platform/static-gem-digest.ts` 54 行目で定義され、同ファイル内 4 箇所
（`listCandidates` の壊れ JSON フォールバック等）で使われている。`digest-feed.ts` 4 行目・36 行目
の import は RSS 側の追加消費に過ぎない。**`digest-feed.ts` を削除すれば済み**、`FALLBACK_META`
自体・`static-gem-digest.ts` 側の 4 箇所はそのまま残す。

ただし `static-gem-digest.ts` 51 行目のコメント
「🔴 RSS 配信側（`src/composition/digest-feed.ts`）からも同じ値を使う（定義を二重化すると…）」
は RSS 撤去後に **嘘のコメントとして残ってしまう**ため、同時に書き換える（例:
「候補プールが読めない/壊れているときに使う帰属メタデータ。`D-29` の帰属表示は省略できないため、
フォールバック時も出典・ライセンスは保持し `generatedAt` だけを空にする。」に単純化し、RSS への
言及を削る）。

### `resolveLandingHost` は撤去不要（RSS 専用ではない）

`src/composition/auth.ts` 55 行目で定義。`app/api/auth/logout/route.ts`・
`app/api/auth/callback/route.ts` が OAuth のオープンリダイレクト対策として使っており、
`app/api/digest/rss/route.ts` の消費（1 行目 import・28 行目使用）は 3 消費者のうちの 1 つに
過ぎない。**RSS 側の import 文が消えるだけ**で `auth.ts` 本体・他 2 消費者に影響なし。

### `src/ui/daily-digest.tsx` の書き換え箇所

- 29〜30 行目: `DailyDigestLabels` 型の `rssLink: string` フィールドを削除
- 148〜163 行目: RSS 購読リンクの `<p>` ブロック全体（コメント含む）を削除
  （`{/* RSS 購読リンク（US-33）。… */}` から `</p>` まで、`</SeenDigestProvider>` 直前）
- `<Link>` を使わず素の `<a>` にしていた理由コメント（150〜152 行目「🔴 素の `<a>` を使う…」）も
  ブロックごと消えるため書き換え不要（ブロック削除で自動的に消える）

### `src/ui/daily-digest.test.tsx`

- 17 行目 `rssLink: 'RSS で購読',`（ja fixture）を削除
- 195 行目 `rssLink: 'Subscribe via RSS',`（en fixture、**JSX インラインリテラル**）を削除
  — こちらは `labels={{ ... }}` という **オブジェクトリテラルを直接 props に渡している**ため、
  `DailyDigestLabels` 型から `rssLink` を外すと TypeScript の excess property check に
  引っかかり `tsc --noEmit` が **red になる**（`run_checks.sh` の型チェック工程が落ちる）。
  17 行目側は `const labels = {...}` を変数経由で渡しているため型エラーにはならないが、
  死んだフィールドとして残すべきではないので同様に削除する。
  他に `rssLink` を assert しているテスト（`getByRole('link', ...)`）は本ファイルに **ない**
  （grep 済み・使用は fixture 定義の 2 箇所のみ）。

### `e2e/sp-15.spec.ts`

- 13 行目 `test.describe('SP-15: 鮮度・出典・差分・RSS', () => {` →
  `test.describe('SP-15: 鮮度・出典・差分', () => {`（末尾の「・RSS」を削る）
- 7〜8 行目の JSDoc「操作レビュー手順 **4 手順** を E2E に写す」→ 3 手順に修正
  （撤去後は `user-story-map.md` SP-15 の操作レビューも 3 手順になる。後述）
- 95〜119 行目 `test('手順4: RSS の URL を購読すると同じ内容が取得できる', ...)` ブロックを丸ごと削除
  （121 行目の `test.describe` 閉じ `})` はそのまま残す）
- 3 行目 `import { readDigestPackageNames } from './helpers'` は **削除しない**
  （41 行目・54 行目の「手順3: 再訪差分」テストが引き続き使用している。grep 済み）

### `messages/ja.json` / `messages/en.json`

- `ja.json` 62 行目 `"rssLink": "RSS で購読"` を削除（`digest` オブジェクトの末尾キー、前行
  61 行目 `"firstVisitNote"` の末尾カンマを外すのを忘れない）
- `en.json` 62 行目 `"rssLink": "Subscribe via RSS"` を同様に削除
- `app/[locale]/page.tsx` 323 行目 `rssLink: messages.home.digest.rssLink,` を削除
  （`DailyDigest` へ渡す `labels` オブジェクトの 1 プロパティ）

## 機械検査の生存確認

`tools/run_checks.sh` が呼ぶスクリプト一式（`check_architecture_boundaries.py` /
`check_ui_dimensions.py` / `check_contrast.py` / `check_adr_coverage.py` /
`check_prefetchable_side_effects.py` / `check_cjk_markdown.py` / `self_review_check.py` /
`retire_preview_aliases.py --self-test` / `check_deploy_gate.py --self-test` /
`workers_build_deploy.sh --self-test` / `check_digest_freshness.py --self-test` /
`check_prod_drift.py --self-test` / `test_wip_commit_guard.sh`）を `grep -rln "rss\|RSS"
tools/*.py tools/*.sh` で確認した結果、**RSS 固有の前提を持つ検査はゼロ**（ヒットは
`tools/discussion_specs/*.json` と `tools/infographic/specs/usm_grid.json` のみで、いずれも
本議論用の一時成果物・別議題の生成物であり検査スクリプト本体ではない）。

`check_prefetchable_side_effects.py` は「`<Link>` でプリフェッチされる先が副作用付き GET か」を
汎用的に検査するものであり、`/api/digest/rss` をハードコードして特別扱いしてはいない
（daily-digest.tsx 側が素の `<a>` を使っていた理由コメントは書き手側の設計判断であり、検査側の
除外リストではない）。よって **ルート削除後もこの検査は落ちない**。`check_digest_freshness.py`
は「ダイジェストデータの鮮度」（`E-25`・candidates JSON の生成時刻）を見るものであり RSS の有無
とは無関係 — 撤去後も引き続き生存させる（後述、`E-25` は撤去範囲外）。

`check_rules_sync.sh` は `docs/rules/` と `.claude/rules/` の symlink 整合だけを見ており
RSS/digest とは無関係（対象外）。

## ドキュメント更新方針（`D-33` / `SP-16` の事後撤去パターンに倣う）

このリポジトリには既に「実装済み機能を事後撤去したときの書き方」の実例がある
（`docs/02_requirements/open-questions.md` **`D-33`**・`user-story-map.md` **`SP-16`** の節・
`prd.md` 583/597 行目の注記・`docs/adr/0009-hidden-gem-score-definition.md` 54 行目の追記）。
**単純削除ではなく「撤去した事実と理由」を新しい決定エントリとして残し、既存記述には打ち消し線
＋ 🔴 注記で誘導する**のが規律。F-5 もこの形を踏襲する。次の決定番号は **`D-34`**
（既存最大は `D-33`・`grep -oE "D-[0-9]+" open-questions.md | sort -u` で確認済み）。

### 1. `docs/02_requirements/open-questions.md`（新規 `D-34` 行を追加）

`D-33` の行（341〜344 行目）に倣った書式で追加する。骨子:

> **D-34** | 🔴 **`US-33`（ダイジェストの RSS 配信・`SP-15` の一部）を撤去する。** 飼い主フィード
> バック（Issue #334・F-5）により決定。**理由**: RSS の実利用が見込めない一方、`resolveLandingHost`
> による Host header cache poisoning 対策・XML エスケープ・RFC 822 日付変換など専用の実装・
> テスト資産（`digest-rss.ts` / `route.ts` とそのテスト）を維持するコストに見合わない。
> **撤去の範囲**: `app/api/digest/rss/`・`src/infrastructure/feed/`・`src/composition/digest-feed.ts`
> （`DAILY_DIGEST_LIMIT` は `app/[locale]/page.tsx` へ移設・存続）・`daily-digest.tsx` の購読リンク・
> `messages/*.json` の `rssLink`。🔵 **日次ダイジェスト本体（`US-30`〜`US-32`・トップページ表示・
> 出典表示・差分表示）は撤去しない**（RSS は配信経路の 1 つに過ぎず、ダイジェストの生成・表示
> 機能とは独立）。反映先は `user-story-map.md` §5.3 `SP-15` / `prd.md` §11 `AR-10` /
> `docs/adr/0014-zero-query-daily-digest.md` §2.5 | 2026-08-21

### 2. `docs/02_requirements/user-story-map.md`

- 109 行目 `| **US-33** | ダイジェストを RSS で購読できる | \`AR-10\` / \`GR-7\` | \`S-3\` |` を
  `D-33` の `US-34` 行（110 行目）と同じ形へ書き換える:
  `| **US-33** | ~~ダイジェストを RSS で購読できる~~ 🔴 **\`D-34\`（2026-08-21）により撤去**（詳細は §5.3 \`SP-15\` の注記） | \`AR-10\` / \`GR-7\` | \`S-3\` |`
- 184 行目「静的な『今日の Gem 一覧』ページ」行の備考「`US-33` で RSS 配信も加わる」を
  「🔴 `US-33`（RSS 配信）は `D-34` により撤去済み」に修正
- §5.3 `SP-15` の節（516〜527 行目付近）:
  - **含む** 行（516 行目）から `US-33` を外す（`US-32` / `E-25` / `AR-10` のみに）
  - **操作レビュー**（4 手順）から「手順4: RSS の URL を購読すると同じ内容が取得できる」を削除
    し 3 手順にする
  - 節の末尾（527 行目の下、`D-33` が `SP-16` 節の末尾に追記したのと同じ位置）に
    `> 🔴 **\`US-33\`（RSS 配信）は \`D-34\`（2026-08-21）により撤去**（詳細は \`open-questions.md\` \`D-34\`）。`
    を追記する
- `E-25`（242 行目・「配信データの鮮度チェックと自己修復」）は **撤去しない**（RSS 専用ではなく
  候補プール JSON 全体の鮮度チェックを指す。`check_digest_freshness.py` が対応）。185 行目の
  「データ出典の明記」行が `E-25` / `SP-15` を参照している通り、出典表示（`AttributionNotice`）
  側の要件でもあるため生かす。

### 3. `docs/02_requirements/prd.md`

- 103 行目・583 行目・597 行目に登場する `AR-9` / `AR-10` の並記のうち、`AR-10`
  （256 行目「ダイジェストの RSS 配信」）の行を `D-33` の `US-34` 撤去注記と同じ書式で:
  `| **AR-10** | ~~ダイジェストの RSS 配信~~ 🔴 **\`D-34\`（2026-08-21）により撤去** | \`P2\` | \`D-27\` / \`GR-7\` | 詳細は \`open-questions.md\` \`D-34\` |`
- 597 行目に `D-33` と同じ体裁の 1 文を追加:
  「🔴 **`US-33`（ダイジェストの RSS 配信・実装単位は `SP-15` の一部）は `D-34` により撤去済み**。
  経緯は `open-questions.md` `D-34` を参照。」

### 4. `docs/adr/0014-zero-query-daily-digest.md`

ADR 本文（§2.5「RSS 配信を採用し…」69〜71 行目、97/113/135 行目の関連記述）は **書き換えない**
（ADR は意思決定当時の記録であり後から改変しない規律。`D-33` が `docs/adr/0009-...md` に対して
本文改変ではなく **追記** で対応した先例に倣う）。71 行目の直後に `D-33` → ADR 0009 の追記
（54 行目）と同じ体裁で 1 段落を追加する:

> 🔴 **`D-34`（2026-08-21）追記**: 本 ADR が「メール/push よりも RSS」を選んだ判断（`D-14`/`D-18`
> 適合性）自体は撤回しない。ただし RSS 配信の実装（`US-33`/`AR-10`）は飼い主フィードバック
> （Issue #334・F-5）により撤去された。日次ダイジェスト本体（トップページ表示・出典表示・
> 差分表示）は本 ADR の対象のまま存続する。詳細は
> [`open-questions.md`](../02_requirements/open-questions.md) `D-34` を参照。

## F-6: 出典表示（Ecosyste.ms）のリンク化

### リンク先 URL の一次情報確認（WebFetch 実施済み）

`https://ecosyste.ms/` を WebFetch で実際に取得し確認した。オープンソースのパッケージ／依存関係
インテリジェンスを提供するプロジェクトのトップページであり（「1,440万パッケージ・2億9,300万
リポジトリをインデックス化」「the world's most comprehensive and accurate dataset about open
source production and use」）、`AttributionNotice` が表示する `{source}`（= `Ecosyste.ms`）の
参照先として妥当な一次情報である。

一方、実データの取得元は `tools/generate_gem_digest.mjs` 23 行目
`const API_BASE = 'https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages'`（npm
registry の packages API）であり、これは **JSON を返す API エンドポイント**でユーザーが
ブラウザで開いても読める説明ページではない。ユーザー向けの「出典について知りたい」導線としては
**`https://ecosyste.ms/`（トップページ）の方が適切**と判断する。`sourceLicenseUrl` が
`https://creativecommons.org/licenses/by-sa/4.0/`（ライセンス条文の deed ページ、人間が読める
説明ページ）であるのと同じ粒度に揃うため一貫性もある。

### `DigestMeta` に `sourceUrl` は存在しない（新規フィールドが要る）

`src/domain/model/gem.ts` 51〜60 行目の `DigestMeta` 型を確認したところ、フィールドは
`source` / `license` / `sourceLicenseUrl` / `generatedAt` の 4 つのみで、**`sourceUrl` は
存在しない**。`public/data/daily-digest.json` の実データ（`python3 -c "import json;
print(json.load(open('public/data/daily-digest.json'))['meta'])"` で確認済み）も同じ 4
フィールドで、`sourceLicenseUrl` はあるが `source` 自体へのリンクは持たない。

**結論**: `{source}` をリンク化するには `DigestMeta` に新規フィールド `sourceUrl` を追加する
実装が要る（`{license}` が `sourceLicenseUrl` を使っているのと対の構造）。行き先は 3 箇所:

1. `src/domain/model/gem.ts` 51〜60 行目 `DigestMeta` 型に
   `readonly sourceUrl: string`（コメント: 「データ提供元のトップページ URL（例
   `https://ecosyste.ms/`）。」）を追加
2. `src/infrastructure/platform/static-gem-digest.ts`:
   - `FALLBACK_META`（54〜59 行目）に `sourceUrl: 'https://ecosyste.ms/'` を追加
   - `parseMeta()`（108〜119 行目）に `sourceUrl: httpUrlOr(source.sourceUrl,
     FALLBACK_META.sourceUrl)`（`sourceLicenseUrl` と同じ `httpUrlOr` バリデータを流用。
     `javascript:` / `data:` スキーム対策のコメント（113 行目）がここにも同様に必要）を追加
3. `public/data/daily-digest.json` のバッチ生成側（`tools/generate_gem_digest.mjs`）が書き込む
   `meta` にも `sourceUrl: 'https://ecosyste.ms/'` を足す必要がある（`FALLBACK_META` はあくまで
   JSON が読めない/壊れている時の代替であり、正常系のデータは生成バッチ側が持つ値が使われる）。
   この改修は `generate_gem_digest.mjs` 側の変更であり本レンズの担当外だが、担当者が見落とさない
   よう明記する。

### `AttributionNotice` の実装形

`src/ui/attribution-notice.tsx` の `{source}` は現状 `fill(beforeHead)` /
`fill(afterHead)` の `formatMessage` テンプレート置換でプレーンテキストとして出力されている
（62 行目 `const fill = (template: string) => formatMessage(template, { source: meta.source })`）。
`{license}` は 69〜76 行目で `splitOn(labels.attribution, '{license}')` によりテンプレート文字列
を事前分割し、間に `<a href={meta.sourceLicenseUrl}>` 要素を挟む方式を取っている。

**`{source}` も同じ作法に揃えるのが一貫性がある**: `splitOn` による分割対象に `{source}` を追加し
（現状 `{license}` → `{generatedAt}` の 2 段分割になっている 59〜61 行目を、`{source}` も含めた
3 段分割に拡張する必要がある）、`<a href={meta.sourceUrl} rel="noopener noreferrer"
target="_blank">{meta.source}</a>` として埋め込む。

**`target="_blank"` と a11y 文言について**: 既存の `{license}` リンク（69〜76 行目）は
`rel="noopener noreferrer"` / `target="_blank"` は付いているが、`sr-only` の「新しいタブで開き
ます」相当の文言は **付いていない**（`repository-detail.tsx` の `opensInNewTab`
パターンとは異なる）。よって `{source}` リンクも `{license}` リンクと同じ作法（`target="_blank"`
+ rel のみ、a11y sr-only 文言なし）に揃えるのが**既存パターンとの一貫性は高い**。ただし
`repository-detail.tsx` はそのすぐ横のコメント（67〜70 行目）で「新しいタブで開くことが
伝わらないと a11y 上の問題になる」（`ui-ux-guidelines.md` §7.4a）と明記しており、`{license}`
リンクが既にこの規律から外れている可能性がある（本レンズの担当外・別レンズ or 別 Issue の
争点として切り出すことを推奨）。**F-6 の実装スコープとしては `{license}` と同じ作法に揃える
（sr-only 文言は追加しない）ことを推奨するが、`{license}` 側の a11y 未対応は別途指摘すべき**。

### `attribution-notice.test.tsx`（既存テストパターンを確認済み）

`src/ui/attribution-notice.test.tsx` 73〜80 行目付近に
`it('ライセンスは sourceLicenseUrl を指すリンクになっている（改変元へ辿れる・D-29）', () => {
const link = screen.getByRole('link', { name: 'CC BY-SA 4.0' }); … })` という既存テストがある。
`{source}` 版として同型のテスト（`getByRole('link', { name: 'Ecosyste.ms' })` が `meta.sourceUrl`
を指すことを検証）を追加する。テストフィクスチャ（11 行目付近の `meta` オブジェクト）にも
`sourceUrl: 'https://ecosyste.ms/'` を足す必要がある。

## 争点になりうる点（反論の余地）

- `DAILY_DIGEST_LIMIT` を `page.tsx` へインライン化する案に対し、「将来また RSS や別の配信経路を
  作るなら composition ファイルを残しておくべき」という反論はありうる。ただし CLAUDE.md の
  「やってはいけないこと」に **YAGNI**（1 箇所しか使わない抽象化を先回りしない）が明記されて
  おり、再導入時に `git log` から `digest-feed.ts` を復元すれば済むため、本分析では削除を推奨する。
  最終判断は着手セッションに委ねる。
- `D-34` の番号は本分析時点（`D-33` が最大）での次番号の見積もり。他ラウンドの提案が同時に
  別の `D-番号` を消費する場合は衝突するため、実装セッションで採番し直す前提で読むこと。

### `arch_domain` — 主張
<sub>2026-08-21T16:43:26+09:00</sub>

## 結論サマリー

- **F-3**: `description` は実は **既にドメイン/ACL 層で完成済み**（`mapper.ts` の `toPublicRepositoryDetail` が `dto.description` を返却済み・`mapper.test.ts:151` が検証済み）。未着手なのは `lastPushedAt` の追加と UI 表示のみ。「最終更新」は **一覧と同じ `pushed_at`（`updated_at` フォールバック）を使うべき**（根拠は既存の `domain-model.md` §2.2 の記述・下記）。
- **F-4**: README 取得は `RepositoryQueryPort` に **`findReadme` を追加**（新ポートは切らない）。取得は「詳細と並行」ではなく **「詳細確定後」の逐次**にする。理由は速度ではなく **セキュリティ**（README エンドポイントには `private` フィールドが無く、詳細取得の private ガードを再利用する以外に安全に絞る手段がない）。

---

## 争点 D（F-3: 型・表示）

### 更新範囲

| ファイル | 変更内容 |
|---|---|
| `src/domain/model/repository.ts` | `RepositoryDetail` に `readonly lastPushedAt: Date` を追加（`description` は追加不要・既存） |
| `src/infrastructure/github/dto.ts` | `repositoryDetailDto` に `pushed_at: z.string().nullable()` と `updated_at: z.string()` を追加（`repositoryDto` と同じ形。現状 `repositoryDetailDto` はこの 2 フィールドを持っていない） |
| `src/infrastructure/github/mapper.ts` | `toPublicRepositoryDetail` の戻り値に `lastPushedAt: new Date(dto.pushed_at ?? dto.updated_at)` を追加（`toSearchResult` と同じフォールバックロジック） |
| `src/infrastructure/github/__fixtures__/repository-detail.json` | `pushed_at` / `updated_at` を追加（現状どちらも無い） |
| `src/infrastructure/github/mapper.test.ts` | `toPublicRepositoryDetail` のテストに `lastPushedAt` の期待値を追加（`toSearchResult` テストの `lastPushedAt は pushed_at 由来` と同種の 1 ケース） |
| `src/infrastructure/github/dto.test.ts` | `repositoryDetailDto` の fixture（42 行目 `const detail = {...}`）に `pushed_at` / `updated_at` を追加しないと新スキーマで既存の成功系テストが壊れる（必須フィールド化するため） |
| `src/infrastructure/github/github-repository-query.test.ts` | `findDetail` 系テストが `detailFixture` を使い回すだけなら fixture 更新で足りる。個別に raw オブジェクトを組み立てているケースがあれば同様に 2 フィールドを追加 |
| `src/ui/repository-detail.tsx` / `repository-detail.test.tsx` | `description`・`lastPushedAt` の表示追加とテスト（UI 側の詳細実装は `ui_nav` の担当領域と重なるため設計判断のみ記す） |
| `messages/ja.json` / `messages/en.json` | `detail.description` は原文言語のまま表示するため見出しラベルのみ要る可能性（`detail.updatedAt` 等）。一覧（`AR-1`）の既存キーを流用できないか先に確認（新規キー乱立を避ける・YAGNI） |
| `docs/03_design/data-model/domain-model.md` | 変更不要の可能性が高い。§2.2 の「`pushed_at` / `updated_at` → `lastPushedAt` / `lastUpdatedAt`」対応表は既に汎用的に書かれており、`RepositoryDetail` 限定の記述ではない。ただし `RepositoryDetail` の項目説明（「詳細ページに出す7項目」）は F-3 で 8 項目（+`description`, +`lastPushedAt`）になるため、この「7項目」という数字の記述と `prd.md` §7 `AC-5`（Given/When/Then の列挙）は数字・列挙が古くなる。**`docs_trace` 側での更新が必要**（自分は変更しない・読むだけ） |

### 「最終更新」は pushed_at か updated_at か（決定と根拠）

**`pushed_at`（`updated_at` へのフォールバック付き）を使うべき。一覧と同じ意味の値にすべき。**

根拠:
1. `docs/03_design/data-model/domain-model.md:72` に既に明記されている: `pushed_at` / `updated_at` → `lastPushedAt` / `lastUpdatedAt` であり「『最終更新日』（`AR-1`）は **`pushed_at`** を使う（メタデータ更新で動く `updated_at` ではない）」。これは `RepositoryDetail` 限定ではなく ACL 変換表全体の規則として書かれている。
2. `mapper.ts` の `toSearchResult` は既にこのルールを実装済み（コメント: 「pushed_at が null（コミット履歴のない空リポジトリ）の場合のみ updated_at にフォールバック」）。
3. **一覧と詳細で値が食い違うと利用者が混乱する**: 一覧カードで見た「最終更新: 3日前」が詳細ページで別の日付（`updated_at` はメタデータ変更でも動くため、ほぼ常に `pushed_at` 以降の直近日時になる）に変わると、同じ「最終更新」ラベルが指す意味が画面遷移で変わったように見える。`AR-1`（一覧の追加表示項目）と `FR-4` 拡張（詳細の追加表示項目）は同じ「最終更新日」という利用者向け概念を指しており、**同一概念には同一の算出規則を適用するのがドメインモデルの一貫性**（`domain-model.md` §1 のユビキタス言語の目的そのもの）。
4. 反対されうる点: GitHub の詳細 API レスポンスは `pushed_at` を検索結果と別のタイミングで返す（キャッシュ TTL が違う・`TTL_DETAIL_SECONDS=300` vs `TTL_SEARCH_SECONDS=60`）ため、一覧カードで見た日付と詳細ページの日付が **同じフィールドでも値がわずかにズレる**ことがある（キャッシュ鮮度の違いによる）。これは「どのフィールドを使うか」の問題ではなく別レイヤ（キャッシュ TTL 設計）の帰結であり、`updated_at` に切り替えても解決しない。実用上許容範囲と判断する。

### 実装形（YAGNI 自己批判）

`RepositoryDetail` に新規プロパティを 1 つ足すだけであり、新しい値オブジェクト・新しい型・新しいポートは不要。`RepositorySummary.lastPushedAt` と同じ `Date` 型を再利用する（`domain-model.md` の「一覧項目」と「詳細」を別型にする方針とは矛盾しない — 型そのものは同じ `Date` を共有してよく、別型にすべきなのは `RepositorySummary` と `RepositoryDetail` という**エンティティの粒度**であって、フィールドの型ではない）。

---

## 争点 B/C（F-4: README のポート設計・取得順序・セキュリティ）

### 1. `RepositoryQueryPort` へ `findReadme` を追加する（新ポートは切らない）

```ts
// src/domain/ports/repository-query-port.ts
export interface RepositoryQueryPort {
  search(query: SearchQuery): Promise<SearchResult>
  findDetail(name: RepositoryFullName): Promise<RepositoryDetail | null>
  /** 単一リポジトリの README を取得する。存在しない・非公開・対象なしの場合は null。 */
  findReadme(name: RepositoryFullName): Promise<string | null>
}
```

**新ポートを切らない理由**（`application-architecture.md` §2 の「ポートを増やすときの条件: `W-1`〜`W-3` のどれを守るかを1行で言えることを条件にする」への回答）:
- README は **同じ GitHub リポジトリという同一エンティティ**（`RepositoryId` = `owner/name`）の副次的な情報であり、`Gem Index`（Ecosyste.ms・別コンテキスト・別データ源・`GemDigestPort` として分離済み）とは性質が違う。README は GitHub API・同じ ACL ファイル（`github-repository-query.ts`）・同じ `RepositoryFullName` 引数を再利用する。
- 新ポートを切ると「2 本目の実装クラス」「2 本目の composition 配線」を用意する必要が生まれるが、実装は今後も `GithubRepositoryQuery` 1 本のままである見込みが高く、差し替え可能性（`W-1`）を守るための分離ではない。**面積を広げるコストに対して守れる `W-n` が無い＝ YAGNI 対象**。
- 既存の `RepositoryQueryPort` の面積表（`application-architecture.md` §2）は「これ以上広げない」と明記されているため、本変更では **その表の行自体を「`+ findReadme(name): Promise<string | null>`」に更新する PR が必須**（黙って広げない）。

反対されうる点: `RepositoryQueryPort` という名前が「検索・詳細取得」に限定して読めるため、3 メソッド目の追加はインターフェース分離原則（ISP）の観点で見ると気持ち悪いという意見はありうる。ただし本プロジェクトは ISP を明示的な設計原則として採用していない（`domain-model.md` §1 の「採る/採らない」表に無い）ため、YAGNI を優先する。

### 2. 取得順序: 「同時（並行）」ではなく「詳細確定後の逐次」にする（速度ではなくセキュリティが理由）

**決定的な技術的事実**: `GET /repos/{owner}/{repo}/readme` のレスポンス（ファイルメタデータ: `name`/`path`/`sha`/`content`/`encoding` 等）には **`private` フィールドが存在しない**。つまり README エンドポイント単体のレスポンスからは「このリポジトリが非公開かどうか」を判定できない。`toPublicRepositoryDetail` が持つ「`private: true` なら `null`」という自己防御パターン（mapper.ts）は README には**そのままでは適用できない**。

したがって README の非公開リポジトリからの漏洩を防ぐ唯一の方法は、**`findDetail` の private 判定結果に依存すること**である。設計:

```ts
// src/usecases/get-repository-readme.ts（新規）
export function makeGetRepositoryReadme(deps: { repos: RepositoryQueryPort }): GetRepositoryReadme {
  return async (input) => {
    const name = tryRepositoryFullName(input.owner, input.repo)
    if (name === null) return null
    const detail = await deps.repos.findDetail(name) // private/404 は既存の ACL 判定を再利用
    if (detail === null) return null
    return deps.repos.findReadme(name)
  }
}
```

- ゲートは **usecase 層**（`src/usecases/get-repository-readme.ts`）に置く。`GithubRepositoryQuery.findReadme` 自身の中に置かない。理由: `GithubRepositoryQuery`（キャッシュを持たない生の ACL 実装）の中でゲートすると、その内部呼び出しは `CachingRepositoryQuery` を経由しないため**キャッシュに乗らず、詳細表示のたびに私有判定用の GET が無条件で 1 回余分に増える**。usecase 層でゲートすれば、`deps.repos`（= `CachingRepositoryQuery` でラップ済み）を経由するため、後述のキャッシュ再利用が効く。
- **これは「呼び出し側の順序を信頼する」設計ではない**（NFR-33 の「構造で強制する」原則に反しない）: `getRepositoryReadmeUseCase` を単独で（`getRepositoryDetailUseCase` を呼ばずに）叩いても、内部で必ず `findDetail` を経由するため非公開データは漏れない。ゲートはこの usecase 関数自体に埋め込まれており、呼び出し元（`app/`）の律儀さに依存しない。

### 3. ページ側の呼び出し順序とキャッシュ再利用

`page.tsx` は元々 `AC-5` のため `notFound()` を **`<Suspense>` の前に**実行する制約があり、`getRepositoryDetailUseCase` の結果を待ってから描画を始める設計になっている（既存コメント参照）。この制約により、README の取得を「詳細と完全並行（`Promise.all`）」にする動機（レイテンシ短縮）はそもそも弱い——detail の解決は notFound 判定のためどのみち待たねばならない。

```ts
const detail = await getRepositoryDetailUseCase(token)({ owner, repo })
if (detail === null) notFound()
// ...FR-4 の描画...
let readme: string | null = null
try {
  readme = await getRepositoryReadmeUseCase(token)({ owner, repo })
} catch {
  readme = null // NFR-9: 内部エラー文言は画面に出さない。詳細ページ全体は落とさない
}
```

`getRepositoryReadmeUseCase` の内部 `findDetail` 呼び出しは、`container.ts` の `sharedCache`（モジュールスコープの単一インスタンス）を経由するため、**逐次実行すれば 1 回目の `findDetail`（ページ本体用）が書き込んだキャッシュエントリに 2 回目（README ゲート用）がヒットする**。したがって実際に GitHub へ飛ぶリクエストは「詳細 1 回 + README 1 回」の **2 リクエスト**に収まる（3 回にはならない）。

⚠️ **`Promise.all` で並行実行すると、この前提が崩れる**: 2 つの `CachingRepositoryQuery` インスタンス（`makeCachingRepositoryQuery()` は呼び出しごとに新規生成・`container.ts`）は `inFlightDetail`（single-flight マップ）を共有しないため、両方が同時に `cache.get()` して両方 MISS になり、`findDetail` が 2 回上流へ飛ぶ可能性がある（3 リクエストに劣化）。**逐次実行を推奨する**理由はこのキャッシュ構造上の帰結であり、恣意的な設計ではない。

### 4. AC-12 / NFR-33 との整合（セキュリティ契約）

- `toPublicRepositoryDetail` の private 除外は「詳細取得の応答を private 判定 → null」という順序で **既に** README 取得の前段に位置する（`getRepositoryReadmeUseCase` が `findDetail` を先に呼ぶ設計のため）。
- 反対されうる点/残るリスク: `findDetail` から `findReadme` 呼び出しまでの間に対象リポジトリが非公開化される **TOCTOU** は理論上あるが、確率・実害ともに無視できる（同一リクエスト内で数百ms以内）。既存の `NFR-33` の脅威モデル（installation token の可視範囲問題）とは別種のリスクであり、本 PR のスコープ外として明示するに留める。
- `docs/02_requirements/prd.md` の `AC-12` は現状「詳細ページ URL を直接開く」ケースのみ記載（460行目台）。README 経路の非公開防止シナリオを `AC-12` に 1 行追加すべきだが、これは `docs_trace` の担当領域として申し送る（自分はドキュメントを編集しない）。

### 5. キャッシュ設計

`src/infrastructure/platform/cache-key.ts` に新規名前空間を追加する:

```ts
const NAMESPACE_README = 'readme'
export function repositoryReadmeCacheKey(owner: string, name: string): CacheKey {
  return `${NAMESPACE_README}:${CACHE_SCHEMA_VERSION}:${normalizeSegment(owner)}/${normalizeSegment(name)}` as CacheKey
}
```

- `CACHE_SCHEMA_VERSION`（既存の `v2`）を **README にもそのまま流用する**（既に `search` と `repository` の 2 namespace が 1 つのバージョンを共有しており、3 つ目の namespace を増やしても既存の結合を悪化させない。専用バージョン変数を新設するのはこの時点では過剰）。
- TTL は **新しい定数を作らず `TTL_DETAIL_SECONDS`（300秒）を再利用する**ことを推奨する（`container.ts` の TTL 決定はどちらも「`R-5` のレート枠逆算待ちの暫定値」という同じ根拠を持っており、README だけ別の値にする実質的な理由が今は無い・YAGNI）。
- `CachingRepositoryQuery` に `findReadme` の read-through 実装を追加（`findDetail` と同じ `readThrough` ヘルパーを再利用。`cacheable: (r) => r !== null` で 404/非公開を キャッシュしない、という既存の `findDetail` と同じ規約を踏襲する）。

### 6. レート枠消費への影響

詳細ページ 1 回の表示あたり、GitHub API 呼び出しは **現状 1（詳細のみ）→ 最大 2（詳細 + README）** に増える（キャッシュ HIT 時はどちらも 0）。README のみが MISS で詳細が HIT というケースは、上記の usecase 内 `findDetail` ゲートが同じキャッシュキーを叩くため発生しない（詳細がキャッシュ済みなら README ゲートも同じ HIT を得る）。逆に詳細のみ MISS で README だけ HIT ということはあり得ない（README がキャッシュされているなら、それより TTL の短くない詳細もキャッシュされているはず——ただし TTL を揃えなければこの前提は崩れる。これも「README の TTL を詳細と揃えるべき」というキャッシュ設計上の根拠になる）。

### 7. YAGNI 自己批判

- **足さない**: README 専用の値オブジェクト/エンティティ型（例: `Readme { content, size, encoding }` のようなラッパークラス）。現状 UI が必要とするのは本文だけであり、`findReadme` の戻り値は素の `string | null` で十分。将来「巨大 README の切り詰め表示」等が要るなら、それは `readme_render` 側の表示関心であり、切り詰めをドメイン型に持たせる理由にはならない。
- **足さない**: README 専用の TTL 定数・専用のキャッシュスキーマバージョン（§5 参照）。
- **足す妥当性がある**: `findReadme` を `RepositoryQueryPort` に追加すること自体（既存ポートの拡張）と、ゲート専用の `getRepositoryReadmeUseCase` を独立ファイルとして持つこと。後者を `getRepositoryDetailUseCase` に合体させない理由は次の争点（F-4 の 404/エラー分離要件）で述べる。

---

## 争点 D/F-4 共通（既存宣言の更新・404 契約との両立）

### 既存宣言「データソースは GET /search/repositories と GET /repos/{owner}/{repo} に限定する（E-2）」の更新箇所

| ファイル | 現在の記述 | 対応 |
|---|---|---|
| `src/infrastructure/github/github-repository-query.ts`（クラス docstring） | 「データソースは GET /search/repositories と GET /repos/{owner}/{repo} に限定する（E-2）」 | **要更新**（コード）。`GET /repos/{owner}/{repo}/readme` を追記する |
| `docs/02_requirements/user-story-map.md:198`（`E-2` の定義） | 「データソースは `GET /search/repositories` と `GET /repos/{owner}/{repo}` に限定し…」 | 要更新（`docs_trace` 担当）。README エンドポイントを追記 |
| `docs/02_requirements/prd.md:178`（`TR-4`）/ `prd.md:278-279`（§4.3 の表） | 検索・詳細の 2 行のみ | 要更新（`docs_trace` 担当）。README の行を追加（`GET /repos/{owner}/{repo}/readme`・404 は「README なし」として `null`、非公開は詳細と同じ「見つからない」扱いである旨） |
| `docs/02_requirements/minimum-requirements.md:26` | 「データソース: GitHub API のリポジトリ検索エンドポイント」 | **変更しない**。これは与件（原文の要件定義書）であり、`prd.md` が「与件への実装上の解釈・補足」を持つ構造（`prd.md` 冒頭の `AC-n`/`TR-n` の説明）。上乗せ機能である README を与件側に書き足すのは筋が違う |

自分（`arch_domain`）はドキュメントを編集しないため、上記は **`docs_trace` への申し送り**として明記する。

### 404 契約（AC-5）との両立

`app/[locale]/repos/[owner]/[repo]/page.tsx` は `<Suspense>` を意図的に置いていない（`notFound()` を送出前にレスポンスヘッダを確定させる必要があるため）。README 取得を「詳細取得後・逐次・try/catch で個別に握る」設計（§3 参照）は、この制約と自然に両立する:

- `notFound()` の判定は `getRepositoryDetailUseCase` の結果だけで完結し、README の成否とは無関係（README 取得コードは `notFound()` 判定の**後**にしか実行されない）。
- README 取得の失敗（`NetworkError` / `RateLimitExceededError` / `UpstreamError` 等のドメインエラー）は **`app/` 層で catch し `null`（＝「README 未取得」の表示状態）へ写す**。これは `application-architecture.md` §4「`app/` はドメインエラーを UI の状態へ写す」という既定パターンと一致し、新しいエラーハンドリング様式を持ち込まない。
- ドメイン/インフラ層では **握り潰さない**（`catch` して `console.error` だけで終わらせない、という既存規律を維持）。`findReadme` / `getRepositoryReadmeUseCase` はエラーをそのまま送出し、`app/` だけが最終的に握って表示状態に変換する。

---

## 反対されうる点（全体）

1. **「詳細確定後の逐次」は本当に必要か**: README エンドポイントが（将来 GitHub 側の仕様変更で）`private` を返すようになれば、mapper 側の自己防御パターンに寄せられ、usecase 層のゲートは冗長になる可能性がある。ただし現状の GitHub REST 仕様（Contents API）に private フィールドは無く、変更を前提にした設計はできない。
2. **`findReadme` をポートに直接足す設計は「面積を広げない」という既存方針とやや緊張する**。表の更新を伴う変更である旨をレビューで明示する必要がある（黙って広げない）。
3. **README の取得を `getRepositoryDetailUseCase` に統合すべきという意見はありうる**（1 usecase で完結する方がシンプルに見える）。しかし統合すると README 取得失敗が `RepositoryDetail` 全体の例外として伝播し、`AC-5` の他 7〜8 項目（Star/Watcher/Fork/Issue/description/lastPushedAt 等）の表示まで巻き添えで壊れる。分離が必須である根拠は「シンプルさ」ではなく「F-4 の要件 6（README 障害が画面全体を壊さない）」そのものである。

### `readme_render` — 主張
<sub>2026-08-21T16:44:33+09:00</sub>

# README 表示（F-4）レンダリング方式・安全性 — 結論

## 結論サマリー

| 争点 | 結論 |
|---|---|
| 取得形式（C） | **`Accept: application/vnd.github.html+json`（GitHub 側レンダリング済み HTML）を採用**。raw + 自前 Markdown パーサはこの Worker では不採用 |
| サニタイザ | **`sanitize-html`**（htmlparser2 ベース）。`parseStyleAttributes: false` で postcss 依存を切る |
| 相対リンク・画像 | GitHub API は relativize しない（**実測で確認済み**）。README エンドポイント自身が返す `html_url`/`download_url` から算出した base URL で自前解決が必須 |
| 表示量 | サーバー側で HTML 文字列の長さで切り詰め＋「GitHub で全文を見る」リンク常設 |
| 失敗時 | README 取得は詳細ページ本体の 404 判定と分離。ネストした `<Suspense>` で個別ストリーミングし、失敗時はインラインで代替リンクのみ表示（ページ全体を落とさない） |
| NFR-3 | 影響なし。README 処理は 100% サーバー側（`use client` 不使用）で完結するため、選ぶライブラリに関わらずクライアント JS はゼロ |

---

## 1. 取得形式の比較

GitHub の Contents API `GET /repos/{owner}/{repo}/readme` は `Accept` ヘッダで 2 メディアタイプを切り替えられる（[GitHub 公式 REST リファレンス](https://docs.github.com/en/rest/repos/contents) で確認済み）:

- `application/vnd.github.raw+json`（既定）: 生 Markdown 文字列
- `application/vnd.github.html+json`: GitHub のオープンソース Markup ライブラリでレンダリング済みの HTML 文字列

**この 2 択の決め手は Cloudflare Workers の CPU 予算**。`wrangler.jsonc` は `"limits": { "cpu_ms": 50 }` を宣言しており、`cloudflare-infrastructure.md` §259 は「🔴 現状（2026-08-20 実機確認）: 本アカウントは Workers Paid（$5/月 + 従量）である」と明記している。つまり `limits.cpu_ms` は **現在まさに有効**（同ドキュメントも「Free では意味を持たないが Paid へ上げた瞬間に効く」と注記）。1 リクエストあたり 50ms の CPU 予算しかない中で、GFM（テーブル・タスクリスト・オートリンク・脚注等）まで含む Markdown を自前で AST 化してから HTML へ変換するのは、GitHub 側が既にやってくれている作業をもう一度 CPU で払い直すことになる。README は数十 KB になることも珍しくなく、自前パースの CPU コストは無視できない。**HTML 方式なら「サニタイズ（1 パスの HTML パース＋フィルタ）」だけで済み、CPU コストが小さく安定する**。

### ライブラリ比較（自前 Markdown レンダラを採る場合の参考・bundlephobia 実測）

| ライブラリ | 役割 | gzip サイズ（概算） | Workers ランタイム互換性 |
|---|---|---|---|
| `marked` | Markdown→HTML（軽量・GFM 拡張は別途） | 約 12.7 KB | 純 JS・DOM 非依存。互換 |
| `micromark`（remark の内部エンジン） | CommonMark トークナイザ | 個別に小さいが `remark-gfm` 等を積むと合算で増える | 純 JS・互換 |
| `react-markdown` + `remark-gfm` | React 要素として描画（unified/remark エコシステム） | `react-markdown` 約 34 KB + `remark-gfm` 約 9.8 KB | 純 JS・互換。Server Component として使う分にはクライアント JS は増えない |
| `markdown-it` | 高機能・プラグイン豊富 | 未計測（同系統で 20〜30 KB 帯が相場） | 純 JS・互換 |

いずれも Workers（DOM 非依存の純 JS 変換）としては動作可能。**ただし採用しない**。理由は上記の CPU 予算に加え、GFM 完全互換（タスクリスト・脚注・オートリンク・絵文字ショートコード・シンタックスハイライト）を自前で仕上げるコストが、GitHub がサーバー側で既に提供している出力を単に受け取るコストを上回るため（YAGNI・過剰実装回避）。

**根拠**: GitHub REST API 公式ドキュメント（WebFetch で取得・確認済み）、`wrangler.jsonc:11`、`docs/03_design/infrastructure/cloudflare-infrastructure.md:156,259`、bundlephobia API 実測値。

**反対されうる点**: 将来 README の構造解析（Q-2 の「README の構造品質」指標化など Gem Score 拡張）が必要になった場合、HTML 方式では Markdown の構文情報（見出し階層・リンク密度等）が失われており AST 解析に不向き。その時が来たら raw 方式 + 自前パーサへの切り替えを再検討する必要がある（現時点の F-4 スコープでは非該当）。

---

## 2. XSS 対策の具体

### GitHub 側の出力を無条件に信頼しない

GitHub は github.com 上での表示のために既に一定のサニタイズ（`<script>`/`<style>`/`<iframe>`/`on*` 属性の除去等）を行っているとみられるが、**これは github.com というホスト・CSP・出所の文脈で安全なだけ**であり、①この API 出力に対する将来のサニタイズ仕様変更を我々が保証できない、②任意の第三者（リポジトリオーナー）が完全に自由に書ける文字列を `dangerouslySetInnerHTML` で自ドメインの DOM に注入する以上、多層防御としてこちら側でも独立にサニタイズすべき。実測で取得した本リポジトリ自身の README HTML には `<script>` `<style>` `<iframe>` `onerror=` `onclick=` `javascript:` は含まれていなかったが（悪意ある内容でないため当然）、これは「安全である証拠」ではなく単に「テストケースが無害だった」だけなので判断根拠にしない。

### 採用: `sanitize-html`（htmlparser2 ベース）

- **なぜ `sanitize-html` か**: `DOMPurify`（`isomorphic-dompurify`）は Node 環境で動かすために内部で `jsdom` を要求する構成が一般的で、`jsdom` は `canvas` 等のネイティブ依存や `window`/`document` の完全実装を前提にしており、**Workers ランタイム（workerd）では動作しない**（DOM 非搭載・`nodejs_compat` でも jsdom の要求する Node API 全体はカバーされない）。除外。
- `rehype-sanitize`（`defaultSchema` が「GitHub style sanitation」を謳っており意味的には理想的）も候補にしたが、これは `rehype-parse`（内部で `parse5`＝フル HTML5 準拠パーサ）とセットで使う必要があり、bundlephobia 実測で `rehype-parse` 単体が **gzip 60.6 KB**（`sanitize-html` の 56.2 KB と同等以上）。「AST 系は軽い」という予断は誤りだった。加えて `parse5` は spec 完全準拠を優先する分、`htmlparser2`（`sanitize-html` の内部パーサ）より低速な傾向があり、cpu_ms 予算の観点では `sanitize-html` の方が有利。**Worker バンドルサイズ自体は 3 MB gzip 上限に対してどちらを選んでも誤差レベルだが、CPU 時間の観点で `sanitize-html` を推奨する。**
- `sanitize-html` は URL 書き換え（`transformTags`）とサニタイズを同一パスで行えるため、後述の相対リンク解決とサニタイズを 1 回の HTML パースで完結できる（rehype 構成だと「rewrite プラグイン」＋「sanitize プラグイン」の 2 段になるが AST 上なので追加パースは不要という点は同等）。

### 許可方針（ホワイトリスト）

- **禁止**: `script` `style` `iframe` `object` `embed` `form` `svg`（`use`/`foreignObject` 経由の XSS ベクタを避けるため意図的に不許可。README 内の手描き SVG バッジ等は表示されなくなるが安全側に倒す）、全 `on*` イベント属性、`style` 属性（`parseStyleAttributes: false` にして postcss 依存自体を切る。GitHub の構文ハイライトはクラスベースで inline style に依存しないため実害は小さい）
- **許可スキーム**: `a[href]` は `http` `https` `mailto` のみ、`img[src]` は `http` `https` のみ（`data:` は SVG 経由の XSS を避けるため両方とも不許可）。`javascript:` 系は当然除外
- **許可タグ/属性**: 見出し `h1`-`h6`（`id` 許可・後述のアンカー整合のため）、`p` `a[href]` `ul` `ol` `li` `blockquote` `pre` `code[class]`（`class` は `/^(language-|pl-)/` の正規表現許可のみ。GitHub 構文ハイライトのトークンクラス。対応 CSS を持たなければ単に無色表示になるだけで無害）、`table` `thead` `tbody` `tr` `th` `td`、`img[src|alt|width|height]`、GFM タスクリスト用に `input[type=checkbox][disabled][checked]`（`type` は `checkbox` 固定のみ許可）、折りたたみセクション用に `details` `summary`（GitHub README で多用される）、`kbd` `sub` `sup` `hr` `br` `del` `em` `strong`

### 外部リンクの `target`/`rel`

`rehype-sanitize` の `defaultSchema` は `a` タグの `target`/`rel`/`style`/`class` を仕様上明示的に不許可にしている（Context7 で確認: 「Note: these 3 are used by GFM footnotes...」のコメント付きで `target` `rel` は許可リストに **存在しない**）。攻撃者が指定した値をそのまま通す設計にはせず、**サニタイズ後の後処理として全ての外部 `<a href="http(s)://...">` に固定値 `target="_blank" rel="noopener noreferrer"` をこちらで一律付与する**（`repository-detail.tsx` のタイトルリンクと同じ既存パターンに合わせる）。

**根拠**: bundlephobia API 実測、Context7 (`/rehypejs/rehype-sanitize`, `/apostrophecms/sanitize-html`) 取得ドキュメント、`src/ui/repository-detail.tsx:71-83`（既存の `target="_blank" rel="noopener noreferrer"` パターン）。

**反対されうる点**: `svg` 全面禁止は GitHub 公式サニタイザより厳しく、CI バッジ等で古い形式（img ではなく inline svg）を使っている README は表示崩れが起きる。実害は「一部装飾が消える」程度でセキュリティ上は安全側なので許容範囲と判断するが、UX 上の劣化として認識しておくべき。

---

## 3. 相対リンク・相対画像の解決（実測で確認）

**GitHub の HTML レンダリング API は相対パスを絶対 URL に書き換えない。** 本リポジトリ自身の README（`kai-kou/gem-hunter`）に対して実際に `GET /repos/kai-kou/gem-hunter/readme` を `Accept: application/vnd.github.html+json` で叩いて確認した:

```
href="./docs" href="./LICENSE" href="./docs/adr/0001-ui-stack.md" ...
```

これらは書き換えられずそのまま返る。ドキュメント上も明記されておらず（WebFetch で GitHub 公式ページを確認したが記載なし）、**実測でしか分からない仕様**だった。github.com 本体のリポジトリ表示ページは相対パスを解決して表示しているが、それは github.com のページレンダリングパイプライン固有の処理であり、Contents API の HTML 出力には適用されていない。

さらに**アンカー ID にも罠がある**: GitHub は見出しに `id="user-content-{slug}"`（`user-content-` プレフィックス付き）を振るが、見出し横のパーマリンクアイコンや README 内目次のリンクは `href="#{slug}"`（プレフィックスなし）を指す。github.com 本体ではこの不一致を吸収する仕組みがあるとみられるが、我々の埋め込み先ページにはそれが無いため、**このまま埋め込むと README 内のアンカーリンク（目次等）が一切機能しない**。

### 解決方針

`GET /repos/{owner}/{repo}/readme` のレスポンス自体が `html_url`（例 `https://github.com/kai-kou/gem-hunter/blob/main/README.md`）と `download_url`（例 `https://raw.githubusercontent.com/kai-kou/gem-hunter/main/README.md`）を返す（実測で確認済み・`ref`＝デフォルトブランチをここから取得できるため、**`GET /repos/{owner}/{repo}` 本体に `default_branch` を追加取得する必要はない**）。これらからベース URL を組み立て、サニタイズと同じ HTML パスの中で:

- `a[href]` がスキーム付き絶対 URL・`mailto:`・`#` 始まりのフラグメント以外なら `https://github.com/{owner}/{repo}/blob/{ref}/` を base に解決
- `#{slug}` 形式のフラグメントは `#user-content-{slug}`（既に `user-content-` 始まりならそのまま）に書き換え、見出し `id` と一致させる
- `img[src]` が相対パスなら `https://raw.githubusercontent.com/{owner}/{repo}/{ref}/` を base に解決

**根拠**: 実測（`curl` で本リポジトリの README を `application/vnd.github.html+json` / 既定 JSON の両方で取得・`html_url`/`download_url`/相対 `href` の実出力を確認済み）。

**反対されうる点**: 画像を持つ README で `raw.githubusercontent.com` への解決が正しいか（GitHub 本体は `camo.githubusercontent.com` プロキシ経由にする場合がある）は本リポジトリの README に画像が無く実測できていない。実装時に画像付き README（例: 検索結果から実在の公開リポジトリ）でもう一段実機確認することを推奨する。

---

## 4. 表示量の方針

巨大 README（数百 KB 級）をそのまま埋め込むと a) cpu_ms 予算内でのサニタイズ処理時間、b) レスポンスサイズ、双方に影響する。**サニタイズ後の HTML 文字列長で上限を設け（例: 一定文字数を超えたら切り詰め）、切り詰めた場合・切り詰めていない場合の両方で「GitHub で全文を読む」導線（`html_url` へのリンク）を常設する**（`repository.htmlUrl` の外部リンクと同じ `target="_blank" rel="noopener noreferrer"` パターン）。HTML 文字列の単純な文字数カットは中途半端な位置でタグを分断するリスクがあるため、サニタイズ後の DOM/トークン単位（`sanitize-html` の `exclusiveFilter` やブロック要素境界）で打ち切るのが安全。具体的な閾値は UX 判断（`ui_nav` ロール）と合わせて決める領域なので、ここでは「文字数ではなく安全な境界で切る」という実装制約のみを申し送る。

---

## 5. 失敗時のフォールバック — AC-5 の 404 制約との両立

`app/[locale]/repos/[owner]/[repo]/page.tsx` は **`<Suspense>`/`loading.tsx` を意図的に置いていない**。理由はコメントの通り「`notFound()` は Suspense 境界より前に呼ぶ必要があり、境界のフォールバックが一度でも描画されるとレスポンスヘッダが確定して 404 を返せなくなる」ため（`node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/loading.md` で実際に確認: *"Place `notFound()` before those boundaries and before any `await` that may suspend."*）。

**この制約はページ本体（`repository` 取得＝404 の判定材料）にのみ適用される。** README 取得は 404 の判定に関与しない（README が無くても「リポジトリは存在する」という 200 の結論は変わらない）。したがって:

- `repository === null` の `notFound()` 判定は**従来どおり同期 `await` で行い、ストリーミングを一切開始させない**（変更なし）
- 404 でないと確定した**後**（＝ `main` の JSX ツリーの中、既存の統計表示より下）に **README 専用の新しい `<Suspense>` 境界を 1 つだけ追加**し、その内側で README を取得・レンダリングする非同期 Server Component を描画する。この境界に入るのは 404 判定が既に確定した後なので、AC-5 を一切壊さない
- 境界の `fallback` は軽量なスケルトン（テキスト 1〜数行程度。クライアント JS 不要）
- README 取得自体が失敗（レート制限・upstream エラー・パース失敗等）した場合は、**例外を投げて最寄りの `error.tsx` に落とさない**。README コンポーネント内部で `try/catch` し、失敗時は「README を読み込めませんでした。GitHub で見る」の 1 行 + `repository.htmlUrl` へのリンクを表示するだけに留める（詳細ページ全体を巻き込まない）
- README 不在（404）は `findDetail` と同じ `notFoundAsNull` パターンを再利用し `null` を返す契約にする（エラーではなく「README セクションを描画しない」という正常系の分岐として扱う）
- 非 UTF-8 / バイナリ混入は実測上 GitHub API 側で正規化済み（JSON 文字列として返る時点で UTF-8 が保証される。raw モードは `encoding: "base64"` を明示的に持つため呼び出し側で誤�った decode をする余地がない。今回採用する HTML モードはそもそも base64 を経由せずテキストとして返る＝実測で日本語含む README を破損なく取得できたことで確認済み）

**根拠**: `app/[locale]/repos/[owner]/[repo]/page.tsx` 冒頭コメント、`node_modules/next/dist/docs/.../loading.md`（本バンドル版 Next.js 16 の公式仕様を直接確認）、`GithubRepositoryQuery.request()` の既存 `notFoundAsNull` パターン（`src/infrastructure/github/github-repository-query.ts:70-78`）。

**反対されうる点**: ネストした `<Suspense>` を使うと、README 取得中はページが 2 段階でストリーミングされる（統計等が先に表示され、README が後から差し込まれる）。E2E テスト（Playwright）がこの非同期性を考慮していないと、README 部分の表示待ちをせずにアサーションして flaky になるリスクがある。SD-2 の E2E 実装時は `await expect(...).toBeVisible()` 等で明示的に待つ設計にする必要がある。

---

## 6. NFR-3（クライアント JS を増やさない）との両立

README の取得・パース・サニタイズ・URL 書き換えは**すべてサーバー側**（README 専用の async Server Component、`use client` なし）で完結し、完成した安全な HTML 文字列を `dangerouslySetInnerHTML` で埋め込むだけになる。したがって **1〜2 節でどのライブラリ（`sanitize-html` / `marked` / `react-markdown` 等）を選んでも、クライアントバンドルへの影響はゼロ**（これらはすべて Worker 側のサーバーバンドルにのみ計上される）。NFR-3 は取得形式・サニタイザ選定の判断材料にはならない（争点 C の期待に反して、この観点は他の 5 点ほど決定力を持たない、という結論自体が申し送り事項）。唯一の注意点は `<Suspense>` 境界そのものは React の標準機能でありクライアント JS 追加を意味しない（RSC のストリーミングはサーバー側の仕組み）。

**根拠**: React Server Components の基本仕様（`dangerouslySetInnerHTML` を使う純粋な Server Component はクライアントへ JS を送らない）、`wrangler.jsonc`/`open-next.config.ts` にクライアント最適化に関する特別な追加設定なし。

---

## 他ロールへの申し送り

- **`arch_domain` 宛て**: `RepositoryQueryPort` に `findReadme(name): Promise<ReadmeContent | null>` のような別ポートメソッドを足す設計を推奨（`findDetail` に合成しない）。理由: README は「無くても正常」「404 でも詳細ページ全体は落とさない」という `findDetail` と異なるエラーセマンティクスを持つため、契約を分けたほうが型で表現しやすい。取得元エンドポイントが別（`/readme` vs 本体）である点も合成しない理由になる。`E-2`「データソースは `GET /search/repositories` と `GET /repos/{owner}/{repo}` に限定」という既存宣言は `GET /repos/{owner}/{repo}/readme` を追加するために更新が必要（ACL のスコープ拡張）。
- **`ui_nav` 宛て**: 詳細ページの見出し階層変更（争点 A）と README セクションの見出し（"README" ラベル等）が衝突しないか確認してほしい。README 内の `<h1>`-`<h6>` は今回の許可方針でそのまま透過するため、ページの `h1`（リポジトリ名）と README 内の `h1` が並存し、見出しレベルの整合性（a11y の見出しナビゲーション）に影響する可能性がある。README 内見出しを `+1` レベルシフトする（`h1→h2` 等）処理を検討候補として挙げる。
- **表示量の具体閾値**（4節）は UX 判断が必要なため未確定のまま。
