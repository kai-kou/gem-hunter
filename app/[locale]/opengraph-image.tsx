import { ImageResponse } from 'next/og'
import { isLocale, locale as toLocale } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'
import { OG_BACKGROUND_DATA_URI } from './og-background-data'

export const alt = 'gem-hunter'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

/**
 * OG 画像の背景（`public/images/og-background.png` の縮小版・ux_visual/perf_asset 生成物）。
 *
 * 🔴 実行時 `readFile(process.cwd())` は不採用（Cloudflare Workers 上で 500 になることを
 * 実デプロイの `curl` で確認済み・Issue #347 追加タスク）: Workers にファイルシステムは無く
 * `public/` の中身はディスク上に存在しない（`ASSETS` バインディング経由でのみ配信される）ため、
 * ビルドが通ってもリクエスト時の `readFile` は失敗する。代わりに背景をビルド時に
 * `tools/ui-assets/build_data_uri_module.mjs` で base64 データ URI の TS モジュールへ変換し、
 * 通常の import としてバンドルへ**埋め込む**（`getCloudflareContext()` 等の事業者固有 API は
 * 使わない・`NFR-21`）。再生成手順は `tools/ui-assets/README.md` 参照。
 */
const backgroundSrc = OG_BACKGROUND_DATA_URI

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
          top: 72,
          left: 64,
          width: 620,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            display: 'flex',
            fontSize: 64,
            fontWeight: 700,
            // 背景左側は明るいクリーム色（og-background の意匠）なので、判読性のため濃色にする
            // （白文字は背景と同化して読めなくなる不具合を実画像の目視確認で発見・修正）。
            color: '#171717',
          }}
        >
          {messages.home.title}
        </div>
        {/*
            🔴 `messages.home.title`（ブランド名）は ja/en で同一文字列のため、それだけでは
            「ロケール別に見た目を変える」という要件を満たさない（争点 B の目的が達成できない）。
            `messages.home.description`（実際に ja/en で異なる本文）を副題として併せて合成し、
            言語ごとに視覚的な差分が実際に生まれるようにする。
          */}
        <div
          style={{
            display: 'flex',
            marginTop: 20,
            fontSize: 28,
            lineHeight: 1.5,
            color: '#3f3f3f',
          }}
        >
          {messages.home.description}
        </div>
      </div>
    </div>,
    { ...size },
  )
}
