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
}
