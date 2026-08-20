import { AxeBuilder } from '@axe-core/playwright'
import type { Page } from '@playwright/test'

/**
 * `@axe-core/playwright` の `page` 引数の型は自身の peerDependency `playwright-core` から
 * 解決される。`@playwright/test`（1.56.1）が同梱する `playwright-core`（1.56.1）と
 * `@axe-core/playwright` が要求する `playwright-core`（>=1.0.0・実解決 1.62.1）はバージョンが
 * 揃わないため、実行時は互換でも `tsc` が構造的に弾く（新しい方の `Page` 型にだけ存在する
 * メソッドが欠けていると判定される）。本ファイルでキャストを 1 箇所に集約して吸収する。
 */
export function createAxeBuilder(page: Page): AxeBuilder {
  return new AxeBuilder({
    page: page as unknown as ConstructorParameters<typeof AxeBuilder>[0]['page'],
  })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
}

/**
 * 🔴 `withTags` による WCAG 2.2 AA ルールセット指定は「axe が持つ自動検出ルールの
 * カバレッジを WCAG 2.2 まで広げる」だけであり、これで `#179` クラス（フォーカスリングの
 * 非テキストコントラスト・SC 1.4.11）が検出できるようになるわけではない。axe-core は
 * `:focus-visible` を発火させる操作（Tab 押下）を行わない DOM 静的解析であり、フォーカス状態
 * そのものを評価しない（`content/discussions/sp10_a11y_20260820/whiteboard.md` round2/round3
 * で a11y_impl・gate_infra が独立に到達し e2e_verify が追認・lead 判定で確定）。
 * この種の欠陥は `tools/check_contrast.py`（静的トークン検査）が担当する
 * （`docs/03_design/ui-ux/ui-ux-guidelines.md` §7 の三層防御を参照）。
 */
