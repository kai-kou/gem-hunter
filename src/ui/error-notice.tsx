import Link from 'next/link'
import type { ErrorKind } from '../domain/errors'
import { Button } from './components/button'
import type { ErrorPresentation } from './i18n/error-message'

type ErrorNoticeProps = {
  /** エラー種別（Issue #364）。装飾イラストの出し分けにのみ使う（文言は `presentation` 側の責務）。 */
  kind: ErrorKind
  /** `toErrorPresentation()` の結果（種別判定・文言整形は呼び出し側で済ませる）。 */
  presentation: ErrorPresentation
  /** 再試行先の URL（`US-24`）。省略すると再試行導線を出さない。 */
  retryHref?: string
  /** 再試行導線のラベル（`common.retry`）。 */
  retryLabel?: string
  /**
   * ログイン開始 URL（`AR-5`）。`presentation.loginHint` があるときだけ使う。
   * 🔴 これが無いときは `loginHint` 自体も出さない（リンクの無い案内だけを残すと行き止まりになる）。
   */
  loginHref?: string
  /** ログイン導線のラベル（`common.auth.login`）。 */
  loginLabel?: string
}

/**
 * `ErrorKind` ごとの装飾イラスト（Issue #364・7 種別すべてを網羅する対応表が仕様）。
 * `Record<ErrorKind, string>` にすることで `ErrorKind` へ新しい種別が増えたときに
 * 型エラーで検出できるようにする（網羅漏れの防止）。
 */
const ERROR_ILLUSTRATION: Record<ErrorKind, string> = {
  network: '/images/error-network.webp',
  rateLimitPrimary: '/images/error-rate-limit.webp',
  rateLimitSecondary: '/images/error-rate-limit.webp',
  auth: '/images/error-upstream.webp',
  upstream: '/images/error-upstream.webp',
  validation: '/images/error-validation.webp',
  // 404 は既存の not-found.webp を流用する（新規生成しない・Issue #364）。
  notFound: '/images/not-found.webp',
}

/**
 * エラーの内容と次の手を伝える表示専用コンポーネント（`AC-8` / `US-24`〜`US-26`）。
 *
 * - `role="alert"` で支援技術へ伝える（`NFR-12`）。`aria-live="assertive"` は
 *   併記しない（iOS VoiceOver の二重読み上げ回避・`ui-ux-guidelines.md` §7.2）
 * - 表示するのは props で渡された文言だけ。例外オブジェクト・HTTP ステータス等の
 *   内部情報はここでは一切足さない（`NFR-9` / `ui-ux-guidelines.md` §5.1）
 * - ログイン導線は `presentation.loginHint`（= 一次レート制限かつ未ログイン）**かつ** `loginHref` /
 *   `loginLabel` が渡されたときだけ出す。導線を出せないときは案内文も出さない（`US-25`）
 *
 * 導線は素の遷移なのでクライアント JS を必要としない（`LoginLink` / `BackLink` と同じ方針・`NFR-3`）。
 * `Button asChild` で `Link` をラップし、見た目だけのテキストリンクにしない — 高さが
 * `--size-control-xs`（24px）を下回るとタップターゲット要件に反するため
 * （`ui-ux-guidelines.md` §2.4 / §5.2「再試行ボタン」・`NFR-10`）。
 * 🔴 サイズは `size` variant 経由でのみ指定し、呼び出し側の `className` に生の `h-*` / `text-*` を
 * 書かない（`ui-ux-guidelines.md` §2.4・`tools/check_ui_dimensions.py` の登録済み呼び出しサイト）。
 * 色は `text-*` ユーティリティだと同機械検査がフォントサイズと区別できないため、トークンを直接
 * 参照する任意プロパティ記法で書く（値は `app/globals.css` のトークンで、生の色は書かない）。
 *
 * 🔴 配色は `tools/check_contrast.py` が検証しているトークンの組み合わせだけを使う（`NFR-13`）。
 * 面を `bg-danger/5` のようなアルファ合成で塗ると `--color-danger` の実効コントラストが
 * 4.36:1 まで落ち axe（wcag143・serious）に落ちるため、本文は素の背景の上に置き、
 * 枠線は検証済みの `--color-border` を使う。新しい合成色を足すときは同ツールへペアを追加すること。
 *
 * 🔴 **装飾イラスト（`ERROR_ILLUSTRATION`・Issue #364）は `role="alert"` の要素の外
 * （兄弟要素）に置く**（`ui-ux-guidelines.md` §7.4 追記の「ライブリージョンの外に置く」原則を
 * `role="status"` だけでなく本コンポーネントの `role="alert"` にも適用する）。エラー表示は
 * `loading-indicator.tsx` の読み込み中イラストのような構造上の例外に当たらない——読み込み中は
 * `<Suspense>` の fallback として `role="status"` の内側に **居続けることが遷移の通知に必須**
 * だが、`ErrorNotice` は一度確定した最終状態として 1 回描画されるだけで、`role="alert"` の
 * 内側に居続けなければならない構造上の理由が無い。したがって既定どおり外（兄弟）に出せる。
 * サイズは控えめ（64〜96px 角）にし、`width`/`height`（実配信ファイルは 256×256）を明示して
 * レイアウトシフトを防ぐ（`next/image` は使わない・`INF-11`）。
 */
export function ErrorNotice({
  kind,
  presentation,
  retryHref,
  retryLabel,
  loginHref,
  loginLabel,
}: ErrorNoticeProps) {
  const showRetry = retryHref !== undefined && retryLabel !== undefined
  const showLogin =
    presentation.loginHint !== undefined && loginHref !== undefined && loginLabel !== undefined

  return (
    <div>
      {/* eslint-disable-next-line @next/next/no-img-element -- INF-11: next/image の最適化は使わない */}
      <img
        src={ERROR_ILLUSTRATION[kind]}
        alt=""
        width={256}
        height={256}
        loading="eager"
        decoding="async"
        className="mb-3 h-20 w-20"
      />
      <div role="alert" className="border-border rounded-lg border p-4">
        <p className="[color:var(--color-danger)]">{presentation.message}</p>
        {showLogin ? (
          <p className="mt-2 [color:var(--color-fg-muted)]">{presentation.loginHint}</p>
        ) : null}
        {showRetry || showLogin ? (
          <div className="mt-3 flex flex-wrap gap-3">
            {showRetry ? (
              <Button asChild size="xl">
                <Link href={retryHref}>{retryLabel}</Link>
              </Button>
            ) : null}
            {showLogin ? (
              <Button asChild variant="outline" size="lg">
                <Link href={loginHref}>{loginLabel}</Link>
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
