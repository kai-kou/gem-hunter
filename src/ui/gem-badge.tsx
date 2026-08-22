/**
 * 検索結果カードに付く Gem バッジ（`SP-18` / `D-36`）。表示だけを持つ Server Component。
 * 文言は props 経由（`E-4`・既存の `src/ui/*.tsx` と同じ作法）。
 *
 * 🔴 **これは「並び順を変えない注釈」である**（`D-36`）。`sort=gem-index` は復活させない。
 * バッジの有無で一覧を並べ替える実装を足さないこと（回帰テストで固定済み）。
 *
 * a11y:
 * - 🔴 **色だけで意味を伝えない**（WCAG 1.4.1）。必ず可視のテキストラベル（`label`）を持つ。
 * - バッジの語（例「Gem」）だけでは意味が伝わらないため、`srHint` を `sr-only` で添える。
 *   `aria-hidden` は付けない（付けると支援技術から消えて意味が失われる）。
 * - 🔴 **`label` と `srHint` の区切りは文言側の括弧で作る**（`ui-ux-guidelines.md` §7.4a）。
 *   インライン要素の境界では読み上げ時に空白が挿入されず `Gemstar の数のわりに…` と連結される
 *   ため、`srHint` は括弧で始まる文言を渡す（コンポーネント側で記号を足さない＝ロケールごとの
 *   約物の違いをメッセージカタログに委ねる）。
 * - カードごとに読み上げられるため `srHint` は 1 文に収める。バッジが付かないことが低評価を
 *   意味しない旨の注記（`gemBadgeNote`）は一覧に 1 回だけ出す（`repository-list.tsx` の責務）。
 *
 * 配色: `--color-accent` / `--color-accent-fg`（`ui-ux-guidelines.md` §2.1 / §2.2 の
 * セマンティックトークン。実測 8.36:1（ライト）/ 8.26:1（ダーク）で `check_contrast.py` が
 * 継続検査する）。topics チップ（`bg-muted` / `text-muted-foreground`）と塗りで区別が付く。
 * 生の色はクラス名にもインラインスタイルにも書かない。
 */
export function GemBadge({ label, srHint }: { label: string; srHint: string }) {
  return (
    <span className="bg-accent text-accent-foreground inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium">
      <span>{label}</span>
      <span className="sr-only">{srHint}</span>
    </span>
  )
}
