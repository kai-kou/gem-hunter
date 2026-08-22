#!/usr/bin/env node
/**
 * gpt-image-2 が生成した原寸 PNG を配信用アセットへ変換する。
 *
 * 使い方:
 *   node tools/ui-assets/to_web_assets.mjs --in <入力PNG> --out <出力パス> \
 *     --width <幅px> [--height <高さpx>] [--format webp|png] [--fit cover|contain|inside] \
 *     [--colors <2-256>] [--dither <0-1>]
 *
 * アルファチャンネルは常に保持する（--format png / webp のどちらでも透過を落とさない）。
 * og-background のような不透過画像でも、入力に alpha が無ければそのまま出力される。
 *
 * --colors を指定すると PNG をパレット（インデックスカラー）で書き出す。gpt-image-2 の出力は
 * プロンプトで「no texture, no grain」を要求してもわずかなノイズが残ることがあり、素の可逆圧縮
 * では色数が減らず容量が膨らむ（og-background で実測 500KB 超）。--colors 32 --dither 0 程度で
 * 大きく縮む（同じ画像で約 140KB）。
 */
import sharp from 'sharp'
import { parseArgs } from 'node:util'
import { mkdir } from 'node:fs/promises'
import { dirname } from 'node:path'

function usageAndExit(message) {
  if (message) console.error(`error: ${message}`)
  console.error(
    'usage: node to_web_assets.mjs --in <src.png> --out <dest> --width <px> ' +
      '[--height <px>] [--format webp|png] [--fit cover|contain|inside]',
  )
  process.exit(1)
}

const { values } = parseArgs({
  options: {
    in: { type: 'string' },
    out: { type: 'string' },
    width: { type: 'string' },
    height: { type: 'string' },
    format: { type: 'string', default: 'webp' },
    fit: { type: 'string', default: 'inside' },
    quality: { type: 'string', default: '82' },
    colors: { type: 'string' },
    dither: { type: 'string' },
  },
})

if (!values.in || !values.out || !values.width) {
  usageAndExit('--in / --out / --width は必須')
}
if (!['webp', 'png'].includes(values.format)) {
  usageAndExit('--format は webp か png のみ対応')
}

const width = Number.parseInt(values.width, 10)
const height = values.height ? Number.parseInt(values.height, 10) : undefined

async function main() {
  await mkdir(dirname(values.out), { recursive: true })

  let pipeline = sharp(values.in, { failOn: 'none' }).resize({
    width,
    height,
    fit: values.fit,
    withoutEnlargement: false,
  })

  if (values.format === 'webp') {
    pipeline = pipeline.webp({ quality: Number.parseInt(values.quality, 10), alphaQuality: 100 })
  } else if (values.colors) {
    pipeline = pipeline.png({
      palette: true,
      colors: Number.parseInt(values.colors, 10),
      dither: values.dither !== undefined ? Number.parseFloat(values.dither) : 1.0,
      compressionLevel: 9,
      effort: 10,
    })
  } else {
    pipeline = pipeline.png({ compressionLevel: 9 })
  }

  const info = await pipeline.toFile(values.out)
  console.log(
    JSON.stringify({
      in: values.in,
      out: values.out,
      width: info.width,
      height: info.height,
      format: info.format,
      bytes: info.size,
      channels: info.channels,
      hasAlpha: info.channels === 4,
    }),
  )
}

main().catch((err) => {
  console.error(`変換に失敗した: ${err.message}`)
  process.exit(1)
})
