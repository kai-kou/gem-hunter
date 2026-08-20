# ADR 0011: i18n のルーティング設計と既定ロケールを、`next-intl` を不採用として自前実装で確定する

- **状態**: **承認**
- **日付**: 2026-08-20 JST
- **対応要件**: `D-4` / `AR-4` / `R-7` / `NFR-21` / [PRD](../02_requirements/prd.md) §4.2 `AR-4`
- **関連**: [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §3.2 / [`open-questions.md`](../02_requirements/open-questions.md) §13（i18n ライブラリ選定・決定済み） / [ADR 0002](0002-cloudflare-workers-infrastructure.md)（決定 #8: `proxy.ts` を使わない）

---

## 1. 文脈

`D-4`（2026-08-17）は「i18n 対応（日英切替）。ただしロケール基盤（ルーティング + メッセージ抽出）は MVP 時点で入れ、翻訳の作り込みは積み上げフェーズに回す」と決めていた。当初の推奨は `next-intl` を第一候補としつつ「Next.js 16 App Router での最新の推奨構成を実装着手時に一次確認する」（`R-7` に統合）というものだった（[`open-questions.md`](../02_requirements/open-questions.md) §3 `D-4` 従属事項）。

2026-08-19、実装着手時の一次確認で `next-intl` の不採用が確定した（[`open-questions.md`](../02_requirements/open-questions.md) §13）。根拠は Next.js 16 の仕様変更である。

> Next.js 16 で `proxy.ts`（旧 `middleware.ts`）は既定で Node.js ランタイム固定になり、`runtime` config を proxy 側で上書きすることも不可（設定するとビルドエラーになる）ため、OpenNext Cloudflare アダプタ（Edge 実行）と両立できない（`node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md` "Runtime" 節・"Version history" v16.0.0 の記載）。

`next-intl` の標準的な App Router 構成はロケール判定・リダイレクトを middleware（`proxy.ts`）で行う。これが Edge ランタイムの Workers 上で動かせない以上、`next-intl` を採用すると同ライブラリの主要な提供価値（ミドルウェアベースのルーティング）を使えないまま依存だけを抱えることになる。あわせて [ADR 0002](0002-cloudflare-workers-infrastructure.md) 決定 #8「`Node.js Middleware` と `proxy.ts` を一切使わない」がインフラ側の制約として既に確定しており、i18n の実装方針はこの制約に従う必要があった。

本 ADR は、この不採用判断とその代替として実装済みの自前実装（`src/domain/model/locale.ts` / `src/shared/i18n/messages.ts` / `next.config.ts` の `redirects()` / `src/ui/url/locale-redirect.ts`）を、`NFR-32` に基づき記録する。

---

## 2. 決定

### 2.1. ライブラリは採用しない（依存を増やさない自前実装）

`next-intl` を含む i18n 専用ライブラリを採用せず、以下の 4 ファイルで完結する自前実装とする。

| ファイル | 役割 |
|---|---|
| `src/domain/model/locale.ts` | ロケール定義（`Locale` ブランド型）・許容ロケール一覧・既定ロケール定数 |
| `src/shared/i18n/messages.ts` | メッセージカタログの解決（ロケール → JSON 辞書） |
| `next.config.ts` `redirects()` | プレフィックスなしパスの既定ロケールへのリダイレクト |
| `src/ui/url/locale-redirect.ts` | リダイレクト判定ロジック（`redirects()` に渡す `source` / `destination` 文字列を生成する純粋関数） |

### 2.2. ルーティング設計

- **URL 形式**: 全ロケールにパス接頭辞を付ける（`/ja/...` / `/en/...`）。実装は `app/[locale]/` ディレクトリ構成で App Router のダイナミックセグメントとして表現する。
- **既定ロケール**: `ja`（`DEFAULT_LOCALE`・`src/domain/model/locale.ts`）。
- **サポートロケール**: `ja` / `en` の 2 つ（`LOCALES`・同ファイル）。
- **リダイレクト条件**（`next.config.ts` `redirects()`。`middleware` / `proxy.ts` は使わない）:
  1. `/` へのアクセスは `/ja` へリダイレクトする（`permanent: false`）。
  2. ロケール接頭辞（`/ja`・`/en`）を持たないパスのうち、`_next` 配下・`api` 配下・静的ファイル拡張子（ico / png / css / js / json 等・`STATIC_FILE_EXTENSIONS`）で終わるパスを除く全パスを、既定ロケール配下へ前置してリダイレクトする（`permanent: false`）。
  3. 判定ロジック（除外パターンの正規表現生成）は `src/ui/url/locale-redirect.ts` の `localeRedirectExclusionPattern()` / `buildLocaleRedirectSource()` に一本化し、他ファイルに同等の判定ロジックを重複させない。
- **不正・未知ロケールの扱い**: `tryLocale()`（`src/domain/model/locale.ts`）が URL 由来の値のように「不正なら既定ロケールへ倒してよい」文脈向けに、パース失敗時に例外を投げず `DEFAULT_LOCALE` へフォールバックする関数として提供される。厳密な検証が要る文脈（内部でロケール値を組み立てる箇所等）は `locale()`（`DomainValidationError` を投げる）を使い分ける。

### 2.3. 翻訳対象の範囲

- 自前の UI 文言のみを翻訳する（`src/shared/i18n/messages.ts` のカタログ経由・ハードコード禁止）。
- GitHub 由来のデータ（リポジトリ説明文・topics・言語名）は原文のまま表示し、機械翻訳は行わない（[PRD](../02_requirements/prd.md) §4.2 `AR-4` の詳細・[`inception-deck.md`](../00_concept/inception-deck.md) Q4.2「GitHub 由来データの機械翻訳」不採用）。
- MVP で入れるのは **ロケール基盤**（ルーティング・ロケール検出・メッセージカタログの仕組み）までであり、日本語 / 英語カタログの翻訳の完成度そのものは積み上げフェーズで上げる（`D-4` の方針を維持）。

---

## 3. 理由

### 3.1. なぜ `next-intl` を不採用にしたか

`next-intl` の標準構成が前提とするミドルウェアベースのロケール判定・リダイレクトは、Next.js 16 で `proxy.ts` が Node.js ランタイム固定になったことにより、OpenNext Cloudflare アダプタ（Edge 実行）と両立できない（§1 引用）。回避策として `proxy.ts` を使わない代替構成を `next-intl` 上に無理に組む選択肢もあり得たが、それは同ライブラリが提供する主要な機能（ミドルウェア連携）を放棄したまま依存関係とバンドルサイズだけを抱えることになり、[ADR 0002](0002-cloudflare-workers-infrastructure.md) が重視する Workers Free のバンドル上限（gzip 3 MB・実測待ちの制約・同 ADR §7 未確認事項 #1）に対しても不利に働く。

### 3.2. なぜ `redirects()` で足りるか（`proxy.ts` を使わない設計との整合）

`next.config.ts` に埋め込まれたコメントが引用する Next.js 公式ドキュメントは「単純なリダイレクトには、まず `next.config.ts` の `redirects` 設定の利用を検討すべき」と明記している。本アプリのロケール判定は「パスにロケール接頭辞があるか」という **単純なパス→パスの静的な条件分岐** であり、リクエストヘッダ（`Accept-Language`）に基づく動的なロケール推定や、Cookie ベースの言語切替の永続化のような、ミドルウェアでなければ実装できない要件を持たない。したがって `redirects()`（ビルド時に確定する設定）で要件を満たせる。

これは [ADR 0002](0002-cloudflare-workers-infrastructure.md) 決定 #8「`Node.js Middleware` と `proxy.ts` を一切使わない。`/` → `/ja` はルート Server Component の `redirect()` で実装する」の実際の実装形を確定させたものである。実装では単一パスの `redirect()` ではなく `next.config.ts` の `redirects()` に判定ロジックを一本化した（`/` 単体の特別扱いと、任意パスへの接頭辞付与の両方を同一の仕組みで扱えるため）。

### 3.3. なぜ全ロケールにパス接頭辞を付けるか（既定ロケールも省略しない）

`D-4` の状態管理原則（[PRD](../02_requirements/prd.md) §2.4）は「ロケールを URL に含める（`/[locale]/...`）」ことを、与件 §4.3 の「検索条件（キーワード・ページ）を URL に反映する」と同じ URL 設計上で解決すると定めている。既定ロケール（`ja`）だけをプレフィックスなしにする設計（例: `/` = 日本語・`/en` = 英語）も選択肢にあり得たが、以下の理由で全ロケール接頭辞方式を採る。

1. **共有リンクで言語が一意に定まる**: URL だけを見て「これは日本語版か英語版か」が常に判定できる。プレフィックスなし方式では、既定ロケールが将来変わったときに同じ URL が指す言語が変わってしまう。
2. **静的生成・キャッシュキーの一貫性**: `app/[locale]/` のダイナミックセグメントとして両ロケールを対称に扱えるため、`generateStaticParams` やキャッシュキー設計（`NFR-18`）でロケールごとの特別扱いが不要になる。
3. **後方互換の維持**: [PRD](../02_requirements/prd.md) `AR-4` の詳細は「ロケール接頭辞は実装の最初に確定させる。後から locale セグメントを足すと既存 URL がすべて変わり、共有リンクが壊れる」と明記しており、対称な設計にしておけば将来ロケールが追加されても既存 URL の形式が変わらない。

### 3.4. なぜ判定ロジックを 1 箇所（純粋関数）に一本化したか

`src/ui/url/locale-redirect.ts` はコメントで明示するとおり、`next.config.ts` の `redirects()` に渡す `source` / `destination` 文字列を生成する **純粋関数** として実装されている。これにより判定ロジック（除外パターン: ロケール接頭辞・`_next`・`api`・静的ファイル拡張子）がテスト可能になり、`next.config.ts` 自身にロジックを直書きしない。

⚠️ **実装上の既知の制約が 2 点、コメントとして残されている**（本 ADR はこれらを実装事実として記録する）。

1. `next.config.ts` は SWC の require hook で `locale-redirect.ts` を直接 require するため、`@/` エイリアスではなく相対 import（`../../domain/model/locale`）を使う必要がある（エイリアス解決が `next.config.ts` 自身からの相対パスとして誤って計算されるため）。
2. `redirects()` の `destination` に `:path` トークンをそのまま書くと、OpenNext Cloudflare アダプタ（`@opennextjs/aws` の `matcher.js`）が `path-to-regexp` の `compile()` を検証オプション既定（`validate: true`）で呼び、複数セグメントを含む値（例 `repos/foo/bar`）で `TypeError` を投げてプレビュー環境で 500 エラーになる（PR #96 で実機検証・修正済み）。`buildLocaleRedirectDestination()` は `:path(.*)` という明示パターンでこれを回避する。ローカルの `next start`（Next.js 自身のルーティング）では `compile()` が `{ validate: false }` で呼ばれるため再現せず、見落としやすい既知の落とし穴として記録する。

---

## 4. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **`next-intl`（middleware ベースの標準構成）** | Next.js 16 で `proxy.ts` が Node.js ランタイム固定になり、OpenNext Cloudflare アダプタ（Edge 実行）と両立できない（§3.1） |
| **`next-intl` を `proxy.ts` なしの構成で無理に採用する** | 同ライブラリの主要機能（ミドルウェア連携）を放棄したまま依存関係とバンドルサイズだけを抱える（§3.1）。Workers Free のバンドル上限（[ADR 0002](0002-cloudflare-workers-infrastructure.md) §7 未確認事項 #1）に対して不利 |
| **サブドメイン方式（`ja.example.com` / `en.example.com`）** | ワイルドカード DNS・証明書の追加設定が必要で、Cloudflare Workers の単一 Worker 構成（[ADR 0002](0002-cloudflare-workers-infrastructure.md)）に対して運用の複雑度が増す。プレビュー環境（PR ごとの preview alias URL）でサブドメインを動的に払い出す経路も存在しない |
| **Cookie 方式（URL にロケールを含めず Cookie で言語を保持する）** | `D-4` の状態管理原則（[PRD](../02_requirements/prd.md) §2.4）が「ロケールは URL に含める」と定めており、共有リンクで言語が保たれない（サーバー側に個人化された Cookie 状態が必要になり、`D-13` / `D-14`「サーバー側に個人情報を持たない」原則とも相性が悪い） |
| **既定ロケールだけプレフィックスを省略する（`/` = 日本語・`/en` = 英語）** | 将来の既定ロケール変更時に同一 URL が指す言語が変わる。静的生成・キャッシュキー設計でロケールごとの特別扱いが必要になる（§3.3） |
| **`middleware.ts`（Next.js 15 以前の名称）でロケール判定を行う** | [ADR 0002](0002-cloudflare-workers-infrastructure.md) 決定 #8 により不採用済み（`Node.js Middleware` を一切使わない） |
| **判定ロジックを `next.config.ts` に直書きする** | テスト不可能になり、リダイレクト条件（除外パターン）の変更時に検証手段を持てない（§3.4） |

---

## 5. 結果（この決定がもたらすもの）

### 良い方向

- i18n 専用ライブラリへの依存がゼロのまま、[ADR 0002](0002-cloudflare-workers-infrastructure.md) の Edge 実行制約と両立する
- ロケール判定ロジックが純粋関数として切り出されており、単体テストの対象にできる
- 全ロケール対称のパス接頭辞方式により、将来ロケールを追加しても既存 URL の形式が変わらない

### 受け入れる代償

| 代償 | 緩和策 |
|---|---|
| メッセージカタログ・複数形処理・数値/日付のロケール依存フォーマットなど、i18n ライブラリが提供する高度な機能を自前で持たない | MVP の翻訳対象は自前 UI 文言のみで、GitHub 由来データは原文表示のため翻訳範囲が小さく、複数形処理等の高度な要件が現時点で発生していない |
| `redirects()` はビルド時に確定する静的な設定であり、`Accept-Language` ヘッダに基づく動的なロケール推定は行わない | `D-4` の要件はロケール基盤（ルーティング + メッセージカタログ）に限定されており、動的推定は要件化されていない。必要になった場合は新たな ADR で再検討する |
| OpenNext Cloudflare アダプタ固有の `path-to-regexp` 検証の落とし穴（§3.4）がローカル環境では再現しない | コメントとして実装に残し、プレビュー環境での実機確認（PR #96）を再発防止の記録として残す |

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`open-questions.md`](../02_requirements/open-questions.md) `D-4` / §13 | i18n 対応の方針決定（2026-08-17）と `next-intl` 不採用の確定（2026-08-19） |
| [`prd.md`](../02_requirements/prd.md) §2.4 / §4.2 `AR-4` | 状態の置き場所（ロケールは URL）・i18n 要件の詳細 |
| [ADR 0002](0002-cloudflare-workers-infrastructure.md) 決定 #8 | `proxy.ts` / Node.js Middleware を使わない制約の初出 |
| `src/domain/model/locale.ts` / `src/shared/i18n/messages.ts` / `next.config.ts` / `src/ui/url/locale-redirect.ts` | 実装の正本 |
