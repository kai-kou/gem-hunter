#!/usr/bin/env node
/**
 * gem_pool_qa.mjs — Gem 候補プール生成物の QA・no-op 判定・反映可否判定を行う CLI
 * （Issue #458・#482・`D-40`）。
 *
 * `.github/workflows/gem-pool-refresh.yml`（**日次生成・週次目安反映**）が
 * `node tools/generate_gem_digest.mjs` を実行した **直後**、コミット・ブランチ作成の前に呼ぶ。
 * 決めることは 3 つ:
 *   1. `--check`          … 生成物が壊れていないか（壊れていれば PR を作らせない・fail-closed）
 *   2. `--no-op`          … 前回コミットと実質同じ内容なら、無駄な PR を作らせない
 *   3. `--should-publish` … 反映（コミット・push・PR 作成）まで進めてよいか（Issue #482）。
 *      生成物 3.6MB は反映のたびにリポジトリ履歴へ積まれるため、コストの実体は実行頻度ではなく
 *      反映頻度にある。日次実行でパイプラインの健全性（生成・QA）を毎日検証しつつ、直近の反映
 *      コミットから 7 日以上経過した回だけ実際に反映することで、履歴コストは週次相当に抑える。
 *
 * 【なぜ jq に依存しないか】
 * GitHub-hosted runner に jq がプリインストールされているかは一次情報で確認できていない
 * （議論ホワイトボード `content/discussions/gem-pool-actions-schedule-20260823/whiteboard.md`
 * round 1 `actions_facts` を参照）。一方 Node 22 はバッチ本体が必須とするため確実に存在する。
 * 判定ロジックはすべて Node の組み込みモジュールだけで完結させる（外部依存ゼロ）。
 *
 * 【設計規律】
 * 判定ロジックは純関数に切り出し、I/O（`git show` / `readFileSync`）と分離する
 * （`tools/check_gem_shards.py` / `tools/check_prod_drift.py` と同じ作法）。これにより
 * `--self-test` はネットワーク・実データ非依存で完走できる。
 *
 * 【`--check` が検査する内容（1 つでも違反すれば exit 1）】
 *   1. 差分パスの限定: 変更・新規ファイルが `public/data/gem-index/` 配下と
 *      `public/data/daily-digest.json` だけであること（生成スクリプトの想定外副作用の検出）
 *   2. レジストリの消失・ゼロ化: 前回 `index.json` の `shards[]` に居た `registry` が、
 *      今回の `shards[]` から消えている、または `count === 0` になっていたら違反
 *   3. レジストリ単位の急減: 各レジストリで `count_今回 / count_前回 < 0.7`（30% 超の減少）なら違反
 *   4. 全体の急減・急増: `totalCount_今回 / totalCount_前回` が `0.85` 未満または `1.15` 超なら違反
 *
 * `--check --json` の出力には合否判定に加えて `comparison`（前回比・レジストリ別件数）を
 * 常に含める。PR 本文が「コミット後に再計算した意味のない差分ゼロ値」を貼らずに済むよう、
 * 呼び出し側（ワークフロー）はこの JSON を生成直後・コミット前に 1 回だけファイルへ保存し、
 * 後続のステップ（PR 本文組み立て）ではそのファイルを読むだけにする（再計算しない）。
 *
 * 🔴 **閾値（0.7 / 0.85 / 1.15）は初期ヒューリスティックであり、実運転で較正し直す前提**である。
 * 根拠は `generate_gem_digest.mjs` の docstring に載っている実測（`minStars` を 1→5 に変えると
 * 88,981→62,565 ＝ 約 30% 減）。これは「意図的な閾値変更」のレジームであり、同一設定の週次運転で
 * ここまで動くのは異常、という桁感でしかない。較正の追跡は Issue（follow-up）を参照。
 *
 * HEAD 側に `index.json` が無い（初回実行）ときは 2〜4 をスキップして PASS にする。
 *
 * 【`--no-op` が判定する内容】
 * `index.json` の `meta.generatedAt` と `daily-digest.json` の `date` は実行のたびに必ず変わる
 * （実行時刻・生成日）。これを正規化してから HEAD 版と比較し、実質差分ゼロなら `no_op=true` を返す。
 * どちらでも exit 0（判定結果は呼び出し側のワークフローが `no_op` フィールドで読む）。
 * 🔴 本モード自身は `git checkout --` を実行しない（副作用を持たせない）。ファイルを戻すのは
 * ワークフロー側の責務（判定結果を見て `git checkout -- public/data/gem-index public/data/daily-digest.json`
 * を実行するかどうかを決める）。
 *
 * 時刻表記: 表示・記録用は JST（`YYYY-MM-DD HH:MM JST`）、機械処理用は UTC を維持
 * （`docs/rules/datetime-rules.md`）。
 *
 * 使い方:
 *   node tools/gem_pool_qa.mjs --check                    # 生成物の QA（違反があれば exit 1）
 *   node tools/gem_pool_qa.mjs --check --json              # 機械可読な JSON で結果を出力
 *   node tools/gem_pool_qa.mjs --no-op                    # 実質差分ゼロ判定（結果に関わらず exit 0）
 *   node tools/gem_pool_qa.mjs --no-op --json              # 機械可読な JSON で結果を出力
 *   node tools/gem_pool_qa.mjs --should-publish            # 反映可否判定（結果に関わらず exit 0）
 *   node tools/gem_pool_qa.mjs --should-publish --force    # workflow_dispatch の force_publish 相当
 *   node tools/gem_pool_qa.mjs --should-publish --json     # 機械可読な JSON で結果を出力
 *   node tools/gem_pool_qa.mjs --self-test                # ネットワーク・実データ不要のユニットテスト
 */

import { execFileSync } from 'node:child_process'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// ── 設定値（generate_gem_digest.mjs / output.mjs と同じパスを正本として参照する） ──
export const SHARD_DIR = 'public/data/gem-index'
export const INDEX_PATH = `${SHARD_DIR}/index.json`
export const DIGEST_PATH = 'public/data/daily-digest.json'

// 🔴 初期ヒューリスティック（docstring 参照・較正は follow-up issue）
export const REGISTRY_MIN_RATIO = 0.7 // 各レジストリの件数が前回比でこれ未満なら違反（30% 超の減少）
export const TOTAL_MIN_RATIO = 0.85 // 全体件数の前回比の下限
export const TOTAL_MAX_RATIO = 1.15 // 全体件数の前回比の上限

const REPO_ROOT = resolve(fileURLToPath(new URL('.', import.meta.url)), '..')

// ============================================================
// 純関数（I/O から分離。--self-test はここだけを検証する）
// ============================================================

/**
 * 差分パスが許可された配下だけかを判定する。
 *
 * @param {string[]} changedPaths `git diff --name-only` + `git ls-files --others --exclude-standard` の結果
 * @returns {{ok: boolean, offending: string[]}} 許可外パスがあれば ok=false・offending に列挙
 */
export function checkDiffScope(changedPaths) {
  const offending = (changedPaths ?? []).filter((p) => !isAllowedPath(p))
  return { ok: offending.length === 0, offending }
}

/** 許可されたパス（`public/data/gem-index/` 配下 または `public/data/daily-digest.json`）か。 */
function isAllowedPath(path) {
  const p = String(path ?? '').trim()
  if (p.length === 0) return true // 空行は無視（差分なし扱い）
  if (p === DIGEST_PATH) return true
  return p.startsWith(`${SHARD_DIR}/`)
}

/**
 * `index.json` の `shards[]` を前回・今回で突き合わせ、レジストリのゼロ化・消失・急減・
 * 全体の急減急増を検出する。
 *
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}|null} prevIndex
 *   HEAD 版の index.json（初回実行なら null）
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}} currIndex 今回の index.json
 * @returns {{ok: boolean, violations: string[]}}
 */
export function checkRegistryCounts(prevIndex, currIndex) {
  // HEAD 側に index.json が無い（初回実行）ときは比較のしようがないため PASS 扱い。
  if (!prevIndex || typeof prevIndex !== 'object') {
    return { ok: true, violations: [] }
  }

  const violations = []
  const prevByRegistry = new Map((prevIndex.shards ?? []).map((s) => [s.registry, s.count]))
  const currByRegistry = new Map((currIndex.shards ?? []).map((s) => [s.registry, s.count]))

  for (const [registry, prevCount] of prevByRegistry) {
    if (!(prevCount > 0)) continue // 前回時点で既に 0 件だったレジストリは急減判定の対象外
    const currCount = currByRegistry.get(registry)
    if (currCount === undefined) {
      violations.push(`registry "${registry}" が shards[] から消失しました（前回 ${prevCount} 件）`)
      continue
    }
    if (currCount === 0) {
      violations.push(`registry "${registry}" が 0 件になりました（前回 ${prevCount} 件）`)
      continue
    }
    const ratio = currCount / prevCount
    if (ratio < REGISTRY_MIN_RATIO) {
      violations.push(
        `registry "${registry}" が ${prevCount} → ${currCount} 件に急減しました（比率 ${ratio.toFixed(3)} < ${REGISTRY_MIN_RATIO}）`,
      )
    }
  }

  const prevTotal = Number(prevIndex.totalCount)
  const currTotal = Number(currIndex.totalCount)
  if (Number.isFinite(prevTotal) && prevTotal > 0 && Number.isFinite(currTotal)) {
    const ratio = currTotal / prevTotal
    if (ratio < TOTAL_MIN_RATIO || ratio > TOTAL_MAX_RATIO) {
      violations.push(
        `totalCount が ${prevTotal} → ${currTotal} に変化しました（比率 ${ratio.toFixed(3)} は許容範囲 [${TOTAL_MIN_RATIO}, ${TOTAL_MAX_RATIO}] 外）`,
      )
    }
  }

  return { ok: violations.length === 0, violations }
}

/**
 * 前回・今回の `index.json` を突き合わせ、PR 本文用の比較データ（前回比・レジストリ別件数）を作る。
 *
 * 🔴 これは合否判定（`checkRegistryCounts`）とは別の関数にする。判定に通っても報告用の
 * スナップショットは必要（PR 本文が「差分ゼロの無意味な値」を貼らないための唯一の情報源に
 * なる。コミット後に再計算すると HEAD が新コミットを指してしまい前回比が消えるため、
 * 呼び出し側はこの結果を生成直後・コミット前に 1 回だけファイルへ保存して使い回すこと）。
 *
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}|null} prevIndex
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}} currIndex
 * @returns {{totalCount: {prev: number|null, curr: number|null, ratio: number|null}, registries: {registry:string, prevCount: number|null, currCount: number|null}[]}}
 */
export function buildComparison(prevIndex, currIndex) {
  const prevByRegistry = new Map((prevIndex?.shards ?? []).map((s) => [s.registry, s.count]))
  const currByRegistry = new Map((currIndex?.shards ?? []).map((s) => [s.registry, s.count]))
  const allRegistries = new Set([...prevByRegistry.keys(), ...currByRegistry.keys()])
  const registries = [...allRegistries].sort().map((registry) => ({
    registry,
    prevCount: prevByRegistry.has(registry) ? prevByRegistry.get(registry) : null,
    currCount: currByRegistry.has(registry) ? currByRegistry.get(registry) : null,
  }))

  const prevTotal =
    prevIndex && Number.isFinite(Number(prevIndex.totalCount)) ? Number(prevIndex.totalCount) : null
  const currTotal = Number.isFinite(Number(currIndex?.totalCount))
    ? Number(currIndex.totalCount)
    : null
  const ratio =
    prevTotal !== null && prevTotal > 0 && currTotal !== null ? currTotal / prevTotal : null

  return { totalCount: { prev: prevTotal, curr: currTotal, ratio }, registries }
}

/**
 * `--check` の全検査を統合する。`comparison` は合否に関わらず常に含める（PR 本文用のスナップショット）。
 *
 * @param {{changedPaths: string[], prevIndex: object|null, currIndex: object}} input
 * @returns {{ok: boolean, diffScope: object, registryCounts: object, comparison: object}}
 */
export function runCheck({ changedPaths, prevIndex, currIndex }) {
  const diffScope = checkDiffScope(changedPaths)
  const registryCounts = checkRegistryCounts(prevIndex, currIndex)
  const comparison = buildComparison(prevIndex, currIndex)
  return { ok: diffScope.ok && registryCounts.ok, diffScope, registryCounts, comparison }
}

/**
 * JSON ドキュメントから `meta.generatedAt` / `date` を正規化する（no-op 判定用）。
 * 元オブジェクトは変更しない（immutable）。
 *
 * @param {object|null} doc
 * @returns {object|null}
 */
export function normalizeForDiff(doc) {
  if (!doc || typeof doc !== 'object') return doc
  const clone = structuredClone(doc)
  if (clone.meta && typeof clone.meta === 'object' && 'generatedAt' in clone.meta) {
    clone.meta.generatedAt = 'NORMALIZED'
  }
  if ('date' in clone) {
    clone.date = 'NORMALIZED'
  }
  return clone
}

/**
 * 正規化後の内容が完全一致するかを比較する（決定論的な JSON なので構造比較で足りる）。
 *
 * @param {object|null} prevDoc HEAD 版（存在しなければ null＝新規ファイル＝実差分扱い）
 * @param {object} currDoc 今回のドキュメント
 * @returns {boolean} 実質差分なしなら true
 */
export function docsEqualIgnoringTimestamps(prevDoc, currDoc) {
  if (prevDoc === null || prevDoc === undefined) return false // 新規ファイル＝実差分
  return JSON.stringify(normalizeForDiff(prevDoc)) === JSON.stringify(normalizeForDiff(currDoc))
}

/**
 * 複数ファイル分の no-op 判定を集約する。
 *
 * @param {{path: string, prevDoc: object|null, currDoc: object}[]} files
 * @returns {{noOp: boolean, changedFiles: string[]}}
 */
export function evaluateNoOp(files) {
  const changedFiles = (files ?? [])
    .filter((f) => !docsEqualIgnoringTimestamps(f.prevDoc, f.currDoc))
    .map((f) => f.path)
  return { noOp: changedFiles.length === 0, changedFiles }
}

/**
 * no-op 比較対象のパス一覧を組み立てる（作業ツリー ∪ HEAD 側の和集合。決定論的にソート）。
 *
 * 🔴 これが分離されている理由: `--no-op` の比較対象を「index.json / daily-digest.json の 2 つ
 * だけ」に固定すると、12 シャード本体（`public/data/gem-index/*.json`）の中身が変わった週でも
 * no_op=true と誤判定し、ワークフローが `git checkout --` でディレクトリごと巻き戻してしまう
 * （実害インシデント）。作業ツリー側の一覧だけでなく HEAD 側にしか無いファイル（今回消えた
 * シャード）も拾うため、両方の列挙結果を渡して和集合を取る。
 *
 * @param {string[]} worktreePaths 作業ツリー側の列挙結果
 * @param {string[]} headPaths HEAD 側の列挙結果
 * @returns {string[]}
 */
export function buildNoOpTargetPaths(worktreePaths, headPaths) {
  return [...new Set([...(worktreePaths ?? []), ...(headPaths ?? [])])].sort()
}

// 🔴 反映（コミット・push・PR 作成）間隔（Issue #482・日次生成 + 週次目安反映）。
// 生成物 3.6MB は反映のたびにリポジトリ履歴へ積まれるため、コストの実体は実行頻度ではなく
// 反映頻度にある。日次でパイプラインの健全性（生成・QA）を毎日検証しつつ、履歴コストは
// 週次相当に抑える。曜日固定にしないのは、`schedule` がドロップされた回に丸ごと飛ぶのを防ぐため
// （経過日数判定なら翌日に自己回復する）。
export const PUBLISH_INTERVAL_DAYS = 7
export const PUBLISH_INTERVAL_SEC = PUBLISH_INTERVAL_DAYS * 24 * 60 * 60

/**
 * 反映すべきかどうかを判定する（純関数・I/O から分離）。
 *
 * @param {number|null|undefined} lastPublishedEpochSec 直近の反映コミットの時刻（UNIX epoch 秒）。
 *   取得できない場合（生成物が main に無い＝初回、または `git log` が引けなかった）は null/undefined
 * @param {number} nowEpochSec 現在時刻（UNIX epoch 秒）
 * @param {boolean} [forcePublish=false] `workflow_dispatch` の `force_publish` 入力
 * @returns {boolean}
 */
export function shouldPublish(lastPublishedEpochSec, nowEpochSec, forcePublish = false) {
  if (forcePublish) return true
  // 🔴 取得できなかった（初回・git log が引けなかった）場合は「反映する」側に倒す。
  // 週次反映が丸ごと飛ぶより、初回相当として反映される方が安全（D-28 の SPOF 方針と同じ考え方）。
  if (lastPublishedEpochSec === null || lastPublishedEpochSec === undefined) return true
  if (!Number.isFinite(lastPublishedEpochSec) || !Number.isFinite(nowEpochSec)) return true
  return nowEpochSec - lastPublishedEpochSec >= PUBLISH_INTERVAL_SEC
}

// ============================================================
// I/O ヘルパー（git show / ファイル読み込み）
// ============================================================

/** `git show HEAD:<path>` の内容を JSON として読む。存在しなければ null。 */
function readHeadJson(relPath) {
  try {
    const text = execFileSync('git', ['show', `HEAD:${relPath}`], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    return JSON.parse(text)
  } catch {
    return null // 新規ファイル、または HEAD に存在しない
  }
}

/** 作業ツリーの JSON を読む。存在しなければ null。 */
function readWorktreeJson(relPath) {
  try {
    return JSON.parse(readFileSync(resolve(REPO_ROOT, relPath), 'utf8'))
  } catch {
    return null
  }
}

/**
 * `INDEX_PATH` を最後に変更したコミット（HEAD から辿れる範囲）の時刻を調べる。
 *
 * 🔴 「履歴に該当コミットが無い（＝初回・正常）」と「`git log` 自体が失敗した（＝異常。
 * 浅いクローン・git の一時的な異常終了等）」を **区別する**。どちらも `epochSec: null` を返し
 * `shouldPublish()` は変わらず反映側に倒す（fail-open は維持。反映しない側に倒すと週次反映が
 * 永久に止まりうるため）が、後者だけ `warning` に理由を積む。これにより「取得が壊れていて
 * 毎日反映へ静かに後退している」事態を `--should-publish --json` の出力・ワークフローの
 * ログから検知できるようにする（本関数を呼ぶ限り、失敗が沈黙しない）。
 *
 * @returns {{epochSec: number|null, warning: string|null}}
 */
function getLastPublishedInfo() {
  try {
    const text = execFileSync('git', ['log', '-1', '--format=%ct', 'HEAD', '--', INDEX_PATH], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'], // 🔴 stderr は握り潰さず拾う（異常時の可視化に使う）
    }).trim()
    if (text.length === 0) {
      // git log 自体は正常終了したが、該当パスの変更履歴が無い（初回。正常系）。
      return { epochSec: null, warning: null }
    }
    const epoch = Number(text)
    if (!Number.isFinite(epoch)) {
      return {
        epochSec: null,
        warning: `git log の出力を時刻として解釈できませんでした（異常終了ではない・出力: ${JSON.stringify(text).slice(0, 200)}）`,
      }
    }
    return { epochSec: epoch, warning: null }
  } catch (err) {
    // git log 自体が失敗（非ゼロ終了・コマンド不在等）。fetch-depth 不足・git の一時的な異常等。
    const stderrText =
      typeof err?.stderr === 'string'
        ? err.stderr
        : Buffer.isBuffer(err?.stderr)
          ? err.stderr.toString('utf8')
          : ''
    const reason = (stderrText || err?.message || 'unknown error').trim().slice(0, 300)
    return {
      epochSec: null,
      warning: `git log が失敗しました（反映側へフォールバックしています。要調査）: ${reason}`,
    }
  }
}

/** 作業ツリー側の `dirRelPath` 配下にある `*.json` の相対パス一覧（ソート済み）。無ければ空配列。 */
function listWorktreeJsonFiles(dirRelPath) {
  try {
    return readdirSync(resolve(REPO_ROOT, dirRelPath))
      .filter((f) => f.endsWith('.json'))
      .map((f) => `${dirRelPath}/${f}`)
      .sort()
  } catch {
    return []
  }
}

/** HEAD 側の `dirRelPath` 配下にある `*.json` の相対パス一覧（ソート済み）。無ければ空配列。 */
function listHeadJsonFiles(dirRelPath) {
  try {
    const text = execFileSync('git', ['ls-tree', '-r', '--name-only', 'HEAD', '--', dirRelPath], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    return text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.endsWith('.json'))
      .sort()
  } catch {
    return []
  }
}

/** `git diff --name-only`（作業ツリー変更） + 未追跡ファイルの一覧を取得する。 */
function listChangedPaths() {
  const tracked = execFileSync('git', ['diff', '--name-only'], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  })
    .split('\n')
    .filter((l) => l.trim().length > 0)
  const untracked = execFileSync('git', ['ls-files', '--others', '--exclude-standard'], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  })
    .split('\n')
    .filter((l) => l.trim().length > 0)
  return [...tracked, ...untracked]
}

/** すべてのシャードファイル名（今回の index.json の shards[].fileName）を列挙する。 */
function listShardFileNames(index) {
  return (index?.shards ?? []).map((s) => s.fileName).filter((f) => typeof f === 'string')
}

// ============================================================
// JST 表示ヘルパー（datetime-rules.md 準拠。人間向け表示のみ・機械処理は UTC のまま扱う）
// ============================================================

/**
 * `Intl.DateTimeFormat` が挿入する非標準の空白（narrow no-break space U+202F・
 * no-break space U+00A0 等。ICU のバージョンによって sv-SE ロケールの日付/時刻区切りに
 * 使われることがある）を通常の半角スペース 1 個へ正規化する（純関数・self-test 対象）。
 *
 * @param {string} value
 * @returns {string}
 */
export function normalizeSpaces(value) {
  return String(value ?? '').replace(/\s+/gu, ' ')
}

function nowJstLabel() {
  const fmt = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Tokyo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date())
  return `${normalizeSpaces(fmt)} JST`
}

// ============================================================
// モード実装
// ============================================================

function runCheckMode({ json }) {
  const currIndex = readWorktreeJson(INDEX_PATH)
  if (!currIndex) {
    // 生成物が無い＝ generate_gem_digest.mjs 側が既に失敗している状態のはず。
    // QA としても検査対象が無いので違反として扱う（fail-closed）。
    const result = {
      ok: false,
      reason: `${INDEX_PATH} が見つかりません（生成が完走していない可能性があります）`,
      checkedAt: nowJstLabel(),
    }
    printResult(result, json)
    process.exit(1)
  }

  const prevIndex = readHeadJson(INDEX_PATH)
  const changedPaths = listChangedPaths()
  const result = {
    ...runCheck({ changedPaths, prevIndex, currIndex }),
    checkedAt: nowJstLabel(),
  }
  printResult(result, json)
  process.exit(result.ok ? 0 : 1)
}

function runNoOpMode({ json }) {
  const currIndex = readWorktreeJson(INDEX_PATH)
  const currDigest = readWorktreeJson(DIGEST_PATH)
  if (!currIndex || !currDigest) {
    const result = {
      no_op: false,
      reason: '生成物（index.json / daily-digest.json）が見つかりません',
      checkedAt: nowJstLabel(),
    }
    printResult(result, json)
    process.exit(0) // no-op 判定モード自体は失敗ではないので exit 0（判定は呼び出し側が読む）
  }

  // 🔴 index.json / daily-digest.json の 2 つだけでなく、12 シャード本体（public/data/gem-index/*.json）
  // も比較対象に含める（長尾エントリだけが動いた週を no_op=true と誤判定しないため）。
  // 作業ツリー側の一覧だけでなく HEAD 側にしか無いファイル（今回消えたシャード）も拾う。
  const shardPaths = buildNoOpTargetPaths(
    listWorktreeJsonFiles(SHARD_DIR),
    listHeadJsonFiles(SHARD_DIR),
  )

  const evaluation = evaluateNoOp([
    ...shardPaths.map((path) => ({
      path,
      prevDoc: readHeadJson(path),
      currDoc: readWorktreeJson(path),
    })),
    { path: DIGEST_PATH, prevDoc: readHeadJson(DIGEST_PATH), currDoc: currDigest },
  ])

  const result = {
    no_op: evaluation.noOp,
    changedFiles: evaluation.changedFiles,
    checkedAt: nowJstLabel(),
  }
  printResult(result, json)
  process.exit(0)
}

/**
 * 反映（コミット・push・PR 作成）すべきかどうかを判定する（Issue #482）。
 * ワークフロー側は本モードの `should_publish` を読むだけにし、日数計算を YAML に書かない。
 */
function runShouldPublishMode({ json, force }) {
  const { epochSec: lastPublishedEpochSec, warning } = getLastPublishedInfo()
  const nowEpochSec = Math.floor(Date.now() / 1000)
  const publish = shouldPublish(lastPublishedEpochSec, nowEpochSec, force)
  const daysElapsed =
    lastPublishedEpochSec === null
      ? null
      : Number(((nowEpochSec - lastPublishedEpochSec) / 86400).toFixed(2))

  const result = {
    should_publish: publish,
    lastPublishedEpochSec,
    nowEpochSec,
    forcePublish: Boolean(force),
    daysElapsed,
    checkedAt: nowJstLabel(),
    // 🔴 正常系（初回・force）ではキー自体を出さない。異常系（git log 失敗）のときだけ載せ、
    // ワークフロー側のログ・PR 本文で「静かな fail-open」を検知できるようにする。
    ...(warning ? { warning } : {}),
  }
  printResult(result, json)
  process.exit(0) // 判定モード自体は失敗ではないので exit 0（判定は呼び出し側が読む）
}

function printResult(result, json) {
  if (json) {
    process.stdout.write(`${JSON.stringify(result)}\n`)
    return
  }
  if ('no_op' in result) {
    if (result.no_op) {
      console.log(`no-op: 実質差分なし（${result.checkedAt}）`)
    } else {
      console.log(`差分あり: ${(result.changedFiles ?? []).join(', ')}（${result.checkedAt}）`)
    }
    return
  }
  if ('should_publish' in result) {
    const elapsed = result.daysElapsed === null ? '(初回/不明)' : `${result.daysElapsed}日`
    console.log(
      `should_publish=${result.should_publish}（経過 ${elapsed}・force=${result.forcePublish}・${result.checkedAt}）`,
    )
    if (result.warning) console.log(`  - WARNING: ${result.warning}`)
    return
  }
  if (result.ok) {
    console.log(`PASS: Gem 候補プール QA（${result.checkedAt}）`)
    return
  }
  console.log(`FAIL: Gem 候補プール QA（${result.checkedAt}）`)
  if (result.reason) console.log(`  - ${result.reason}`)
  for (const p of result.diffScope?.offending ?? []) {
    console.log(`  - 許可外パスの差分: ${p}`)
  }
  for (const v of result.registryCounts?.violations ?? []) {
    console.log(`  - ${v}`)
  }
}

// ============================================================
// self-test（ネットワーク・実データ非依存）
// ============================================================

function selfTest() {
  const failures = []
  const assert = (label, cond) => {
    if (!cond) failures.push(label)
  }

  // --- normalizeSpaces ---
  assert(
    'normalizeSpaces: narrow no-break space (U+202F) を半角スペースへ正規化する',
    normalizeSpaces('2026-08-23\u202F10:38') === '2026-08-23 10:38',
  )
  assert(
    'normalizeSpaces: no-break space (U+00A0) を半角スペースへ正規化する',
    normalizeSpaces('2026-08-23\u00A010:38') === '2026-08-23 10:38',
  )
  assert(
    'normalizeSpaces: 連続する空白は 1 個にまとめる（g フラグが効いている）',
    normalizeSpaces('a\u202F\u202Fb   c') === 'a b c',
  )
  assert(
    'normalizeSpaces: 通常の半角スペースはそのまま',
    normalizeSpaces('2026-08-23 10:38') === '2026-08-23 10:38',
  )

  // --- checkDiffScope ---
  assert(
    'checkDiffScope: 許可パスのみなら ok',
    checkDiffScope([`${SHARD_DIR}/registry-a.json`, DIGEST_PATH, `${SHARD_DIR}/index.json`]).ok ===
      true,
  )
  assert(
    'checkDiffScope: 許可外パスがあれば ok=false',
    checkDiffScope([`${SHARD_DIR}/index.json`, 'tools/generate_gem_digest.mjs']).ok === false,
  )
  assert('checkDiffScope: 空配列は ok', checkDiffScope([]).ok === true)
  assert(
    'checkDiffScope: 空文字列を含んでも無視される',
    checkDiffScope(['', `${SHARD_DIR}/a.json`]).ok === true,
  )

  // --- checkRegistryCounts ---
  assert(
    'checkRegistryCounts: prevIndex が null なら PASS（初回実行）',
    checkRegistryCounts(null, { totalCount: 100, shards: [{ registry: 'registry-a', count: 100 }] })
      .ok === true,
  )
  {
    const prev = {
      totalCount: 1000,
      shards: [
        { registry: 'registry-a', count: 600 },
        { registry: 'registry-b', count: 400 },
      ],
    }
    const currOk = {
      totalCount: 980,
      shards: [
        { registry: 'registry-a', count: 590 },
        { registry: 'registry-b', count: 390 },
      ],
    }
    assert('checkRegistryCounts: 軽微な増減は PASS', checkRegistryCounts(prev, currOk).ok === true)

    const currZero = {
      totalCount: 600,
      shards: [{ registry: 'registry-a', count: 600 }],
    }
    const zeroResult = checkRegistryCounts(prev, currZero)
    assert('checkRegistryCounts: レジストリ消失は violation', zeroResult.ok === false)
    assert(
      'checkRegistryCounts: 消失メッセージに registry 名を含む',
      zeroResult.violations.some((v) => v.includes('registry-b')),
    )

    const currRegistryDrop = {
      totalCount: 750,
      shards: [
        { registry: 'registry-a', count: 600 },
        { registry: 'registry-b', count: 150 }, // 400 → 150 = 62.5%減 > 30%
      ],
    }
    const dropResult = checkRegistryCounts(prev, currRegistryDrop)
    assert('checkRegistryCounts: 30% 超の急減は violation', dropResult.ok === false)

    const currTotalSpike = {
      totalCount: 1300, // 1000 → 1300 = 比率 1.3 > 1.15
      shards: [
        { registry: 'registry-a', count: 750 },
        { registry: 'registry-b', count: 550 },
      ],
    }
    const spikeResult = checkRegistryCounts(prev, currTotalSpike)
    assert('checkRegistryCounts: 全体急増は violation', spikeResult.ok === false)

    const currRegistryZeroCount = {
      totalCount: 600,
      shards: [
        { registry: 'registry-a', count: 600 },
        { registry: 'registry-b', count: 0 },
      ],
    }
    assert(
      'checkRegistryCounts: count===0（配列には残るがゼロ）も violation',
      checkRegistryCounts(prev, currRegistryZeroCount).ok === false,
    )

    const prevWithZero = {
      totalCount: 600,
      shards: [
        { registry: 'registry-a', count: 600 },
        { registry: 'gone.org', count: 0 },
      ],
    }
    assert(
      'checkRegistryCounts: 前回時点で既に 0 件だったレジストリの消失は対象外',
      checkRegistryCounts(prevWithZero, {
        totalCount: 600,
        shards: [{ registry: 'registry-a', count: 600 }],
      }).ok === true,
    )
  }

  // --- checkRegistryCounts: 閾値の境界値（REGISTRY_MIN_RATIO / TOTAL_MIN_RATIO / TOTAL_MAX_RATIO） ---
  {
    // REGISTRY_MIN_RATIO(0.7) ちょうど: PASS（`<` であって `<=` ではない）。他方を補って totalCount は 1.0 に保つ。
    const prevReg = {
      totalCount: 2000,
      shards: [
        { registry: 'registry-a', count: 1000 },
        { registry: 'registry-b', count: 1000 },
      ],
    }
    const currRegAtBoundary = {
      totalCount: 2000,
      shards: [
        { registry: 'registry-a', count: 700 },
        { registry: 'registry-b', count: 1300 },
      ],
    }
    const atBoundary = checkRegistryCounts(prevReg, currRegAtBoundary)
    assert(
      'checkRegistryCounts: レジストリ比率がちょうど 0.7 は PASS（境界値）',
      atBoundary.ok === true && atBoundary.violations.length === 0,
    )

    // 境界のわずか下（0.699）: FAIL
    const currRegBelowBoundary = {
      totalCount: 2000,
      shards: [
        { registry: 'registry-a', count: 699 },
        { registry: 'registry-b', count: 1301 },
      ],
    }
    const belowBoundary = checkRegistryCounts(prevReg, currRegBelowBoundary)
    assert(
      'checkRegistryCounts: レジストリ比率が 0.7 をわずかに下回ると violation（境界値）',
      belowBoundary.ok === false && belowBoundary.violations.length === 1,
    )

    // TOTAL_MIN_RATIO(0.85) ちょうど: PASS。各レジストリは 0.85（>=0.7）で個別 violation を踏まない。
    const prevTotalLow = {
      totalCount: 1000,
      shards: [
        { registry: 'registry-a', count: 500 },
        { registry: 'registry-b', count: 500 },
      ],
    }
    const currTotalAtLowBoundary = {
      totalCount: 850,
      shards: [
        { registry: 'registry-a', count: 425 },
        { registry: 'registry-b', count: 425 },
      ],
    }
    const totalLowBoundary = checkRegistryCounts(prevTotalLow, currTotalAtLowBoundary)
    assert(
      'checkRegistryCounts: totalCount 比率がちょうど 0.85 は PASS（境界値）',
      totalLowBoundary.ok === true && totalLowBoundary.violations.length === 0,
    )

    // 【項目4】各レジストリは 0.7 以上を保ったまま、totalCount だけが 0.85 をわずかに下回る（単独発火の確認）。
    const currTotalOnlyDrop = {
      totalCount: 824,
      shards: [
        { registry: 'registry-a', count: 400 },
        { registry: 'registry-b', count: 424 },
      ],
    } // 0.8 / 0.848 はいずれも >= 0.7
    const totalOnlyDrop = checkRegistryCounts(prevTotalLow, currTotalOnlyDrop)
    assert(
      'checkRegistryCounts: 各レジストリが 0.7 以上でも totalCount 単独で < 0.85 なら violation',
      totalOnlyDrop.ok === false,
    )
    assert(
      'checkRegistryCounts: totalCount 単独違反は violations が 1 件だけ（レジストリ単位は無傷）',
      totalOnlyDrop.violations.length === 1,
    )
    assert(
      'checkRegistryCounts: totalCount 単独違反のメッセージに totalCount を含む',
      totalOnlyDrop.violations[0].includes('totalCount'),
    )

    // TOTAL_MAX_RATIO(1.15) ちょうど: PASS
    const prevTotalHigh = { totalCount: 1000, shards: [{ registry: 'registry-a', count: 1000 }] }
    const currTotalAtHighBoundary = {
      totalCount: 1150,
      shards: [{ registry: 'registry-a', count: 1150 }],
    }
    const totalHighBoundary = checkRegistryCounts(prevTotalHigh, currTotalAtHighBoundary)
    assert(
      'checkRegistryCounts: totalCount 比率がちょうど 1.15 は PASS（境界値）',
      totalHighBoundary.ok === true && totalHighBoundary.violations.length === 0,
    )

    // 境界のわずか上（1.151）: FAIL
    const currTotalAboveHighBoundary = {
      totalCount: 1151,
      shards: [{ registry: 'registry-a', count: 1151 }],
    }
    const totalAboveHighBoundary = checkRegistryCounts(prevTotalHigh, currTotalAboveHighBoundary)
    assert(
      'checkRegistryCounts: totalCount 比率が 1.15 をわずかに超えると violation（境界値）',
      totalAboveHighBoundary.ok === false,
    )
  }

  // --- buildComparison ---
  {
    const prev = {
      totalCount: 1000,
      shards: [
        { registry: 'registry-a', count: 600 },
        { registry: 'registry-b', count: 400 },
      ],
    }
    const curr = {
      totalCount: 950,
      shards: [
        { registry: 'registry-a', count: 600 },
        { registry: 'registry-c', count: 350 },
      ],
    }
    const cmp = buildComparison(prev, curr)
    assert(
      'buildComparison: totalCount.prev/curr が入る',
      cmp.totalCount.prev === 1000 && cmp.totalCount.curr === 950,
    )
    assert('buildComparison: ratio が計算される', Math.abs(cmp.totalCount.ratio - 0.95) < 1e-9)
    assert(
      'buildComparison: 消失レジストリは currCount=null',
      cmp.registries.find((r) => r.registry === 'registry-b')?.currCount === null,
    )
    assert(
      'buildComparison: 新規レジストリは prevCount=null',
      cmp.registries.find((r) => r.registry === 'registry-c')?.prevCount === null,
    )
    assert(
      'buildComparison: registries はレジストリ名昇順',
      cmp.registries.map((r) => r.registry).join(',') === 'registry-a,registry-b,registry-c',
    )

    const cmpFirstRun = buildComparison(null, curr)
    assert(
      'buildComparison: 初回実行（prevIndex=null）は totalCount.prev/ratio が null',
      cmpFirstRun.totalCount.prev === null && cmpFirstRun.totalCount.ratio === null,
    )
  }

  // --- runCheck 統合 ---
  {
    const prevIndex = { totalCount: 100, shards: [{ registry: 'registry-a', count: 100 }] }
    const currIndex = { totalCount: 98, shards: [{ registry: 'registry-a', count: 98 }] }
    const ok = runCheck({
      changedPaths: [`${SHARD_DIR}/registry-a.json`, `${SHARD_DIR}/index.json`],
      prevIndex,
      currIndex,
    })
    assert('runCheck: 正常系は ok', ok.ok === true)

    const bad = runCheck({
      changedPaths: [`${SHARD_DIR}/index.json`, 'README.md'],
      prevIndex,
      currIndex,
    })
    assert('runCheck: 許可外パスがあれば ok=false', bad.ok === false)
  }

  // --- normalizeForDiff / docsEqualIgnoringTimestamps ---
  {
    const a = { meta: { generatedAt: '2026-08-22T06:00:00.000Z', source: 'x' }, totalCount: 5 }
    const b = { meta: { generatedAt: '2026-08-29T06:00:00.000Z', source: 'x' }, totalCount: 5 }
    assert(
      'docsEqualIgnoringTimestamps: generatedAt だけ違えば同一扱い',
      docsEqualIgnoringTimestamps(a, b) === true,
    )
    assert(
      'normalizeForDiff: 元オブジェクトを変更しない',
      a.meta.generatedAt === '2026-08-22T06:00:00.000Z',
    )

    const c = { date: '20260822', meta: { generatedAt: 'x' }, candidates: [1, 2] }
    const d = { date: '20260829', meta: { generatedAt: 'y' }, candidates: [1, 2] }
    assert(
      'docsEqualIgnoringTimestamps: date だけ違えば同一扱い（digest）',
      docsEqualIgnoringTimestamps(c, d) === true,
    )

    const e = { date: '20260829', meta: { generatedAt: 'y' }, candidates: [1, 2, 3] }
    assert(
      'docsEqualIgnoringTimestamps: candidates が違えば実差分',
      docsEqualIgnoringTimestamps(c, e) === false,
    )

    assert(
      'docsEqualIgnoringTimestamps: prevDoc が null なら実差分（新規ファイル）',
      docsEqualIgnoringTimestamps(null, c) === false,
    )
  }

  // --- evaluateNoOp ---
  {
    const files = [
      {
        path: INDEX_PATH,
        prevDoc: { meta: { generatedAt: 'a' }, totalCount: 5 },
        currDoc: { meta: { generatedAt: 'b' }, totalCount: 5 },
      },
      {
        path: DIGEST_PATH,
        prevDoc: { date: '20260822', meta: { generatedAt: 'a' }, candidates: [] },
        currDoc: { date: '20260829', meta: { generatedAt: 'b' }, candidates: [] },
      },
    ]
    const evalOk = evaluateNoOp(files)
    assert('evaluateNoOp: 両方 timestamp だけ違えば no_op=true', evalOk.noOp === true)

    files[1].currDoc.candidates = [{ x: 1 }]
    const evalChanged = evaluateNoOp(files)
    assert('evaluateNoOp: 片方に実差分があれば no_op=false', evalChanged.noOp === false)
    assert(
      'evaluateNoOp: changedFiles に対象パスが載る',
      evalChanged.changedFiles.includes(DIGEST_PATH) &&
        !evalChanged.changedFiles.includes(INDEX_PATH),
    )
  }

  // --- evaluateNoOp: シャード本体（public/data/gem-index/*.json）を含めたケース（CRITICAL 再発防止） ---
  // 「index.json / daily-digest.json の集計値は前回と同じまま、シャードの長尾エントリだけが
  // 変わった週」を no_op=true と誤判定しないことを固定する（実インシデントの再現）。
  {
    const shardA = `${SHARD_DIR}/registry-a.json`
    const shardB = `${SHARD_DIR}/registry-b.json`
    const baseFiles = () => [
      {
        path: INDEX_PATH,
        prevDoc: { meta: { generatedAt: 'a' }, totalCount: 2 },
        currDoc: { meta: { generatedAt: 'b' }, totalCount: 2 },
      },
      {
        path: DIGEST_PATH,
        prevDoc: { date: '20260822', meta: { generatedAt: 'a' }, candidates: [] },
        currDoc: { date: '20260829', meta: { generatedAt: 'b' }, candidates: [] },
      },
      {
        path: shardA,
        prevDoc: {
          registry: 'registry-a',
          meta: { generatedAt: 'a' },
          entries: [['owner/repo', 'pkg', 100, 5, 1]],
        },
        currDoc: {
          registry: 'registry-a',
          meta: { generatedAt: 'b' },
          entries: [['owner/repo', 'pkg', 100, 5, 1]],
        },
      },
    ]

    const unchangedShard = evaluateNoOp(baseFiles())
    assert(
      'evaluateNoOp: シャードも timestamp だけ違えば no_op=true（回帰しないことの確認）',
      unchangedShard.noOp === true,
    )

    // 1) シャード 1 件だけ中身（entries の長尾エントリ）が変わった → no_op=false
    const filesShardChanged = baseFiles()
    filesShardChanged[2].currDoc.entries = [['owner/repo', 'pkg', 101, 6, 1]]
    const shardChanged = evaluateNoOp(filesShardChanged)
    assert(
      'evaluateNoOp: シャード本体の entries だけが変わっても no_op=false（CRITICAL 再発防止の核心）',
      shardChanged.noOp === false,
    )
    assert(
      'evaluateNoOp: changedFiles にシャードのパスが載る',
      shardChanged.changedFiles.includes(shardA),
    )

    // 2) シャードが新規追加された（HEAD に無く作業ツリーにだけ存在）→ no_op=false
    const filesShardAdded = [
      ...baseFiles(),
      {
        path: shardB,
        prevDoc: null,
        currDoc: { registry: 'registry-b', meta: { generatedAt: 'b' }, entries: [] },
      },
    ]
    const shardAdded = evaluateNoOp(filesShardAdded)
    assert('evaluateNoOp: シャードの新規追加は no_op=false', shardAdded.noOp === false)
    assert(
      'evaluateNoOp: 新規シャードのパスが changedFiles に載る',
      shardAdded.changedFiles.includes(shardB),
    )

    // 3) シャードが消失した（HEAD にはあったが作業ツリーに無い＝ currDoc=null）→ no_op=false
    const filesShardRemoved = [
      ...baseFiles(),
      {
        path: shardB,
        prevDoc: { registry: 'registry-b', meta: { generatedAt: 'a' }, entries: [] },
        currDoc: null,
      },
    ]
    const shardRemoved = evaluateNoOp(filesShardRemoved)
    assert('evaluateNoOp: シャードの消失は no_op=false', shardRemoved.noOp === false)
  }

  // --- buildNoOpTargetPaths ---
  {
    const worktree = [`${SHARD_DIR}/a.json`, `${SHARD_DIR}/index.json`]
    const head = [`${SHARD_DIR}/a.json`, `${SHARD_DIR}/removed.json`]
    const union = buildNoOpTargetPaths(worktree, head)
    assert(
      'buildNoOpTargetPaths: 作業ツリー ∪ HEAD の和集合・重複排除・ソート済み',
      union.join(',') === `${SHARD_DIR}/a.json,${SHARD_DIR}/index.json,${SHARD_DIR}/removed.json`,
    )
    assert('buildNoOpTargetPaths: 両方空なら空配列', buildNoOpTargetPaths([], []).length === 0)
    assert(
      'buildNoOpTargetPaths: 片方 undefined でも例外を投げない',
      buildNoOpTargetPaths(undefined, [`${SHARD_DIR}/x.json`]).length === 1,
    )
  }

  // --- shouldPublish（Issue #482: 日次生成・週次目安反映） ---
  {
    const now = 1_700_000_000 // 適当な基準時刻（UNIX epoch 秒）
    const sevenDaysAgo = now - PUBLISH_INTERVAL_SEC
    assert(
      'shouldPublish: ちょうど 7 日経過は反映する（境界値・>= であって > ではない）',
      shouldPublish(sevenDaysAgo, now, false) === true,
    )

    const justUnderSevenDays = now - (PUBLISH_INTERVAL_SEC - 1) // 7 日に 1 秒足りない ≒ 6.99...日
    assert(
      'shouldPublish: 7 日にわずかに満たない場合は反映しない（境界値）',
      shouldPublish(justUnderSevenDays, now, false) === false,
    )

    assert(
      'shouldPublish: 経過日数が null（初回・取得不能）なら反映する',
      shouldPublish(null, now, false) === true,
    )
    assert(
      'shouldPublish: 経過日数が undefined でも反映する',
      shouldPublish(undefined, now, false) === true,
    )

    assert(
      'shouldPublish: force_publish=true なら経過日数 0 でも反映する',
      shouldPublish(now, now, true) === true,
    )
    assert(
      'shouldPublish: force_publish=false・経過日数 0 は反映しない',
      shouldPublish(now, now, false) === false,
    )
    assert(
      'shouldPublish: NaN 等の不正な数値は安全側（反映する）に倒す',
      shouldPublish(Number.NaN, now, false) === true,
    )

    // クロックずれ（前回反映のコミット時刻が実行時計より進んでいる）: 無闇に反映しない。
    const futureEpoch = now + 3600 // 1 時間先の未来
    assert(
      'shouldPublish: 前回反映が未来時刻（クロックずれ）なら反映しない',
      shouldPublish(futureEpoch, now, false) === false,
    )
    // ただし十分時間が経てば自己回復する（未来時刻 + 8 日後の now なら反映する）。
    const eightDaysAfterFuture = futureEpoch + 8 * 24 * 60 * 60
    assert(
      'shouldPublish: 未来時刻でも 8 日後には自己回復して反映する',
      shouldPublish(futureEpoch, eightDaysAfterFuture, false) === true,
    )
  }

  // --- listShardFileNames（純関数として export はしていないが、内部ロジックの健全性を index 経由で確認） ---
  assert(
    'listShardFileNames 相当: shards[].fileName を列挙できる',
    listShardFileNames({ shards: [{ fileName: 'a.json' }, { fileName: 'b.json' }] }).join(',') ===
      'a.json,b.json',
  )

  if (failures.length > 0) {
    console.error(`FAIL: gem_pool_qa.mjs --self-test（${failures.length} 件失敗）`)
    for (const f of failures) console.error(`  - ${f}`)
    process.exit(1)
  }
  console.log(`PASS: gem_pool_qa.mjs --self-test（${nowJstLabel()}）`)
  process.exit(0)
}

// ============================================================
// CLI エントリポイント
// ============================================================

function main() {
  const argv = process.argv.slice(2)
  const json = argv.includes('--json')

  if (argv.includes('--self-test')) {
    selfTest()
    return
  }
  if (argv.includes('--check')) {
    runCheckMode({ json })
    return
  }
  if (argv.includes('--no-op')) {
    runNoOpMode({ json })
    return
  }
  if (argv.includes('--should-publish')) {
    runShouldPublishMode({ json, force: argv.includes('--force') })
    return
  }

  console.error(
    '使い方: node tools/gem_pool_qa.mjs [--check|--no-op|--should-publish [--force]|--self-test] [--json]',
  )
  process.exit(2)
}

const isMain =
  typeof process.argv[1] === 'string' &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))
if (isMain) {
  main()
}
