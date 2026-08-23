import { UpstreamError } from '../../domain/errors'
import type { AuthPort } from '../../domain/ports/auth-port'
import { resolveLoopbackOverridableOrigin } from './loopback-origin'

/**
 * GitHub OAuth（自前実装・AR-5）。authorize URL 組み立てと token 交換のみを扱う。
 * 🔴 秘匿情報（OAuth クライアント ID / シークレット）を読んでよいのはこのファイルだけ
 * （ARCH-5 / NFR-9 / NFR-22）。`/user` プロフィール取得は SP-8 スコープ外（呼ばない）。
 *
 * whiteboard `content/discussions/sp8-auth-i18n-20260819/whiteboard.md` 争点 A/C の決定に従う:
 * ライブラリ（Auth.js 等）は導入せず、`fetch` と Web Crypto のみに依存する自前実装にする
 * （Cloudflare Workers ランタイムとの親和性・プレビュー無効化方針との相性）。
 */

const DEFAULT_OAUTH_ORIGIN = 'https://github.com'

type OAuthCredentials = {
  clientId: string
  clientSecret: string
  callbackUrl: string
}

function readCredentials(): OAuthCredentials | null {
  const clientId = process.env.GITHUB_OAUTH_CLIENT_ID
  const clientSecret = process.env.GITHUB_OAUTH_CLIENT_SECRET
  const callbackUrl = process.env.GITHUB_OAUTH_CALLBACK_URL

  if (!clientId || !clientSecret || !callbackUrl) {
    return null
  }
  return { clientId, clientSecret, callbackUrl }
}

/**
 * OAuth 資格情報（client id / secret / callback URL）が揃っているか。
 * composition root のログイン導線表示ゲート用（値は一切返さない）。
 */
export function oauthCredentialsConfigured(): boolean {
  return readCredentials() !== null
}

/**
 * `GITHUB_OAUTH_CALLBACK_URL` のオリジンのみを返す（秘匿値である client secret は含まない）。
 * PR #141 レビュー指摘: callback/logout route handler のリダイレクト先を、クライアント送信の
 * `Host` ヘッダではなくこの値で検証するために使う（オープンリダイレクト対策）。
 */
export function callbackOrigin(): string | null {
  const raw = process.env.GITHUB_OAUTH_CALLBACK_URL
  if (!raw) {
    return null
  }
  try {
    return new URL(raw).origin
  } catch {
    return null
  }
}

function oauthOrigin(): string {
  return resolveLoopbackOverridableOrigin('GITHUB_OAUTH_ORIGIN', DEFAULT_OAUTH_ORIGIN)
}

/** authorize へのリダイレクト先 URL を組み立てる（no-scope・`scope` パラメータを付けない）。 */
export function buildAuthorizeUrl(state: string): string {
  const credentials = readCredentials()
  if (!credentials) {
    throw new Error('GitHub OAuth の資格情報が設定されていません')
  }

  const url = new URL('/login/oauth/authorize', oauthOrigin())
  url.searchParams.set('client_id', credentials.clientId)
  url.searchParams.set('redirect_uri', credentials.callbackUrl)
  url.searchParams.set('state', state)
  return url.toString()
}

type AccessTokenResponse = {
  access_token?: string
  error?: string
  error_description?: string
}

/** `AuthPort` の実装（ARCH-5）。GitHub とのやり取りをこのファイルに閉じ込める。 */
export function makeGithubOAuth(): AuthPort {
  return {
    async exchangeAuthorizationCode(code: string): Promise<{ accessToken: string }> {
      const credentials = readCredentials()
      if (!credentials) {
        throw new UpstreamError('GitHub OAuth の資格情報が設定されていません')
      }

      const body = new URLSearchParams({
        client_id: credentials.clientId,
        client_secret: credentials.clientSecret,
        code,
        redirect_uri: credentials.callbackUrl,
      })

      let response: Response
      try {
        response = await fetch(new URL('/login/oauth/access_token', oauthOrigin()), {
          method: 'POST',
          headers: {
            accept: 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'user-agent': 'gem-hunter',
          },
          body: body.toString(),
        })
      } catch (cause) {
        throw new UpstreamError('GitHub OAuth トークンエンドポイントへ到達できませんでした', {
          cause,
        })
      }

      if (!response.ok) {
        throw new UpstreamError(
          `GitHub OAuth トークン交換に失敗しました（HTTP ${response.status}）`,
        )
      }

      const data = (await response.json()) as AccessTokenResponse
      if (data.error || !data.access_token) {
        const detail = data.error
          ? `${data.error}${data.error_description ? `: ${data.error_description}` : ''}`
          : 'access_token が応答に含まれていません'
        throw new UpstreamError(`GitHub OAuth トークン交換がエラーを返しました（${detail}）`)
      }

      return { accessToken: data.access_token }
    },
  }
}
