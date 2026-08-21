import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { ImageResponse } from 'next/og'
import { isLocale, locale as toLocale } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'

export const alt = 'gem-hunter'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

/**
 * OG 画像の背景（`public/images/og-background.png`・ux_visual/perf_asset 生成物）。
 *
 * ロケールに依存しないアセットなのでリクエストごとではなくモジュールスコープで 1 度だけ読む
 * （Next.js 公式ドキュメント `file-conventions/01-metadata/opengraph-image.md`
 * 「Using Node.js runtime with local assets」の Predictable values パターンに準拠）。
 *
 * 🔴 未検証事項（whiteboard round4 lead verdict の critical 1 番）: `readFile(process.cwd())`
 * 方式が OpenNext + Cloudflare Workers のビルドで成立するかは `npx opennextjs-cloudflare build`
 * を実際に走らせて確認済み（実装時レポート参照）。
 */
const backgroundData = await readFile(join(process.cwd(), 'public/images/og-background.png'), 'base64')
const backgroundSrc = `data:image/png;base64,${backgroundData}`

/**
 * ロケール別 OG 画像（Issue #347・whiteboard 争点 B）。
 *
 * 背景（原石モチーフ）は言語に依存しない 1 枚をそのまま敷き、タイトル文言だけを
 * `getMessages(locale)` から**実行時合成**する。静的にテキストを焼き込まないことで、
 * `messages/*.json` の文言変更に画像の再生成なしで追随できる（lead 裁定・争点B）。
 *
 * `params` を使うだけで `headers()`/`cookies()` 等のリクエスト時 API は使わないため、
 * ビルド時に静的最適化される（ja/en 2 種類が生成される想定・doc「Good to know」）。
 */
export default async function Image({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: rawLocale } = await params
  const locale = isLocale(rawLocale) ? toLocale(rawLocale) : toLocale('ja')
  const messages = getMessages(locale)

  return new ImageResponse(
    (
      <div style={{ width: '100%', height: '100%', display: 'flex', position: 'relative' }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- next/og は satori ベースの独自レンダラで next/image 非対応 */}
        <img
          src={backgroundSrc}
          width={size.width}
          height={size.height}
          style={{ position: 'absolute', inset: 0 }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: 56,
            left: 64,
            right: 64,
            display: 'flex',
            fontSize: 56,
            fontWeight: 600,
            color: '#ffffff',
          }}
        >
          {messages.home.title}
        </div>
      </div>
    ),
    { ...size },
  )
}
