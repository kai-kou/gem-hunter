import type { CacheKey, CachePort } from '../../domain/ports/cache-port'
import { assertPositiveTtlSeconds } from './ttl'

/**
 * secondary HIT のときに primary へ充填する TTL（秒）の既定値。
 *
 * 🔴 **なぜ固定値なのか**: `CachePort` は「残り TTL」を返さない（`get` の戻り値は値だけ）。
 * したがって secondary エントリの残存時間を知る手段が無く、充填時に「secondary と同じ時刻に
 * 失効する」よう揃えることは **できない**。ここは意図的に固定値で妥協する。
 *
 * 🔴 **受け入れる制約（明示しておく）**: 充填した primary のコピーが secondary より
 * 長生きしうる。最悪ケースは「secondary の残 TTL が 1 秒の状態で充填」で、その isolate は
 * 最大 `refillTtlSeconds - 1` 秒だけ、secondary から見れば失効済みの値を返し続ける。
 * これは既存の `InMemoryCache` 単独運用でも同種の古さ（isolate 内 TTL ぶん）を許容していた
 * 範囲であり、レート枠の逆算（`R-5`）で見ている「上流 API 呼び出し回数」を増やす方向の
 * 劣化ではない。
 *
 * **値の根拠**: 本プロジェクトで使う TTL のうち最短のもの（`container.ts` の
 * `TTL_SEARCH_SECONDS = 60`）に合わせる。こうすると充填したコピーは「その値を今 secondary へ
 * 新規に書いた場合の寿命」を超えない（検索は同値・詳細 300 秒はより短い）。TTL 設定を
 * 変えるときは本定数の根拠も見直すこと。
 */
export const DEFAULT_REFILL_TTL_SECONDS = 60

/**
 * 2 段キャッシュ（Issue #121）。primary = isolate 内（`InMemoryCache`）、
 * secondary = isolate 跨ぎ（`WorkersCache` / Cloudflare Cache API）。
 *
 * 🔴 **なぜ置き換えではなく 2 段なのか**: Cloudflare 公式ドキュメント
 * （https://developers.cloudflare.com/workers/runtime-apis/cache/ ）には、
 * ① Worker 自身のゾーン / ホスト名に属さない **合成 URL をキーにできるか** の記載が無い、
 * ② **ダッシュボードエディタ / Playground のプレビューでは Cache API 操作が無効（no impact）**、
 * ③ `*.workers.dev` での動作可否が明示されていない、という未確定要因がある。
 * Cache API で `InMemoryCache` を **置き換える** と、Cache API が実質 no-op だった場合に
 * HIT 率が現状（ADR 0016 §1.1 の起票時点の実測）から **0% へ悪化しうる**。2 段にすれば
 * 最悪でも現状維持（primary だけが効く）で、変化は片方向の改善に限定される。
 *
 * 契約（`cache-port.ts`）の遵守:
 * - `get` は throw しない（どちらの層の失敗も `null` / フォールバックへ倒す）
 * - `set` の `RangeError`（TTL 値域外）は **自身の先頭で検証して伝播** させる（fail-open も、
 *   片方の層にだけ書かれる非対称も作らない）
 * - `invalidate` は片方が throw してももう片方を実行し、自身は throw しない（冪等）
 */
export class LayeredCache implements CachePort {
  private readonly refillTtlSeconds: number

  constructor(
    private readonly primary: CachePort,
    private readonly secondary: CachePort,
    options: { refillTtlSeconds?: number } = {},
  ) {
    const refillTtlSeconds = options.refillTtlSeconds ?? DEFAULT_REFILL_TTL_SECONDS
    // 充填は `get` の中で行うため、ここで弾かないと「毎回 RangeError が握り潰されて
    // 充填だけ静かに効かない」状態になる（生成時に落とす）。
    assertPositiveTtlSeconds(refillTtlSeconds, 'refillTtlSeconds')
    this.refillTtlSeconds = refillTtlSeconds
  }

  async get<T>(key: CacheKey): Promise<T | null> {
    const fromPrimary = await this.tryGet<T>(this.primary, key)
    if (fromPrimary !== null) {
      // primary HIT。secondary は引かない（isolate 跨ぎの往復を省く）。
      return fromPrimary
    }

    const fromSecondary = await this.tryGet<T>(this.secondary, key)
    if (fromSecondary === null) {
      return null
    }

    try {
      // 同じ isolate の次のリクエストが secondary に触らずに済むよう充填する。
      // TTL の決め方と制約は `DEFAULT_REFILL_TTL_SECONDS` の JSDoc を参照。
      await this.primary.set(key, fromSecondary, this.refillTtlSeconds)
    } catch {
      // 充填失敗は取得結果に影響させない（次回また secondary を引くだけ）。
    }
    return fromSecondary
  }

  async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
    // 🔴 **TTL 検証は層へ委ねず自分の先頭で行う**（`assertPositiveTtlSeconds` は 3 実装の共通関数）。
    //    層に委ねると「primary は受理したが secondary だけ RangeError → その例外が下の catch に
    //    握り潰されて **primary にだけ書かれる非対称**」が無音で起きる。ここで弾けば
    //    「どちらの層にも書かれない」で確定する（fail-open も非対称も作らない）。
    assertPositiveTtlSeconds(ttlSeconds)
    // TTL 以外の理由（層の内部障害）で片方が throw しても、もう片方の書き込みは活かす。
    // キャッシュ書き込みの失敗でリクエスト本体を壊さない。
    try {
      await this.primary.set(key, value, ttlSeconds)
    } catch {
      // primary へ書けなくても secondary には書ける（次の isolate が HIT できる）。
    }
    try {
      await this.secondary.set(key, value, ttlSeconds)
    } catch {
      // secondary へ書けなくても primary には書けている（isolate 内では HIT する）。
    }
  }

  async invalidate(key: CacheKey): Promise<void> {
    // 🔴 片方の失敗でもう片方を飛ばさない（配列にまとめて `Promise.all` へ渡すと、
    //    同期 throw する実装では 2 つ目が呼ばれないため個別に try で囲む）。
    try {
      await this.primary.invalidate(key)
    } catch {
      // 冪等の契約: 失敗しても throw しない。
    }
    try {
      await this.secondary.invalidate(key)
    } catch {
      // 同上。
    }
  }

  /** どちらの層でも「失敗は MISS と同義」に倒す（`get` は throw しない契約）。 */
  private async tryGet<T>(port: CachePort, key: CacheKey): Promise<T | null> {
    try {
      return await port.get<T>(key)
    } catch {
      return null
    }
  }
}
