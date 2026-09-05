/**
 * キーワード非依存の発見面（日次ダイジェスト・`SP-14` / `ADR 0014`）のドメイン型。
 *
 * 🔴 本ファイルは **層間の契約（型定義）だけ** を持つ。値オブジェクトのスマートコンストラクタ
 * （`GemIndex` の算出・検証）は `src/domain/model/gem-index.ts`、選定ロジックは
 * `src/usecases/get-daily-digest.ts` に置く（ロジックを型ファイルへ混ぜない）。
 */

import type { GemIndex } from './gem-index'

/**
 * ダイジェストに載る 1 件の Gem。候補プール（静的 JSON・`D-28`）の 1 エントリに対応する。
 *
 * 🔴 Ecosyste.ms の生テキスト（description 等）は再配信しない（`D-29`）。ここに持つのは
 * 数値・識別子・自作の派生値（`GemIndex`）に限る。表示名・リンクはパッケージ名／リポジトリ
 * URL という識別子であって生テキストではない。
 */
export type Gem = {
  /** npm パッケージ名（エコシステム内で一意・候補プールの識別子）。 */
  readonly packageName: string
  /** GitHub リポジトリ完全名（`owner/repo`）。詳細画面へのリンク解決に使う。 */
  readonly repositoryFullName: string
  /**
   * 被依存パッケージ数（Ecosyste.ms `dependent_packages_count`・実利用の量）。
   * 🔴 GitHub API のライブ値ではなく **Ecosyste.ms が独自にクロールした値**（`stars` と同じ出所・
   * 鮮度の注意点は `stars` の JSDoc を参照）。
   */
  readonly dependentCount: number
  /**
   * star 数（GitHub `stargazers_count`・注目度）。
   *
   * 🔵 **出所と鮮度（Issue #310 で刷新・元は `SP-16` 初見ユーザーフィードバック議論で判明した課題）**:
   * かつては Ecosyste.ms が独自にクロールした値をそのまま使っており、銘柄ごとにクロール時点が
   * 大きくばらつく問題があった（サンプル調査 20 件中 6 件が 700 日超・最大 2.7 年前）。
   * `tools/generate_gem_digest.mjs`（`tools/gem-pool/github-stars.mjs`）が **バッチ生成時点で
   * GitHub API から取り直す**ため、この値は「その日のダイジェスト生成時点」の GitHub の値である。
   * ただし詳細画面（`GithubRepositoryQuery.findDetail` 経由）はユーザーが開いた瞬間のライブ値を
   * 返すため、生成後に star 数が変動していれば両者はなお一致しないことがある（取得タイミングの
   * 違いによる差・出所は同じ GitHub API）。
   *
   * 🔴 個別リポジトリの再取得に失敗した場合（404・レート制限等）は **旧値（Ecosyste.ms 由来）を
   * 保持したままスキップする**（バッチ全体は止めない・`refreshStars` の完了条件 2）。
   *
   * `dependentCount` は引き続き Ecosyste.ms 由来（再取得の対象外・Issue #310 のスコープ注記）。
   */
  readonly stars: number
  /**
   * 過小評価度（`ADR 0009` の `Gem Index`）。被依存数パーセンタイル順位 − star パーセンタイル
   * 順位。並び順にのみ使い、健全性（`criticality_score` / Scorecard）とは合算しない。
   */
  readonly gemIndex: GemIndex
}

/**
 * 出典メタデータ（`D-29` の帰属表示・必須）。候補プール JSON のトップレベルに載り、UI の
 * 出典表示（「このデータについて: … Ecosyste.ms（CC BY-SA 4.0）…」）へそのまま流す。
 */
export type DigestMeta = {
  /** データ提供元（例 `Ecosyste.ms`）。 */
  readonly source: string
  /** データ提供元のトップページ URL（例 `https://ecosyste.ms/`）。出典表示のリンク先（`F-6`）。 */
  readonly sourceUrl: string
  /** ライセンス識別子（例 `CC BY-SA 4.0`）。 */
  readonly license: string
  /** ライセンス原文への URL。 */
  readonly sourceLicenseUrl: string
  /** 候補プールを生成したバッチの実行時刻（ISO 8601・UTC）。鮮度の目安として表示する。 */
  readonly generatedAt: string
}

/**
 * ある日付シードに対して確定した「今日の Gem」。
 *
 * `date` は決定論的生成の唯一のシード（`ADR 0014` §2.2）。同じ `date` は全ユーザーで同じ
 * `items` を返し、リロードしても再現し、`date` が変わると顔ぶれが入れ替わる。`items` は
 * 有限件数（既定 5 件・実データで確定するまで暫定）。
 */
export type DailyDigest = {
  /** この一覧を確定させた UTC 日付文字列（`YYYYMMDD`）。 */
  readonly date: string
  /** 表示順に並んだ Gem。空配列もありうる（候補プール枯渇時）。 */
  readonly items: readonly Gem[]
  /** 出典メタデータ（`D-29`）。 */
  readonly meta: DigestMeta
}

/**
 * Gem 候補プール（レジストリ別シャードの全量・`D-38`）の 1 レコード。
 *
 * `Gem` に、どのレジストリから収集したかを足したもの（`D-36` の緊急除外・一覧の出所表示に使う）。
 * 🔴 `registry` は **レジストリ名そのもの**（`npmjs.org` / `pypi.org` / `repo1.maven.org` …）で
 * あって、エコシステム名（`npm` / `pypi` / `cargo` …）ではない（`domain-model.md` §2.1 の
 * 「レジストリ」と「エコシステム」は似て非なる 2 語）。成層化・パーセンタイル母集団の区切りに
 * 使うのは `registry` の方。
 */
export type GemPoolEntry = Gem & { readonly registry: string }
