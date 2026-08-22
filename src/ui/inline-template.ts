/**
 * 文言テンプレート（`{source}` / `{license}` のようなプレースホルダを含む 1 本の文）の中へ
 * リンク要素を差し込むための共有部品。
 *
 * 🔴 **複製を作らない**: 帰属表示（`D-29`）はトップページ（`attribution-notice.tsx`）と
 * Gem 一覧（`gem-list.tsx`）の 2 箇所で描画される。以前は両者が同じ定数・同じ関数を
 * 別々に持っており、片方だけ改定されて体裁が食い違う状態になっていた（PR #440 Layer 1 指摘）。
 */

/**
 * 本文中インラインリンク（出典元・ライセンス等）の共通クラス。
 * 同じ段落に複数のリンクがあるため、片方だけ意匠を変えて食い違うことを構造的に防ぐ
 * （Issue #334 Layer 1 レビュー指摘）。
 */
export const INLINE_LINK_CLASS_NAME =
  'text-primary rounded-sm underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring'

/**
 * `template` を `token` の最初の出現位置で 2 分割する（`String.prototype.split(limit)` は
 * 残りを捨てるため使わない）。見つからなければ `[template, '']` を返す。
 *
 * 呼び出し側は「見つからなかった」を後半が空文字であることでは判定できない（末尾に
 * プレースホルダがある正常系と区別できない）ため、必要なら `includes()` で別途判定する。
 */
export function splitOn(template: string, token: string): [string, string] {
  const idx = template.indexOf(token)
  if (idx < 0) return [template, '']
  return [template.slice(0, idx), template.slice(idx + token.length)]
}

/** `http(s)` の絶対 URL か（`javascript:` 等を `href` へ流さないための入口判定）。 */
export function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}
