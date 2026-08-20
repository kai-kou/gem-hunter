# リポジトリのパブリック化 可否レビューと対応チェックリスト

> **対象**: `kai-kou/gem-hunter`（2026-08-20 時点で `private`）
> **射程**: 🔴 **GitHub リポジトリのソース公開** に限る。`M-4`（第三者へ **サービス** を公開するかの判断ゲート・[`roadmap.md`](../02_requirements/roadmap.md) §3）とは別の判断である。両者の相互作用は §5 で扱う。
> **調査日**: 2026-08-20 JST / **調査対象**: 追跡ファイル 589 件・全 50 コミット・リモートブランチ 46 本・Issue 110 件（open）

---

## 0. 結論

**技術的なブロッカーは無い。秘密情報の混入はゼロ件だった。** ただし公開前に決着させるべき事項が 4 件あり、うち **1 件はユーザーにしか判断できない**（§2 の `B-1`）。

| 判定 | 内容 |
|---|---|
| ✅ **秘密情報** | 作業ツリー・git 履歴とも **検出ゼロ**。鍵らしき文字列はすべてテスト用ダミーで、コード内にその旨が明記されている |
| ✅ **個人情報** | コミット作者は GitHub の `noreply` アドレスのみ。個人メールアドレスの露出なし |
| ✅ **第三者コード** | 同梱の Apache-2.0 スキルは `LICENSE.txt` を保持しており再配布可能 |
| 🔴 **要判断** | **与件（選考課題の原本）を公開してよいか**（`B-1`。提供元との関係でしか決まらない） |
| 🟡 **要対応** | LICENSE 不在（`B-2`）/ コストテレメトリブランチの公開（`B-3`）/ 秘密管理ルールの根拠記述の誤り（`B-4`） |

---

## 1. 実施したスキャンと結果（証跡）

### 1.1 秘密情報スキャン

| 対象 | 手法 | 結果 |
|---|---|---|
| 追跡ファイル 589 件 | `gh[pousr]_` / `sk-ant-` / `xox[baprs]-` / `AKIA` / `AIza` / `ya29.` / `BEGIN * PRIVATE KEY` / `hooks.slack.com/services/` の正規表現走査 | **実値の検出ゼロ**（ヒット 3 件はいずれもドキュメント内のプレースホルダ、またはマスク処理ツールの docstring） |
| git 履歴 全 50 コミット | 同上を全リビジョンへ適用 | **検出ゼロ** |
| 履歴上の削除済みファイル | 追加された全パスと現追跡ファイルの差分 | 5 件（`.github/workflows/deploy-*.yml` 2 本・`app/layout.tsx` 等）。**削除済みワークフローは `${{ secrets.* }}` 参照のみで実値なし** |
| `.env` 系 | 全履歴のパス走査 | **一度もコミットされていない**（`.gitignore` が `.env` / `.env.*` / `*.pem` / `*.key` を網羅） |
| 高エントロピー値 | 32 桁 hex（Cloudflare アカウント ID 相当）の走査 | **検出ゼロ** |

**検出された「鍵らしき文字列」はすべてテスト専用のダミー** である。

- `e2e/stub/e2e-env.mjs`: `GITHUB_OAUTH_CLIENT_SECRET: 'e2e-dummy-client-secret'` / `SESSION_ENCRYPTION_KEY: 'Z2VtLWh1bnRlci1lMmUtZHVtbXktc2Vzc2lvbi0zMmI'`（base64url の 32 バイト固定値）
- `playwright.config.ts` / `src/infrastructure/platform/session-cookie.test.ts`: 同種の固定ダミー。`.gitguardian.yaml` が **この 2 ファイルのみ** をパス指定で除外しており、除外範囲が最小に保たれている

> 🔵 公開後は GitHub の **Secret scanning**（公開リポジトリでは無料）が同じ 2 ファイルを再検出しうる。`.gitguardian.yaml` は ggshield 用であって GitHub 側には効かないため、GitHub 側でも dismiss するか、ダミー値を `process.env` 経由に寄せるかを §6 で決める。

### 1.2 個人情報・帰属

| 項目 | 実測 |
|---|---|
| コミット作者 | `kai kou <41495183+kai-kou@users.noreply.github.com>` 46 件 / `claude[bot] <209825114+claude[bot]@users.noreply.github.com>` 4 件 |
| コミッター | すべて `GitHub <noreply@github.com>`（Web 経由コミット） |
| 生メールアドレス | **なし**（検出された `i@izs.me` は npm 依存のライセンス表記由来） |
| 提供元・評価者の実名 | **リポジトリ全体で一度も登場しない**（`inception-deck.md` は「課題の提出先（評価者）」という役割名でのみ言及） |

### 1.3 第三者著作物

| 対象 | ライセンス | 判定 |
|---|---|---|
| `.claude/skills/skill-creator/` | Apache License 2.0（`LICENSE.txt` 同梱） | ✅ 再配布可。**リポジトリ自体のライセンスを定める際、このディレクトリを対象外として明記する**（`B-2` と連動） |
| `.claude/` ハーネス一式・`docs/rules/` | `kai-kou/claude-code-repository-base`（自身の公開ベース）由来 | ✅ 自作物 |
| npm 依存 | すべて公開レジストリからの取得。ベンダリングなし（`node_modules` は `.gitignore` 済み） | ✅ 問題なし |
| `docs/02_requirements/minimum-requirements.md` | **外部提供の与件**。`inception-deck.md` が「与件の原本（編集しない）」と明記 | 🔴 **`B-1` として §2 で扱う** |
| `public/vercel.svg` ほか 4 件 | Next.js のスキャフォールド既定物。**アプリから未参照** | 🟡 Vercel のロゴを、Vercel を使っていないリポジトリで再配布する状態。削除が無難（§3 `M-4'`） |

---

## 2. 公開前に決着させる項目（ブロッカー）

### 🔴 B-1: 与件（選考課題の原本）を公開してよいか — **ユーザー判断が必要**

`docs/02_requirements/minimum-requirements.md` は **外部から提供された選考課題の要件定義そのもの** であり、`inception-deck.md` が「与件は変更不可の外部制約」「与件の原本（編集しない）」と位置づけている。リポジトリを公開すると、この文書が **第三者の著作物として全世界へ再配布される**。

これは技術的な問題ではなく、**課題の提供元との関係でしか決まらない**（本リポジトリのどこにも公開可否の合意記録がない）。

| 選択肢 | 何が変わるか |
|---|---|
| **A（推奨）: 与件を要約に差し替えてから公開する** | 原本を削除し、「何が求められていたか」を自分の言葉で書いた要約（受け入れ基準 11 項目の再構成）に置き換える。**設計判断の説明可能性は落ちない**（要件 ID `FR-n` / `AC-n` の参照網は保てる）。履歴からの完全削除が必要なら `git filter-repo` + 強制 push が要る |
| B: 提供元へ確認し、許諾が取れたら原本ごと公開する | 最も誠実だが、返答待ちで公開が止まる。許諾が取れれば手戻りゼロ |

> ⚠️ **原本をファイルから消しても履歴には残る**（`1801e82 docs: MVPの最低要件定義を追加 (#4)` で追加済み）。公開前に消しきるなら履歴の書き換えが必要で、履歴を書き換えると **Issue / PR に紐づくコミット SHA がすべて orphan になる**。「AI 自律開発の履歴を丸ごと見せる」という本リポジトリ最大の価値と真っ向から衝突するため、**選択肢 B が取れるならその方が損失は小さい**。

### 🟡 B-2: LICENSE ファイルが存在しない

現状はライセンス表記なし＝**全権利留保**。公開しても他者は法的にフォーク・改変・再利用ができず、「OSS として公開した」形にならない。かつ `package.json` が `"private": true` のままである。

- **ライセンス表記のない公開リポジトリは、閲覧はできても利用できない**。ポートフォリオとして「読んでもらう」だけならこれでも成立するが、意図的な選択として明記すべき
- `.claude/skills/skill-creator/`（Apache-2.0）は自リポジトリのライセンスの対象外である旨を LICENSE か README に併記する
- `B-1` の結論と連動する（与件を残したままリポジトリ全体に MIT を付けると、**他人の著作物を自分の名義で再ライセンスしたことになる**）

### 🟡 B-3: `telemetry/cost-data` ブランチが AI 実費を公開する

`.gitignore` で `main` からは除外されているため作業ツリーには現れないが、**リモートには実在する独立ブランチ** であり、公開すると誰でも読める。

```
telemetry/cost-data:content/analytics/cost_monthly/2026-08.json
  → sessions: 48 / cost_usd: 403.12 / cost_jpy_approx: 60,468（2026-08-17〜20 の 4 日間）
  → セッション単位の UUID・日次内訳つき
```

秘密情報ではない（認証情報ではなく、UUID はセッション識別子であって資格情報ではない）が、**個人の AI 開発費という私的な支出情報** である。

| 選択肢 | 何が変わるか |
|---|---|
| **A（推奨）: 公開前にブランチを削除し、テレメトリの push 先をローカルまたは別プライベートリポジトリへ切り替える** | 支出が公開されない。`tools/commit_cost_telemetry.py` の push 先変更が必要 |
| B: そのまま公開する | 「AI 自律開発は 4 日で 6 万円かかる」という **他に類例の少ない実測データの公開** になる。ポートフォリオとしての訴求力はむしろ上がる |

> 🔵 これは好みの問題であり、どちらでも技術的な害はない。**ただし「気づかないまま公開される」ことだけは避ける** 必要がある（`.gitignore` されているため通常のレビューでは絶対に目に入らない）。

### 🟡 B-4: 秘密管理ルールの「安全である根拠」の記述が誤っている

`docs/rules/env-vars.md` が GitHub Secrets ではなく Variables を選んだ根拠として、こう書いている。

> **セキュリティの現実的判断**: Variables はプレーンテキスト保存だが、**プライベートリポジトリのため** アクセスはリポジトリ権限保有者のみ。

**この根拠は誤りで、公開しても実際の安全性は変わらない**（一次情報で確認済み）。

- リポジトリ Variables の読み取りは **リポジトリの公開/非公開にかかわらず collaborator 権限が必須**。匿名ユーザーは公開リポジトリでも読めない（[REST API endpoints for GitHub Actions variables](https://docs.github.com/en/rest/actions/variables)）
- **fork からの pull request で起動したワークフローには、secrets と同様に変数も渡らない**（[community discussion #44322](https://github.com/orgs/community/discussions/44322)）。つまり「fork PR にワークフローを仕込んで `vars` を echo させる」という攻撃経路は成立しない

したがって **公開の障害にはならない**。ただし「private だから安全」という記述を残すと、**公開後に読んだ人（将来の自分を含む）が誤った安全性の前提を引き継ぐ** ため、根拠を「collaborator 権限で保護されている」へ訂正する。

---

## 3. 公開すると何が起きるか（一次情報で確認済み）

[Setting repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility) より。

| 項目 | 公開後 |
|---|---|
| コード | 誰でも閲覧・**フォーク可能** になる |
| **Issue / PR** | **全件が公開される**（open 110 件 + クローズ済み全件 + PR 全件 + レビューコメント全件） |
| **Actions の履歴とログ** | **公開される** |
| ブランチ | **リモート 46 本すべて公開**（うち 43 本が `claude/*` の作業ブランチで、42 本はマージ済み） |
| push ruleset | **無効化される** |
| stars / watchers | 消去される（現在 0 のため実害なし） |
| Wiki / Projects | `has_wiki: true` / `has_projects: true`。中身の有無を要確認 |

### 🟢 公開によって **得られる** もの（Free プランでは公開リポジトリ限定の機能）

現在このリポジトリは **ブランチ保護がゼロ**（`main` を含め全ブランチが `protected: false`）である。GitHub Free ではプライベートリポジトリにブランチ保護もルールセットも適用できないためで、これは `A-1`（`main` への直接 push 禁止）が **フックによる自主規制だけで支えられている** ことを意味する。

**公開すると Free プランのままブランチ保護／ルールセットが使えるようになる**（[About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)）。`A-1` を GitHub 側で機械強制できるようになるのは、公開の純粋なメリットである。

あわせて Secret scanning・Dependabot alerts・Code scanning（CodeQL）が公開リポジトリで無料になり、`docs/rules/security-posture-controls.md` が挙げる補償統制に **プラットフォーム側の層が 1 つ増える**。

---

## 4. 中リスク項目（公開の可否は左右しないが、事前に決める）

| ID | 項目 | 内容と対応 |
|---|---|---|
| **M-1'** | **Cloudflare アカウントのサブドメインとプレビュー URL が露出する** | `content/discussions/` 配下に `sp1-gem-hunter.kinamocchi-tech.workers.dev` / `pr-183-gem-hunter.kinamocchi-tech.workers.dev` が実 URL のまま記録されている。**公開後は誰でも叩ける**（workers.dev は元々認証なしの公開 URL のため新たな露出ではないが、「発見可能になる」ことが実質的な変化）。踏まれれば共有の GitHub API レート枠（認証済み 30 req/分）を消費する（`RK-3`） |
| **M-2'** | **Issue #187 が open のまま** | 「プレビュー version に secret が渡っておらず、認証とレート制限がプレビューで動作しない」。**レート制限が効かないプレビュー環境の URL が公開される** 状態なので、`M-1'` と合わせて先に潰すか、旧プレビュー version を破棄する |
| **M-3'** | **`content/discussions/` の内部議論が全文公開される** | 飼い主の指示の逐語引用、プロセス逸脱の記録（役割外のサブエージェントが直接コミットした件、GitGuardian に検出された WIP 混入事故など）を含む。**秘密情報ではなく、むしろ「AI 自律開発の実像」を示す資産** だが、都合の悪い部分も含めて公開されることを認識した上で出す |
| **M-4'** | **未使用のスキャフォールド資産** | `public/vercel.svg` `next.svg` `file.svg` `globe.svg` `window.svg` はアプリから未参照。Vercel を使っていないリポジトリで Vercel ロゴを再配布する形になるため削除が無難 |
| **M-5'** | **停止済みブランチ 42 本** | マージ済みの `claude/*` ブランチが残存。公開しても害はないが、リポジトリの第一印象を損なう。`project-sync` の Abandoned ブランチ検出で一掃できる |
| **M-6'** | **`package.json` の `"private": true`** | npm 公開を防ぐフラグであり GitHub の公開可否とは無関係。ただし公開リポジトリで残っていると意図が読みにくいので、`license` フィールドとあわせて整理する |

---

## 5. `M-4`（サービス公開判断ゲート）との関係

**リポジトリの公開は `M-4` の通過を要求しない。** `M-4` は「第三者にこのサービスを使わせるか」の判断であり、ソースの公開はそれに該当しない。

ただし **一方向の影響がある**: リポジトリを公開すると `README` とドキュメントからデプロイ済み URL が辿れるため、**事実上「第三者が使える状態」に近づく**。したがって以下のどちらかを取る。

- **(a) URL を伏せて公開する**: 実 URL を含む記述（`M-1'`）を伏字化し、ローカル起動手順だけを案内する。`M-4` は未通過のままでよい
- **(b) URL ごと公開する**: `M-4` の通過判定（`R-8` GitHub 利用規約の一次確認 / `R-5` に基づくキャッシュ TTL の確定 / `R-6` 運用コスト試算）を先に済ませる

> 🔵 選考課題としての提出が主目的（`D-3`）である以上、**(a) で十分** である。評価者はローカルで動かすか、提出時に個別に共有された URL を見る。

---

## 6. 公開手順チェックリスト

### Phase 0: 判断（ユーザー）

- [ ] **`B-1`**: 与件を原本のまま公開してよいか決める（提供元へ確認 / 要約へ差し替え）
- [ ] **`B-2`**: ライセンスを決める（MIT / Apache-2.0 / ライセンスなしを明示 のいずれか）
- [ ] **`B-3`**: コストテレメトリを公開するか決める
- [ ] **§5**: プレビュー URL を伏せるか（(a)）、`M-4` を先に通すか（(b)）決める

### Phase 1: 公開前の整備（Claude が実行できる）

- [ ] `B-1` の結論を反映（要約への差し替え、必要なら履歴の扱いを決定）
- [ ] `LICENSE` を追加し、`.claude/skills/skill-creator/`（Apache-2.0）の除外を明記
- [ ] `docs/rules/env-vars.md` の「private だから安全」を「collaborator 権限で保護されている」へ訂正（`B-4`）
- [ ] `M-1'`: 実プレビュー URL を伏字化（`content/discussions/` は履歴記録なので、伏字化するか「当時の URL」と注記するかを選ぶ）
- [ ] `M-2'`: Issue #187 を解消するか、露出しているプレビュー version を破棄する
- [ ] `M-4'`: 未使用のスキャフォールド資産を削除
- [ ] `M-5'`: マージ済み `claude/*` ブランチ 42 本を削除
- [ ] `M-6'`: `package.json` の `private` / `license` を整理
- [ ] **Issue / PR 全件の最終スキャン**（本文・コメントに秘密情報や伏せたい記述がないか）。**リポジトリのファイルスキャンとは別に必要**
- [ ] Wiki / Projects の中身を確認（空でなければ内容を確認）

### Phase 2: 公開（ユーザーのみ実行可能 — `A-6` 相当）

- [ ] Settings → Danger Zone → Change visibility → Public（リポジトリ名の入力と影響への同意チェックが必要）

### Phase 3: 公開直後（Claude が実行できる）

- [ ] **`main` にブランチ保護／ルールセットを設定**（公開して初めて Free プランで使える。`A-1` の機械強制。直接 push の禁止 + PR 経由の強制）
- [ ] Secret scanning / Dependabot alerts / Code scanning を有効化し、初回検出をトリアージ（`.gitguardian.yaml` で除外済みのダミー 2 件は GitHub 側でも dismiss する）
- [ ] Actions の fork PR 実行ポリシーを「**Require approval for all outside collaborators**」以上に設定
- [ ] リポジトリの description / topics を設定（公開リポジトリの第一印象）

---

## 7. ユーザーにしかできない対応（`A-6` 相当）

| # | 対応 | なぜユーザーだけか |
|---|---|---|
| 1 | **与件の公開可否の決定**（`B-1`） | 提供元との関係・提出時の取り決めを知っているのはユーザーだけ |
| 2 | **リポジトリの visibility 変更** | リポジトリ管理者権限が物理的に必要（API 経路でも Claude 側に手段がない）。かつ **取り消しが困難な外部公開**（`A-2`） |
| 3 | **ライセンスの決定**（`B-2`） | 著作権者の意思表示であり、代理で決められない |
| 4 | **コストテレメトリの公開可否**（`B-3`） | 私的な支出情報 |
| 5 | Actions / Secret scanning などリポジトリ設定の一部 | 設定 UI 側の操作が要る項目がある（API で届く分は Claude が実行する） |

---

## 8. 公開後の運用で変わること

- **Issue / PR が公開の場になる**: 以後に書く内容（エラーログの貼り付け・環境変数名・URL）は「そのまま公開される」前提で書く。ハーネスの自動投稿（Sprint Planning コメント・セルフレビュー結果）も同様
- **fork PR が届きうる**: `pull_request` イベントのワークフローには secrets も vars も渡らないが、**fork の head にあるワークフロー定義が実行される** ため、Actions の承認設定（Phase 3）を先に入れる
- **セッションの作業ブランチが公開される**: `claude/*` ブランチの push はリアルタイムで公開に反映される。WIP 自動コミット（Stop フック）が意図しない内容を push しうる点は、非公開時より影響が大きい
- **`main` 保護が入るとハーネスの前提が変わる**: `pre-git-push-check.sh` による自主規制に GitHub 側の強制が重なる。自動マージ（squash）が保護ルールと衝突しないか、設定時に 1 度だけ実マージで確認する

---

## 9. 参照

| 種別 | 出典 |
|---|---|
| リポジトリ可視性の変更 | [Setting repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility) |
| Actions 変数の読み取り権限 | [REST API endpoints for GitHub Actions variables](https://docs.github.com/en/rest/actions/variables) |
| fork PR への変数の非伝播 | [community discussion #44322](https://github.com/orgs/community/discussions/44322) |
| ルールセットの提供範囲 | [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) |
| プロジェクト内の関連判断 | [`roadmap.md`](../02_requirements/roadmap.md) `M-4` / [`inception-deck.md`](../00_concept/inception-deck.md) `RK-10` / [`open-questions.md`](../02_requirements/open-questions.md) `R-8` |
