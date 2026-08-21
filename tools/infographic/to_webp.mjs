// 生成した PNG をまとめて WebP へ変換し docs/infographics/ へ置く。
// 使い方: node tools/infographic/to_webp.mjs <PNG が入ったディレクトリ> [出力先ディレクトリ]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const sharp = createRequire(import.meta.url)(path.resolve("node_modules/sharp"));

const srcDir = process.argv[2];
const dstDir = process.argv[3] ?? "docs/infographics";
if (!srcDir) {
  console.error("usage: node tools/infographic/to_webp.mjs <src-dir> [dst-dir]");
  process.exit(1);
}

const files = fs.readdirSync(srcDir).filter((f) => f.endsWith(".png")).sort();
if (files.length === 0) {
  console.error(`no .png found in ${srcDir}`);
  process.exit(1);
}

let totalKb = 0;
for (const file of files) {
  const out = path.join(dstDir, file.replace(/\.png$/, ".webp"));
  await sharp(path.join(srcDir, file)).webp({ quality: 90 }).toFile(out);
  const kb = fs.statSync(out).size / 1024;
  totalKb += kb;
  console.log(`${path.basename(out).padEnd(24)} ${kb.toFixed(0)}KB`);
}
console.log(`TOTAL ${(totalKb / 1024).toFixed(2)}MB / ${files.length} files`);
