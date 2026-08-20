/**
 * エラー種別（prd.md §7「エラー種別の判別仕様」）。
 * 🔴 利用者向けの文言は **この kind から i18n で引く**。各エラーの `message` は開発者向けの
 * ログ用であり、そのまま画面や API 応答へ出さない（内部情報を漏らさない・SP-9）。
 */
export type ErrorKind =
  /** fetch 自体が失敗（到達不可） */
  | 'network'
  /** 一次レート制限（枠の枯渇。`x-ratelimit-reset` で復帰時刻が分かる） */
  | 'rateLimitPrimary'
  /** 二次レート制限（短時間の集中。`retry-after` 秒後に再試行できる） */
  | 'rateLimitSecondary'
  /** 401 / 403（レート制限以外）。サーバー設定の問題なので汎用エラーとして扱う */
  | 'auth'
  /** 入力・検索クエリが不正（422 / 値オブジェクトの検証失敗） */
  | 'validation'
  /** 対象なし */
  | 'notFound'
  /** 5xx・スキーマ不一致・その他の上流異常 */
  | 'upstream'

/** レート制限に対応する `ErrorKind`。 */
export type RateLimitKind = Extract<ErrorKind, 'rateLimitPrimary' | 'rateLimitSecondary'>

/** ドメインエラーの基底。層をまたいで型で判別できるようにする。 */
export abstract class DomainError extends Error {
  /** 利用者への提示を決めるキー（prd.md §7）。 */
  abstract readonly kind: ErrorKind

  protected constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = new.target.name
  }
}

/** 値オブジェクトの不変条件を満たさない入力（domain-model.md §4）。 */
export class DomainValidationError extends DomainError {
  readonly kind = 'validation' as const

  constructor(
    readonly valueObject: string,
    readonly raw: unknown,
    message?: string,
  ) {
    super(message ?? `${valueObject} として扱えない値です`)
  }
}

const DEFAULT_RATE_LIMIT_MESSAGE: Record<RateLimitKind, string> = {
  rateLimitPrimary: 'GitHub API のレート制限に達しました',
  rateLimitSecondary: 'GitHub API の二次レート制限に達しました',
}

/**
 * 上流（GitHub）のレート制限に達した。
 * 一次（枠の枯渇）は復帰時刻 `retryAfter`、二次（短時間の集中）は待機秒数
 * `retryAfterSeconds` を持つ（どちらも上流が返さなければ undefined）。
 */
export class RateLimitExceededError extends DomainError {
  /** 再試行可能になる時刻（一次レート制限の `x-ratelimit-reset` 由来）。 */
  readonly retryAfter?: Date
  /** 再試行までの待機秒数（二次レート制限の `retry-after` 由来）。 */
  readonly retryAfterSeconds?: number

  constructor(
    readonly kind: RateLimitKind,
    options: { retryAfter?: Date; retryAfterSeconds?: number; message?: string } = {},
  ) {
    super(options.message ?? DEFAULT_RATE_LIMIT_MESSAGE[kind])
    this.retryAfter = options.retryAfter
    this.retryAfterSeconds = options.retryAfterSeconds
  }
}

/** 上流へ到達できなかった（DNS・接続断など fetch 自体の失敗）。 */
export class NetworkError extends DomainError {
  readonly kind = 'network' as const

  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
  }
}

/**
 * 認証・権限の問題（401 / 403）。
 * 🔴 サーバー設定の問題であり利用者は対処できないため、内部情報を出さない汎用エラーとして扱う（prd.md §7）。
 */
export class AuthError extends DomainError {
  readonly kind = 'auth' as const

  constructor(message: string) {
    super(message)
  }
}

/** 上流が想定外の応答を返した（5xx・スキーマ不一致）。 */
export class UpstreamError extends DomainError {
  readonly kind = 'upstream' as const

  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
  }
}

/** 対象が存在しない。 */
export class NotFoundError extends DomainError {
  readonly kind = 'notFound' as const

  constructor(message: string) {
    super(message)
  }
}
