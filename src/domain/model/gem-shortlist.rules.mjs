// @ts-check
// 🔴 本ファイルは `tsconfig.json` の `include`（`**/*.ts` / `**/*.mts`）に載らず
//    `tsc --noEmit` の対象外になるため、`@ts-check` で JSDoc 型を検証させる（`gem-index.rules.mjs` と同様）。
/**
 * shortlist（Gem Index 上位帯）選定ロジックの **単一正本**（Issue #335）。
 *
 * 🔴 **なぜドメイン層に `.mjs` を置くのか**（`gem-index.rules.mjs` と同じ理由）: 同じロジックを
 * 使う経路が 2 つあり、片方が TypeScript を読めないため。
 *
 * - アプリ（`src/domain/model/gem-shortlist.ts`）: `GemIndex` ブランド型を伴う
 * - 較正計測ツール（`tools/analyze_shortlist_distribution.mjs`）: `node tools/... .mjs` で
 *   直接実行されるため TypeScript を import できない
 *
 * かつて計測ツールは esbuild でその場トランスパイルして `gem-shortlist.ts` を import していたが、
 * 実行のたびにビルドを走らせるのは `gem-index.rules.mjs` が既に確立した「TypeScript を読めない側は
 * 型を剥がした共有実装を直接 import する」という解法から外れていた。本ファイルへの分離でその解法に揃える。
 *
 * 🔵 `gemIndexValue()`（ブランド剥がし・実体はキャストのみ）は型システム上の演算であり実行時の
 * 処理を持たないため、本ファイルは `Gem` を「`{ packageName: string, gemIndex: number }` の
 * 構造的部分型」として扱う（`@template` で表現）。ブランドの検証（`Number.isFinite`）は
 * `gem-index.ts` の `gemIndex()` コンストラクタ側の責務で、ここでは再検証しない。
 *
 * 🔵 依存ゼロの純粋関数のみで構成する（`import` を足さない）。ドメイン層の依存規則
 * （`docs/rules/architecture-rules.md`）どおり、ここは何にも依存しない。
 */

/**
 * 日次シャッフルの母集団サイズ（Gem Index 上位帯・shortlist）。
 *
 * 較正根拠の正本は `ADR 0014` §2.2.3。値の意味・再測定コマンドは
 * [`gem-shortlist.ts`](./gem-shortlist.ts) の JSDoc を参照（説明の重複を避けるため、
 * 詳しい根拠はそちらか ADR のどちらか片方にのみ書く）。
 */
export const GEM_INDEX_SHORTLIST_SIZE = 60

/**
 * Gem Index 昇順の比較関数（値が小さいほど過小評価度が高い＝上位）。タイブレークなし。
 *
 * @template {{ packageName: string, gemIndex: number }} G
 * @param {G} a
 * @param {G} b
 * @returns {number}
 */
export function byGemIndexAsc(a, b) {
  return a.gemIndex - b.gemIndex
}

/**
 * 候補群から Gem Index 上位 `size` 件を選ぶ。同値は packageName asc でタイブレークし、
 * 入力順に依存させない。`size` が候補数以上のときは全件を返し、`size` が 0 以下のときは
 * 空配列を返す。
 *
 * @template {{ packageName: string, gemIndex: number }} G
 * @param {readonly G[]} candidates
 * @param {number} size
 * @returns {readonly G[]}
 */
export function selectGemIndexShortlist(candidates, size) {
  if (size <= 0) return []
  return [...candidates]
    .sort((a, b) => {
      const diff = byGemIndexAsc(a, b)
      if (diff !== 0) return diff
      return a.packageName < b.packageName ? -1 : a.packageName > b.packageName ? 1 : 0
    })
    .slice(0, size)
}
