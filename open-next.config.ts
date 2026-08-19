import { defineCloudflareConfig } from '@opennextjs/cloudflare'

// キャッシュは HTTP Cache-Control + Workers Caching のみ（D-18）。
// R2 / D1 / KV / Durable Objects のインクリメンタルキャッシュは使わない。
export default defineCloudflareConfig()
