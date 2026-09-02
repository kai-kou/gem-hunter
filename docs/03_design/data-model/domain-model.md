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
| Gem（原石） | `Gem` | **被依存数（実利用）に対して star（注目度）が不釣り合いに小さい OSS**（[ミッション](../../project-mission.md)）。`SP-14` で型として実体化した（`src/domain/model/gem.ts`）。候補プール JSON の 1 エントリに対応し、`packageName` / `repositoryFullName` / `dependentCount` / `stars` / `gemIndex` を持つ。🔵 **`SP-17`（`D-37`）以降、候補プール JSON の 1 エントリは `registry`（下記）も持つ** が、`Gem` 型はまだこのフィールドを写していない（レジストリ別の配信シャード側で使う・`SP-18` / `D-38`）。🔵 **`SP-19` で `registry` を写した派生型 `GemPoolEntry`（下記）を追加した** — `Gem` 自体は据え置きで、レジストリを必要とする Gem 候補の一覧だけが `GemPoolEntry` を使う | 🔴 **MVP では算出しなかったが、`D-27`（`M-5` を「着手する」で通過）により Phase 2 が実装対象へ格上げされ、`SP-14` で実装済み**。「良いリポジトリ」一般を指す語として使わない。生テキスト（`description` 等）は持たない（`D-29`・再配信しない）。🔴 **`Gem.stars` / `Gem.dependentCount` は Ecosyste.ms のバッチ取得時点のスナップショット** であり、`RepositoryDetail.starCount` のようなライブ値ではない（銘柄ごとにクロール時点が異なり実測で最大 2.7 年ばらつく。表示上は参考値として扱う・[ADR 0014](../../adr/0014-zero-query-daily-digest.md) §5 項番 8）。UI 表示ラベルは `dependentCount` = 「利用パッケージ数」/ "Used by" に対応する（コード識別子は変更しない） |
| レジストリ | `registry` | **パッケージが公開されている 1 つの配布サイト**。値は Ecosyste.ms の registry 名そのもの（`npmjs.org` / `pypi.org` / `repo1.maven.org` … 全 12 件・定義の実体は `tools/gem-pool/registries.mjs` の `REGISTRIES[].name`）。`D-37` のレジストリ別成層化（各レジストリから被依存数降順で同数を取る固定枠）と、パーセンタイル再計算の母集団を区切る単位 | 🔴 **下の「エコシステム」と混同しない**（似て非なる 2 語）。API パス・候補プール JSON・配信シャードのファイル名に載るのは **こちら**。「リポジトリ」とも別物（1 レジストリに多数のパッケージ、1 リポジトリに複数レジストリのパッケージがありうる） |
| エコシステム | `ecosystem` | **パッケージ管理系の分類名**。値は Ecosyste.ms の ecosystem 名（`npm` / `pypi` / `cargo` / `go` … `REGISTRIES[].ecosystem`）。表示・分類にのみ使う | 🔴 **`registry` と 1 対 1 に見えるが同じ語ではない**（`crates.io` の ecosystem は `cargo`、`proxy.golang.org` は `go`）。成層化・パーセンタイル母集団の区切りに使うのは `registry` であり、こちらを識別子として使わない。ADR 0014 §2.6 の「母集団はエコシステム内で閉じて計算する」という原則は、実装上は **`registry` 単位** で満たしている |
| 候補プールのエントリ | `GemPoolEntry` | **Gem 候補プール（レジストリ別シャードの全量・`D-38`）の 1 レコード**（`src/domain/model/gem.ts`）。`Gem` に `registry` を足した派生型で、`GemIndexPort#search` の返り値と Gem 候補の一覧（`/[locale]/gems`・`SP-19`）が使う | 🔴 **「上位 N 件のスライス」である `DailyDigest.items`（`Gem`）と母集団が違う** — 一覧に載るのは **プールに載っているもの全部** で、`gemIndex` は順序にだけ使う（閾値で絞らない）。「検索結果」（`SearchResult`・GitHub 由来）とも別物なので、同じ画面語（「一覧」）で混ぜて呼ばない |
| 同伴 | `GemPoolSearchInput.includeFullNames` | **検索語の照合とは独立に、一覧へ必ず含める `repositoryFullName` 群**（`SP-19` 追補・`案3'`・Issue #453・`src/domain/ports/gem-index-port.ts`）。検索結果ページで `GemIndexPort#lookup` によりバッジが付いた候補のうち、一覧側の名前照合（`GemIndexPort#search`）には一致しないものを URL 経由で一覧へ明示的に連れてくる操作を指す | 🔴 **`GemIndexPort#lookup`（バッジ＝候補プールへの所属照会・検索語と無関係）と `#search`（一覧＝リポジトリ名・パッケージ名の単語境界一致・`D-37`）は判定基準が別物である。** バッジは「プールに載っているか」だけで決まり検索語を見ないのに対し、一覧は検索語のトークンに対する AND 一致で決まるため、`q=next.js` のようにバッジが複数件付いても一覧が 1 件に落ちる食い違いが起きうる（Issue #453 の症状）。「同伴」はこの 2 系統の判定基準の差を埋めるための橋渡しであり、`#search` の照合規則そのもの（`D-37`）を変えるものではない。⚠️ **同伴を利用者に注記しない**（追加件数を返す `includedCount` は 2026-08-23 の飼い主フィードバックで撤去した。説明されても理解できないため、一覧は総件数だけを示す）。経緯は [`open-questions.md`](../../02_requirements/open-questions.md) `D-36` / `D-37` を参照 |
| 照合トークン | `tokenizeQuery` / `tokenizeIdentifier` の出力（`readonly string[]`） | **候補プールの絞り込みで突き合わせる、小文字の ASCII 英数字の語**（`src/domain/model/gem-keyword.ts`）。検索語側は `tokenizeQuery`、照合対象（`repositoryFullName` / `packageName`）側は `tokenizeIdentifier` が作る。`-` `_` `/` `.` `@` `+` 空白などはすべて区切り。`D-37` が定める **単語境界一致**（部分一致ではない）の実体 | 🔴 **キャメルケースでは分割しない**（`TensorRT` → `['tensorrt']`。`tensor` では引けない・仕様）。⚠️ **非 ASCII も区切り扱い** なので日本語だけの検索語は空トークン列になる。空トークン列は「絞り込みなし＝全件」を意味するため、`searchGems` は **照合不能な検索語**（生値はあるがトークンが 0 語）を全件表示に化けさせず 0 件へ倒す（`unmatchableQuery`）。🔴 上限は生値 256 文字（`MAX_QUERY_LENGTH`）/ 16 語（`MAX_QUERY_TOKENS`）で、超過分は切り捨てる（`SP-19` のセキュリティ検証で 800 語・URL 4.8KB が CPU を使い切り `Error 1102` を返したため） |
| 緩和 | `relaxed` / `selectMostSelectiveToken` | **全語 AND 一致が 0 件のときだけ、「最も選択的な 1 語」（単独ヒット数が最小の語）へ絞り込みを緩めること**（`D-37`・`gem-keyword.ts`）。緩和が起きたかは `GemPoolSearchResult.relaxed`、実際に使った語は `usedTokens` で返し、UI が「全語では 0 件だったので 1 語で絞り込んだ」と明示する | 🔴 **「あいまい一致」「フォールバック検索」と呼ばない** — 照合規則そのものは単語境界一致のままで、**使う語の数だけ** を減らす操作である。緩和で部分一致・編集距離を持ち込むと `D-37` が排除したノイズが戻る。緩和は 1 段だけ（1 語でも 0 件ならそのまま 0 件） |
| 日次ダイジェスト | `DailyDigest` | ある日付シード（`DateSeed`）に対して確定した「今日の Gem」の並び（`src/domain/model/gem.ts`）。`date` / `items`（表示順）/ `meta` を持つ（[ADR 0014](../../adr/0014-zero-query-daily-digest.md) §2.2） | 同じ `date` は全ユーザーで同じ `items`。「フィード」「タイムライン」と呼ばない（有限件数であることが設計の核・ADR 0014 §2.1） |
| shortlist（Gem Index 上位帯） | `GEM_INDEX_SHORTLIST_SIZE` ほか（`src/domain/model/gem-shortlist.ts`・ドメイン層へ移設予定） | 候補プールを `Gem Index` 昇順（同値は `packageName` 昇順でタイブレーク）に並べた上位帯。日次ダイジェストのシャッフル母集団になる | 既定値は 60 件。根拠（star 分布のスナップショット統計）は [ADR 0014](../../adr/0014-zero-query-daily-digest.md) §2.2.3 が正本（本表では重複記載しない） |
| 出典メタデータ | `DigestMeta` | 候補プールの提供元・ライセンス・生成時刻（`source` / `sourceUrl` / `license` / `sourceLicenseUrl` / `generatedAt`）。`D-29` の帰属表示に使う | 🔴 **表示は任意ではなく義務**（CC BY-SA 4.0）。`DailyDigest` から切り離して持ち回らない |
| 既視ダイジェスト | `SeenDigest` | **前回訪問時にそのブラウザが見たダイジェストのスナップショット**（`date` + `packageNames`・`src/domain/model/digest-diff.ts`）。`SP-15` の差分表示（`US-32`）の入力 | 🔴 **1 世代だけ保持する**（履歴を蓄積しない）。保存先はクライアントの `localStorage` のみで **サーバーに永続化しない**（`D-14` / `D-18`）。Safari ITP により消えうる前提の値であり、無い＝初回として扱う（`ADR 0014` §2.4） |
| ダイジェスト差分 | `DigestDiff` | `SeenDigest` と当日の `DailyDigest` を突き合わせた結果（`newNames`＝前回に無かった `packageName` 集合 / `isFirstVisit`・`src/domain/model/digest-diff.ts`） | 🔵 **`isFirstVisit` のとき `newNames` は空**（初回に「全件が新着」と示さない・`ADR 0014` §2.4 のフォールバック要件）。「未読」「既読」とは呼ばない（読んだかではなく前回表示に含まれたかで判定するため） |
| リポジトリ | `Repository` | GitHub 上の 1 リポジトリ。同一性は `owner/repo` | 「プロジェクト」「レポ」と混在させない |
| リポジトリ識別子 | `RepositoryId` | `owner` と `name` の組。文字列 1 本では持たない | URL・キャッシュキーの素材（`NFR-18`） |
| リポジトリ完全名 | `RepositoryFullName` | `"owner/repo"` 形式のブランド型（`src/domain/model/repository-full-name.ts`）。`RepositoryQueryPort#findDetail` の引数として使う。🔴 **厳格版（`repositoryFullName` / `tryRepositoryFullName`）と許容版（`isLenientRepositoryFullName` / `tryParseLenientRepositoryFullName`）の 2 系統が同居する**（実データ 62,783 件中 26 件・ユニーク owner 25 件で判定が割れる。すべて末尾ハイフン owner の実在リポジトリ。詳細は §4） | `RepositoryId`（`owner`/`name` を分解して持つ設計）とは別物。詳細取得のポート境界でのみ使う軽量な識別子。**許容版はブランド型を返さない**（§4） |
| オーナー | `Owner` | リポジトリの所有者（ユーザーまたは Organization）。表示に使うのは名前とアイコン | 「ユーザー」は **本アプリの利用者** を指すので混同しない |
| 検索条件 | `SearchQuery` | キーワード・ページ・ソート・表示件数の 4 つ組。**URL と 1 対 1 で対応する**（`NFR-2`） | UI 状態ではなくドメインの値。バラバラの引数で持ち回らない |
| 検索結果 | `SearchResult` | 検索条件に対する `RepositorySummary` の並びと総件数 | |
| 一覧項目 | `RepositorySummary` | 一覧カードに出す範囲（`AR-1`）。**追加 API 呼び出し無しで得られるものだけ** | 詳細と同じ型にしない（取得コストが違う） |
| 詳細 | `RepositoryDetail` | 詳細ページに出す項目一式（`FR-4`。リポジトリ名・オーナーアイコン・言語・Star 数・Watcher 数・Fork 数・Issue 数・🔵 `description`・🔵 `lastPushedAt`・🔵 README。`src/domain/model/repository.ts`。README（`findReadme` の戻り値）はドメイン型のフィールドではなく `RepositoryQueryPort` の別メソッドで取得する別データ・Issue #334 F-3/F-4） | `watchers` は `subscribers_count` 由来（§2.2 の変換表）。`RepositoryQueryPort#findDetail` は存在しない場合 `null` を返す（404 を例外にしない） |
| 閲覧者 | `Viewer` | 本アプリの利用者。未ログインが既定で、ログインしても **変わるのはレート枠だけ**（`D-6`） | 「ログインユーザー限定機能」という概念は存在しない |
| レート枠 | `RateLimitBudget` | GitHub API の残り呼び出し可能回数と回復時刻 | 「クォータ」と混在させない |
| キャッシュキー | `CacheKey` | 検索結果・単一リポジトリの名前空間つきキー（`NFR-18`） | 命名規約を先に固定する。後から変えると全無効化される |
| ロケール | `Locale` | `ja` / `en`。URL のパスセグメントで表す（`AR-4`） | |
| エラー種別 | `ErrorKind` | 失敗の原因を利用者への提示単位で分類した 7 値（`network` / `rateLimitPrimary` / `rateLimitSecondary` / `auth` / `validation` / `notFound` / `upstream`）。判別条件の正本は [`prd.md`](../../02_requirements/prd.md) §7（`src/domain/errors.ts`） | 🔴 **利用者向けの文言はこの kind から i18n で引く**。各 `DomainError` の `message` は開発者向けのログ用であり、画面・API 応答へそのまま出さない（内部情報を漏らさない・`NFR-8`） |
| 上流に拒否された検索条件 | `SearchQueryRejectedError` | GitHub が検索クエリを受理しなかった（HTTP 422）ことを表すエラー（`kind: 'validation'`） | 🔴 **`DomainValidationError`（値オブジェクトの不変条件違反）と混同しない**。載せる値は ACL が付与した `is:public` を除いた利用者入力のみ（`NFR-33`） |

### 2.2. 🔴 GitHub API の語との対応（腐敗防止層の変換表）

**外部の語をそのままドメインへ持ち込まない。** 変換は `src/infrastructure/github/mapper.ts` の 1 箇所だけで行う。

| GitHub API のフィールド | ドメインの名前 | nullable？（`dto.ts` の Zod スキーマが正） | 🔴 注意 |
|---|---|---|---|
| `subscribers_count` | `watcherCount` | 非 nullable（`z.number()`） | **これが「Watcher 数」の正体**（`FR-4`）。`watchers` / `watchers_count` は star と同値であり、使うと表示が間違う |
| `stargazers_count` | `starCount` | 非 nullable（`z.number()`） | 「人気」と呼ばない（偽 star の存在がミッションの出発点） |
| `forks_count` | `forkCount` | 非 nullable（`z.number()`） | |
| `open_issues_count` | `openIssueCount` | 非 nullable（`z.number()`） | **PR を含む**（GitHub の仕様）。UI 文言もこの事実に合わせる |
| `full_name` | `RepositoryId`（分解して保持） | 非 nullable（`z.string()`） | 文字列のまま持ち回らない |
| `owner.avatar_url` | `Owner.avatarUrl` | 非 nullable（`z.string()`） | |
| `pushed_at` | `lastPushedAt` | **nullable**（`z.string().nullable()`。コミットが一度もない空リポジトリで `null`。`SP-6` Issue #129 の実インシデント） | 「最終更新日」（`AR-1`）は **`pushed_at`** を使う（メタデータ更新で動く `updated_at` ではない）。🔵 **この規則は `RepositoryDetail.lastPushedAt` にも同様に適用する**（`pushed_at ?? updated_at` のフォールバックも一覧側の `toSearchResult` と同一・Issue #334 F-3） |
| `updated_at` | `lastUpdatedAt` | 現状の実装は非 nullable（`z.string()`）として扱っている。GitHub API 一次情報を継続確認しない限り将来変更されうる前提で扱う（`CP-2`） | 同上（`pushed_at` の代替としてのみ使う） |
| `topics` | `topics` | optional（`z.array(z.string()).optional()`） | |
| `language` | `primaryLanguage` | **nullable**（`z.string().nullable()`） | 「言語」だけだと `Locale` と紛れる |
| `total_count` | `SearchResult.totalCount` | 非 nullable（`z.number()`） | GitHub 検索は上限があるため **概算**。UI で「約」と表現する余地を残す |

🔴 **`starCount` と `Gem.stars` の名前の衝突について（`SP-14`）**: 上表の `starCount` は **GitHub API → `RepositorySummary` / `RepositoryDetail`** の変換規則であり、`src/infrastructure/github/mapper.ts` の 1 箇所だけに適用される。一方 `Gem.stars`（`src/domain/model/gem.ts`）は **Gem Index の候補プール（Ecosyste.ms 由来の静的 JSON）** から来る別コンテキストの値で（§6 の **Gem Index コンテキスト**）、変換箇所も供給元も異なる。したがって現状は「同じ概念に 2 つの名前がある」のではなく「**別コンテキストの同名概念が別の識別子を持っている**」状態である。

- ⚠️ ただし将来 2 コンテキストが同じ画面で混ざると読み手が取り違える。**`Gem.stars` を `starCount` へ寄せて統一するかどうかは別 Issue として扱う**（本ファイルは衝突の存在を明示するに留め、`gem.ts` の識別子は `SP-14` の PR では変更しない）。
- 🔴 **鮮度も異なる**（初見ユーザーのフィードバック⑦・Issue #308）: `RepositorySummary.starCount` / `RepositoryDetail.starCount` は GitHub API のライブ値（`ADR 0005` の TTL でキャッシュ）だが、`Gem.stars` / `Gem.dependentCount` は Ecosyste.ms がクロールした時点のスナップショットで、銘柄ごとにクロール時点が異なり実測で最大 2.7 年ばらつく。一覧（`Gem`）と詳細（`Repository`）で star 数が食い違って見えるのはこのため（バグではなく設計上の必然）。詳細は [ADR 0014](../../adr/0014-zero-query-daily-digest.md) §5 項番 8。

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
| `SortOrder` | `relevance` / `stars` / `updated`（`AR-2`）。🔴 **`gem-index`（`SP-16`）は `D-33`（2026-08-21）により撤去済み**。候補プールの被覆率不足で機能として成立しなかったため（[`open-questions.md`](../../02_requirements/open-questions.md) `D-33`）。旧 URL の `sort=gem-index` は不正値として既定値へ丸める | 同上 |
| `Locale` | `ja` / `en`（`AR-4`） | 既定ロケールに倒す |
| `CacheKey` | 名前空間 + 正規化済みの構成要素（`NFR-18`） | 生成関数以外で組み立てない |
| `DateSeed` | 🔴 **`YYYYMMDD` の 8 桁数字**（UTC）かつ **実在する日付**（`20260231` は不可・`Date.UTC` の往復一致で検証）。日次ダイジェストの唯一のシード（[ADR 0014](../../adr/0014-zero-query-daily-digest.md) §2.2・`src/domain/model/date-seed.ts`） | `parse` は `DomainValidationError`。`tryParse(raw, now)` は **不正値・未指定を当日（UTC）へ倒す**（URL の `?date=` 改変で 500 にしない・ADR 0014 §2.2） |
| `GemIndex` | **被依存数のパーセンタイル順位 − star のパーセンタイル順位**（`ADR 0009` §2.1・`src/domain/model/gem-index.ts`）。`gemIndex(value)` は有限数のみ、`computeGemIndex(dependentRank, starRank)` は入力を **0〜100** に制限する（Ecosyste.ms の `rankings` の値域）。🔴 **算出式と値域規則の実体は `src/domain/model/gem-index.rules.mjs`（依存ゼロの純関数）が単一正本**（#276）。本番の候補プール生成（`tools/gem-pool/pipeline.mjs`）も同じファイルを import するため、規則を写した第 2 の実装を作らない | `DomainValidationError`。🔴 **値が小さいほど上位**（`rankings` は 0 が最上位。並べ替えは昇順）。健全性（`criticality_score` / Scorecard）と 1 つのスコアに合算しない（`ADR 0009` §2.2） |
| ~~`GemFacet`~~ | 🔴 **`D-33`（2026-08-21）により撤去**（`{ gemIndex: GemIndex; dependentCount: number }`・旧 `src/domain/model/gem.ts`）。`SP-16` が検索結果（`RepositorySummary`）を候補プール（`Gem`）と突合し Gem Index 順に並べ替えるために持っていた型で、`gemFacetKey` / `toGemFacetMap` / `sortByGemIndex`（旧 `src/domain/model/gem-index.ts`）とともに削除済み。並べ替え適用先（検索結果一覧）が撤去されたため、突合専用のこの型に存在理由がなくなった。**`GemIndex` 型・`computeGemIndex` は撤去しない**（「今日の Gem」＝日次ダイジェストが使い続ける） | （撤去済み） |

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

**`RepositoryFullName` の 2 系統（厳格版 / 許容版・実データ 62,783 件で実測・#141 系）**: 上記「ブランド型 + スマートコンストラクタ」は原則だが、`RepositoryFullName`（`src/domain/model/repository-full-name.ts`）だけは **目的の異なる 2 つの判定系統** を同じファイルに持つ。

| 系統 | 関数 | 判定内容 | 返り値 | 使う場面 |
|---|---|---|---|---|
| **厳格版** | `repositoryFullName` / `tryRepositoryFullName` | GitHub の命名規則そのもの（`owner` は英数字とハイフンのみ・先頭末尾ハイフン不可・最大 39 文字。`repo` は `[A-Za-z0-9._-]+`・`.` `..` 単体不可・最大 100 文字） | `RepositoryFullName`（ブランド型） | GitHub の命名規則を不変条件として保証したい場面（新規作成時の入力検証） |
| **許容版** | `isLenientRepositoryFullName` / `tryParseLenientRepositoryFullName` | スラッシュ 1 個で 2 分割でき、両セグメントが空白を含まず `.` / `..` 単体でないことだけ | `{ readonly owner: string; readonly name: string }`（**生の `string` の組・ブランド型ではない**） | 実データの読み取り（候補プール JSON のパース・一覧行の描画・検索の同伴指定 URL 解釈） |

**なぜ緩い方が要るか**: GitHub リポジトリ実データ 62,783 件を両系統で全件突合したところ、**厳格版は 26 件（ユニーク owner 25 件）を拒否した**。すべて「owner が末尾ハイフンで終わる実在リポジトリ」（例: `Qix-/color-convert`・`qix-/node-is-arrayish`・`main--/rust-timerfd`）。GitHub 自体は現在ハイフン終わりの owner 名の作成を禁止しているが、命名規則変更前に作られた既存アカウントは生き残っている。候補プール（インフラ層が読む配信データ）や一覧画面（UI 層が描く行）はこの実データをそのまま扱うため、厳格版で弾くと実在する正当な行が消える・リンクが壊れる。

🔴 **許容版がブランド型を返さない理由**: 上記の「ブランド型 + スマートコンストラクタ」は **GitHub の命名規則という不変条件を保証したい値** に対する形であり、許容版は意図的にこの形を取らない。許容版は末尾ハイフン owner のような「本来の命名規則には違反するが実在する」値をそのまま素通りさせる設計であり、GitHub の命名規則そのものを不変条件として検証しない。ブランド型で包むと「`RepositoryFullName` 型である＝厳格版の不変条件を満たす」という既存の意味が壊れるため、許容版は素の `{ owner, name }` を返すに留める。

**使い分け**: 実データの読み取り（配信 JSON のパース・一覧行の描画・検索の同伴指定 URL 解釈）→ 許容版を使う。GitHub の命名規則そのものを検証したい（新規作成時の入力検証・ドメインの不変条件として "正しい owner/repo 名" を保証したい）→ 厳格版を使う。

🔴 **厳格版はインフラ層・UI 層の実データ読み取りには使わないこと**。実在データの一部を拒否し、一覧からの消失・リンク破損を招く（`static-gem-index.ts` / `static-gem-digest.ts` / `gem-list.tsx` は過去に独自の緩い判定を重複実装していたが、許容版へ統合済み）。

**`CacheKey` の実装位置（Issue #67・Issue #89 で改訂）**: **ブランド型の定義** は `src/domain/ports/cache-port.ts`（`CachePort` と同じファイル）に置く — `CachePort.get` / `set` / `invalidate` の引数を `key: CacheKey` にして、生成関数を経ない生の `string` を渡すとコンパイルエラーになるよう型で強制するため（ARCH-1 により domain は infrastructure を import できず、ポート側で型を持つほかない）。**生成関数（キーの組み立て）** は引き続き `src/infrastructure/platform/cache-key.ts` に置く（`CachePort` の実装と同じ層。キー形式が `CachePort` 実装詳細と不可分なため・`src/domain/model/` ではない）。domain 側はブランド型を **定義するだけ** で構築しない。生成関数は `searchResultCacheKey(query: SearchQuery)` / `repositoryCacheKey(owner, name)` / `readmeCacheKey(owner, name)` の 3 本。正規化は `trim → toLowerCase → encodeURIComponent`、利用者識別子は含めない。実際のキー形式:

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
- **なぜ必要か**: キーが検索条件だけで構成されていると、**同一 isolate が生存している間**（および将来 L3 の外部ストアを導入した場合は、その TTL が切れるまで）**古い意味の値が入ったエントリがヒットし続ける**。バージョンを上げれば全キーが別物になり、既存エントリを一括で論理的に無効化できる（明示的なパージ機構を持たずに済む）。⚠️ 現行の L2 は isolate 内メモリの `InMemoryCache` であり、デプロイで isolate が入れ替われば内容自体は失われる（[Cloudflare インフラ設計](../infrastructure/cloudflare-infrastructure.md) §4.2 / [ADR 0005](../../adr/0005-cache-port-yagni-exception-and-ttl.md)）。バージョンセグメントは「デプロイで消えること」に依存せずに無効化できる手段として持つ。
- **改訂履歴**: **導入前**（バージョンセグメントなし・`v1` は一度も生成されていない）/ `v2` バージョンセグメントの導入とあわせ、検索を公開リポジトリ限定（`is:public`）にして同じ検索条件に対する結果の範囲が変わったため `v2` から開始（Issue #142・`NFR-33`）。

---

## 5. ドメインサービス

| サービス | 責務 | 状態 |
|---|---|---|
| `GemIndex` | 被依存数と star の乖離から Gem 度（過小評価度）を算出する | ✅ **`SP-14` で実装済み**。🔴 **置き場所は `src/domain/model/gem-index.ts`**（値オブジェクト + 算出関数 `computeGemIndex`）。🔴 **式と値域規則そのものは同じディレクトリの `gem-index.rules.mjs` が単一正本**（#276。`node` で直接実行される候補プール生成バッチが TypeScript を import できないため、両者が共有できる依存ゼロの純関数として切り出してある。`.ts` 側はそこへ型・ブランド・`DomainValidationError` を被せる層）。**専用のサービス層（`src/domain/services/`）は作らない** — 実体は状態を持たない純粋関数 1 本であり、値オブジェクトのスマートコンストラクタと同じファイルに置くのが最も単純だから（`architecture-rules.md` の YAGNI）。当初 `src/domain/services/` に置き場所を確保する計画だったが、実装時に不要と判断して撤回した |

| 照合規則（`gem-keyword`） | 検索語と候補プールのエントリを **単語境界一致** で突き合わせる規則を持つ（`tokenizeQuery` / `tokenizeIdentifier` / `matchesAllTokens` / `selectMostSelectiveToken`・`D-37`） | ✅ **`SP-19` で実装済み**。🔴 **置き場所は `src/domain/model/gem-keyword.ts`**（`GemIndex` と同じく **値オブジェクト脇の純粋関数** として置き、`src/domain/services/` は作らない）。🔴 **本ファイルが照合規則の唯一の正本** — `GemIndexPort#search` の実装はここの純粋関数だけを使い、infra 層・UI 層で独自の照合（部分一致・あいまい一致）を再実装しない。依存なし・例外なしの純粋関数だけを置く（`ARCH-1`） |

- 健全性スコアは **自作しない**（OpenSSF に依存する・`GR-2` / `Q-1` / `Q-2`）。ドメインサービスとして再実装する誘惑を明示的に禁じる。
- 上表のとおり **`src/domain/services/` ディレクトリは存在しない**。ドメインサービスに見えるものが出てきたら、まず「値オブジェクトの関数として置けないか」を先に問う。

---

## 6. 境界づけられたコンテキストと腐敗防止層

| コンテキスト | 位置づけ | 関係 |
|---|---|---|
| **Search**（MVP） | 本アプリの中核。検索・一覧・詳細 | — |
| **Gem Index**（Phase 2） | 被依存数・健全性を扱う | Search とは **別コンテキスト**。同じ `Repository` でも持つ属性が違う。共通化を急がない。🔴 **両コンテキストの突合（`SP-16`・`GemFacet` 経由で検索結果へ Gem Index を適用する経路）は `D-33` により撤去済み**。現在は「今日の Gem」（日次ダイジェスト）に閉じたコンテキストとして存在する |
| **GitHub**（外部・上流） | データ源 | 🔴 **腐敗防止層（`src/infrastructure/github/`）を必ず挟む**。上流の変更に本体を追随させない |
| **Ecosyste.ms / OpenSSF**（Phase 2・外部・上流） | 被依存数・健全性の供給元 | 同じく ACL を挟む。`RepositoryQueryPort` と別ポートにする → ✅ **`SP-14` で `GemDigestPort`（`src/domain/ports/gem-digest-port.ts`・`listCandidates()` 1 本）として分離済み**。候補プールはバッチ生成の静的 JSON 経由で読むため、Worker から Ecosyste.ms を直接叩かない（`D-28`） |

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
