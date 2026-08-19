# ドメインモデルとユビキタス言語（DDD・SSOT）

> **このファイルは「本プロジェクトのドメイン語彙（ユビキタス言語）とドメインモデル」の唯一の正本（SSOT）である。**
> 層・依存規則・配置の正本は [アプリケーションアーキテクチャ](../architecture/application-architecture.md)、
> 要件 ID の正本は [PRD](../../02_requirements/prd.md)。
>
> 🔴 **ここに載っていない語をコードの識別子に使わない。** 新しい語が必要になったら **先に本ファイルへ追記** してから実装する（ユビキタス言語はコードと同じ速度で更新されて初めて機能する）。

---

## 1. 本プロジェクトで採る DDD の範囲（採らないものを先に決める）

MVP は **DB を持たない読み取り専用アプリ**（`D-5`）。したがって永続化を前提とする戦術パターンは **採らない**。

| 採る | 理由 |
|---|---|
| **ユビキタス言語**（§2） | GitHub API の語彙をそのまま使うと `watchers` のような **実データと食い違う名前** が UI まで届く（§2.2 の罠） |
| **値オブジェクト**（§4） | 検索条件・識別子の不正値を境界で止める。`NFR-19` の型安全を「型が付いている」以上の水準にする |
| **エンティティ**（§3） | `owner/repo` という同一性が業務上意味を持つ |
| **ドメインサービス**（§5） | Gem Index のようにどのエンティティにも属さない計算の置き場 |
| **腐敗防止層（ACL）**（§6） | データ源を差し替えられる状態を保つ（`W-1`） |
| **ドメインエラー** | 失敗を UI の状態へ正しく写すため（アーキテクチャ §4） |

| 🔴 採らない | 理由 |
|---|---|
| 集約ルート / リポジトリパターン（永続化） | 書き込みも DB も無い。読み取りは `RepositoryQueryPort` 1 本で足りる |
| ドメインイベント / CQRS / イベントソーシング | 状態遷移が無い。導入は純粋な過剰設計（YAGNI） |
| レイヤーごとの DTO 二重定義 | 変換は ACL の 1 箇所だけ。層ごとに DTO を作らない |

> ⚠️ Phase 2（Gem Index・お気に入り）で書き込みや永続化が必要になった時点で、本節を **ADR とともに** 見直す。

---

## 2. ユビキタス言語（用語集）

### 2.1. 中核の語

| 用語（日本語） | コード上の識別子 | 定義 | 注意 |
|---|---|---|---|
| Gem（原石） | `Gem` | **被依存数（実利用）に対して star（注目度）が不釣り合いに小さい OSS**（[ミッション](../../project-mission.md)） | 🔴 MVP では **算出しない**（Phase 2）。「良いリポジトリ」一般を指す語として使わない |
| リポジトリ | `Repository` | GitHub 上の 1 リポジトリ。同一性は `owner/repo` | 「プロジェクト」「レポ」と混在させない |
| リポジトリ識別子 | `RepositoryId` | `owner` と `name` の組。文字列 1 本では持たない | URL・キャッシュキーの素材（`NFR-18`） |
| リポジトリ完全名 | `RepositoryFullName` | `"owner/repo"` 形式のブランド型（`src/domain/model/repository-full-name.ts`）。`RepositoryQueryPort#findDetail` の引数として使う | `RepositoryId`（`owner`/`name` を分解して持つ設計）とは別物。詳細取得のポート境界でのみ使う軽量な識別子 |
| オーナー | `Owner` | リポジトリの所有者（ユーザーまたは Organization）。表示に使うのは名前とアイコン | 「ユーザー」は **本アプリの利用者** を指すので混同しない |
| 検索条件 | `SearchQuery` | キーワード・ページ・ソート・表示件数の 4 つ組。**URL と 1 対 1 で対応する**（`NFR-2`） | UI 状態ではなくドメインの値。バラバラの引数で持ち回らない |
| 検索結果 | `SearchResult` | 検索条件に対する `RepositorySummary` の並びと総件数 | |
| 一覧項目 | `RepositorySummary` | 一覧カードに出す範囲（`AR-1`）。**追加 API 呼び出し無しで得られるものだけ** | 詳細と同じ型にしない（取得コストが違う） |
| 詳細 | `RepositoryDetail` | 詳細ページに出す 7 項目（`FR-4`。`src/domain/model/repository.ts`） | `watchers` は `subscribers_count` 由来（§2.2 の変換表）。`RepositoryQueryPort#findDetail` は存在しない場合 `null` を返す（404 を例外にしない） |
| 閲覧者 | `Viewer` | 本アプリの利用者。未ログインが既定で、ログインしても **変わるのはレート枠だけ**（`D-6`） | 「ログインユーザー限定機能」という概念は存在しない |
| レート枠 | `RateLimitBudget` | GitHub API の残り呼び出し可能回数と回復時刻 | 「クォータ」と混在させない |
| キャッシュキー | `CacheKey` | 検索結果・単一リポジトリの名前空間つきキー（`NFR-18`） | 命名規約を先に固定する。後から変えると全無効化される |
| ロケール | `Locale` | `ja` / `en`。URL のパスセグメントで表す（`AR-4`） | |

### 2.2. 🔴 GitHub API の語との対応（腐敗防止層の変換表）

**外部の語をそのままドメインへ持ち込まない。** 変換は `src/infrastructure/github/mapper.ts` の 1 箇所だけで行う。

| GitHub API のフィールド | ドメインの名前 | 🔴 注意 |
|---|---|---|
| `subscribers_count` | `watcherCount` | **これが「Watcher 数」の正体**（`FR-4`）。`watchers` / `watchers_count` は star と同値であり、使うと表示が間違う |
| `stargazers_count` | `starCount` | 「人気」と呼ばない（偽 star の存在がミッションの出発点） |
| `forks_count` | `forkCount` | |
| `open_issues_count` | `openIssueCount` | **PR を含む**（GitHub の仕様）。UI 文言もこの事実に合わせる |
| `full_name` | `RepositoryId`（分解して保持） | 文字列のまま持ち回らない |
| `owner.avatar_url` | `Owner.avatarUrl` | |
| `pushed_at` / `updated_at` | `lastPushedAt` / `lastUpdatedAt` | 「最終更新日」（`AR-1`）は **`pushed_at`** を使う（メタデータ更新で動く `updated_at` ではない） |
| `topics` | `topics` | |
| `language` | `primaryLanguage` | 「言語」だけだと `Locale` と紛れる |
| `total_count` | `SearchResult.totalCount` | GitHub 検索は上限があるため **概算**。UI で「約」と表現する余地を残す |

---

## 3. エンティティ

| エンティティ | 同一性 | 不変条件 |
|---|---|---|
| `Repository`（`RepositorySummary` / `RepositoryDetail` の共通識別） | `RepositoryId`（`owner/name`） | 識別子は生成後に変わらない。カウント系は 0 以上 |

- エンティティは **プレーンな TypeScript のクラスまたは `readonly` オブジェクト** で表す。フレームワーク・ORM・デコレータを持ち込まない（アーキテクチャ §1.2 の import 禁止）。
- `RepositorySummary` と `RepositoryDetail` は **別の型** にする（前者は検索レスポンスだけで作れ、後者は追加取得が要る）。

---

## 4. 値オブジェクト（不正値を境界で止める）

| 値オブジェクト | 制約 | 破ったときの挙動 |
|---|---|---|
| `RepositoryId` | `owner` / `name` とも GitHub の命名規則に適合 | `DomainValidationError` |
| `RepositoryFullName` | `owner` は英数字とハイフン（先頭・末尾のハイフン不可・最大 39 文字）、`repo` は英数字 `.` `-` `_`（最大 100 文字・`.` `..` 単体不可）。**リポジトリ名のドット（例 `user.github.io`）は許容する**（#97） | `DomainValidationError`。`try*` 版は既定で `null`（URL 由来の値を 500 にしない） |
| `SearchKeyword` | 空白のみ不可・前後トリム・長さ上限 | `DomainValidationError`（UI は「検索を促す表示」に倒す・`AC-3`） |
| `PageNumber` | 1 以上の整数。上限は GitHub 検索の到達可能範囲 | `tryParse` は既定値 `1` に倒す（URL 改変で 500 にしない） |
| `PerPage` | 🔴 **20 / 50 / 100 のみ**（`AR-3`。任意値はキャッシュ断片化を招く） | `tryParse` は既定値に倒す |
| `SortOrder` | `relevance` / `stars` / `updated`（`AR-2`） | 同上 |
| `Locale` | `ja` / `en`（`AR-4`） | 既定ロケールに倒す |
| `CacheKey` | 名前空間 + 正規化済みの構成要素（`NFR-18`） | 生成関数以外で組み立てない |

**実装の型（決定）**: **ブランド型 + スマートコンストラクタ** を使う。クラスで包むのは振る舞いを持つものだけにし、単純な識別子・数値はブランド型で軽量に保つ。

```ts
// src/domain/model/search-keyword.ts
declare const brand: unique symbol
export type SearchKeyword = string & { readonly [brand]: 'SearchKeyword' }

export function searchKeyword(raw: string): SearchKeyword {
  const trimmed = raw.trim()
  if (trimmed.length === 0) throw new DomainValidationError('SearchKeyword', raw)
  return trimmed as SearchKeyword
}
export function trySearchKeyword(raw: string): SearchKeyword | null { /* … */ }
```

- 🔴 **生の `string` / `number` をユースケースの引数にしない。** 境界（`searchParams` の読み取り・ACL）で値オブジェクトへ変換する。
- 値オブジェクトは **不変**（`readonly`）。等価性は値で判定する。
- `zod` は **`src/infrastructure/` 側の外部データ検証で使う**。ドメインは依存ゼロを保つ（アーキテクチャ §1.2）。

**`CacheKey` の実装位置（Issue #67）**: ブランド型 + 生成関数を `src/infrastructure/platform/cache-key.ts` に置く（`CachePort` の実装と同じ層。`src/domain/model/` ではない — キー形式が `CachePort` 実装詳細と不可分なため）。生成関数は `searchResultCacheKey(query: SearchQuery)` / `repositoryCacheKey(owner, name)` の 2 本。正規化は `trim → toLowerCase → encodeURIComponent`、利用者識別子は含めない。実際のキー形式:

```text
search:{バージョン}:{正規化キーワード}:page={ページ番号}:sort={ソート順}:per_page={表示件数}   # searchResultCacheKey
repository:{バージョン}:{正規化owner}/{正規化name}                                             # repositoryCacheKey

# 現行（CACHE_SCHEMA_VERSION = 'v2'）の実例
search:v2:react:page=1:sort=stars:per_page=20
repository:v2:vercel/next.js
```

ソート順（`AR-2`）・表示件数（`AR-3`）は `SearchQuery` の構成要素であり、キャッシュ断片化を招くため `searchResultCacheKey` に必ず含める。

**🔴 バージョンセグメント（`CACHE_SCHEMA_VERSION`・Issue #142）**: 名前空間の直後に置く **キャッシュスキーマバージョン** で、両方の生成関数が同じ定数（`src/infrastructure/platform/cache-key.ts` の `export const CACHE_SCHEMA_VERSION`）を共有する。

- **bump する条件**: **キャッシュ値の「意味」が変わったとき** — 取得範囲・フィルタ条件・レスポンスのマッピングの変更が対象。キーの構成要素（キーワード・ページ・ソート順・表示件数）が同じままでも、**同じキーに対して返るべき値の中身が変われば bump する**。
- **なぜ必要か**: キーが検索条件だけで構成されていると、修正をデプロイしても **古い意味の値が入ったエントリが TTL 切れまでヒットし続ける**。バージョンを上げれば全キーが別物になり、既存エントリを一括で論理的に無効化できる（明示的なパージ機構を持たずに済む）。
- **改訂履歴**: `v1` 初版 / `v2` 検索を公開リポジトリ限定（`is:public`）にし、同じ検索条件に対する結果の範囲が変わったため引き上げ（Issue #142・`NFR-33`）。

---

## 5. ドメインサービス

| サービス | 責務 | 状態 |
|---|---|---|
| `GemIndex`（Phase 2） | 被依存数と star の乖離から Gem 度を算出する | 🔴 **MVP では実装しない**。ミッションの中核なので **置き場所だけ** `src/domain/services/` に確保する |

- 健全性スコアは **自作しない**（OpenSSF に依存する・`GR-2` / `Q-1` / `Q-2`）。ドメインサービスとして再実装する誘惑を明示的に禁じる。

---

## 6. 境界づけられたコンテキストと腐敗防止層

| コンテキスト | 位置づけ | 関係 |
|---|---|---|
| **Search**（MVP） | 本アプリの中核。検索・一覧・詳細 | — |
| **Gem Index**（Phase 2） | 被依存数・健全性を扱う | Search とは **別コンテキスト**。同じ `Repository` でも持つ属性が違う。共通化を急がない |
| **GitHub**（外部・上流） | データ源 | 🔴 **腐敗防止層（`src/infrastructure/github/`）を必ず挟む**。上流の変更に本体を追随させない |
| **Ecosyste.ms / OpenSSF**（Phase 2・外部・上流） | 被依存数・健全性の供給元 | 同じく ACL を挟む。`RepositoryQueryPort` と別ポートにする |

---

## 7. 完了・成功の定義

- [ ] コード上の識別子が §2 の表の名前と一致している（表に無い語を使っていない）
- [ ] `subscribers_count` / `pushed_at` の対応（§2.2）を実装が守っている
- [ ] ユースケースの引数が値オブジェクトになっている（生の `string` / `number` でない）
- [ ] ドメイン層に外部ライブラリの import が無い
- [ ] 新しいドメイン語を導入する PR が、本ファイルの更新を含んでいる

---

## 8. 参照

| ドキュメント | 関係 |
|---|---|
| [アプリケーションアーキテクチャ](../architecture/application-architecture.md) | 本ファイルのモデルを **どこに置くか** の正本 |
| [テスト戦略](../../04_development/testing-strategy.md) | 値オブジェクト・ドメインサービスのテスト方針 |
| [PRD](../../02_requirements/prd.md) | `FR-n` / `AR-n` / `NFR-n` の正本 |
| [GitHub API リサーチ](../../04_development/api/20260817-github-api-research.md) | 上流フィールドの一次情報 |
| [プロジェクトミッション](../../project-mission.md) | `Gem` の定義の出所 |
