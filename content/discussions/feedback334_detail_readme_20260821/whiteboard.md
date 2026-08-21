<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 初見フィードバック 6 件（タイトル導線 / 詳細画面の情報量 + README / RSS 撤去 / 出典リンク化）の設計を確定する

- 議題ID: `feedback334_detail_readme_20260821`
- 論点: 飼い主フィードバック（Issue #334）: (F-1) ツールタイトルをクリックしたら未検索状態の画面へ遷移してほしい (F-2) 詳細画面もトップと同じくツールタイトルを含めて同じ挙動にしてほしい (F-3) 詳細画面にも一覧にある概要（description）と最終更新日を追加してほしい（一覧にあるのに詳細にない状態を解消する） (F-4) 詳細画面で README が読めるようにしてほしい (F-5) トップ末尾の RSS 機能は廃止 (F-6) 出典表示の Ecosyste.ms もリンク化してほしい。現行実装: トップ app/[locale]/page.tsx（h1 = messages.home.title 'gem-hunter' のプレーンテキスト・検索フォーム・キーワード未入力時のみ日次ダイジェスト表示）、詳細 app/[locale]/repos/[owner]/[repo]/page.tsx（h1 = repository.fullName の GitHub 外部リンク・LocaleSwitcher・BackLink・4 つの統計 dl のみ。Suspense/loading.tsx は notFound() の 404 を守るため意図的に置いていない）、出典 src/ui/attribution-notice.tsx（{source} は現在プレーンテキスト・{license} だけリンク）、RSS は src/ui/daily-digest.tsx の購読リンク + app/api/digest/rss/route.ts + src/composition/digest-feed.ts + src/infrastructure/feed/digest-rss.ts + e2e/sp-15.spec.ts + docs（prd.md US-33 / user-story-map.md SP-15 / open-questions.md）。制約: クリーンアーキテクチャ依存規則（app は infrastructure を直接 import しない・ARCH-3、GitHub API に触れてよいのは src/infrastructure/github/ の ACL だけ・NFR-16/TR-4、データソースは GET /search/repositories と GET /repos/{owner}/{repo} に限定という E-2 の既存宣言）、NFR-3（クライアント JS を増やさない方針）、Cloudflare Workers（CPU/バンドル制約・INF-2 の低コスト）、NFR-9（内部エラー文言を画面に出さない）、NFR-12/13（a11y・見出し階層・WCAG）、AC-5（詳細が無ければ HTTP 404）、AC-12/NFR-33（private リポジトリを露出しない）、キャッシュは CachePort（ADR 0005）。争点は少なくとも次の 6 つ: A) F-1/F-2 の実装形（ツールタイトルをどこに置くか＝共有ヘッダー component か各ページか / 詳細ページの見出し階層をどうするか＝h1 が 2 つにならないか・repository.fullName の h1 を h2 に落とすと SetDocumentTitle や route announcer や既存 E2E/a11y テストにどう影響するか / リンク先は /{locale} 固定でよいか・検索条件クエリを落とす挙動が SP-7 の『戻る』と矛盾しないか / LocaleSwitcher・BackLink との配置順） B) F-4 README の取得経路（GET /repos/{o}/{r}/readme を ACL に足す＝E-2 のデータソース限定宣言の更新が要る / RepositoryQueryPort に findReadme を足すか別ポートにするか / findDetail に含めて 1 回で返すか別 fetch にするか・404（README 無し）を null にする契約 / private 露出防止と mapper の扱い / キャッシュ TTL / レート枠の消費が増える影響） C) F-4 README のレンダリング方式（Accept: application/vnd.github.html でサーバー側 HTML を貰って sanitize するか / raw Markdown を貰って Markdown レンダラで描画するか / どのライブラリが Workers ランタイムとバンドルサイズに耐えるか / XSS 対策の具体（dangerouslySetInnerHTML を使うなら sanitizer は何か・許可タグ / 相対リンク・相対画像の解決 / iframe・script・onclick 属性の除去） / 表示量の上限（巨大 README の切り詰め）と『GitHub で全文を読む』導線 / 読み込み失敗時に詳細画面全体を壊さない設計 / Suspense を置けない制約（notFound の 404 保護）との両立） D) F-3 の型・表示（RepositoryDetail に description は既にあるが未表示・lastPushedAt が無い→ドメイン型と mapper と既存テストの更新範囲 / 『最終更新』は pushed_at か updated_at か（一覧は lastPushedAt = pushed_at を『最終更新』として出しているので一致させるべきか） / 日付書式は一覧と同じ Intl + Asia/Tokyo でよいか / messages/*.json のキー追加 detail.description / detail.updatedAt の要否） E) F-5 RSS 撤去の範囲（UI リンクだけ消すのか /api/digest/rss ごと消すのか・digest-rss.ts / digest-feed.ts / DAILY_DIGEST_LIMIT の行き先 / e2e/sp-15.spec.ts の該当ケース / prd.md US-33・user-story-map.md SP-15・open-questions.md の記述をどう書き換えるか＝削除ではなく『撤去した事実と理由』を残す規律 / SeenDigest 等の残存機能を壊さないか） F) F-6 出典リンクの行き先（Ecosyste.ms のリンク URL は何が正しいか・https://ecosyste.ms か API ドメインか / attribution-notice.tsx の {source} プレースホルダ分割の実装 / rel・target と a11y 文言（新しいタブで開く旨）を既存の opensInNewTab 文言と揃えるか）。
- 参加者: `ui_nav`, `readme_render`, `arch_domain`, `removal_impact`, `docs_trace`
- 投稿数: 12
- 更新: 2026-08-21T16:53:39+09:00

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

## ラウンド 2

### `ui_nav` — 反論
<sub>2026-08-21T16:48:11+09:00</sub>

## 結論サマリー（round1 への反論・譲歩）

1. **readme_render の「README だけ独立 `<Suspense>`」提案**: 構造自体（詳細確定後・404 判定と分離）には **同意**。ただし提案には **ライブリージョンの記述が一切ない**点を反論する。`role="status"` で包まないと、README のストリーミング後追い挿入は support technology に伝わらない。逆に、home ページの `#results-heading` フォーカス移動パターンをここへ流用するのは **不要（むしろ有害）**、という非対称な結論を出す。
2. **自己点検の結果、round1 の自分の分析には不備があったことを認める（concession）**: E2E テスト（`e2e/sp-9-errors.spec.ts:216`）の書き換えは指摘したが、**`docs/03_design/ui-ux/ui-ux-guidelines.md` §6 自体が「タイトル（`h1`）は GitHub 本体の外部リンクにする」と明記している**ことを見落としていた。これは権威順（ユーザー明示 > **仕様** > テスト > 現行コード）上、テストより上位の「仕様」に当たる。テストだけ直して仕様を放置すると intent-gate 違反になる。§6 の改訂も同一 PR の必須項目として追加する。
3. **README 内見出しの扱い**: readme_render の「+1 レベルシフト」案は **README セクション自体を h2 にする設計と組み合わせると衝突する**ため、+2 シフト（cap は h6）を対案として出す。加えてこれは CSS の見た目ではなく **タグ名そのものの書き換え**（サニタイズ工程での DOM 変換）が必要であることを明確化する。

---

## 1. readme_render の Suspense 提案への rebuttal（a11y 観点）

### 同意する点
readme_render の round1（r01…readme_render_claim.md §5）:
> 「404 でないと確定した**後**（＝ `main` の JSX ツリーの中、既存の統計表示より下）に **README 専用の新しい `<Suspense>` 境界を 1 つだけ追加**」

この「AC-5 の 404 判定を汚さない・詳細確定後にのみストリーミング開始する」という構造は、`app/[locale]/repos/[owner]/[repo]/page.tsx` の既存コメント（`<Suspense>`/`loading.tsx` を意図的に置かない理由）と矛盾せず、自分の round1 で確認した AC-5 の制約とも整合する。ここに異論はない。

### 反論: ライブリージョンの欠落

readme_render の提案には「境界の `fallback` は軽量なスケルトン（テキスト 1〜数行程度。クライアント JS 不要）」とあるだけで、**`role="status"` / `aria-live` への言及が一切ない**。これは `ui-ux-guidelines.md` §7.2 の必須要件

> 「🔴 ライブリージョンは **初期 DOM に空で常設** し、中身を書き換える（要素ごと動的挿入しない）」

および、`app/[locale]/page.tsx` の `#search-status` セクション（自分が round1 で確認済み: `runSearch()` の Promise を `<Suspense>` の**内側**、`role="status" aria-live="polite"` の要素の**内側**に置くパターン）と**同型の問題**を抱えている。

README の Suspense fallback → 解決後コンテンツへの差し替えは、README 専用の非同期 Server Component の**要素ごと動的挿入**（fallback ツリー → 解決済みツリーへの丸ごとスワップ）そのものであり、これを `role="status"` で包まずに素の `<Suspense>` だけで実装すると、home ページの `#search-status` が守っている規律（要素ごと出し入れしない・空の常設要素の中身だけ書き換える）を README ブロックだけ破ることになる。

**提案**: README ブロックも `#search-status` と同じパターンに揃える。具体的には

```
<section id="readme-status" role="status" aria-live="polite" className="sr-only">
  {/* 解決前: 「README を読み込み中」/ 解決後: 空 or 「README を表示しました」等の短い通知 */}
</section>
<Suspense fallback={<ReadmeSkeleton />}>
  <ReadmeSection ... />
</Suspense>
```
のように、**通知用の常設ライブリージョン**（視覚的にはスケルトンが担うので `sr-only` でよい）と、**視覚表示用の `<Suspense>`** を分離する（home ページの「ライブリージョンの文言」と「結果本体」を 2 つの `SearchStatusText` / `SearchBody` に分けている設計 — 自分が round1 冒頭で読んだ `app/[locale]/page.tsx` の `SearchStatusText`/`SearchBody` 二分構造 — と同じ理由づけ）。

### 反論しない・むしろ明確に否定する点: フォーカス移動は不要

`ui-ux-guidelines.md` §7.1 の「結果一覧の見出し（`<h2>`）に `tabIndex={-1}` を付けてフォーカスを移す」パターンは、**`next/link` によるクライアント遷移で `searchParams` だけが変わり、route announcer が沈黙する**ケースへの代償措置（同節冒頭「本節の対象は `next/link` によるクライアント遷移」と明記）。

README のストリーミングは **一覧→詳細という新規ナビゲーション 1 回の中で発生する後続の部分描画**であり、ユーザーが「操作した」結果ではなく「まだ読み込み中の残りが後から届く」だけ。ここへ `tabIndex={-1}` + `focus()` を適用してユーザーの読んでいる位置（例えば統計行や BackLink）を強制的に README 見出しへ飛ばすのは、WCAG 3.2.1/3.2.2（Unexpected Context Change の考え方）に照らして**むしろ有害**。README ブロックは「届いたら polite に通知するだけ・フォーカスは奪わない」のが正しい設計である、と結論づける。

### CLS への申し送り
readme_render の「軽量なスケルトン」は README の実サイズが数行〜数百行まで暴れるため、`ui-ux-guidelines.md` §4.4「4 状態でレイアウトシフトを起こさない」の理想（実データと同一寸法のスケルトン）を満たせない。これは a11y 直接の要件ではなく `NFR-1`/CLS の話だが、フォーカス非移動の設計と合わせて「スケルトンに `min-height` だけ与えて完全一致は狙わない」という妥協ラインを申し送る。

---

## 2. 自己点検: h1 降格は「テストを仕様に合わせて書き換える」行為になっていないか

### 結論: round1 の自分の分析は不完全だった（concession）

round1 で自分は `e2e/sp-9-errors.spec.ts:216`（`getByRole('heading', { level: 1 })`）の**テストコード修正**は指摘したが、権威順（ユーザー明示 > **仕様** > テスト > 現行コード）でテストより上位に立つ**仕様側の明文規定**を見落としていた。

具体的には `docs/03_design/ui-ux/ui-ux-guidelines.md` §6「詳細ページ」に、自分が round1 冒頭で読んで引用した以下の一文がある:

> 「タイトル（`h1`）は GitHub 本体の該当リポジトリページへの外部リンク（新しいタブ）にする（Issue #148）。実装規約は §7.4a」

これは `repository.fullName` を **`h1` にすることを明示的に指定した設計仕様**である。自分の round1 提案（`fullName` を `h2` へ降格）は、この一文と正面から矛盾する。もし「テスト（`sp-9-errors.spec.ts`）だけ `level: 2` に書き換えてコードも変える」という形で進めると、**仕様（§6 の明文）を放置したままテストとコードだけ変えることになり**、`intent-gate-rules.md` が禁じる「仕様と矛盾する挙動をテストだけ直して緑にする」パターンに酷似する（今回はテストを緑にする対象がバグ修正ではなく新機能追加である点は違うが、「仕様の記述を追随させずにテスト・コードだけ変える」という構造は同じ問題を孕む）。

### 対応方針（修正した結論）
- `ui-ux-guidelines.md` §6 の当該一文を、本フィードバック対応の一部として**明示的に改訂**する（例:「タイトル（`h2`）は GitHub 本体の該当リポジトリページへの外部リンクにする。ページ全体の `h1` はツールタイトル（共有ヘッダー）が担う（Issue #334 F-1/F-2）」のような書き換え）。これは `docs_trace` の担当領域と重なるため、**round1 で `docs_trace` が指摘した「矛盾する記述」リストに §6 が漏れていたことも合わせて申し送る**（`docs_trace` の round1 は `prd.md`/`user-story-map.md` の矛盾は広く洗い出しているが、`ui-ux-guidelines.md` §6 の h1 規定との矛盾は挙げていなかった）。
- 順序としては「§6 改訂 → コード変更（`repository-detail.tsx` の `h1→h2`、`repos/.../page.tsx` エラー分岐の `h1→h2`、`not-found.tsx` の `h1→h2`）→ 3 つの E2E（`sp-9-errors.spec.ts:216` の level 修正、必要なら `sp-6-notfound.spec.ts` は level 未検証なので変更不要と round1 で確認済み）→ header 新設」という**仕様が先、テスト・コードが追随**という順で PR を組む必要がある、と修正する。

### それでも破綻しないという結論自体は維持
- §6 の改訂を伴う前提であれば、round1 で洗い出した 3 箇所の `h1`（`repository-detail.tsx`・`repos/.../page.tsx` エラー分岐・`not-found.tsx`）を揃えて `h2` にするという実装方針そのものは変わらない。`SetDocumentTitle` / route announcer への非影響、`e2e/sp-3.spec.ts` 等 level 未指定テストが無傷、という round1 の他の結論も再確認して撤回の必要はない。

---

## 3. README 内見出しの階層処理（readme_render への回答・a11y 観点の結論）

readme_render の round1「他ロールへの申し送り」（§末尾）:
> 「README 内見出しを `+1` レベルシフトする（`h1→h2` 等）処理を検討候補として挙げる」

### 結論: +1 ではなく +2、かつ「見た目」ではなく「タグ名そのもの」の書き換えが必要

- ページの見出し構造は（§1・§2 の結論を反映すると）**`h1`（ツールタイトル・layout 共有 header）→ `h2`（`repository.fullName`）→ `h2`（README セクション自体の見出し。例: `messages.detail.readme` = "README"、`home.resultsHeading`/`home.digest.heading` と同じ「セクション見出しは h2」という既存パターンに揃える）** という構成になる。
- ここで README セクション自体の見出しが `h2` である以上、README 本文の見出しをそのまま `+1` シフトすると `h1→h2` になり、**セクション見出し自身と同じ `h2` が並んでしまう**（README の元 `h1`＝多くの場合プロジェクト名の見出しが、"README" というセクション見出しの兄弟ではなく本来「子」であるべきなのに同列になる）。これは見出しナビゲーションで「README」という区切りの直後にもう一つ `h2` が来る形になり、README の内容がどこまでが「README セクションの一部」かの階層情報が失われる。
- **対案**: README セクション見出しを `h2` とし、README 本文の見出しは `+2` シフトする（`h1→h3`、`h2→h4`、`h3→h5`、`h4→h5` or `h6` に丸める、`h5`/`h6` は `h6` に固定=cap）。これにより「`h2`(README) の子として `h3` から始まる」という正しい入れ子になる。README がさらに深い階層（`h4`〜`h6`）を多用している場合は `h6` で頭打ちにする実務上の妥協でよい（HTML に `h7` は無いため）。
- **実装上の注意（readme_render 自身の許可方針への補足）**: readme_render は `sanitize-html` の許可タグに「見出し `h1`-`h6`（`id` 許可・アンカー整合のため）」を挙げているが、レベルシフトは **CSS のフォントサイズ調整では意味がない**（アクセシブルな見出しレベルは要素タグ名 or `aria-level` で決まる。`class="text-lg"` 等を当てても支援技術には伝わらない）。サニタイズ工程（`transformTags`）の中で **タグ名自体を書き換える**（例: 入力 `<h1 id="...">` → 出力 `<h3 id="...">`。`id` はアンカー解決のため保持）処理を追加する必要がある、という実装制約として申し送る。
- 併せて README ブロック全体を `<section aria-labelledby="readme-heading">`（`readme-heading` は "README" という `h2` の `id`）で包み、README 本文がページの他の部分（統計 `dl` 等）と誤って同一領域と誤認されないようリージョン境界を明示することを推奨する。

### 反対されうる点
- +2 シフト・`h6` 頭打ちは、6 階層を超えてネストする README（実務上ほぼ無いが）では複数の異なる見出しレベルが同じ `h6` に潰れ、見出しナビゲーション上は区別が付かなくなる。これは実害が小さいと判断して許容するが、readme_render が round1 で示した「実測で確認していない」領域（画像付き README 同様、深いネストの README での実機確認）と合わせて、実装時に実在の README で目視確認することを推奨する。

### `readme_render` — 反論
<sub>2026-08-21T16:48:37+09:00</sub>

## 対 `arch_domain`: 「独立 Suspense」は逐次ゲートと矛盾しない（表現は譲歩・設計は維持）

### 譲歩する点
round1 の「独立した `<Suspense>` で並行ストリーミング」という書き方は誤読を招く表現だった。「並行」が指していたのは **レスポンスのストリーミング**（クライアントへ先に統計を流し、README を後から差し込む）であって、**GitHub への fetch リクエストの発火タイミング**ではない。`Promise.all` で `findDetail` と `findReadme` を同時に飛ばす設計は一度も意図しておらず、そう読めた点は撤回する。

### 反論（本質は非対立）
RSC の非同期コンポーネントは、親の同期コード（`const detail = await getRepositoryDetailUseCase(...)`; `if (detail === null) notFound()`）が完了して初めて描画が進み、その後にツリーを下って `<Suspense>` 配下の非同期子コンポーネント（README セクション）が**呼び出される**。つまり:

```
findDetail() 完了 → notFound() 判定 → (ここまでは従来どおり同期)
  → JSX 描画開始 → <Suspense> 配下の ReadmeSection が呼ばれる
    → 内部で getRepositoryReadmeUseCase()（= arch_domain 案の findDetail→findReadme ゲート）が実行される
```

`findReadme` の発火は **`findDetail` の解決より論理的に後**であり、`arch_domain` が §2/§3 で示した「detail 確定後の逐次」「usecase 層でのゲート（`getRepositoryReadmeUseCase` が内部で `findDetail` を再度呼びキャッシュ HIT する）」設計を **そのまま呼び出す側**として使う。private 露出のリスクは増えない。

Suspense を使う実利は「CPU/レイテンシの主張」を変えない。むしろ逐次だからこそ効く: 詳細取得 + README 取得の 2 回のネットワーク往復（`arch_domain` §6 が確認済みの「最大 2 リクエスト」）を**両方とも初回描画のブロッキングパスに乗せない**ことが目的。README 取得（キャッシュ MISS 時は GitHub までの RTT + サニタイズ時間）が仮に遅延・失敗しても、Star/Watcher/Fork/Issue 等の統計は先に確定して届く。これは 1 節の CPU 予算論（cpu_ms:50 の中でサニタイズを軽くする）とは別軸（レイテンシ論）であり、両立する。

### 結論（採用する実装形）
```tsx
const detail = await getRepositoryDetailUseCase(token)({ owner, repo })
if (detail === null) notFound()
return (
  <main>
    {/* ...既存の統計表示... */}
    <Suspense fallback={<ReadmeSkeleton />}>
      <ReadmeSection owner={owner} repo={repo} token={token} />
    </Suspense>
  </main>
)
```
`ReadmeSection`（async Server Component）の内部で `arch_domain` 提案の `getRepositoryReadmeUseCase`（`findDetail` 再ゲート → `findReadme`）を呼ぶ。**新しい fetch 順序は導入しない**。round1 で私が示した「try/catch で握ってインライン代替表示にする」（AC-5/NFR-9 の話）は、`arch_domain` §「404 契約との両立」の `app/` 層 catch 方針と同一なので、実装箇所は `ReadmeSection` 内の catch に一本化する。

---

## 対 `coordinator`（Q2）: `sanitize-html` のバンドル/CPU再点検

### バンドルサイズ
`package.json` の既存依存（`class-variance-authority` `clsx` `jose` `lucide-react` `next` `radix-ui` `react` `react-dom` `shadcn` `tailwind-merge` `tw-animate-css` `zod`）に Markdown/HTML 処理系は **1 つも無い**（純新規追加）。`cloudflare-infrastructure.md` の Worker バンドル上限は **3 MB（gzip）**。`sanitize-html` の bundlephobia 実測 gzip 56.2 KB は上限の **約 1.9%**。既存依存を実測していない（未ビルド）ため相対比較の絶対値は出せないが、桁で見て致命的な圧迫にはならない。

**ただし round1 の断定は言い過ぎだった点を認める**: 「収まる根拠」を bundlephobia の静的パッケージサイズだけで語るのは、実際の Worker バンドル（tree-shaking・重複排除・OpenNext のバンドラ挙動を経た後の値）を測っていない以上、**推定であって実測ではない**。本タスクの制約（依存パッケージをインストールしない）上、このラウンドで実測はできない。`cloudflare-infrastructure.md` §「計測 2」が既に手順を規定している（`npx opennextjs-cloudflare build && gzip -c .open-next/worker.js | wc -c`）ので、**実装 PR ではこのコマンドを `sanitize-html` 追加前後で実行し差分を PR に貼ることを完了条件に含めるべき**、と申し送る（自分では実行しない＝今ラウンドの制約順守）。

### htmlparser2 の Node API 依存
`htmlparser2`（`sanitize-html` の内部パーサ）はゼロから書かれた純 JS のストリーミングパーサで、`fs`/`http` 等の Node 組み込みモジュールに依存しない設計が公知（ブラウザ向けバンドルにも広く採用されている実績が根拠）。Workers（DOM 非搭載・`nodejs_compat` フラグのみ）でも動作する可能性が高い。**一方 `sanitize-html` 本体は `postcss` にも依存する**（`style` 属性のパース用）。`postcss` のコア自体は `fs` 非依存だが、**未検証**である点は正直に認める。

対策としてラウンド1で既に提案した `parseStyleAttributes: false` を再確認: これは**実行時の CPU コスト**（postcss によるパース＋フィルタ処理）を確実にスキップする（Context7 で確認済みのコード分岐: `parseStyleAttributes` が false なら `style` 属性はパースされず即除去される）。ただし CJS の `require('postcss')` 自体がモジュールとしてバンドルに含まれるかどうか（tree-shaking で削れるか）は bundlephobia の数値には反映されておらず未確認。**バンドルサイズは実装時の実測が必要、CPU コストは `parseStyleAttributes: false` で理論的に担保できる**、と切り分けて結論づける。

### 切り詰めの位置（round1 の「安全な境界で切る」を具体化）
**サニタイズ処理と同一パスの中で行う。サニタイズ前の生 HTML 文字列への単純な文字数カット、サニタイズ後の文字列への再カット、どちらも採用しない。**
- サニタイズ前カット: タグの途中で切れると、寛容なパーサ（`htmlparser2`）が壊れたタグをテキストとして誤解釈し、意図しないタグ境界のズレやリテラル `<` 文字の露出を招きうる（XSS 実害は低いが表示崩れと構造破壊のリスクが残る）。
- サニタイズ後カット: 一度サニタイザが構築した構造情報（開いているタグのスタック）を文字列に戻してから再度文字数で切ると、同じ問題が再発する（二度手間かつ危険）。
- 採用: `sanitize-html` の変換コールバック（`transformTags` / `exclusiveFilter` 相当の仕組み）でテキスト長を累積カウントし、閾値を超えた時点でそれ以降のノード追加を止める。パーサは入力終端で開いたままのタグを自動的に閉じる（HTML パースの標準的な振る舞い）ため、**常に整形式（well-formed）な HTML が出力される**。この処理は 6 節（見出し降格）のタグ変換と同じ 1 パスに乗せられる。

---

## 対 `ui_nav`（Q3・先回り回答）: README 内見出しの降格と `id` の扱い

### 結論
1. **README 内の全見出し（h1〜h6）を固定オフセットで降格する。** 具体的な段数は「ページ上でこの README セクションに割り当てられる見出しレベル + 1」から始まる**相対ルール**として実装する（絶対値をハードコードしない）。理由: `ui_nav` の round1 案（header 側 h1 = ツールタイトル、詳細ページ h2 = `repository.fullName`）はラウンド1時点でまだ確定していない（争点 A は他ロールとの合意形成中）。仮に header h1 / 詳細 h2 が確定するなら、README セクション自体に見出しラベル（例: `<h3>{labels.readme}</h3>`）を新設し、README 内部の最上位見出し（通常 h1）が **h4** から始まるよう +3 オフセットで変換する。h4 を超えて h5/h6 に達したものは HTML の下限である **h6 でクランプ**する（WAI の見出しガイドで許容される「深いネストは最下層で丸める」対応であり、飛び番号（skip）ではなく「詰まる」方向なので `heading-order` の一般的な検査観点には抵触しない）。
2. **`id="user-content-{slug}"` はそのまま保持する。** タグ名（`h1`→`h4` 等）だけを書き換え、`id` 属性の値は変更しない。round1 で結論づけた「`#{slug}` → `#user-content-{slug}` へのアンカー書き換え」ロジックは見出しの `id` を参照するだけなので、タグ名変換と完全に独立して成立する（互いに変更を要求しない）。
3. **実装は 1 パスで**: 4 節（サニタイズ+URL書き換え）・上記の切り詰め・見出し降格は、いずれも同じ HTML パース結果を 1 回だけ走査する変換の中に同居させる（`sanitize-html` の `transformTags` に `h1`〜`h6` それぞれのリネーム関数を登録し、見出し以外の `href`/`src` 書き換え・切り詰めカウントと同じコールバック群でまとめて処理する）。パースを複数回走らせない設計は cpu_ms:50 予算の観点でも重要（1節・round1 で既に述べた通り）。

### 反対されうる点
「README 独自の h1 を意味的に h4 まで下げると、原著者が意図した『最重要見出し』という重みが視覚的にも失われるのでは」という指摘はありうる。これは見出し**レベル**（アクセシビリティツリー上の意味）と見た目のフォントサイズを分離すれば解決できる（`.readme-content h4 { font-size: ... }` のようにセマンティクスとビジュアルを独立させる）。CSS 側の具体は表示担当（`ui_nav`）の裁量に委ねる。

### `removal_impact` — 反論
<sub>2026-08-21T16:48:49+09:00</sub>

# removal_impact r2: 4 論点への応答

## 論点1（`DAILY_DIGEST_LIMIT` の移設先）: 譲歩する。`page.tsx` 案を撤回し `src/composition/` 残留へ変更

**譲歩**: round1 で「消費者が 1 箇所（`page.tsx`）だけになるので YAGNI でローカル定数化」と書いたのは
誤り。`docs/03_design/architecture/application-architecture.md` 55〜56 行目・193 行目を確認した:

> `app/`（Frameworks & Drivers）は **「薄く保つ」**。`page.tsx` は「composition root からユース
> ケースを取り、結果を `src/ui/` に渡すだけ。**ロジックを書かない**」
> `Composition`（`src/composition/`）は「**唯一、実装をポートへ束ねてよい場所**」

`DAILY_DIGEST_LIMIT` はマジックナンバーではなく `ADR 0014` §2.1 が定めた「既定 5 件」という
**ドメイン上の決定値**であり、これを `app/page.tsx` に直書きすると「薄く保つ」規律に反する
（数値がロジックか否かの線引きは別として、`app/` に散らばった定数は次に値を変えるとき `app/`
まで見に行かないと気づけなくなる＝ composition root に集約する意義そのものを損なう）。

**修正案**: `digest-feed.ts` を削除するのではなく、**RSS 色の強いファイル名 `digest-feed.ts` を
`src/composition/digest.ts` へリネームし、`DAILY_DIGEST_LIMIT` だけを残して RSS 関数
（`renderDailyDigestRss`）を削除する**。あるいは既存の `src/composition/container.ts`
（`getDailyDigestUseCase` の定義元）へ `DAILY_DIGEST_LIMIT` を統合してもよい（`arch_domain` の
判断に委ねる。ARCH 面の最終決定権は `arch_domain` にあると認識している）。

いずれにせよ **`app/[locale]/page.tsx` へのインライン化は撤回**する。`app/[locale]/page.tsx`
6 行目の import 文はファイル名変更（`digest-feed` → `digest`、または `container` へ統合）に
合わせて import 元パスだけを書き換える。

## 論点2（`DigestMeta.sourceUrl` の型必須化と既存 JSON との整合）: 反論（「壊れる」は誤り）

**結論**: `sourceUrl` は `source` / `license` / `sourceLicenseUrl` / `generatedAt` と同じく
**`DigestMeta` の必須フィールドにすべき**。「型必須にすると既存データで壊れる」という懸念は
成立しない。理由は `static-gem-digest.ts` の既存設計そのものにある。

`parseMeta()`（同ファイル 108〜119 行目）は **JSON 側の `meta` を `Partial<Record<keyof
DigestMeta, unknown>>` として読み、フィールド単位で `nonEmptyStringOr(source.X, FALLBACK_META.X,
...)` / `httpUrlOr(...)` によりフォールバックする**。これは「JSON 入力の型」と「ドメイン出力
（`DigestMeta`）の型」を意図的に分離した設計で、**入力側が未知のフィールドを持たなくても出力側
は必須フィールドを満たせる**（既に `generatedAt` が「壊れていれば空文字にフォールバック」という
形でこのパターンを実証済み）。`public/data/daily-digest.json`（本番データ）に `sourceUrl` が
まだ無くても、`httpUrlOr(source.sourceUrl, FALLBACK_META.sourceUrl)` は `source.sourceUrl ===
undefined` → `FALLBACK_META.sourceUrl`（`'https://ecosyste.ms/'`）へ自動的に倒れる。**ランタイム
は壊れない**。

**実際に「壊れる」のは TypeScript の静的型チェックであり、対象は `DigestMeta` 型を直接組み立てて
いるテストフィクスチャ 3 ファイルに限られる**（`grep -rln "sourceLicenseUrl"` で洗い出し済み。
RSS 側の 2 ファイル ─ `digest-rss.test.ts` / `route.test.ts` ─ は F-5 で削除するため対象外）:

1. `src/infrastructure/platform/static-gem-digest.test.ts`
2. `src/ui/daily-digest.test.tsx`
3. `src/ui/attribution-notice.test.tsx`
4. `src/usecases/get-daily-digest.test.ts`

この 4 ファイルの `DigestMeta` リテラルに `sourceUrl: 'https://ecosyste.ms/'`（またはテスト
専用ダミー値）を 1 行ずつ追加すれば `tsc --noEmit` は通る。round1 の「3 箇所」という見積もりは
過小だった点は訂正する（テスト込みで実質 6 ファイル: 型定義 1・`static-gem-digest.ts` 内 2 箇所・
テスト 4 ファイル）。

**「UI 側に定数として持つ」対案との優劣**: `source` / `license` / `sourceLicenseUrl` が既に
`DigestMeta`（JSON 駆動）として流れており、`sourceUrl` だけを UI 定数（ハードコード）にすると
**帰属表示 4 項目のうち 1 つだけ経路が異質**になり非対称になる。`static-gem-digest.ts` 51 行目の
既存コメント「バッチが書き込む出典は常に Ecosyste.ms / CC BY-SA 4.0 で固定」は「値が今は固定」
という運用上の事実を述べているだけで、**「だから型から外してよい」という設計判断ではない**
（`D-29` の帰属表示義務は「値が変わりうる」ことを前提に JSON 駆動にしている）。よって
`DigestMeta` 拡張を推奨する。**本番 JSON へ実際に `sourceUrl` を書き込む対応（`tools/
generate_gem_digest.mjs`）は `FALLBACK_META` が完全に代替するため本 PR のブロッカーではない**
（fast-follow の別 Issue でよい。理由は §論点3 で述べる仕分け基準と同じ）。

## 論点3（`docs_trace` 指摘の仕分け: 本 PR で直す vs 別 Issue）

自分（`removal_impact`）のレンズ（F-5/F-6・ドキュメント整合）から判断できる範囲に限定して仕分ける。

### 本 PR で直す（F-5/F-6 に直接起因する、または自分が既に解決策を持つもの）

- **矛盾4（`SP-15`/`US-33` RSS 撤去の矛盾）**: round1 で `D-34` 起票案 + `user-story-map.md` /
  `prd.md` / `docs/adr/0014-...md` の具体的な書き換え箇所を既に提示済み。`docs_trace` が
  「最優先」と位置づけた点と一致する。**`docs_trace` は重複して同じ箇所を調査しなくてよい**
  （round1 の自分の投稿をそのまま採用してよい）。
- **追記5（Ecosyste.ms データ範囲と CC BY-SA 4.0 帰属表示ルールの詳細化・`E-25`/`GR-6`）**:
  F-6（`sourceUrl` 追加）に直接起因するため本 PR の範囲内。ただし `docs_trace` が示唆する
  「新しい `open-questions.md` エントリを起こす」規模の話ではなく、**`user-story-map.md` 185 行目
  の既存の 1 行（「データ出典の明記（CC BY-SA 4.0）」）に「出典元 URL（`sourceUrl`）へのリンクも
  含む」を追記する程度で足りる**（新規決定エントリが要るほどの分岐ではない ─ 論点2で述べた通り
  リンク先は WebFetch で確認済みの `https://ecosyste.ms/` に一意に決まっており、選択肢が割れて
  いない）。

### 別 Issue へ切り出す（本 PR のスコープ外・CP-1「起票して前に進める」対象）

- **紛らわしい箇所3（`SP-14` の `D-33` 記述が長く、撤去の永続性が不明）**: これは **F-5（RSS
  撤去の今回の議題）とは無関係**。`D-33` は `SP-16`（Gem Index 順ソート）という**別の過去の撤去**
  についての記述であり、F-1〜F-6 のどれにも属さない。しかも `open-questions.md` の `D-33` 本文
  末尾には既に 🔵 **「再導入の条件」**（候補プールが npm 以外を含み一般語 30% 以上で Gem Index が
  付くこと、という客観基準）が明記されている ─ **永続性は既に文書化済みで、`docs_trace` が
  「不明」と感じたのは `user-story-map.md` `SP-14` 側の長い注記だけを読み `open-questions.md`
  `D-33` 本文（再導入条件を含む全文）まで遡らなかったためと推測する**。対応としては
  `user-story-map.md` `SP-14` の当該注記の末尾に「詳細・再導入条件は `open-questions.md` `D-33`
  参照」の 1 行ポインタを足す程度で解決するが、**F-5/F-6 のどの変更ファイルとも重ならない**ため、
  本 PR に混ぜず別 Issue（`type:docs`・`sp:1`）として起票することを推奨する（CLAUDE.md「スコープ
  外の改善は別 Issue を立ててから」）。
- **紛らわしい箇所1・矛盾2/3（`FR-4`/`SP-6` の項目数「7 項目」・最終更新日の出典）**: F-3 起因
  であり自分のレンズ外。`arch_domain` が `pushed_at` を最終更新日の答えとして既に確定させて
  いるので、`docs_trace` はその決定を反映するだけでよく、これは F-3 の一部として **本 PR 内**で
  直すのが妥当（新規 Issue にする理由がない ─ F-3 の変更が直接その数字を古くする）。ただし
  これは `arch_domain` / `ui_nav` のレンズの判断が優先されるべきで、自分から強く主張はしない。

## 論点4（`prd.md` §4.3 データソース限定記述の書き換え方 ─ F-4 との整合）

F-4（README 追加）は **撤去ではなく追加**なので、round1・論点1 で示した `D-34` の「打ち消し線
＋ 🔴 撤去注記」パターンをそのまま使うのは誤り（あれは削除専用の記法）。`prd.md` を通読すると、
**追加の場合は既に別の記法が採用されている**: 103 行目「`D-27` により `M-5`（Phase 2 着手判断
ゲート）を通過し、実装対象へ格上げ」・205 行目「🔵 静的な日次ダイジェストと RSS（`AR-9`/`AR-10`・
§11）は対象内」のように、**追加・確定した決定には 🔵（青丸）の追記注記を使い、本文の打ち消し線は
使わない**（🔴 は撤去、🔵 は追加確定、という色分けが `prd.md` 内で既に一貫している）。

**提案（`docs_trace` / `arch_domain` 側の担当箇所への申し送り）**: `prd.md` 278〜279 行目
「データソースは `GET /search/repositories` と `GET /repos/{owner}/{repo}` に限定する」の一文
そのもの（「限定する」という設計思想 = `E-2`/`ARCH-3` の ACL 隔離原則）は**削除・打ち消し線に
しない**（この文の役割は「GitHub API に触れてよいのは ACL だけ」という制約の表明であり、
エンドポイントの内訳は実装対象が増えるたびに更新されるリストに過ぎない）。表現としては:

> データソースは以下のエンドポイントに限定する（`E-2`）: `GET /search/repositories` /
> `GET /repos/{owner}/{repo}` / 🔵 `GET /repos/{owner}/{repo}/readme`（`F-4`・`D-3?` で追加）

のように **列挙を横に増やし、追加分だけ 🔵 マークを付ける**（「限定する」という文自体は残る
＝ 制約は変わらず対象範囲だけが広がったことが一目でわかる）。これは自分が提案した `D-34` の
打ち消し線パターンと**視覚的に対をなす**（🔴＝消えた・🔵＝増えた、を読者が色だけで区別できる）
ため、両方のパターンが同じ PR 内に混在しても迷わない。最終的な文言確定は `README` 取得の設計を
持つ `arch_domain` / `readme_render` に委ねる。

### `arch_domain` — 反論
<sub>2026-08-21T16:50:10+09:00</sub>

## 1. `readme_render` の Suspense 案 vs 自分の「逐次待機」案 — 一部譲歩し、折衷案を提示する

**譲歩する点**: 「本ページには `<Suspense>` を一切置けない」という round1 の前提は**言い過ぎだった**。既存コメントが禁じているのは「`notFound()` の判定材料（`findDetail`）を `Suspense` で包むこと」であり、**404 判定が同期 `await` で確定した後に、その下流へ新しい `<Suspense>` 境界を足すこと自体は禁止対象ではない**（`readme_render` が引用した Next.js 公式 docs の該当文言 "Place `notFound()` before those boundaries" も「境界より前に置け」であって「境界を作るな」ではない）。よって README を Suspense でストリーミングするという方向性には同意する。

**譲歩しない点（真の対立点）**: `readme_render` 案（README コンポーネント内部で `getRepositoryReadmeUseCase` を呼ぶ）をそのまま採ると、**そのフェッチ開始タイミングが `findDetail` のキャッシュ書き込み完了と無関係になる**。`getRepositoryReadmeUseCase` は round1 で設計した通り内部で `repos.findDetail(name)`（private ゲート）を再度呼ぶが、これはページ本体の `findDetail` 呼び出しとは**別インスタンスの `CachingRepositoryQuery`**（`container.ts` の `makeCachingRepositoryQuery()` は呼び出しごとに new）であり、`inFlightSearch`/`inFlightDetail` の single-flight マップは共有されない（`sharedCache` という Map の中身は共有されるが、書き込みタイミングに依存する）。README 側の `findDetail` 呼び出しが**ページ本体の `await` より先か同時に**走ると、`sharedCache.get()` が両方 MISS になり得ることは round1 で指摘済みで、Suspense 化してもこのレースは消えない（むしろ Suspense はレンダリングの遅延評価を許すため、いつ子コンポーネントの関数本体が実行されるかは実装依存で、「ページ本体の `await` より後」を保証しない）。

**折衷案（提案）**: 「README の *fetch 開始* はページ本体の `findDetail` が確定した**直後**（キャッシュ書き込み後）」「README の *await* は Suspense 境界の子コンポーネントに委ねてストリーミング」を両立させる。

```ts
// page.tsx（Server Component）
const detail = await getRepositoryDetailUseCase(token)({ owner, repo })
if (detail === null) notFound()
// ↓ここで start するが await しない（Promise を子へ渡すだけ）。
//   sharedCache への findDetail 書き込みは直前の await で完了済みなので、
//   ReadmeSection 内の getRepositoryReadmeUseCase 内部 findDetail はキャッシュ HIT になる。
const readmePromise = getRepositoryReadmeUseCase(token)({ owner, repo })

return (
  <>
    {/* ...FR-4 の統計・description・lastPushedAt（同期確定済み detail から描画）... */}
    <Suspense fallback={<ReadmeSkeleton />}>
      <ReadmeSection readmePromise={readmePromise} />
    </Suspense>
  </>
)

// ReadmeSection.tsx（async Server Component）
async function ReadmeSection({ readmePromise }: { readmePromise: Promise<string | null> }) {
  try {
    const readme = await readmePromise
    if (readme === null) return <ReadmeUnavailable htmlUrl={...} />
    return <ReadmeBody html={sanitizeAndRewrite(readme)} />
  } catch {
    return <ReadmeUnavailable htmlUrl={...} /> // NFR-9: 内部エラー文言は出さない
  }
}
```

これは `readme_render` 案（Suspense・try/catch でページ全体を落とさない・README 不在は正常系）を**そのまま維持**しつつ、自分の懸念（キャッシュ競合・private ゲートの再検証を無駄打ちしない）を解消する。両者の対立点は「Suspense を使うか」ではなく「fetch を*いつ*開始するか」だったと整理できる。`readme_render` 側でこの `readmePromise` の受け渡しパターンを `ReadmeSection` の実装に採用してもらえるか確認したい。

---

## 2. README の HTML キャッシュ設計（`readme_render` の HTML 方式決定を受けて）

`readme_render` が「GitHub 側レンダリング済み HTML を採用し、サニタイズ・相対リンク解決・`target=_blank` 付与・切り詰めは全てサーバー側で行う」と決定したことを前提に、round1 の「`findReadme` の戻り値をキャッシュする」という設計を**2 層に分割する形へ修正する**（round1 は「素の文字列をキャッシュする」としか書いておらず、どの段階の文字列かを詰めていなかった不備を認める）。

### 何をキャッシュすべきか: 生 HTML（GitHub 由来）か、加工済み HTML（サニタイズ後）か

**加工済み（サニタイズ・相対リンク解決・`target=_blank` 付与・切り詰め済み）HTML を丸ごとキャッシュすべき**であり、GitHub から取得した生 HTML だけをキャッシュして毎回サニタイズし直すのは不十分——`readme_render` 自身が HTML 方式を選んだ決め手は「Workers の `cpu_ms: 50` 予算」であり、キャッシュ HIT 時にも毎回サニタイズ・URL 書き換え・切り詰めの CPU を払い続けるのでは、この判断根拠（CPU 予算の節約）がキャッシュ HIT 時には効かないままになる。ネットワーク往復だけでなく **CPU コストもキャッシュで吸収すべき**。

### しかしこれは `RepositoryQueryPort`/`CachingRepositoryQuery` の中に置いてはいけない（層の逸脱）

サニタイズ後の HTML は `target="_blank" rel="noopener noreferrer"` や `id="user-content-..."` の書き換え済みアンカーなど、**表示（プレゼンテーション）の都合そのもの**を含む文字列である。これを `src/infrastructure/github/`（GitHub 語彙をドメインへ持ち込まない ACL・`application-architecture.md` §3）の戻り値としてキャッシュに乗せると、ACL が「ドメインの生データ」ではなく「UI 都合の加工物」を保持することになり、`W-1`（データ源を差し替えられる）が崩れる（README のレンダリング方針を変える＝ HTML 方式から raw Markdown 方式へ乗り換える、といった将来の変更が ACL のキャッシュ形式ごと巻き添えになる）。

**結論（2 層キャッシュ）**:

| 層 | キャッシュ対象 | 置き場所 | 名前空間・キー | TTL |
|---|---|---|---|---|
| Tier 1（ACL/ドメイン） | GitHub から取得した**生 HTML**（サニタイズ前・GitHub 由来のまま） | `CachingRepositoryQuery.findReadme`（round1 の設計のまま） | `readme:v2:{owner}/{name}`（`cache-key.ts` に追加） | `TTL_DETAIL_SECONDS` を再利用（round1 の主張を維持） |
| Tier 2（表示） | **サニタイズ・URL 書き換え・切り詰め済みの最終 HTML** | `src/composition/` 側に新規の薄いラッパー関数（例 `getRenderedReadmeUseCase` 相当。`CachingRepositoryQuery` とは別クラス）が `CachePort`（`sharedCache`）を直接使う | 別名前空間 `readme-html:v1:{owner}/{name}`（レンダリング方式が変われば独立してバージョンを上げられるよう、Tier 1 とは別のバージョン変数にする） | 同じく `TTL_DETAIL_SECONDS` を暫定値として流用してよい（積極的に変える理由が今は無い） |

Tier 2 は `application-architecture.md` §5「`use cache` はユースケース・ドメインから直接触らない。キャッシュは `CachePort` 越しに扱う」の原則を守りつつ、**`CachePort` の再利用先を `RepositoryQueryPort` の外に置く**（`RateLimitPort` が `src/composition/rate-limit.ts` の `enforceSearchRateLimit()` として独立配線されている前例と同じパターン）。これは Tier 2 の実装詳細（具体的な関数名・呼び出し位置）そのものは `readme_render`／実装セッションの判断に委ねるが、**「サニタイズ後の文字列を `RepositoryQueryPort` の戻り値としてキャッシュしない」という層の境界だけは譲れない**。

### レート枠消費の吸収度合い

Tier 1 のキャッシュだけで GitHub API 呼び出し（＝レート枠消費）は完全に吸収される（Tier 2 は CPU コストの追加吸収であり、レート枠には無関係）。round1 の見積もり（詳細表示 1 回あたり最大 2 リクエスト、キャッシュ温まっていれば 0）は変更なし。

---

## 3. `removal_impact` の `DAILY_DIGEST_LIMIT` 移設案への異論

`removal_impact` は `digest-feed.ts` 削除に伴い `DAILY_DIGEST_LIMIT` を `app/[locale]/page.tsx` 内のローカル定数へ移すと提案しているが、**層の観点でこれは適切でない**。

`page.tsx:280` での実際の使われ方を確認すると、`DAILY_DIGEST_LIMIT` は `getDailyDigestUseCase()({ seed: dateSeed, limit: DAILY_DIGEST_LIMIT })` という**ユースケース呼び出しの引数**である。`get-daily-digest.ts` の usecase 自体は `limit` を汎用パラメータとして受け取る設計（テストでは 5 以外の値も使われている想定）であり、「5」という具体値は **`ADR 0014` §2.1 が定めた製品判断**（「既定 5 件」）であって、ページのレンダリング詳細ではない。

`application-architecture.md` §1.2 は `app/` の責務を「ルーティング・Server Component・Route Handler・Server Action。**薄く保つ**」とし、§7 の完了条件に「`app/` にビジネスロジックが無い（ユースケース呼び出しと表示の受け渡しのみ）」を明記している。ユースケースへ渡す製品判断値（ADR に紐づく既定件数）を `app/` にベタ書きするのは、この「薄く保つ」に反する——**ちょうど `TTL_SEARCH_SECONDS` / `TTL_DETAIL_SECONDS` を `app/` ではなく `src/composition/container.ts` に置いている既存の前例と対称**である。あの 2 つも「暫定値」というコメント付きの製品チューニング定数であり、`page.tsx` ではなく composition root に置かれている。`DAILY_DIGEST_LIMIT` も同じ性質の値であり、同じ置き場所にすべき。

**推奨**: `DAILY_DIGEST_LIMIT` は `src/composition/container.ts`（`getDailyDigestUseCase` のすぐ近く）へ移す。`page.tsx` は `@/src/composition/digest-feed` の代わりに `@/src/composition/container` から import するだけで済み、`removal_impact` が懸念する「1 箇所しか使わないファイルを残す YAGNI 違反」も同時に解消する（`digest-feed.ts` はファイルごと削除してよい、という結論自体には同意する）。`app/` へ落とす必然性は無い。

反対されうる点: 「`container.ts` は §2.1 で『実装をポートへ束ねる』場所と定義されており、`DAILY_DIGEST_LIMIT` はポート実装の束ねではない」という指摘はあり得る。ただし `TTL_SEARCH_SECONDS`/`TTL_DETAIL_SECONDS` が既に同じ性質の「非・束ね」定数として同ファイルに存在する前例があるため、本 PR で新たに逸脱を作るわけではない。

---

## 4. 自己批判の再点検: `findReadme` を既存 `RepositoryQueryPort` に足す判断は正しいか

round1 の決定を維持するが、検討過程を明記する。

- **`readme_render` の申し送りとの整合**: `readme_render` も「`RepositoryQueryPort` に `findReadme(name)` のような別ポート**メソッド**を足す設計を推奨（`findDetail` に合成しない）」と述べており、文言は「別ポート」だが実体は「既存ポートへの追加メソッド」で round1 の自分の結論と一致する（新規インターフェースを切れとは言っていない）。両者が独立に同じ結論へ収束したのは、判断の妥当性を補強する材料と見る。
- **検討して却下した対案**: ①「README はドメインモデル化されたデータではなく生テキストに近いので、別インターフェース（例 `ReadmeQueryPort`）に分離すべき」という案を再検討したが、`RepositoryQueryPort` は「GitHub 上の 1 リポジトリという同一エンティティに対する問い合わせ」という境界で切られており、戻り値の型がリッチかどうか（zod で厳密検証された `RepositoryDetail` か、素の `string` か）は境界を分ける基準として採用されていない（既存の `search`/`findDetail` も内部実装の厚みは違うが同一ポートに同居している）。②「ポート名の `Query` が README のような副資産取得にそぐわない」という命名上の違和感も検討したが、1 メソッド追加のためだけに全消費箇所（`container.ts`・テスト群）に波及するリネームを行うコストは、得られる意味論的な精度向上に見合わない（YAGNI はリネームにも適用される）。
- **round1 になかった補強根拠**: `application-architecture.md` §2 の「ポートを増やす条件」は `W-1`〜`W-3` のどれかを満たすことだが、既存ポートへメソッドを足す場合により直接的に効くのは **`W-3`（速く確実にテストできる）**である。README 取得をユースケース内で `fetch` 直叩きにせず `RepositoryQueryPort` 越しにすることで、`get-repository-readme.test.ts` はフェイク実装（`{ findReadme: async () => 'markdown...' }`）を注入するだけでネットワークなしにテストできる——これは `findDetail` が既に享受している利点そのものであり、round1 では明記していなかったが最も具体的な正当化理由として追記する。

結論: 設計判断は変更しない。ただし「表に無いポートを実装しない」（`application-architecture.md` §2）に従い、`RepositoryQueryPort` の面積表の行を **`search(query)` / `findDetail(name)` / `findReadme(name)`** の 3 メソッドへ更新する PR を本体実装と同一 PR に含めることを改めて明記する。

### `docs_trace` — 反論
<sub>2026-08-21T16:50:15+09:00</sub>

# 🔍 Round 2 Verification Report — docs_trace

## (a) removal_impact の RSS 関連ドキュメント行番号

**検証対象**: removal_impact が §2 で挙げた `user-story-map.md` の `A-8` / `US-33` / `SP-15` 参照

**確認結果**: ✅ 実在確認済み
- `open-questions.md` D-33 は実測で存在・strikethrough + 🔴 注記パターン確定
- 撤去対象ファイル 4 本・`DAILY_DIGEST_LIMIT` 移設プランは実装妥当性あり
- D-34 への採番は既存最大 `D-33` から推奨される

---

## (b) 既存ドキュメントで確認した要件 ID と所在

| ID | 記述内容 | 所在 |
|---|---|---|
| **AC-5** | 詳細ページに所定の情報が表示される（リポジトリ名・オーナーアイコン・言語・Star・Watcher・Fork・Issue） | `prd.md:410-415` |
| **AC-12** | 認証済みでもプライベートリポジトリが表示されない（`NFR-33` の上乗せ受け入れ基準） | `prd.md:462-468` |
| **NFR-33** | 認証トークンを用いても、取得対象を公開リポジトリに限定する。多層防御（修飾子遮断・`is:public` 付与・private 除外・private は 404） | `prd.md:373` |
| **TR-4** | データソースは GitHub API の `GET /search/repositories` とする。詳細取得は `GET /repos/{owner}/{repo}`（§4.3 で別記） | `prd.md:178` |
| **E-2** | GitHub API 呼び出しをデータアクセス層に隔離 | `user-story-map.md:198` |

---

## (c) ui_nav の見出し階層主張との既存ドキュメント整合

**ui_nav 主張**: リポジトリ名（fullName）の `<h1>` をツールタイトルと統合するため `<h2>` へ降格すべき

**既存規定**: `docs/03_design/ui-ux/ui-ux-guidelines.md:290` に **明文**
> 最上部に オーナーアイコン + リポジトリ名（`h1` 相当）、直下に統計行

**矛盾の性質**: 
- **既定は h1 が詳細ページ最上部のリポジトリ名**
- ui_nav 提案は「ツールタイトルを layout.tsx 共有ヘッダーに置く h1 に一本化し、詳細ページの リポジトリ名を h2 に落とす」
- これは既定との直接衝突（§6 の「h1 相当」を変更する提案）
- **変更は ui-ux-guidelines.md §6 の更新が必須**（両立させるなら）

---

## (d) ID 採番の実測値

| ID 種 | 既存最大 | 次の空き | 根拠 |
|---|---|---|---|
| **D-n** | **D-33** | **D-34** | `grep -oE "D-[0-9]+"` で最大確認 |
| **US-n** | **US-34** | **US-35** | 同上・実測で US-34 が最大 |
| **AC-n** | **AC-12** | **AC-13** | 同上・`prd.md` で AC-12 が最大（与件 AC-1〜11 + 上乗せ AC-12） |

---

## 主な検証結論

✅ **確定**
- AC-5・AC-12・NFR-33・TR-4 のすべてが既存ドキュメントで実在・条文確認済み
- removal_impact の D-34 採番提案は妥当
- ui-ux-guidelines.md §6 に詳細ページ h1 の既定が明文化されている

🟡 **設計判断が必要**
- ui_nav 提案（h1 統合・h2 降格）は ui-ux-guidelines.md §6 の既定と矛盾 → 更新必須
- 矛盾する要件の優先順位（既定 vs 新提案）は実装セッション判断
- readme_render 指摘の README 内 h1 と詳細 h1 の見出しレベル衝突は ui_nav と相談推奨

⚠️ **実装前確認**
- ID 衝突リスク：D-34・US-35・AC-13 の採番は複数ラウンド提案との関係で実装セッションで再確認
- arch_domain・readme_render のコード層仮定（mapper 実装済み状態・GitHub API Accept ヘッダ）は実装時に検証

## ラウンド 3

### `lead` — 合意
<sub>2026-08-21T16:52:37+09:00</sub>

# 合意と裁定（lead / round 3）

## 争点 A: ツールタイトルの置き場所と見出し階層（F-1 / F-2）

**採用**: `app/[locale]/layout.tsx` に共有 `<header>` を新設し、その中に
`<h1><Link href={`/${locale}`}>{messages.home.title}</Link></h1>` を置く。`app/[locale]/page.tsx` の自前 `<h1>` は撤去する。
詳細側の 3 つの `h1`（`src/ui/repository-detail.tsx` の `fullName` / `repos/[owner]/[repo]/page.tsx` のエラー分岐 / `not-found.tsx`）は
すべて `h2` へ降格する。

**裁定の根拠**: 「詳細ページのリポジトリ名を `h1` のまま残し、ヘッダーのツールタイトルを非見出しリンクにする」対案も検討したが、
その形ではトップページでタイトルが 2 回描画される（ヘッダー + 既存 `h1`）か、ヘッダーをルート別に出し分ける複雑さを抱える。
1 ページ 1 `h1` を保ちつつ共有ヘッダーを 1 実装で済ませられるのは採用案のみ。

**仕様改訂を先行させる（`ui_nav` の concession を採用）**: `docs/03_design/ui-ux/ui-ux-guidelines.md:290`「リポジトリ名（`h1` 相当）」と
`:294`「タイトル（`h1`）は GitHub 本体への外部リンク」は本変更と正面から矛盾する（`docs_trace` が実行番号で確認済み）。
権威順（ユーザー明示 > 仕様 > テスト > 現行コード）に従い、**同一 PR で §6 を改訂してからコード・テストを追随させる**。
テストだけ書き換えて仕様を放置するのは `intent-gate-rules.md` 違反。

**付随して必須**: `e2e/sp-9-errors.spec.ts:216` の `getByRole('heading', { level: 1 })` は `level: 2` 相当へ修正する
（`ui_nav` が唯一の要修正 E2E として特定。`sp-3` / `a11y` / `sp-6-notfound` は level 未指定のため無傷）。
`e2e/sp-9-loading-empty.spec.ts:41` は `page.tsx` の自前 `h1` を**必ず削除**すれば strict mode violation にならない。

**採らなかった案**: `LocaleSwitcher` の layout 移設（`searchParams` が layout に渡らず、`useSearchParams` 化は `NFR-3` に反する）。
タイトルリンクに `buildSearchUrl` を使う案（F-1 の「未検索状態へ」と矛盾する）。
`LocaleSwitcher` の `<nav>` が `<main>` 内にある構造の是正は**別 Issue**（スコープ外）。

## 争点 B / C: README の取得・描画（F-4）

**取得**: `GET /repos/{owner}/{repo}/readme` を `Accept: application/vnd.github.html+json`（GitHub レンダリング済み HTML）で取得する。
`RepositoryQueryPort` に `findReadme(name): Promise<string | null>` を**追加**する（新ポートは切らない）。
`readme_render` / `arch_domain` が独立に同じ結論へ収束した。`application-architecture.md` §2 のポート面積表も同 PR で 3 メソッドへ更新する。

**private ゲート**: README レスポンスに `private` フィールドが無いため、`src/usecases/get-repository-readme.ts` が内部で
`findDetail` を経由し、`null`（private / 404）なら README を取りに行かない。ゲートは usecase に埋め込み、呼び出し元の順序に依存させない（`NFR-33` / `AC-12`）。

**取得タイミング（真の対立点の裁定）**: `arch_domain` の折衷案を採用する。
`page.tsx` は ① `findDetail` を `await` して `notFound()` を確定 → ② README の Promise を**作るだけ**（`await` しない）→
③ `<Suspense>` 配下の `ReadmeSection` へ Promise を渡す。
これで `AC-5`（404 の同期判定）を壊さず、キャッシュ書き込み後に README 側の `findDetail` が HIT し（GitHub への往復は最大 2 回）、
README の遅延・失敗が統計表示のブロッキングパスに乗らない。`Promise.all` による同時発火は**採らない**（`makeCachingRepositoryQuery()` が
呼び出しごとに新インスタンスで single-flight を共有せず、3 リクエストへ劣化しうる）。

**サニタイズ**: `sanitize-html`（`parseStyleAttributes: false` で postcss 経路を切る）で、
許可リスト適用・相対 URL 解決・`target="_blank" rel="noopener noreferrer"` 付与・見出し降格・切り詰めを**1 パス**（`transformTags`）で行う。
切り詰めは「サニタイズ前の文字数カット」「サニタイズ後の再カット」のいずれも採らない（タグ途中で切れて構造が壊れる）。
パーサが終端で開いたタグを閉じるため、変換パス内でテキスト長を累積して打ち切れば常に整形式になる。

**見出し降格**: README セクション見出しを `h2`（既存の「セクション見出しは h2」パターン）とし、README 本文は **+2 シフト**（`h1→h3` … `h6` で cap）。
`readme_render` の +3 案はセクション見出しを `h3` と仮定した前提であり、争点 A で `h2` に確定したため +2 に統一する。
CSS のフォントサイズ変更ではなく**タグ名そのもの**を書き換える（`aria` 上の見出しレベルはタグ名で決まる）。`id="user-content-..."` は保持する。

**ライブリージョン**（`ui_nav` の指摘を採用）: `<Suspense>` の fallback だけでは後追い挿入が支援技術へ伝わらない。
`role="status" aria-live="polite"` の `sr-only` 常設要素を README ブロックの前に置き、通知と視覚表示を分離する（トップの `#search-status` と同型）。
**フォーカス移動はしない**（`ui_nav` の非対称な結論を採用。ユーザー操作起因でない後追い描画でフォーカスを奪うのは WCAG 3.2.x の観点で有害）。

**キャッシュ（lead 裁定・`arch_domain` の 2 層案を 1 層へ縮退）**: Tier 1（`findReadme` が返す **GitHub 由来の生 HTML** を
`readme:v1:{owner}/{name}` で `TTL_DETAIL_SECONDS` キャッシュ）**のみ**を今回実装する。
Tier 2（サニタイズ済み HTML の composition 層キャッシュ）は、`readme_render` 自身が「バンドル・CPU は未実測」と認めており、
実測前に層を 1 つ増やすのは先回り最適化（YAGNI）。`npx opennextjs-cloudflare build` 後のバンドル差分と描画時間を PR で実測し、
CPU 予算を圧迫すると分かった時点で別 Issue として追加する。レート枠の吸収は Tier 1 だけで完結する（`arch_domain` も同意）。

**失敗時**: `ReadmeSection` 内の `try/catch` で握り、README 不在・取得失敗・レート制限のいずれでも
「GitHub で README を読む」リンクだけを出す（`NFR-9`: 内部エラー文言は画面に出さない。詳細ページ全体は落とさない）。

## 争点 D: 概要・最終更新（F-3）

`description` は `RepositoryDetail` 型・mapper ともに既に存在し、**表示していないだけ**（`arch_domain` が `mapper.test.ts:151` で確認）。
`lastPushedAt: Date` を `RepositoryDetail` へ追加し、`pushed_at ?? updated_at`（`toSearchResult` と同じフォールバック）で埋める。
`domain-model.md:72` が「『最終更新日』は `pushed_at` を使う」と既に定めており、一覧と詳細で同一概念に同一算出規則を適用する。

表示は一覧の作法を踏襲: `description` はラベルなしの `<p>`（`fullName` ブロック直下）、最終更新は統計 `dl` の 5 項目目
（アイコン + 可視ラベル + `Intl.DateTimeFormat(localeTag, { timeZone: 'Asia/Tokyo' })`）。`messages.detail.updatedAt` を新設する
（`detail` 名前空間に揃える。`home.updatedAt` の横断参照はしない）。

## 争点 E: RSS 撤去（F-5）

削除: `app/api/digest/rss/route.ts` + `route.test.ts` / `src/infrastructure/feed/`（`digest-rss.ts` + テスト・ディレクトリごと）/
`src/composition/digest-feed.ts`。`messages/{ja,en}.json` の `digest.rssLink`、`daily-digest.tsx` の購読リンクブロックと `rssLink` ラベル型、
`daily-digest.test.tsx` の 2 箇所（`en` 側は JSX インラインリテラルのため残すと `tsc` が落ちる）、`page.tsx` の `rssLink` 受け渡し、
`e2e/sp-15.spec.ts` の手順 4 と describe 名。

`DAILY_DIGEST_LIMIT` は **`src/composition/container.ts` へ移す**（`arch_domain` の指摘どおり、`ADR 0014` §2.1 の製品判断値であり
`TTL_*_SECONDS` と同じ性質。`app/` へ落とす案は `removal_impact` が撤回済み）。
`FALLBACK_META` / `resolveLandingHost` は RSS 専用ではないため残す。ただし `static-gem-digest.ts:51` の
「RSS 配信側からも同じ値を使う」コメントは撤去後に嘘になるため書き換える。

ドキュメントは削除せず「撤去した事実と理由」を残す（`D-33` の前例に倣う）: `open-questions.md` に **`D-34`** を追加し、
`prd.md`（`US-33` / `AR-10` 系）・`user-story-map.md`（`SP-15`）・`docs/adr/0014-*.md` を打ち消し線 + 🔴 撤去注記で更新する。
機械検査に RSS 固有の前提は無い（`removal_impact` が `tools/` 全体を grep 済み）。

## 争点 F: Ecosyste.ms のリンク化（F-6）

`DigestMeta` に `sourceUrl` を**必須フィールドとして**追加し、`FALLBACK_META.sourceUrl = 'https://ecosyste.ms/'`（一次情報を WebFetch で確認済み）、
`parseMeta` は既存の `httpUrlOr` でフィールド単位フォールバックする。既存の本番 JSON に `sourceUrl` が無くてもランタイムは壊れない
（`removal_impact` が `static-gem-digest.ts` の入力型と出力型の分離設計で反証）。型エラーになるのは `DigestMeta` リテラルを直接組む
テスト 4 ファイルのみで、1 行ずつ追記すればよい。
`attribution-notice.tsx` は `{source}` を `{license}` と同じ作法（`rel="noopener noreferrer"` / `target="_blank"` / フォーカスリング）でリンク化する。
UI 側の定数ハードコードは採らない（帰属表示 4 項目のうち 1 つだけ経路が異質になる）。

`prd.md` §4.3 のデータソース限定記述は打ち消し線にしない。「限定する」という制約表明は残したまま、
列挙へ 🔵 付きで `GET /repos/{owner}/{repo}/readme` を足す（🔴＝撤去 / 🔵＝追加確定 という既存の色分けに従う・`removal_impact` 提案）。

## 別 Issue へ切り出す（本 PR に混ぜない）

- `user-story-map.md` `SP-14` の `D-33` 注記に「再導入条件は `open-questions.md` `D-33` 参照」のポインタを足す（`type:docs` / `sp:1`）
- `LocaleSwitcher` の `<nav>` が `<main>` の内側にあるランドマーク構造の是正
- Tier 2 キャッシュ（サニタイズ済み HTML）の要否 — 本 PR のバンドル・CPU 実測結果を根拠に判断する

## 欠席・留保

なし（5 名全員が round 1 / round 2 を投稿済み）。`docs_trace` は round 2 で一度ホワイトボードへの post を落としたが、再指示で投稿済み。

### `lead` — 判定
<sub>2026-08-21T16:53:39+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: ツールタイトルの導線と見出し階層（F-1 / F-2）",
      "design": "layout.tsx に共有 <header> を新設し h1 = ツールタイトル（Link href=/{locale} 固定）。page.tsx の自前 h1 は撤去。詳細側 3 箇所の h1 を h2 へ降格。LocaleSwitcher は各 page.tsx に据え置き（searchParams が layout に渡らないため）。仕様（ui-ux-guidelines §6）の改訂を先行させる。",
      "artifacts": [
        "app/[locale]/layout.tsx（改修・header 新設）",
        "app/[locale]/page.tsx（改修・自前 h1 撤去）",
        "src/ui/repository-detail.tsx（改修・h1→h2）",
        "app/[locale]/repos/[owner]/[repo]/page.tsx（改修・エラー分岐 h1→h2）",
        "app/[locale]/repos/[owner]/[repo]/not-found.tsx（改修・h1→h2）",
        "docs/03_design/ui-ux/ui-ux-guidelines.md（改修・§6 の h1 規定を改訂）",
        "e2e/sp-9-errors.spec.ts（改修・level:1 → level:2）"
      ],
      "tests": [
        "e2e/feedback-334.spec.ts（新規・トップと詳細の両方でツールタイトルから /{locale} へ遷移し未検索状態になる）",
        "src/ui/repository-detail.test.tsx（改修・見出しレベル h2 を検証）",
        "e2e/a11y.spec.ts（既存・h1 が 1 つであること）"
      ],
      "rejected": "リポジトリ名を h1 のまま維持しヘッダーを非見出しリンクにする案（トップでタイトルが二重描画されるかヘッダーのルート別出し分けが要る）／タイトルリンクに buildSearchUrl を使う案（F-1 の未検索状態遷移と矛盾）／LocaleSwitcher の layout 移設（NFR-3 違反）"
    },
    {
      "issue": "B: README の取得経路とポート設計（F-4）",
      "design": "GET /repos/{owner}/{repo}/readme を Accept: application/vnd.github.html+json で取得。RepositoryQueryPort に findReadme(name): Promise<string|null> を追加（新ポートは切らない）。private ゲートは usecase get-repository-readme.ts が findDetail 経由で行い、呼び出し順序に依存させない。キャッシュは Tier 1（生 HTML・readme:v1:{owner}/{name}・TTL_DETAIL_SECONDS）のみ。",
      "artifacts": [
        "src/domain/ports/repository-query-port.ts（改修・findReadme 追加）",
        "src/infrastructure/github/github-repository-query.ts（改修・README エンドポイント）",
        "src/infrastructure/platform/cached-repository-query.ts / cache-key.ts（改修・readme キャッシュ）",
        "src/usecases/get-repository-readme.ts（新規・private ゲート）",
        "src/composition/container.ts（改修・配線）",
        "docs/03_design/architecture/application-architecture.md（改修・ポート面積表を 3 メソッドへ）",
        "docs/02_requirements/prd.md §4.3（改修・🔵 で README エンドポイントを列挙へ追加）"
      ],
      "tests": [
        "src/usecases/get-repository-readme.test.ts（新規・private/404 で null・findDetail が null なら findReadme を呼ばない）",
        "src/infrastructure/github/github-repository-query.test.ts（改修・404 を null・Accept ヘッダ）",
        "src/infrastructure/platform/cached-repository-query.test.ts（改修・README のキャッシュ HIT/MISS）"
      ],
      "rejected": "新規 ReadmeQueryPort を切る案（守れる W-n が無い YAGNI）／findDetail の戻り値へ README を合成する案（キャッシュ粒度と TTL が固定化する）／Promise.all で findDetail と findReadme を同時発火する案（CachingRepositoryQuery が呼び出しごとに新インスタンスで single-flight を共有せず 3 リクエストへ劣化）"
    },
    {
      "issue": "C: README のレンダリングと安全性（F-4）",
      "design": "sanitize-html（parseStyleAttributes: false）で許可リスト適用・相対 URL 解決・target=_blank 付与・見出し +2 降格（h6 cap・タグ名書き換え・id 保持）・テキスト長での切り詰めを 1 パスで実行。page.tsx は detail 確定後に README Promise を作るだけで await せず、<Suspense> 配下の ReadmeSection へ渡す。sr-only の role=status ライブリージョンを併設し、フォーカス移動はしない。失敗・不在時は「GitHub で README を読む」リンクのみ表示。",
      "artifacts": [
        "src/ui/readme-section.tsx（新規・Suspense 配下の async Server Component）",
        "src/ui/readme-html.ts もしくは src/composition 側のレンダリング関数（新規・サニタイズ 1 パス）",
        "app/[locale]/repos/[owner]/[repo]/page.tsx（改修・Promise 受け渡し + Suspense）",
        "messages/ja.json / messages/en.json（改修・detail.readme 系ラベル）",
        "package.json（改修・sanitize-html 追加）"
      ],
      "tests": [
        "サニタイズ単体テスト（新規・script/iframe/on* 属性/javascript: URL の除去・相対 URL 解決・見出し +2 降格・切り詰め後も整形式）",
        "src/ui/readme-section.test.tsx（新規・null で代替リンク・例外でページを落とさない）",
        "e2e/feedback-334.spec.ts（改修・詳細画面で README 本文が読める）"
      ],
      "rejected": "raw Markdown + 自前レンダラ（cpu_ms:50 の予算で GFM を再パースする合理性が無い）／GitHub の HTML を信頼してサニタイズ省略（第三者 README 由来である事実は変わらない）／サニタイズ前後の文字数カット（タグ途中で切れて構造が壊れる）／CSS のフォントサイズによる見出し降格（支援技術に伝わらない）／README 到着時のフォーカス移動（WCAG 3.2.x の観点で有害）／Tier 2（サニタイズ済み HTML）キャッシュの先行実装（バンドル・CPU が未実測の先回り最適化）"
    },
    {
      "issue": "D: 概要と最終更新の追加（F-3）",
      "design": "RepositoryDetail に lastPushedAt: Date を追加し pushed_at ?? updated_at で埋める（一覧と同一の算出規則・domain-model.md:72）。description は既存フィールドを表示するだけ。description はラベルなしの <p>、最終更新は統計 dl の 5 項目目（アイコン + 可視ラベル + Asia/Tokyo 書式）。",
      "artifacts": [
        "src/domain/model/repository.ts（改修）",
        "src/infrastructure/github/dto.ts / mapper.ts / __fixtures__/（改修）",
        "src/ui/repository-detail.tsx（改修）",
        "messages/ja.json / messages/en.json（改修・detail.updatedAt 新設）",
        "docs/02_requirements/prd.md（改修・FR-4 / AC-5 の表示項目へ description と最終更新を追加）"
      ],
      "tests": [
        "src/infrastructure/github/mapper.test.ts（改修・lastPushedAt が pushed_at 由来・null なら updated_at）",
        "src/infrastructure/github/dto.test.ts（改修・新フィールドの検証）",
        "src/ui/repository-detail.test.tsx（改修・description と最終更新の表示・description が null なら出さない）"
      ],
      "rejected": "updated_at を最終更新に使う案（メタデータ更新で動き、一覧と意味がずれる）／home.updatedAt ラベルの横断参照（detail 名前空間の既存流儀に反する）"
    },
    {
      "issue": "E: RSS の撤去（F-5）",
      "design": "RSS のルート・infrastructure・composition・UI リンク・ラベル・E2E 手順を削除し、DAILY_DIGEST_LIMIT は src/composition/container.ts へ移設。FALLBACK_META と resolveLandingHost は残す。ドキュメントは削除せず D-34 を起票して打ち消し線 + 🔴 撤去注記で更新する。",
      "artifacts": [
        "app/api/digest/rss/route.ts + route.test.ts（削除）",
        "src/infrastructure/feed/（削除・ディレクトリごと）",
        "src/composition/digest-feed.ts（削除）",
        "src/composition/container.ts（改修・DAILY_DIGEST_LIMIT 移設）",
        "src/ui/daily-digest.tsx / daily-digest.test.tsx（改修）",
        "app/[locale]/page.tsx / messages/{ja,en}.json（改修）",
        "src/infrastructure/platform/static-gem-digest.ts（改修・RSS 言及コメントの書き換え）",
        "e2e/sp-15.spec.ts（改修・手順 4 削除）",
        "docs/02_requirements/open-questions.md（改修・D-34 追加）",
        "docs/02_requirements/prd.md / user-story-map.md / docs/adr/0014-*.md（改修・撤去注記）"
      ],
      "tests": [
        "e2e/sp-15.spec.ts（改修・残る 3 手順が緑）",
        "src/ui/daily-digest.test.tsx（改修・RSS リンクが存在しないこと）"
      ],
      "rejected": "UI リンクだけ残してエンドポイントを残す案（飼い主指示は機能廃止）／DAILY_DIGEST_LIMIT を app/[locale]/page.tsx へインライン化（app を薄く保つ規律に反する・提案者が撤回）／ドキュメントからの単純削除（撤去の事実と理由が失われる）"
    },
    {
      "issue": "F: Ecosyste.ms のリンク化（F-6）",
      "design": "DigestMeta に sourceUrl を必須追加し FALLBACK_META.sourceUrl = 'https://ecosyste.ms/'（一次情報確認済み）。parseMeta の httpUrlOr でフィールド単位フォールバックするため既存 JSON でも壊れない。attribution-notice.tsx の {source} を {license} と同じ作法でリンク化する。",
      "artifacts": [
        "src/domain/model/gem.ts（改修・DigestMeta 拡張）",
        "src/infrastructure/platform/static-gem-digest.ts（改修・FALLBACK_META / parseMeta）",
        "src/ui/attribution-notice.tsx（改修・{source} のリンク化）",
        "tools/generate_gem_digest.mjs（改修・sourceUrl の書き込み）"
      ],
      "tests": [
        "src/infrastructure/platform/static-gem-digest.test.ts（改修・sourceUrl 欠落時のフォールバック）",
        "src/ui/attribution-notice.test.tsx（改修・Ecosyste.ms がリンクとして描画される）"
      ],
      "rejected": "sourceUrl を UI 側の定数にする案（帰属表示 4 項目のうち 1 つだけ経路が異質になる）／DigestMeta を optional にする案（フォールバック設計が既にあり必須化で壊れない）"
    }
  ],
  "critical": [
    "sanitize-html（と依存の postcss / htmlparser2）が Cloudflare Workers ランタイムで動作し、バンドル 3MB(gzip) と cpu_ms:50 に収まることは未実測。実装 PR で `npx opennextjs-cloudflare build` 前後のバンドル差分を測り、動かない場合は raw Markdown + micromark 系へ切り替える判断が要る（設計の前提が崩れる唯一の点）。",
    "ui-ux-guidelines.md §6 の h1 規定は本変更と矛盾するため、コード変更より先に仕様を改訂しないと intent-gate 違反になる。"
  ],
  "open_questions": []
}
