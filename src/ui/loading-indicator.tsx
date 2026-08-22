/**
 * 処理中であることを伝える表示専用コンポーネント（`AC-8` / `US-22` / `US-26`）。
 *
 * 🔴 `role="status"` / `aria-live` は自身で持たない（#180・`ui-ux-guidelines.md` §7.2）。
 * このコンポーネントは常に `app/[locale]/page.tsx` の `<section id="search-status"
 * role="status" aria-live="polite">` の内側にだけ `<Suspense>` の fallback として現れる。
 * 以前は自身にも `role="status"` を持っていたため、外側の `section` と入れ子になり、
 * 支援技術に対して未定義動作（二重読み上げ／無視のいずれも起こりうる）を生んでいた。
 * ライブリージョンは画面に唯一（外側の `section`）とし、本コンポーネントは
 * その中身を差し替える **テキスト + 装飾イラスト** の表示だけを担う。
 *
 * 🔴 **装飾イラストがライブリージョンの「内側」にある唯一の例外である**
 * （`ui-ux-guidelines.md` §7.4 の追記。0 件・404・待ち受けのイラストは
 * `role="status"` の **外**（兄弟要素）に置く規約になっている）。本コンポーネントは
 * `<Suspense>` の fallback として構造上必ずライブリージョンの内側に現れるため、
 * 兄弟へ出すと「読み込み中 → N 件中 M 件を表示」の遷移が通知されなくなる。
 * **この例外が成立する条件は `alt=""` 単独であること 1 点のみ**——空 alt の `<img>` は
 * アクセシビリティツリーから除外されるため、ライブリージョンの再構成対象に実質含まれない。
 * 🔴 **この画像に有意味な `alt` を与えない**（与えた瞬間、再検索のたびに代替テキストまで
 * 読み上げ直され §7.2 の不変条件が破れる）。画像自体もアニメーションさせない
 * 🔴 **文言にも `animate-pulse` を付けない**（Issue #364 の E2E で実測）。opacity を落とす
 * アニメーションは脈動の谷で実効コントラストを下げ、`--color-fg-muted` の文言が
 * **4.35:1**（AA の 4.5:1 未満）まで落ちて axe の `color-contrast`（serious・wcag143）に
 * 掛かる。テキストのコントラストは**アニメーションの全位相で**満たす必要があるため、
 * 進行中であることは静止したイラストだけで伝える（`ui-ux-guidelines.md` §2.2 / `NFR-13`）。
 *
 * 文言は視覚的にも表示し（`sr-only` にしない）、0 件・エラーと同じ領域で
 * 見た目が区別できるようにする。
 *
 * ⚠️ `ui-ux-guidelines.md` §4.4 が読み込み中に定める 🔵 推奨（実データと同一寸法の
 * カード形状スケルトン・0〜300ms は何も出さない）は **まだ満たしていない**。本実装はテキスト
 * + イラストであり、§4.4 は現状を支持する根拠ではない（🔵 は必須ではないため本スプリントの
 * 範囲外）。Issue #347 のユーザーフィードバックを受け、スケルトンではなくイラスト表示を
 * 明示的に採用した（Issue #359）。スケルトン化は引き続き別 Issue（#169）で検討する。
 */
export function LoadingIndicator({ label }: { label: string }) {
  return (
    <div className="py-8 text-center">
      {/* eslint-disable-next-line @next/next/no-img-element -- INF-11: next/image の最適化は使わない */}
      <img
        src="/images/loading.webp"
        alt=""
        width={256}
        height={256}
        loading="eager"
        decoding="async"
        className="mx-auto mb-2 h-16 w-16"
      />
      <p className="text-muted-foreground text-sm">
        {label}
      </p>
    </div>
  )
}
