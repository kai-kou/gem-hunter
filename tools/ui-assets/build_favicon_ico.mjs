#!/usr/bin/env node
/**
 * gpt-image-2 由来のロゴ PNG（`app/icon.png` 等・透過）から、複数サイズを内包する
 * `favicon.ico` を組み立てる。
 *
 * `sharp` は ICO を書き出せないため、各サイズの PNG を `sharp` でリサイズしたうえで、
 * 単純な ICO コンテナ（ICONDIR + ICONDIRENTRY の配列 + PNG バイト列）へ自前で包む
 * （PNG-in-ICO は Windows Vista 以降でサポートされている一般的な形式）。新規 npm 依存は
 * 追加しない。
 *
 * 使い方:
 *   node tools/ui-assets/build_favicon_ico.mjs --in <src.png> --out <dest.ico> \
 *     [--sizes 16,32,48]
 *
 * アルファチャンネル（透過）は常に保持する。
 */
import sharp from 'sharp'
import { parseArgs } from 'node:util'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'

function usageAndExit(message) {
  if (message) console.error(`error: ${message}`)
  console.error(
    'usage: node build_favicon_ico.mjs --in <src.png> --out <dest.ico> [--sizes 16,32,48]',
  )
  process.exit(1)
}

const { values } = parseArgs({
  options: {
    in: { type: 'string' },
    out: { type: 'string' },
    sizes: { type: 'string', default: '16,32,48' },
  },
})

if (!values.in || !values.out) {
  usageAndExit('--in / --out は必須')
}

const sizes = values.sizes
  .split(',')
  .map((s) => Number.parseInt(s.trim(), 10))
  .filter((n) => Number.isInteger(n) && n > 0)

if (sizes.length === 0) {
  usageAndExit('--sizes は 1 個以上の正の整数をカンマ区切りで指定する')
}
for (const size of sizes) {
  if (size > 256) {
    usageAndExit(`ICO の 1 バイトサイズフィールドに収まらない（256 以下のみ対応）: ${size}`)
  }
}

/**
 * PNG バッファ配列から ICO ファイル本体（Buffer）を組み立てる。
 * 参照: MS-ICO 仕様（ICONDIR 6 バイト + ICONDIRENTRY × N・各 16 バイト + 画像データ列）。
 */
function buildIco(entries) {
  const count = entries.length
  const headerSize = 6
  const dirEntrySize = 16
  const dataOffsetStart = headerSize + dirEntrySize * count

  const header = Buffer.alloc(headerSize)
  header.writeUInt16LE(0, 0) // reserved
  header.writeUInt16LE(1, 2) // type: 1 = icon
  header.writeUInt16LE(count, 4) // image count

  const dirEntries = []
  const dataChunks = []
  let offset = dataOffsetStart

  for (const { size, png } of entries) {
    const entry = Buffer.alloc(dirEntrySize)
    // 256px は ICO 仕様上 1 バイトフィールドに 0 として格納する（本ツールは 256 超を弾いているため
    // size===256 のケースのみ該当）。
    entry.writeUInt8(size === 256 ? 0 : size, 0) // width
    entry.writeUInt8(size === 256 ? 0 : size, 1) // height
    entry.writeUInt8(0, 2) // color palette count (0 = no palette / >=8bpp)
    entry.writeUInt8(0, 3) // reserved
    entry.writeUInt16LE(1, 4) // color planes
    entry.writeUInt16LE(32, 6) // bits per pixel
    entry.writeUInt32LE(png.length, 8) // size of image data
    entry.writeUInt32LE(offset, 12) // offset of image data
    dirEntries.push(entry)
    dataChunks.push(png)
    offset += png.length
  }

  return Buffer.concat([header, ...dirEntries, ...dataChunks])
}

async function main() {
  await mkdir(dirname(values.out), { recursive: true })

  const entries = []
  for (const size of sizes) {
    const png = await sharp(values.in, { failOn: 'none' })
      .resize({ width: size, height: size, fit: 'contain' })
      .png({ compressionLevel: 9 })
      .toBuffer()
    entries.push({ size, png })
  }

  const ico = buildIco(entries)
  await writeFile(values.out, ico)

  console.log(
    JSON.stringify({
      in: values.in,
      out: values.out,
      entries: entries.map((e) => ({ size: e.size, bytes: e.png.length })),
      totalBytes: ico.length,
    }),
  )
}

main().catch((err) => {
  console.error(`変換に失敗した: ${err.message}`)
  process.exit(1)
})
