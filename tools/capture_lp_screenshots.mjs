/**
 * site/（ランディングページ）に載せるアプリ実画面のスクリーンショットを撮り直す。
 *
 * 前提: アプリを本番ビルドしてローカルで起動しておく（dev サーバーは CSS の
 * パース差でスタイルが当たらないことがあるため使わない）。
 *
 *   npx next build
 *   npx next start -p 3100
 *   node tools/capture_lp_screenshots.mjs
 *
 * 出力: site/assets/img/shot-search.webp / shot-digest.webp / shot-mobile.webp
 *
 * 注意:
 * - アバター画像は外部ホストのため、取得できない環境では `curl` 経由で差し込む
 *   （このスクリプトはネットワークが直結していないコンテナでも動くようにしてある）。
 * - 日本語グリフを持たない Geist のフォールバックが明朝になる環境があるため、
 *   撮影時だけサンセリフの CJK フォールバックを注入する（表示は実利用環境と同等）。
 */
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BASE = process.env.LP_SHOT_BASE ?? 'http://localhost:3100';
const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const IMG_DIR = join(ROOT, 'site/assets/img');

const FONT_FIX = `
  body, body * { font-family: var(--font-geist-sans), "IPAPGothic", "IPAGothic", "Noto Sans JP", sans-serif !important; }
  code, pre, .font-mono { font-family: var(--font-geist-mono), monospace !important; }
`;

const SHOTS = [
  { name: 'shot-search', path: '/ja?q=react', viewport: { width: 1280, height: 820 }, width: 1600 },
  {
    name: 'shot-digest',
    path: '/ja',
    viewport: { width: 1280, height: 1400 },
    clip: { x: 0, y: 470, width: 1280, height: 700 },
    width: 1400,
  },
  { name: 'shot-mobile', path: '/ja?q=zod', viewport: { width: 390, height: 780 }, width: 640 },
];

const avatarCache = new Map();
function fetchAvatar(url) {
  if (avatarCache.has(url)) return avatarCache.get(url);
  try {
    const buf = execFileSync('curl', ['-sL', '--max-time', '20', url], { maxBuffer: 20e6 });
    avatarCache.set(url, buf);
    return buf;
  } catch {
    return null;
  }
}

const browser = await chromium.launch();

for (const shot of SHOTS) {
  const context = await browser.newContext({
    viewport: shot.viewport,
    deviceScaleFactor: 2,
    locale: 'ja-JP',
  });
  await context.route('**://avatars.githubusercontent.com/**', async (route) => {
    const body = fetchAvatar(route.request().url());
    if (body) await route.fulfill({ status: 200, contentType: 'image/png', body });
    else await route.abort();
  });

  const page = await context.newPage();
  const response = await page.goto(BASE + shot.path, { waitUntil: 'load', timeout: 60_000 });
  if (!response?.ok()) throw new Error(`${shot.path} が ${response?.status()} を返した`);
  await page.addStyleTag({ content: FONT_FIX });
  await page.waitForTimeout(2000);

  const broken = await page.evaluate(() =>
    Array.from(document.images)
      .filter((image) => !image.complete || image.naturalWidth === 0)
      .map((image) => image.src),
  );
  if (broken.length > 0) throw new Error(`画像が読めていない: ${broken.join(', ')}`);

  const pngPath = join(IMG_DIR, `${shot.name}.png`);
  await page.screenshot({ path: pngPath, ...(shot.clip ? { clip: shot.clip } : {}) });
  await context.close();

  // WebP へ変換（sharp / cwebp が無い環境でも動くよう Chromium の canvas を使う）
  const converter = await browser.newPage();
  await converter.setContent('<canvas id="c"></canvas>');
  const dataUrl = await converter.evaluate(
    async ({ base64, width }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${base64}`;
      await image.decode();
      const scale = width / image.naturalWidth;
      const canvas = document.getElementById('c');
      canvas.width = Math.round(image.naturalWidth * scale);
      canvas.height = Math.round(image.naturalHeight * scale);
      const ctx = canvas.getContext('2d');
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL('image/webp', 0.86);
    },
    { base64: readFileSync(pngPath).toString('base64'), width: shot.width },
  );
  const webp = Buffer.from(dataUrl.split(',')[1], 'base64');
  writeFileSync(join(IMG_DIR, `${shot.name}.webp`), webp);
  execFileSync('rm', ['-f', pngPath]);
  await converter.close();

  console.log(`${shot.name}.webp を更新した（${webp.length} bytes）`);
}

await browser.close();
console.log('🔴 index.html の width / height 属性が変わっていないか確認すること');
