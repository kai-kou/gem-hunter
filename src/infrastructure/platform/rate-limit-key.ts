/**
 * レート制限キー生成（cloudflare-infrastructure.md §9.1「Rate Limiting の key を HMAC 化する」）。
 * 🔴 事業者固有ヘッダ（`cf-connecting-ip` 等）の参照はこのファイル（src/infrastructure/platform/）に閉じる（NFR-21 / INF-5）。
 *
 * ⚠️ **生 IP をログにも戻り値にも出さない**: `clientIpOf` が取り出した値は必ず `hashRateLimitKey` で
 * HMAC 化してから `RateLimitPort.consume` へ渡す。生 IP をそのまま Cloudflare Rate Limiting binding の
 * key や Workers Logs へ渡さない（プライバシー設定 §9.1）。
 */

/**
 * Cloudflare が付ける接続元 IP ヘッダから利用者を識別する値を取り出す。
 * `cf-connecting-ip` を最優先し、無ければ `x-forwarded-for` の先頭要素（カンマ区切り・前後の空白を除去）を使う。
 * どちらも無い・空文字なら null（呼び出し側でフォールバックの判断をする）。
 *
 * 🔴 `x-forwarded-for` はクライアントが自由に詐称できるため、**これを唯一の識別子として
 * レート制限を効かせてはならない**。実際、`cf-connecting-ip`（Cloudflare が付与し詐称できない）が
 * 無い環境は Cloudflare の外であり、そこでは Rate Limiting binding 自体が未提供で間引きは働かない
 * （`src/composition/rate-limit.ts` のフェイルオープン 3 条件）。ここでのフォールバックは
 * 別のプロキシ配下でも「誰か」を識別できるようにするための保険にとどめる。
 */
export function clientIpOf(headers: Headers): string | null {
  const direct = headers.get('cf-connecting-ip')
  if (direct && direct.trim() !== '') {
    return direct.trim()
  }
  const forwarded = headers.get('x-forwarded-for')
  if (!forwarded) {
    return null
  }
  const first = forwarded.split(',')[0]?.trim()
  return first && first !== '' ? first : null
}

/**
 * レート制限キーを HMAC-SHA256(salt, source) の hex 文字列にして返す（生 IP を Cloudflare へ渡さない）。
 * Workers / Node 18+ / jsdom いずれでもグローバル `crypto`（Web Crypto API）が使えるため、
 * `node:crypto` は import しない（Workers 実行環境に存在しない API に依存させない）。
 */
export async function hashRateLimitKey(source: string, salt: string): Promise<string> {
  const encoder = new TextEncoder()
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    encoder.encode(salt),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  const signature = await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(source))
  return Array.from(new Uint8Array(signature))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}
