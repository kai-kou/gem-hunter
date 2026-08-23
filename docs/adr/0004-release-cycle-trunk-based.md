# ADR 0004: リリースサイクルを trunk-based（PR プレビュー + `main` = 本番）に確定し、常設の dev 環境を持たない

- **状態**: **承認**（`M-4` 公開判断ゲートで、`[env.dev]` と gradual deployment の追加要否を再判定する）
- **日付**: 2026-08-18 JST
- **対応要件**: `D-21` / `D-26` / `D-16` / `INF-4` / `INF-20` / `INF-21` / `SD-1` / `CP-6` / `minimum-requirements.md` §4 / §6
- **関連**: [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §6 / [議論記録](../../content/discussions/release-cycle-20260818/whiteboard.md) / Issue #38 / #39 / #40

---

## 1. 文脈

2026-08-18、ユーザーから相談があった。

> 最低限の要件の中にプロダクションを意識するという事項があったかと思いますが、それを踏まえて、リリースサイクルとして dev リポジトリはプレビュー環境へのデプロイ、main は本番環境へのデプロイと環境を分けるべきか悩んでいます。

これは **実装指示ではなく「与件から dev 分離という結論が導けるか」の検証依頼** である（`user-instruction-issue-rules.md` の「質問か指示か」の分類）。相談の背後にあるのは「プロダクション運用を意識していないと見られること」への懸念であり、本 ADR はその懸念に対する設計上の回答でもある。

既存の構成は [`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §6.1 が定める 3 環境（local / preview / production）で、preview は **PR ごとの version + preview alias**（`pr-<N>`）、production は `main` マージによる `wrangler deploy` である。dev ブランチは存在しない。

専門チーム（5 レンズ・2 ラウンドの敵対的相互検証）で争点 A〜E を検証した結果を以下に記録する。

---

## 2. 決定

**リリースサイクルは trunk-based を維持する。** 作業ブランチ → PR（プレビュー）→ `main`（本番）の 1 ホップ構成とし、**常設の dev ブランチ / dev 環境を追加しない**。

あわせて次を決める。

1. 本番直結のリスクは、**`main` マージ後のテストゲート**（テスト失敗時は `wrangler deploy` に進ませない）で塞ぐ（Issue #39）
2. 判断の根拠は **README「設計上の判断」** に記載する（`minimum-requirements.md` §6 が README への設計判断記載を与件として要求しているため、ADR より確実に読まれる導線になる）
3. **`M-4`（第三者へ公開するかの判断ゲート）** で、OAuth 検証用 `[env.dev]` と gradual deployment の追加要否を再判定する（Issue #40）

---

## 3. 理由

### 3.1. 与件は環境分離を要求していない（が、禁止もしていない）

`minimum-requirements.md` §4「プロダクション運用を想定した実装とする」は、直後の §4.1〜§4.4 で **アプリ実装品質**（エラー処理・秘匿情報の非露出・性能・a11y・型安全・Lint）を列挙しており、環境構成・ブランチ戦略には触れていない。§7 の受け入れ基準チェックリスト 11 項目にも環境分離は含まれない。

🔴 ただし **「与件に書いていないから禁止」ではない**（与件は下限であって上限ではない）。正しい位置づけは「**与件充足の判定範囲外にある、費用対効果で決める任意の上乗せ**」であり、以下 3.2〜3.4 がその費用対効果の評価である。

### 3.2. この運用体制では dev に発生させられる価値がない

本プロジェクトは単一開発者 + AI の自律ルーティン（`sprint-cycle-router`）が 1 時間ごとに自走し、実装 → PR → セルフレビュー → 自動マージまで人間の介入なしで進む。

- **dev を確認する人間がいない**。dev は「PR 時点で通過済みの CI と同じ検証をもう一度走らせるだけの環境」になる
- **dev には実トラフィックが通らない**。実トラフィック下でしか出ない不具合は、PR プレビューと同じく検出できない
- 自動昇格（`main` へ自動で上げる）を実装しても、**(a) 一定時間待つだけの機械的タイマー**（安全性の上積みゼロ・リードタイムだけ増加）か、**(b) dev 滞在中に新しい検証を行う仕組み**（それは dev という「場所」ではなく検証の仕組みが価値の源泉であり、プレビューや本番でも実装できる）のどちらかにしかならない

### 3.3. 「合成状態の検証層が無い」問題は dev では閉じない

議論の中で、現行設計の実在する穴が見つかった。`deploy-production.yml` は `push`（`main`）で即 `wrangler deploy` するため、**複数 PR を積み上げた合成状態を最初に浴びるのは本番トラフィックそのもの** である（個々の PR はプレビューで検証されるが、組み合わせは検証されない）。

ただしこの穴は dev を挟んでも閉じない。**「誰が・いつ dev → `main` を昇格させるか」が未定義である限り、同じ問いが 1 段上に移動して滞留リスクへ転化するだけ** である（`sprint-cycle-router` の分岐にも昇格ステップは存在しない）。低コストで確実に閉じる手段は、**`main` マージ後に test suite を走らせ、成功しなければ本番デプロイに進ませない CI ゲート**（新しいブランチも昇格の主体も不要）。

### 3.4. 実装するなら `[env.dev]` 一択で、コストが確定する

`versions` + 固定 preview alias（例 `--preview-alias dev`）で安く済ませる案は、Cloudflare の実仕様で否定された。シークレットは alias 単位ではなく **Worker 1 本の版チェーン全体で線形に継承される**（`--secrets-file` は「ファイルに含まれないシークレットは前の版から引き継ぐ」）。したがって dev 専用シークレット（OAuth Client Secret 等）の分離を **構造的に保証できない**。

真の分離には `[env.dev]`（別 Worker）が必要で、これは Worker 数を恒久的に +1 する（`INF-2` の Free 枠維持と `INF-4` の定常運用ゼロに対するコスト）。

---

## 4. 結果（この決定がもたらすもの）

### 良い方向

- 変更のリードタイムが最短のまま保たれる（作業ブランチ → PR → `main` の 1 ホップ）
- 自律ルーティンに新しい判断点（昇格の主体・タイミング）を持ち込まずに済む（`CP-6` / `INF-4` を維持）
- Worker 数・シークレット管理の複雑化を回避できる（`INF-2`）
- 「なぜ dev を持たないか」を言語化して残すことで、`project-mission.md` の優先順位 3 位「説明可能性」に直接寄与する

### 受け入れる代償

| 代償 | 緩和策 |
|---|---|
| `main` 上の合成状態が本番で初めて動く | `main` マージ後のテストゲート（Issue #39・`SP-4` のテスト CI 完成が前提）。**2026-08-20 追記**: スプリント PR に限り、テストゲートの上にスプリントレビューゲートを重ねる（下記「スプリントレビューゲートの追加」）。**2026-08-23 追記**: GitHub Actions が起動できない（`D-23`）ため、このテストゲートは CI ではなく **セッションが `main` HEAD で `npm run check` を再実行する形** で運用している（[Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §8.2 が手順の正本）。🔴 **本 ADR 本文（§3.2 / §3.3）の「CI」もすべてこの読み替えを適用する**。Actions が復帰したら CI へ戻す |
| OAuth 経路を本番でしか検証できない（プレビューは PR ごとに URL が変わりコールバック URL を登録できない） | OAuth 自体が未実装のため現時点では顕在化しない。`M-4` で `[env.dev]` の要否を判定する |
| 段階的な本番投入（カナリア）ができない | `INF-21`（ロールバック）で戻す。段階的展開の導入可否は Issue #40 で別途決定する |
| ブランチ構成だけを見た第三者に「環境分離をしていない」と映る可能性 | README「設計上の判断」に理由を明記する（与件 §6 が要求する導線） |
| **（2026-08-20 追記）** rejected 判定が続く間、その rejected スプリントと無関係な非スプリント PR のデプロイも足止めされる | `main` が 1 本の Worker である以上、部分的デプロイができないため不可避。「反映が遅れる」に留まり「壊れたコードが本番に出る」より軽いため trunk-based の 1 ホップ原則は維持できると判断する |

---

### スプリントレビューゲートの追加（2026-08-20 改訂・`D-26`）

🔴 **`main` マージ後のテストゲート（§3.3・Issue #39）は、スプリント PR に限り「スプリントレビュー accepted ゲート」で拡張する。置き換えではない。**

- **対象はスプリント PR（`Sprint Goal:` 行のある PR）のみ**。テストゲート（`npm run check` が `main` HEAD で通ること）は全 PR に引き続き必須の前提として残る。スプリントレビューゲートは、その上に **人格化された受け入れ判定**（accepted / accepted_with_conditions / rejected）を追加で通す。
- **本番デプロイの発火点**: スプリント PR は Sprint Review 判定が `accepted`（または `accepted_with_conditions` かつ `deploy: yes`）になるまでデプロイしない。`rejected` の間はデプロイしない（fail-closed）。
- **非スプリント PR**（改善 Issue・retro-try・docs 等）: 従来どおりマージ直後にデプロイするが、main 上に判定未確定または rejected のスプリント Issue が残っている間はデプロイを待機する（デプロイの直列化）。マージ・push 自体は妨げない — 止めるのは `npm run deploy` の呼び出しだけ。
- **trunk-based の 1 ホップ構成は維持する**: main の巻き戻し・rejected コミットの revert は導入しない。rejected 後に必要な修正は次の PR として重ねてマージし、その Sprint Review で改めて accepted となった時点でゲートは自然に解除される。
- 実装の詳細・コマンドは [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §8.2 が正本（本 ADR は理由と適用範囲のみを持つ）。決定ログは [`open-questions.md`](../02_requirements/open-questions.md) `D-26`。根拠は [議論記録](../../content/discussions/sprint-env-lifecycle-20260820/whiteboard.md)。

---

## 5. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **dev ブランチ = 常設プレビュー環境 / `main` = 本番の 2 段構成** | 確認者も実トラフィックも無い体制では CI 以上の検証を追加せず、リードタイムと未定義の判断点だけが増える（§3.2） |
| **`versions` + 固定 preview alias `dev` で安く dev 環境を作る** | シークレットが Worker 1 本の版チェーン全体で線形継承されるため、dev 専用シークレットの分離を構造的に保証できない（§3.4） |
| **`[env.dev]`（別 Worker）を今すぐ導入する** | 塞ぐべき穴（OAuth 経路の事前検証）がまだ存在しない（OAuth 未実装・公開判断も未通過）。Worker 恒久 +1 のコストが先行する |
| **feat → dev → `main` の 2 段マージを自動昇格で回す** | 技術的には成立し `CP-6` 違反も避けられるが、待機時間が増えるだけで検証内容が増えない（§3.2 の (a)） |
| **「与件に書いていないから dev は不要」で結論づける** | 与件は下限であって上限ではない。不記載を禁止と読むのは過剰解釈（§3.1） |
| **gradual deployment があるから dev は不要、と言い切る** | `INF-21` は「戻す手段」であって段階的展開ではなく、`wrangler versions deploy --percentage` は現行設計に存在しない。導入には新規決定が要る（Issue #40） |

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`open-questions.md`](../02_requirements/open-questions.md) `D-21` / `D-26` | 決定ログ（本 ADR が理由と却下案の正本） |
| [`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §6 / §8 | 環境構成・CI/CD の実装の正本（§8.2 がスプリントレビューゲート・退役手順の実体） |
| [`roadmap.md`](../02_requirements/roadmap.md) `M-4` | 再判定のタイミング（OAuth 検証用 `[env.dev]` / gradual deployment の要否） |
| [議論記録](../../content/discussions/release-cycle-20260818/whiteboard.md) | 5 レンズ・2 ラウンドの敵対的相互検証の全文（trunk-based 決定の原議論） |
| [議論記録（2026-08-20）](../../content/discussions/sprint-env-lifecycle-20260820/whiteboard.md) | スプリントレビューゲート追記の専門チーム議論 |
