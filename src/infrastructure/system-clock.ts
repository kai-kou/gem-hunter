import type { ClockPort } from '../domain/ports/clock-port'

/**
 * `ClockPort` の既定実装（実時刻）。composition root でのみ束ねる。
 */
export class SystemClock implements ClockPort {
  now(): Date {
    return new Date()
  }
}
