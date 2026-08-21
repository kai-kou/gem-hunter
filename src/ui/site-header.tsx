import Link from 'next/link'
import type { Locale } from '../domain/model/locale'
import { LocaleSwitcher, type LocaleSwitcherLabels } from './locale-switcher'
import { LoginLink, type LoginLinkLabels } from './login-link'

export type SiteHeaderProps = {
  locale: Locale
  currentPath: string
  title: string
  localeSwitcherLabels: LocaleSwitcherLabels
  isLoggedIn: boolean
  showAuthLink: boolean
  /** `showAuthLink=true` のときだけ必須（呼び出し側で保証）。 */
  authLabels?: LoginLinkLabels
}

/**
 * 一覧・詳細・404 共通のヘッダー（Issue #347）。Server Component のまま（`'use client'` 不要）。
 *
 * 左にツールタイトル（`h1 > Link(/{locale})`・ロゴ画像 + テキスト）、右に言語切替 + ログイン導線
 * （`justify-between`）を置く。「言語設定は頻繁に触れないので画面右上へ」というユーザー指示
 * （Issue #347）を満たす配置（`content/discussions/ui_image_assets_20260821` lead 裁定）。
 *
 * ロゴ画像は `public/images/logo.webp` として生成・配置済み（Issue #347・`tools/ui-assets/`）。
 * `alt=""` 単独（`aria-hidden` は重ねない・隣接するタイトルテキストで意味を伝えるため装飾扱い）。
 * `next/image` は使わない（INF-11）。
 *
 * ARCH-6: `src/ui/` は `src/usecases/` を import しない（本コンポーネントは表示のみ）。
 */
export function SiteHeader({
  locale,
  currentPath,
  title,
  localeSwitcherLabels,
  isLoggedIn,
  showAuthLink,
  authLabels,
}: SiteHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2">
      <h1 className="text-base font-semibold">
        <Link
          href={`/${locale}`}
          className="text-primary inline-flex items-center gap-2 rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- INF-11: next/image 最適化は使わない */}
          <img
            src="/images/logo.webp"
            alt=""
            width={24}
            height={24}
            loading="eager"
            decoding="async"
            className="shrink-0"
          />
          <span>{title}</span>
        </Link>
      </h1>
      <div className="flex flex-wrap items-center gap-2">
        <LocaleSwitcher currentLocale={locale} currentPath={currentPath} labels={localeSwitcherLabels} />
        {showAuthLink && authLabels ? <LoginLink isLoggedIn={isLoggedIn} labels={authLabels} /> : null}
      </div>
    </header>
  )
}
