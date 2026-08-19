import Link from 'next/link'
import { locale as toLocale, LOCALES, type Locale } from '../domain/model/locale'
import { buttonVariants } from './components/button'
import { buildLocaleUrl } from './url/build-locale-url'

type LocaleSwitcherLabels = {
  navLabel: string
  localeNames: Record<(typeof LOCALES)[number], string>
}

type LocaleSwitcherProps = {
  /** 現在表示中のロケール（`aria-current` の判定に使う）。 */
  currentLocale: Locale
  /**
   * 現在のパス（クエリ文字列を含んでよい）。呼び出し元（`app/[locale]/layout.tsx` 等・
   * 統合担当が配線）が `usePathname()` 等から組み立てて渡す。
   */
  currentPath: string
  labels: LocaleSwitcherLabels
}

/**
 * 言語切替 UI（US-2・SP-8）。ja/en への GET リンクの集合として実装し、`search-form.tsx` /
 * `sort-picker.tsx` と同じくクライアント JS を持たない（NFR-3）。
 *
 * 表示名（labels.localeNames）は言語の自称（endonym・「日本語」「English」）を使い、
 * 現在の UI 言語に関わらず両方とも変えない（自分の言語を探せることを優先する一般的な言語切替の
 * UX 慣行。実装手段レベルの判断のため確認不要・SD-3 対象外・1 行記録）。
 *
 * ARCH-6: `src/ui/` は `src/usecases/` を import しない（本コンポーネントは表示のみ）。
 * ドメインへは `Locale` 型・値オブジェクト（`locale()` / `LOCALES`）のみ依存する。
 */
export function LocaleSwitcher({ currentLocale, currentPath, labels }: LocaleSwitcherProps) {
  return (
    <nav aria-label={labels.navLabel} className="flex flex-wrap items-center gap-1">
      {LOCALES.map((option) => {
        const isCurrent = option === currentLocale
        const href = buildLocaleUrl(currentPath, toLocale(option))

        return (
          <Link
            key={option}
            href={href}
            aria-current={isCurrent ? 'true' : undefined}
            className={buttonVariants({
              variant: isCurrent ? 'secondary' : 'ghost',
              size: 'sm',
            })}
          >
            {labels.localeNames[option]}
          </Link>
        )
      })}
    </nav>
  )
}
