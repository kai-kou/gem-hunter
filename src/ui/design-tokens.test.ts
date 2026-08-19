import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * デザイントークンの回帰テスト（NFR-13 / WCAG 1.4.11）。
 *
 * jsdom は CSS レイアウトエンジンを持たず実測高さを取得できないため、
 * ここではトークンの「宣言値」と「参照されているか」を検証する。
 * 実描画での高さ実測は E2E（SP-4）の担当。
 */

const REPO_ROOT = join(__dirname, '..', '..')
const COMPONENTS_DIR = join(REPO_ROOT, 'src', 'ui', 'components')
const componentFiles = readdirSync(COMPONENTS_DIR).filter((file) => file.endsWith('.tsx'))
const globalsCss = readFileSync(join(REPO_ROOT, 'app', 'globals.css'), 'utf8')
const inputSource = readFileSync(join(COMPONENTS_DIR, 'input.tsx'), 'utf8')
const buttonSource = readFileSync(join(COMPONENTS_DIR, 'button.tsx'), 'utf8')

/** Tailwind CSS v4 の `--spacing` 既定値（0.25rem = 4px）。 */
const SPACING_BASE_PX = 4

/** `--spacing-<name>: calc(var(--spacing) * N)` を px に解決する。 */
function controlSizePx(name: string): number {
  const pattern = new RegExp(
    `--spacing-${name}:\\s*calc\\(\\s*var\\(--spacing\\)\\s*\\*\\s*([\\d.]+)\\s*\\)`,
  )
  const matched = globalsCss.match(pattern)
  if (matched === null) {
    throw new Error(`--spacing-${name} が calc(var(--spacing) * N) 形式で定義されていない`)
  }
  return Number(matched[1]) * SPACING_BASE_PX
}

/** `:root { ... }` / `.dark { ... }` ブロックからトークンの宣言値を取り出す。 */
function tokenValue(selector: string, token: string): string {
  const block = globalsCss.match(new RegExp(`${selector}\\s*\\{([\\s\\S]*?)\\n\\}`))
  if (block === null) {
    throw new Error(`${selector} ブロックが見つからない`)
  }
  const matched = block[1].match(new RegExp(`(?:^|\\n)\\s*--${token}:\\s*([^;]+);`))
  if (matched === null) {
    throw new Error(`${selector} に --${token} が定義されていない`)
  }
  return matched[1].trim()
}

/**
 * グレースケール `oklch(L 0 0)` の相対輝度（WCAG 2.x 定義）。
 * 彩度 0 なら OKLab の L を 3 乗した値が線形 sRGB の全チャンネル値になり、
 * 相対輝度（0.2126R + 0.7152G + 0.0722B）もその値と一致する。
 */
function relativeLuminanceOfNeutralOklch(value: string): number {
  const matched = value.match(/oklch\(\s*([\d.]+)\s+0\s+0\s*\)/)
  if (matched === null) {
    throw new Error(`グレースケールの oklch(L 0 0) 形式ではない: ${value}`)
  }
  return Number(matched[1]) ** 3
}

/** WCAG のコントラスト比。 */
function contrastRatio(a: number, b: number): number {
  const [lighter, darker] = a >= b ? [a, b] : [b, a]
  return (lighter + 0.05) / (darker + 0.05)
}

describe('コントロールサイズトークン', () => {
  it('主要コントロールの既定（control-md）が 44px である', () => {
    expect(controlSizePx('control-md')).toBe(44)
  })

  it('副次コントロール用（control-sm）と余裕を持たせる用（control-lg）も 4px グリッドに載る', () => {
    expect(controlSizePx('control-sm')).toBe(36)
    expect(controlSizePx('control-lg')).toBe(48)
  })

  it('コンポーネントの既定サイズを生の高さ値で書かない（shadcn add した分も含む）', () => {
    // shadcn の既定（radix-nova）は密な管理画面向けで h-8(32px)。素通しさせないための回帰ゲート。
    // xs / sm / icon-* バリアントは密な文脈用として意図的に小さいため対象外。
    for (const file of componentFiles) {
      const source = readFileSync(join(COMPONENTS_DIR, file), 'utf8')
      const defaultSizes = [...source.matchAll(/default:\s*\n?\s*'([^']*)'/g)].map((m) => m[1])
      const baseClasses = [...source.matchAll(/cn\(\s*\n?\s*'([^']*)'/g)].map((m) => m[1])
      // cva の第一引数（ベースクラス）。shadcn の生成物は二重引用符で直接渡す
      const cvaBases = [...source.matchAll(/cva\(\s*\n?\s*["']([^"']*)["']/g)].map((m) => m[1])

      for (const classNames of [...defaultSizes, ...baseClasses, ...cvaBases]) {
        expect(classNames, `${file}: 既定サイズは h-control-* トークンで指定する`).not.toMatch(
          /(^|\s)h-\d/,
        )
      }
    }
  })

  it('主要コントロール（Input / Button の既定）が control-md を参照する', () => {
    expect(inputSource).toContain('h-control-md')
    expect(buttonSource.match(/default:\s*\n?\s*'([^']*h-[^']*)'/)?.[1]).toContain('h-control-md')
  })
})

describe('入力欄のフォントサイズ（iOS / iPadOS Safari のオートズーム対策）', () => {
  it('ブレークポイントで 16px 未満に落とさない', () => {
    expect(inputSource).toContain('text-base')
    expect(inputSource).not.toContain('md:text-sm')
  })
})

describe('フォーカスリングのコントラスト（WCAG 1.4.11 Non-text Contrast・AA）', () => {
  it('ライトモードで背景に対し 3:1 以上ある', () => {
    const ring = relativeLuminanceOfNeutralOklch(tokenValue(':root', 'ring'))
    const background = relativeLuminanceOfNeutralOklch(tokenValue(':root', 'background'))
    expect(contrastRatio(ring, background)).toBeGreaterThanOrEqual(3)
  })

  it('ダークモードで背景に対し 3:1 以上ある', () => {
    const ring = relativeLuminanceOfNeutralOklch(tokenValue('\\.dark', 'ring'))
    const background = relativeLuminanceOfNeutralOklch(tokenValue('\\.dark', 'background'))
    expect(contrastRatio(ring, background)).toBeGreaterThanOrEqual(3)
  })

  it('フォーカスリングを半透明にしない（合成でコントラストが目減りするため）', () => {
    expect(inputSource).toContain('focus-visible:ring-ring')
    expect(inputSource).not.toContain('ring-ring/')
    expect(buttonSource).toContain('focus-visible:ring-ring')
    expect(buttonSource).not.toContain('ring-ring/')
  })
})
