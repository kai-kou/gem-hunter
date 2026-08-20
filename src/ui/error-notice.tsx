import Link from 'next/link'
import type { ErrorPresentation } from './i18n/error-message'

type ErrorNoticeProps = {
  /** `toErrorPresentation()` の結果（種別判定・文言整形は呼び出し側で済ませる）。 */
  presentation: ErrorPresentation
  /** 再試行先の URL（`US-24`）。省略すると再試行導線を出さない。 */
  retryHref?: string
  /** 再試行導線のラベル（`common.retry`）。 */
  retryLabel?: string
  /** ログイン開始 URL（`AR-5`）。`presentation.loginHint` があるときだけ使う。 */
  loginHref?: string
  /** ログイン導線のラベル（`common.auth.login`）。 */
  loginLabel?: string
}

/**
 * エラーの内容と次の手を伝える表示専用コンポーネント（`AC-8` / `US-24`〜`US-26`）。
 *
 * - `role="alert"` で支援技術へ伝える（`NFR-12`）。`aria-live="assertive"` は
 *   併記しない（iOS VoiceOver の二重読み上げ回避・`ui-ux-guidelines.md` §7.2）
 * - 表示するのは props で渡された文言だけ。例外オブジェクト・HTTP ステータス等の
 *   内部情報はここでは一切足さない（`NFR-9` / `ui-ux-guidelines.md` §5.1）
 * - ログイン導線は `presentation.loginHint`（= 一次レート制限かつ未ログイン）のときだけ出す（`US-25`）
 *
 * リンクは素の遷移なのでクライアント JS を必要としない（`LoginLink` / `BackLink` と同じ方針・`NFR-3`）。
 *
 * 🔴 配色は `tools/check_contrast.py` が検証しているトークンの組み合わせだけを使う（`NFR-13`）。
 * 面を `bg-danger/5` のようなアルファ合成で塗ると `--color-danger` の実効コントラストが
 * 4.36:1 まで落ち axe（wcag143・serious）に落ちるため、本文は素の背景の上に置き、
 * 枠線は検証済みの `--color-border` を使う。新しい合成色を足すときは同ツールへペアを追加すること。
 */
export function ErrorNotice({
  presentation,
  retryHref,
  retryLabel,
  loginHref,
  loginLabel,
}: ErrorNoticeProps) {
  const showRetry = retryHref !== undefined && retryLabel !== undefined
  const showLogin =
    presentation.loginHint !== undefined && loginHref !== undefined && loginLabel !== undefined
  const linkClassName = 'text-primary text-sm underline-offset-4 hover:underline'

  return (
    <div role="alert" className="border-border rounded-lg border p-4">
      <p className="text-danger text-sm">{presentation.message}</p>
      {presentation.loginHint ? (
        <p className="text-muted-foreground mt-2 text-sm">{presentation.loginHint}</p>
      ) : null}
      {showRetry || showLogin ? (
        <p className="mt-3 flex flex-wrap gap-4">
          {showRetry ? (
            <Link href={retryHref} className={linkClassName}>
              {retryLabel}
            </Link>
          ) : null}
          {showLogin ? (
            <Link href={loginHref} className={linkClassName}>
              {loginLabel}
            </Link>
          ) : null}
        </p>
      ) : null}
    </div>
  )
}
