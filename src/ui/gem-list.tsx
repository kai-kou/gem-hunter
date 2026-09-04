import Link from 'next/link'

import { DEFAULT_PER_PAGE } from '@/src/domain/model/per-page'
import { DEFAULT_SORT_ORDER } from '@/src/domain/model/sort-order'
import { formatMessage } from '@/src/shared/i18n/format-message'
import type { DigestMeta, GemPoolEntry } from '../domain/model/gem'
import { gemIndexValue } from '../domain/model/gem-index'
import type { Locale } from '../domain/model/locale'
import { tryParseLenientRepositoryFullName } from '../domain/model/repository-full-name'
import { AttributionNotice } from './attribution-notice'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'
import { LinkPendingHint } from './link-pending-hint'
import { buildSearchUrl } from './url/build-search-url'
import { GEM_LIST_SOURCE_PARAM_KEY, GEM_LIST_SOURCE_PARAM_VALUE } from './url/search-params'

/**
 * Gem 一覧（`/{locale}/gems`）が描画に必要とする値だけを持つ ViewModel。
 *
 * 🔴 **ポートの契約型（`GemPoolSearchResult`）を props に採らない**（`application-architecture.md`
 * §3 のデータフローは「ドメインモデル → ユースケース → ViewModel → UI」）。ポートは複数の
 * 消費者を持つ境界契約なので、直接採ると別の消費者の都合で表示契約が動く／UI 都合でポート面積が
 * 膨らむ、の両方が起きる（PR #440 Layer 1 指摘）。ページ側がユースケースの結果からここへ写す。
 */
export type GemListViewModel = {
  /** 表示順に並んだ 1 ページ分のエントリ（`gemIndex` 昇順）。**ここで並べ替えない**。 */
  readonly items: readonly GemPoolEntry[]
  /** 絞り込み結果の総件数（ページ内件数ではない）。 */
  readonly totalCount: number
  /** 実際に表示しているページ（1 始まり）。詳細から戻ったとき同じページへ帰るために使う。 */
  readonly effectivePage: number
  /**
   * 全語 AND が 0 件で 1 語へ緩めたときに、実際に使った語。緩和していなければ `null`。
   * 🔴 「緩和したか」と「使った語」を 2 つの値で持たない（片方だけ更新される状態を作らない）。
   */
  readonly relaxedToken: string | null
  /**
   * 🔴 **0 件の理由が「照合不能」か**（検索語は空でないのに、照合に使えるトークンが 1 つも
   * 取れなかった。日本語だけの検索語など）。判定の正本は `src/usecases/search-gems.ts`
   * （生の検索語 → トークン列の変換を持つ層）で、ここは受け取って文言を切り替えるだけ。
   * **必須フィールド**（既定値を付けない）: 省略できると呼び出し側の書き忘れが型で通り、
   * 日本語クエリの 0 件画面が「候補プールに載っていません」へ黙って化ける。
   */
  readonly unmatchableQuery: boolean
  /** 出典メタデータ（`D-29` の帰属表示）。 */
  readonly meta: DigestMeta
}

/**
 * Gem 一覧（`/{locale}/gems`）の文言。**UI コンポーネントに日本語を直書きしない**（`E-4`）。
 * テンプレート文字列のプレースホルダ（`{query}` / `{token}` / `{count}` / `{source}` /
 * `{license}`）は本コンポーネントが置換する（呼び出し側で置換済みの文字列を渡しても
 * 単に置換対象が無いだけで壊れない）。
 */
export type GemListLabels = {
  /** 見出し。検索語を埋める `{query}` を含む。 */
  heading: string
  /**
   * 0 件時の本文。🔴 **母集団を明示する文言を渡す**（`D-36`）: この一覧は 12 のパッケージ
   * レジストリの被依存数上位から作った限定的な候補プールが対象であり、載っていないことは
   * 評価が低いことを意味しない。
   *
   * ⚠️ こちらは **候補プールに載っていなかった** ときの説明。照合そのものができなかったとき
   * （日本語だけの検索語など）は `unmatchableQuery` を出す（2 つの空状態を取り違えない）。
   */
  empty: string
  /**
   * 照合不能時の本文（`view.unmatchableQuery` が `true` のとき）。🔴 **照合規則
   * （パッケージ名・リポジトリ名という英数字識別子に対する単語境界一致・`D-37`）と、
   * 利用者が次に取れる行動（英語のキーワードで試す）を含む文言を渡す**。
   */
  unmatchableQuery: string
  /** 全語 AND が 0 件で 1 語へ緩めたときの注記。使ったトークンを埋める `{token}` を含む。 */
  relaxedNotice: string
  /** 総件数の表示。整形済みの件数を埋める `{count}` を含む。 */
  totalCount: string
  /** star 数の `sr-only` ラベル（`★` の意味が言語間で伝わらないため）。 */
  starCount: string
  /** 利用パッケージ数の見出し語（可視・`domain-model.md` §2.1 が表示語まで正本）。 */
  dependentCount: string
  /** Gem Index の見出し語（可視）。 */
  gemIndexLabel: string
  /** レジストリの見出し語（可視）。 */
  registryLabel: string
  /** 帰属表示（`D-29`）。`{source}` / `{license}` を含む。 */
  attribution: string
  /** ライセンスリンクが新しいタブで開くことの `sr-only` 告知（`ui-ux-guidelines.md` §7.4a）。 */
  opensInNewTab: string
}

/**
 * ページ送り後にフォーカスを移す受け口（`ui-ux-guidelines.md` §7.1・`AC-8`）。
 * `app/` 側が `<FocusOnNavigate targetId={GEM_LIST_HEADING_ID} />` で参照する。
 */
export const GEM_LIST_HEADING_ID = 'gems-heading'

/**
 * Gem 候補プールの絞り込み結果一覧（`SP-19` / `D-37`）。表示だけを持つ Server Component。
 *
 * - 並び順は `view.items` の順序そのまま（`gemIndex` 昇順）。**ここで並べ替えない**
 *   （`gemIndex` は母集団相対の値で、UI で閾値・順序を作り直すと正本が 2 箇所に分かれる）
 * - ページネーション UI は持たない（`app/` 側の配線が扱う）。総件数の表示までにとどめる
 */
export function GemList({
  view,
  query,
  locale,
  labels,
}: {
  view: GemListViewModel
  /** 画面に出ている検索語（見出しと戻り先クエリに使う）。 */
  query: string
  locale: Locale
  labels: GemListLabels
}) {
  const localeTag = toIntlLocaleTag(locale)
  const numberFormat = new Intl.NumberFormat(localeTag)
  // Gem Index は差分スコアで小数・負値をとる。桁を揃えて小数 1 桁に丸める。
  const gemIndexFormat = new Intl.NumberFormat(localeTag, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })

  // 戻り先の保持（`SP-7` と同じ考え方）。URL 契約を組み立てる実装は `build-search-url.ts` の
  // 1 本だけ（`from` は付帯パラメータとして渡す）。sort / per_page は Gem 一覧が持たない条件
  // なので既定値を渡して省略させる。
  const backQuery = buildSearchUrl(
    '',
    {
      keyword: query,
      page: view.effectivePage,
      sort: DEFAULT_SORT_ORDER,
      perPage: DEFAULT_PER_PAGE,
    },
    { [GEM_LIST_SOURCE_PARAM_KEY]: GEM_LIST_SOURCE_PARAM_VALUE },
  )

  return (
    <>
      {/*
        🔴 ページ送り（クライアント遷移）の完了をフォーカス移動で伝えるための受け口
        （`ui-ux-guidelines.md` §7.1）。`tabIndex={-1}` はプログラムからのフォーカスだけを
        許し Tab 順には入れない。フォーカスリングは検索一覧の見出しと同じ意匠に揃える。
      */}
      <h2
        id={GEM_LIST_HEADING_ID}
        tabIndex={-1}
        // `query` は利用者が入力した任意長の文字列がそのまま入るため折り返し指定が要る（§3）。
        className="rounded-sm text-lg font-semibold break-words outline-none focus-visible:ring-3 focus-visible:ring-ring"
      >
        {formatMessage(labels.heading, { query })}
      </h2>
      {/*
        全語 AND が 0 件だったため 1 語へ緩めたことの明示（`D-37`）。一覧の **前** に出す。
        ライブリージョンにはしない（0 件の `role="status"` と二重に読み上げられるのを避ける・
        `ui-ux-guidelines.md` §7.2「ライブリージョンは 1 つ」）。
      */}
      {view.relaxedToken !== null ? (
        <p className="text-muted-foreground mt-2 text-sm break-words">
          {/* `token` は利用者の入力語がそのまま入る（最長 256 文字の連続文字列があり得る）。
              上の `<h2>` と同じく折り返し指定が要る（`ui-ux-guidelines.md` §3）。 */}
          {formatMessage(labels.relaxedNotice, { token: view.relaxedToken })}
        </p>
      ) : null}
      {/*
        🔴 空状態には理由が 2 つあり、説明も次の行動も違う（`D-36` / `D-37`）。
        ① 照合自体ができなかった（`unmatchableQuery`）→ 照合規則と次の行動を案内する
        ② 候補プールに載っていなかった（`totalCount === 0`）→ 母集団を明示する
        ⚠️ 「ヒットはあるがこのページには無い」（`totalCount > 0` かつ `items` が空）は
        どちらでもない。ページ範囲の問題を「候補プールに載っていない」と説明するのは
        **誤った理由** なので何も出さない（ページ番号の解決は `app/` 側が最終ページへ
        クランプするため、通常は到達しない防御的な分岐）。
      */}
      {view.unmatchableQuery ? (
        // 0 件は視覚表現だけにせず `role="status"` で支援技術にも伝える（§7.2）。
        // `role="alert"` は使わない（0 件は緊急の割り込みではない）。
        <p role="status" className="text-muted-foreground mt-4 text-sm">
          {labels.unmatchableQuery}
        </p>
      ) : view.totalCount === 0 ? (
        <p role="status" className="text-muted-foreground mt-4 text-sm">
          {labels.empty}
        </p>
      ) : (
        <>
          <p role="status" className="text-muted-foreground mt-2 text-sm">
            {formatMessage(labels.totalCount, { count: numberFormat.format(view.totalCount) })}
          </p>
          {view.items.length > 0 ? (
            <ul className="divide-border mt-2 divide-y">
              {view.items.map((entry) => {
                const repo = tryParseLenientRepositoryFullName(entry.repositoryFullName)
                return (
                  <li
                    // 🔴 `repositoryFullName` を key にする（`byRepo` のキーがその小文字なので
                    // 一意性が構造的に保証されている）。`registry/packageName` は
                    // `packageName` 欠損時に空文字で埋まる仕様のため同一ページ内で衝突する。
                    key={entry.repositoryFullName}
                    className="relative flex gap-3 py-4"
                    // E2E（`e2e/sp-19.spec.ts`）が並び順を機械的に検証するための値。可視テキストは
                    // ロケール桁区切り・丸めで表記が変わるため、生値を `data-` 属性で出す。
                    data-gem-index={String(gemIndexValue(entry.gemIndex))}
                    data-repository-full-name={entry.repositoryFullName}
                  >
                    {/*
                      avatar 画像（飼い主フィードバック「通常の一覧で表示している項目も含める」）。
                      🔴 候補プールの静的シャードには description/primaryLanguage/topics/lastPushedAt
                      が存在しない（実測確認済み）ため、GitHub API 呼び出しなしで足せるのは
                      avatar だけ。`repository-list.tsx` の 2 カラム構造をそのまま複製する
                      （器は揃え、載せる情報は変えない）。
                      🔴 `repo` が `null`（`owner/name` に割れない）のときは avatar も出さない
                      （壊れたリンクを出さないのと同じ判定を再利用し、壊れた画像 URL を出さない）。
                      Link の **外**（兄弟）に置く（`repository-list.tsx` と同じ配置理由）。
                      🔴 **なぜ `avatars.githubusercontent.com/u/{id}` ではないか**（`AR-11` の詳細）:
                      候補プールのシャードに `avatar_url` / owner の数値 ID の列が無く、`AR-11` の
                      方針でこの表示のためだけに GitHub API を追加で呼ばない。そのため公式には非推奨の
                      `github.com/{owner}.png` を使う。
                      ⚠️ **既知の制約**: owner のリネーム・削除後にスナップショットが古いままだと
                      404 になり avatar が表示されないことがある（Server Component のため
                      `onError` での差し替えはできない）。`bg-muted` を敷いておき、404 時も
                      壊れたアイコンではなく丸い無地のプレースホルダに見えるようにする。
                    */}
                    {repo ? (
                      // eslint-disable-next-line @next/next/no-img-element -- INF-11: next/image 最適化は使わない
                      <img
                        src={`https://github.com/${encodeURIComponent(repo.owner)}.png?size=80`}
                        // オーナー名は repositoryFullName として隣接テキスト表示されるため装飾扱い
                        // （ui-ux-guidelines.md §7.4・repository-list.tsx と同じ方針）
                        alt=""
                        width={40}
                        height={40}
                        loading="lazy"
                        decoding="async"
                        className="size-10 shrink-0 rounded-full bg-muted"
                      />
                    ) : null}
                    {/* 第三者由来テキスト（`repositoryFullName` / `packageName`）の折り返し。
                        この `<div>` は flex アイテムだが `min-w-0` で floor を外してあるため、
                        ここに `break-words` を 1 回当てれば配下へ継承で届く
                        （判定規則は `ui-ux-guidelines.md` §3・`repository-list.tsx` と同型）。 */}
                    <div className="min-w-0 flex-1 break-words">
                      {/*
                        詳細ページ（独立 URL・`AC-4`）への遷移。カード全体をクリック可能にするが
                        `<a>` で全体を包まず、リポジトリ名だけをリンクにして `::after` で領域を
                        広げる（`ui-ux-guidelines.md` §4.3）。`::after` は `<li className="relative">`
                        基準なので avatar の上にもクリック領域が及ぶ。
                        🔴 `repositoryFullName` が `owner/name` に割れない値のときはリンクを作らない
                        （壊れたリンクを出すより、テキストとして見せる方が害が小さい）。
                      */}
                      {repo ? (
                        <Link
                          href={`/${locale}/repos/${encodeURIComponent(repo.owner)}/${encodeURIComponent(repo.name)}${backQuery}`}
                          // ネイティブ <a> の既定フォーカスは太さが足りないため `ring-3` に揃える（§7.3）。
                          className="text-primary rounded-sm font-medium underline-offset-4 outline-none after:absolute after:inset-0 hover:underline focus-visible:ring-3 focus-visible:ring-ring"
                        >
                          {entry.repositoryFullName}
                          {/* 詳細ページは `AC-5` の 404 ステータスを保つため `loading.tsx` を持てない（Issue #167）。
                              遷移中であることは `<Link>` の内側のこのヒントで伝える（`US-22`）。 */}
                          <LinkPendingHint />
                        </Link>
                      ) : (
                        <span className="font-medium">{entry.repositoryFullName}</span>
                      )}
                      <p className="text-muted-foreground mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                        {/* この `<span>` は `p.flex.flex-wrap` の flex アイテムなので `wrap-anywhere`
                            を直付けする（`ui-ux-guidelines.md` §3 の表・`repository-list.tsx` の
                            topics `<li>` と同じ理由）。パッケージ名は第三者由来で区切りが無いことがある。 */}
                        <span className="wrap-anywhere">{entry.packageName}</span>
                        <span>
                          {labels.registryLabel} {entry.registry}
                        </span>
                        <span>
                          <span aria-hidden="true">★ </span>
                          <span className="sr-only">{labels.starCount} </span>
                          {numberFormat.format(entry.stars)}
                        </span>
                        {/*
                          🔴 メタ情報は可視ラベルを添える（`ui-ux-guidelines.md` §4.2）。
                          ここだけ裸の数値にすると、支援技術なしの利用者には star の別表記なのか
                          利用パッケージ数なのか判別できない（`sr-only` の方が情報量が多い逆転）。
                        */}
                        <span>
                          {labels.dependentCount} {numberFormat.format(entry.dependentCount)}
                        </span>
                        <span>
                          {labels.gemIndexLabel}{' '}
                          {gemIndexFormat.format(gemIndexValue(entry.gemIndex))}
                        </span>
                      </p>
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : null}
        </>
      )}
      {/*
        帰属表示（`D-29`）はトップページと同じ `AttributionNotice` を使う（実装を 2 本持たない）。
        `gems.attribution` は `{generatedAt}` を含まないため生成時刻のノードは描かれない。
      */}
      <AttributionNotice
        meta={view.meta}
        labels={{
          attribution: labels.attribution,
          opensInNewTab: labels.opensInNewTab,
        }}
        locale={locale}
      />
    </>
  )
}
