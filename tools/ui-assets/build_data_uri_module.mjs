#!/usr/bin/env node
/**
 * PNG/WebP をビルド成果物（TS モジュールの base64 データ URI 文字列）へ変換する。
 *
 * `app/[locale]/opengraph-image.tsx`（`next/og` の `ImageResponse`）が Cloudflare Workers 上で
 * 実行時に `readFile()` で `public/` を読もうとすると 500 になる（Workers にファイルシステムが無く
 * `public/` の中身はディスク上に存在しない・`ASSETS` バインディング経由でしか配信されないため）。
 * この事実は `wrangler versions upload` で実際にデプロイしたプレビュー URL への `curl` で確認済み
 * （ビルド成功だけでは検出できない・Issue #347 追加タスク）。
 *
 * 対策として、背景画像をアプリのソースコード（JS バンドル）へ**埋め込む**。`getCloudflareContext()` 等の
 * Cloudflare 固有 API は使わない（`NFR-21`）——生成された TS モジュールはただの文字列定数であり、
 * どのランタイムでも同じ動きをする。
 *
 * 使い方:
 *   node tools/ui-assets/build_data_uri_module.mjs --in <src.png> --out <dest.ts> \
 *     --export-name <定数名> [--mime image/png]
 */
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { dirname } from 'node:path'
import { parseArgs } from 'node:util'

const { values } = parseArgs({
  options: {
    in: { type: 'string' },
    out: { type: 'string' },
    'export-name': { type: 'string' },
    mime: { type: 'string', default: 'image/png' },
  },
})

if (!values.in || !values.out || !values['export-name']) {
  console.error(
    'usage: node build_data_uri_module.mjs --in <src.png> --out <dest.ts> --export-name <NAME> [--mime image/png]',
  )
  process.exit(1)
}

async function main() {
  const bytes = await readFile(values.in)
  const base64 = bytes.toString('base64')
  const dataUri = `data:${values.mime};base64,${base64}`

  const banner = [
    '/**',
    ` * 自動生成ファイル。手で編集しない。`,
    ` * 再生成: node tools/ui-assets/build_data_uri_module.mjs --in <src> --out ${values.out} \\`,
    ` *   --export-name ${values['export-name']} --mime ${values.mime}`,
    ` * 元絵の再生成手順は tools/ui-assets/README.md 参照。`,
    ' */',
  ].join('\n')

  const content = `${banner}\nexport const ${values['export-name']} = "${dataUri}";\n`

  await mkdir(dirname(values.out), { recursive: true })
  await writeFile(values.out, content, 'utf8')

  console.log(
    JSON.stringify({
      in: values.in,
      out: values.out,
      sourceBytes: bytes.length,
      moduleBytes: Buffer.byteLength(content, 'utf8'),
    }),
  )
}

main().catch((err) => {
  console.error(`変換に失敗した: ${err.message}`)
  process.exit(1)
})
