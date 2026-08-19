/** ドメインエラーの基底。層をまたいで型で判別できるようにする。 */
export abstract class DomainError extends Error {
  protected constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = new.target.name
  }
}

/** 値オブジェクトの不変条件を満たさない入力（domain-model.md §4）。 */
export class DomainValidationError extends DomainError {
  constructor(
    readonly valueObject: string,
    readonly raw: unknown,
    message?: string,
  ) {
    super(message ?? `${valueObject} として扱えない値です`)
  }
}

/** 上流（GitHub）のレート制限に達した。 */
export class RateLimitExceededError extends DomainError {
  constructor(
    message: string,
    readonly retryAfter?: Date,
  ) {
    super(message)
  }
}

/** 上流が想定外の応答を返した（通信失敗・5xx・スキーマ不一致）。 */
export class UpstreamError extends DomainError {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
  }
}

/** 対象が存在しない。 */
export class NotFoundError extends DomainError {
  constructor(message: string) {
    super(message)
  }
}
