import { SignJWT, importPKCS8 } from 'jose'

import { UpstreamError } from '../../domain/errors'
import type { TokenProvider } from './github-repository-query'

/**
 * GitHub App の installation token を供給する（ADR 0003 / D-20）。
 * 🔴 秘匿情報を読んでよいのはこのファイルだけ（E-6 / NFR-9 / NFR-22）。
 *
 * ⚠️ 秘密鍵は PKCS#8 で供給する。GitHub が発行する PKCS#1 のままでは
 * Workers の Web Crypto が importKey できない（cloudflare-infrastructure.md §7.6）。
 */
const TOKEN_EXPIRY_MARGIN_MS = 60_000

type CachedToken = { value: string; expiresAt: number }
let cached: CachedToken | null = null

type AppCredentials = {
  clientId: string
  installationId: string
  privateKeyPkcs8: string
}

function readCredentials(): AppCredentials | null {
  const clientId = process.env.GITHUB_APP_CLIENT_ID
  const installationId = process.env.GITHUB_APP_INSTALLATION_ID
  const privateKeyPkcs8 = process.env.GITHUB_APP_PRIVATE_KEY_PKCS8

  if (!clientId || !installationId || !privateKeyPkcs8) {
    return null
  }
  return { clientId, installationId, privateKeyPkcs8 }
}

async function requestInstallationToken(credentials: AppCredentials): Promise<CachedToken> {
  const now = Math.floor(Date.now() / 1000)
  const key = await importPKCS8(credentials.privateKeyPkcs8.replace(/\\n/g, '\n'), 'RS256')
  const jwt = await new SignJWT({})
    .setProtectedHeader({ alg: 'RS256' })
    .setIssuer(credentials.clientId)
    .setIssuedAt(now - 60)
    .setExpirationTime(now + 540)
    .sign(key)

  const response = await fetch(
    `https://api.github.com/app/installations/${credentials.installationId}/access_tokens`,
    {
      method: 'POST',
      headers: {
        accept: 'application/vnd.github+json',
        authorization: `Bearer ${jwt}`,
        'x-github-api-version': '2022-11-28',
        'user-agent': 'gem-hunter',
      },
    },
  )

  if (!response.ok) {
    throw new UpstreamError(`installation token を取得できませんでした（HTTP ${response.status}）`)
  }

  const body = (await response.json()) as { token?: string; expires_at?: string }
  if (!body.token || !body.expires_at) {
    throw new UpstreamError('installation token の応答が想定と異なります')
  }

  return { value: body.token, expiresAt: new Date(body.expires_at).getTime() }
}

/**
 * 資格情報が揃っていれば installation token を、揃っていなければ null を返す。
 * null のときデータアクセス層は未認証で GitHub API を叩く（枠は狭いが動作は止めない）。
 */
export const installationTokenProvider: TokenProvider = async () => {
  const credentials = readCredentials()
  if (!credentials) {
    return null
  }

  const now = Date.now()
  if (cached && cached.expiresAt - TOKEN_EXPIRY_MARGIN_MS > now) {
    return cached.value
  }

  cached = await requestInstallationToken(credentials)
  return cached.value
}

/** テスト用にキャッシュを捨てる。 */
export function resetInstallationTokenCache(): void {
  cached = null
}
