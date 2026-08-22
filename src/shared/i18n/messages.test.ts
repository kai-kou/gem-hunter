import { describe, expect, it } from 'vitest'

import { getMessages } from './messages'

/**
 * カタログ本文（`messages/*.json`）の要件を **実カタログに対して** 固定する。
 *
 * 🔴 コンポーネントのユニットテストはテストファイル内に手書きした labels を検証しており、
 * 実カタログを 1 文字も見ていない。E2E も描画元と同じ定数を突き合わせるトートロジーなので、
 * 「文言を短縮したら要件が静かに失われる」経路が閉じていなかった（PR #440 Layer 1 指摘）。
 * ここで固定するのは **意思決定（`D-36` / `D-37`）が要求している要素** に限る
 * （語尾・言い回しの改稿でむやみに落ちないようにする）。
 */
describe('messages カタログ', () => {
  const ja = getMessages('ja')
  const en = getMessages('en')

  describe('gems.empty（`D-36`: 母集団を明示し、載らないことが低評価ではないと伝える）', () => {
    it('ja は候補プールの母集団（12 のパッケージレジストリ）を明示する', () => {
      expect(ja.gems.empty).toContain('12 のパッケージレジストリ')
    })

    it('ja は「載らない = 評価が低い」ではないと明示する', () => {
      expect(ja.gems.empty).toContain('評価が低いことを意味しません')
    })

    it('en も同じ母集団を明示する', () => {
      expect(en.gems.empty).toContain('12 package registries')
    })
  })

  describe('gems.unmatchableQuery（`D-37`: 照合規則と次に取れる行動を伝える）', () => {
    it('ja は照合規則（単語境界一致）を説明する', () => {
      expect(ja.gems.unmatchableQuery).toContain('単語境界')
    })

    it('en も照合規則（whole-word）を説明する', () => {
      expect(en.gems.unmatchableQuery).toContain('whole-word')
    })
  })

  /**
   * `domain-model.md` §2.1 が「UI 表示ラベルは `dependentCount` = 「利用パッケージ数」/ "Used by"」
   * と表示語まで正本として固定している。日次ダイジェストと Gem 一覧で別語にしない。
   */
  describe('dependentCount の表示ラベル（`domain-model.md` §2.1 が正本）', () => {
    it('ja は日次ダイジェストと Gem 一覧で同じ「利用パッケージ数」を使う', () => {
      expect(ja.home.digest.dependentLabel).toBe('利用パッケージ数')
      expect(ja.gems.dependentCount).toBe('利用パッケージ数')
    })

    it('en は日次ダイジェストと Gem 一覧で同じ "Used by" を使う', () => {
      expect(en.home.digest.dependentLabel).toBe('Used by')
      expect(en.gems.dependentCount).toBe('Used by')
    })

    it('「被依存」表記が Gem 一覧の文言に残っていない（ja）', () => {
      expect(ja.gems.dependentCount).not.toContain('被依存')
      expect(ja.gems.attribution).not.toContain('被依存')
    })
  })

  /** 帰属表示（`D-29`）は `{source}` / `{license}` を必ず持つ（リンク差し込み位置）。 */
  describe('帰属表示のプレースホルダ（`D-29`）', () => {
    it.each([
      ['ja', ja],
      ['en', en],
    ])('%s の gems.attribution は {source} と {license} を持つ', (_name, messages) => {
      expect(messages.gems.attribution).toContain('{source}')
      expect(messages.gems.attribution).toContain('{license}')
    })

    it.each([
      ['ja', ja],
      ['en', en],
    ])('%s の home.digest.attribution は {generatedAt} も持つ', (_name, messages) => {
      expect(messages.home.digest.attribution).toContain('{source}')
      expect(messages.home.digest.attribution).toContain('{license}')
      expect(messages.home.digest.attribution).toContain('{generatedAt}')
    })
  })

  /**
   * 🔴 候補プールの **取得失敗** は 0 件とは別の状態で、原因も別（自前の静的アセット
   * `public/data/gem-index/` が読めていない）。`common.errors.upstream`（「GitHub 側で問題が
   * 起きています」）を流用すると **存在しない原因** を利用者に伝えることになるため、
   * 専用の文言を持つ（PR #440 Layer 1 指摘 F-05）。型では守れないのでカタログ本文で固定する。
   */
  describe('gems.loadFailed（取得失敗の原因を GitHub にすり替えない）', () => {
    it('ja は障害元（Gem 候補プール）を名指しする', () => {
      expect(ja.gems.loadFailed).toContain('Gem 候補プール')
    })

    it('ja は原因を GitHub のせいにしない', () => {
      expect(ja.gems.loadFailed).not.toContain('GitHub')
    })

    it('en も障害元を名指しし、GitHub のせいにしない', () => {
      expect(en.gems.loadFailed).toContain('Gem candidate pool')
      expect(en.gems.loadFailed).not.toContain('GitHub')
    })

    it.each([
      ['ja', ja],
      ['en', en],
    ])('%s は再試行を促す（行き止まりにしない・`US-24`）', (_name, messages) => {
      expect(messages.gems.loadFailed.length).toBeGreaterThan(0)
      expect(messages.common.retry.length).toBeGreaterThan(0)
    })
  })
})
