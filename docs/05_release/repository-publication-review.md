# リポジトリのパブリック化 可否レビューと対応チェックリスト

> **対象**: `kai-kou/gem-hunter`
> **現況**: ✅ **2026-08-20 JST に公開済み**（`visibility: public` / ライセンス判定 `MIT` / `main` にルールセット `protect-main` 適用済み）。本書は **調査時点（公開前）の判断過程をそのまま残したうえで**、各節に完了状態を追記している。「なぜ公開してよいと判断したか」を後から辿れるようにするのが目的で、結論だけに書き換えない。
> **射程**: 🔴 **GitHub リポジトリのソース公開** に限る。`M-4`（第三者へ **サービス** を公開するかの判断ゲート・[`roadmap.md`](../02_requirements/roadmap.md) §3）とは別の判断である。両者の相互作用は §5 で扱う。
> **調査日**: 2026-08-20 JST / **調査対象**: 追跡ファイル 589 件・全 50 コミット・リモートブランチ 46 本・Issue 110 件（open）

---

## 決定事項（2026-08-20 JST・飼い主の明示決定）

| 論点 | 決定 | 帰結 |
|---|---|---|
| 与件（`minimum-requirements.md`） | 🔴 **原本のまま公開する** | 第三者著作物として `LICENSE` の対象外を明示し、ファイル冒頭に権利表示を付ける（要件本文は無改変） |
| ライセンス | 🔴 **MIT License** | `LICENSE` は MIT 原文のみ。第三者著作物（与件・`skill-creator`）は `NOTICE` へ分離 |
| `telemetry/cost-data` | 🔴 **そのまま公開する** | 対応不要。AI 開発費の実測データとして公開する |
| プレビュー URL | 🔴 **URL ごと公開する** | 🔴 **`M-4` の通過判定（`R-5` / `R-6` / `R-8`）と Issue #187 の解消が公開前の前提に入る**（§5・§6 Phase 1.5） |

---

## 0. 結論

> ✅ **後日追記（2026-08-20）**: 下記 4 件はすべて決着し、**公開まで完了した**。`B-1` は「原本のまま公開する」、`B-2` は MIT（第三者著作物は `NOTICE` へ分離）、`B-3` は「そのまま公開する」、`B-4` は根拠を訂正済み。以降の節は当時の判断過程の記録である。

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

### 1.3 Issue / PR と全ブランチ履歴のスキャン（2026-08-20 追加実施）

ファイルスキャン（§1.1）とは別に、**公開されるのはコードだけではない** ため以下も走査した。

| 対象 | 件数 | 結果 |
|---|---|---|
| Issue（open + closed・本文） | 233 | **秘密情報の検出ゼロ** |
| Issue コメント | 196 | 同上 |
| PR（本文） | 53 | 同上 |
| PR レビュー本文 | 197 | 同上 |
| PR 行単位レビューコメント | 415 | 同上 |
| **全リモートブランチの全コミット** | **368**（46 ブランチ） | 同上。`.env` / `*.pem` / `*.key` は **一度もコミットされていない** |

検出されたのは以下だけで、いずれも実値ではない。

- ドキュメント内のプレースホルダ（`SLACK_BOT_TOKEN=xoxb-xxxxx-xxxxx-xxxxx`）
- マスク処理ツールの docstring（`mask_value("xoxb-abc123def456")`）
- 鍵形式の説明文（`-----BEGIN RSA PRIVATE KEY-----` という **形式名** への言及）
- GitGuardian bot が PR #141 / #143 / #183 に残した検出通知（参照している値はテスト用ダミー。通知本文に値そのものは含まれない）

> 🔵 **`main` の 50 コミットだけでは不十分** だった点に注意。`main` は squash マージのため、各 PR のスカッシュ前のコミットは `claude/*` ブランチ側にしか存在しない。46 ブランチ 368 コミットへ広げて初めて全履歴を見たことになる。

> 🔵 SP-10 のレトロが記録している「検証用ビルド成果物 269 ファイルの WIP 混入」（`.next-r5verify/`）は、**現在どのリモート参照からも到達できない** ことを確認した（`git log --remotes --name-only` に `.next-*` が一切現れない）。ただし GitHub は PR に紐づくコミットを **ブランチ削除後も PR ページから参照可能なまま保持する** ため、PR #183 のコミット一覧からは辿れる可能性が残る。中身は Next.js の RSC キャッシュ情報でありビルドハッシュの誤検知であるため、実害はない。

### 1.4 第三者著作物

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

### Phase 0: 判断（ユーザー） — ✅ 完了（2026-08-20 JST）

- [x] **`B-1`**: 与件 → **原本のまま公開する**
- [x] **`B-2`**: ライセンス → **MIT License**
- [x] **`B-3`**: コストテレメトリ → **そのまま公開する**
- [x] **§5**: プレビュー URL → **(b) URL ごと公開する**（`M-4` の通過判定を先に済ませる）

### Phase 1: 公開前の整備（Claude が実行できる）

- [x] `B-1` の結論を反映 — 原本を維持し、`NOTICE` とファイル冒頭の権利表示で第三者著作物であることを明示（要件本文は無改変・`inception-deck.md` の参照行にも例外を記録）
- [x] `LICENSE`（MIT）を追加し、第三者著作物（**与件** と `.claude/skills/skill-creator/`・Apache-2.0）は `NOTICE` へ分離した。⚠️ 当初は `LICENSE` 内に Exclusions 節を追記していたが、**公開後の実測で GitHub のライセンス判定が `NOASSERTION`（Other）になり MIT のバッジが出ないことが判明**。`LICENSE` を MIT 原文のみへ戻して解消した
- [x] README にライセンス節と権利表示を追加
- [x] 🔴 **与件を自動整形の対象外にした** — `tools/check_cjk_markdown.py` に `EXCLUDED_PATHS` を追加。本プロジェクトの CJK 表記ルールを他者の文書へ機械適用すると、整形で本文が変わり「原文のまま収録している」という権利表示自体が虚偽になる（実際に 1 度発生し、原本から作り直した）。self-test でパス判定と対象ファイルの実在を検証する
- [x] `docs/rules/env-vars.md` の「private だから安全」を「collaborator 権限で保護されている」へ訂正（`B-4`）
- [x] `M-4'`: 未使用のスキャフォールド資産（`public/*.svg` 5 件）を削除
- [x] `M-6'`: `package.json` に `license` / `repository` を追加（`private: true` は npm 誤公開防止として意図的に維持）
- [x] **Issue / PR 全件の最終スキャン** — §1.3 に結果を記録
- [x] **全リモートブランチの履歴スキャン** — §1.3 に結果を記録
- [x] 🔴 **削除予定だったブランチにしか無い記録を回収** — `claude/kind-curie-r63oz8` に `SP-8` のスプリントレビュー記録 9 ファイルが残っていた（PR #141 のスカッシュマージ **後** に追記されたため `main` へ入っていなかった）。ブランチごと消していたら失われていた
- [ ] `M-5'`: マージ済み `claude/*` ブランチ 40 本を削除 — ⚠️ **本セッションからは実行不可**。`git push --delete` も REST `DELETE /git/refs` も **プロキシが 403 で拒否** し、GitHub MCP にブランチ削除ツールが存在しない。ユーザー作業へ切り出し（§7.6）
- [ ] Wiki / Projects の中身を確認（空でなければ内容を確認）

### Phase 1.5: `M-4` の通過判定（プレビュー URL ごと公開する選択の前提）

- [x] `R-8`: GitHub 利用規約 / AUP / API Terms の一次確認 → [ADR 0013](../adr/0013-public-operation-under-github-terms.md)（§7.1）
- [x] `R-5`: 必要レート枠の逆算 → 暫定 TTL のままで充足。検索 60 秒 / 詳細 300 秒を確定（§7.2）
- [x] `R-6`: 運用コストの試算 → **Workers Paid** と確定。撤退ライン $10 に触れるには日 89 万リクエストの継続が要り、上流の GitHub API が先に律速するため **公開の阻害要因ではない**（§7.3）
- [ ] 🔴 **本番 URL を正常応答させる**（§7.4）— 現在 404。Issue #231 / PR #235（別セッション）が対処中。**公開前に再確認する**
- [ ] Issue #187（§7.5）— 公開の阻害要因ではない。§7.4 の退役完了で実質的に解消する

### Phase 2: 公開（ユーザーのみ実行可能 — `A-6` 相当） — ✅ 完了（2026-08-20 JST）

- [x] Settings → Danger Zone → Change visibility → Public
- [x] 公開状態を実測で確認: `visibility: public` / 匿名 `GET /repos` が 200 / README・`LICENSE`・`NOTICE`・Issues・Pulls がいずれも匿名で 200

### Phase 3: 公開直後 — 🔴 **すべてユーザー作業だった**（Claude 側からは実行不可）

> 🔴 **当初「Claude が実行できる」と書いていたが誤りだった。** 公開後に実測したところ、リポジトリ設定系の書き込みは
> **プロキシが例外なく遮断** しており、GitHub MCP にも該当ツールが無い（§7.6 と同じ構造）。
>
> | 経路 | 結果 |
> |---|---|
> | `GET /repos/{o}/{r}/rulesets` | 200（読み取りは通る） |
> | `POST /repos/{o}/{r}/rulesets`（ブランチ保護の作成） | 🔴 403 プロキシ遮断 |
> | `PATCH /repos/{o}/{r}`（description・セキュリティ機能） | 🔴 403 プロキシ遮断 |

- [x] **`main` にルールセット `protect-main` を設定** — ✅ 完了（下記に実測値）
- [ ] Secret scanning / Push protection / Dependabot alerts / Code scanning を有効化し、初回検出をトリアージ（テスト用ダミー鍵 2 件は GitHub 側で dismiss する。`.gitguardian.yaml` は ggshield 用で GitHub には効かない）
- [ ] Actions の fork PR 実行ポリシーを「**Require approval for all outside collaborators**」以上に設定
- [ ] リポジトリの description / topics を設定（公開リポジトリの第一印象）

#### `protect-main` の実測値（`GET /rulesets/21082714`・2026-08-20）

```
name        : protect-main
enforcement : active
target      : branch
bypass      : （空 = リポジトリ管理者・オーナーを含む全員に適用）
conditions  : {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}
rules       : deletion / non_fast_forward /
              pull_request { required_approving_review_count: 0,
                             allowed_merge_methods: ["squash"] }
```

🟢 **これで `A-1`（`main` への直接 push 禁止）が GitHub 側で機械強制されるようになった。** 従来はフック（`pre-git-push-check.sh`）の自主規制だけが支えだった。

🔵 **意図的に入れなかったもの**:

| ルール | 入れない理由 |
|---|---|
| `Require status checks to pass` | 🔴 GitHub Actions が使えない状態（`D-23`）で有効にすると、**チェックが 1 つも報告されず全マージが永久にブロックされる**。Actions 復活時に追加する |
| `Required approvals` を 1 以上 | 🔴 **PR 自律化の恒久委任（`CLAUDE.md`）と両立しない**。承認者が現れるまで自動マージが止まる |
| Bypass list への管理者追加 | `A-1` の意図は「オーナー自身も PR を経由する」こと。緊急時は Enforcement を一時的に Disabled にする |
| `Require linear history` | squash マージのみ許可しているため、既に線形になる。二重の制約を置かない |

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

---

## 7. `M-4` 通過判定の記録（プレビュー URL ごと公開する選択に伴う前提）

> 🔴 **本節は `R-5` の逆算と `R-6` の試算の正本である。** [ADR 0005](../adr/0005-cache-port-yagni-exception-and-ttl.md) §3.4 追補はここを参照する（同じ数字を 2 箇所に書かない）。

### 7.1. `R-8`: GitHub 利用規約の一次確認 — ✅ 完了

[ADR 0013](../adr/0013-public-operation-under-github-terms.md) に記録した。結論は「**現在の実装のまま公開して運用してよい**」で、規約上の制約を `T-1`〜`T-4`（スクレイピングしない / アバターを再配信しない / 過度な一括リクエストをしない / スパム・個人情報販売に使わない）として設計制約に固定した。`RK-10` の対策状態も更新済み。

### 7.2. `R-5`: 必要レート枠の逆算 — ✅ 完了（TTL は暫定値のまま確定）

**律速は GitHub 検索 API の 30 req/分**（認証済み）である。詳細取得は Core API（GitHub App の installation token で 5,000 req/時 ≒ 83 req/分）を使うため、検索側が先に枯れる。

| 項目 | 値 | 出典 |
|---|---|---|
| 検索 API のレート枠 | **30 req/分**（アプリ全体で共有） | [`prd.md`](../02_requirements/prd.md) §2.2 |
| 1 検索あたりの上流呼び出し | **1 回**（キャッシュミス時） | `src/infrastructure/github/` の 2 経路のみが外部通信する |
| 1 詳細表示あたりの上流呼び出し | **1 回**（同上・Core API 側） | 同上 |
| 検索キャッシュ TTL | 60 秒 | [ADR 0005](../adr/0005-cache-port-yagni-exception-and-ttl.md) |
| クライアント単位のレート制限 | 60 req / 60 秒 | `wrangler.jsonc` の `RATE_LIMITER`（`NFR-7`） |

**逆算**: 1 セッションで利用者が異なるキーワードを 4 回打ち、所要 3 分と仮定すると **1 利用者あたり約 1.3 検索/分**。キャッシュミスを最悪ケース（全て異なるキーワード）と置くと、

```
30 req/分 ÷ 1.3 検索/分/人 ≒ 同時実利用者 23 名 が上限
```

**判定**: 選考課題・ポートフォリオとしての公開（`D-3`）で想定される同時実利用者は 23 名を大きく下回るため、**暫定 TTL のままで必要枠を満たす**。TTL を延ばす変更は不要と判断し、検索 60 秒 / 詳細 300 秒を確定値とする。

⚠️ **残余リスク（明示しておく）**

- `InMemoryCache` は **isolate 内メモリ** であり、コロケーション／isolate をまたいで共有されない。したがって上記の「キャッシュミス最悪ケース」は実際には常に近い状態になりうる。**上の逆算はその最悪ケースで計算しているため、この事実によって結論は変わらない**
- レート制限（`NFR-7`）は **クライアント単位** であり、上流の 30 req/分という **総量** は守らない。多数の別クライアントが同時に来れば枯れる。枯れたときの挙動は `SP-9` で実装済み（レート制限超過を区別して伝え、再試行手段を提供する）
- 枯渇が実際に起きた場合の緩和策は任意 OAuth ログイン（[ADR 0012](../adr/0012-optional-github-oauth.md)・ログインすると各自のレート枠を使う）。⚠️ **Issue #187 が解消されるまでプレビューではこの緩和が働かない**

⚠️ **`SP-16`（`sort=gem-index`）は本逆算の前提が成り立たない（PR #293 セルフレビュー指摘）**: 上表「1 検索あたりの上流呼び出し」は **1 回** を前提にしているが、`sort=gem-index` は内部で最大 10 ページを逐次取得するため **1 検索あたり最大 10 リクエスト** になりうる（`src/usecases/search-repositories.ts` の `GEM_INDEX_FETCH_MAX_PAGES`）。🔴 **`sort=gem-index` 自体が `D-33`（2026-08-21）により撤去されたため、本注記は解消済み**（[`open-questions.md`](../02_requirements/open-questions.md) `D-33`）。1 検索あたりの上流呼び出しは常に 1 回に戻り、再逆算は不要になった。

### 7.3. `R-6`: 運用コストの試算 — ✅ 完了（**Workers Paid** と確定）

[Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §5 が条件を定義済みで、本節はそれに数字を当てる。

| 項目 | Free の上限 | 試算 |
|---|---|---|
| リクエスト | 100,000 / 日 | 100,000 ÷ 86,400 秒 ≒ **1.16 req/秒を継続して初めて到達** する。§7.2 のとおり上流が先に枯れるため、この水準のトラフィックは GitHub API 側が支えられない。**到達しない** |
| CPU 時間 | 10 ms / invocation | `SP-1` の実測ゲート（§5.3）で判定済みの前提。⚠️ 下記の確認事項を参照 |
| Worker バンドル | 3 MB（gzip 後） | 同上 |

**🟢 Free である限りコストは構造的に 0 円** である。超過しても課金されず HTTP Error 1027 で停止するため、`INF-2` の「課金ではなく停止側に倒す」が満たされる。撤退ライン $10（`D-19`）に触れる経路が存在しない。

**🔴 プランの実機確認（2026-08-20 実施・飼い主がダッシュボードで確認）**: 本アカウントは **Workers Paid（$5/月 + 従量）** である。`wrangler.jsonc` の `limits.cpu_ms: 50` が有効に働く一方、`INF-2` が想定した「超過したら課金されず停止する」構造は **効いていない**。

⚠️ **したがって [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §5.1「月額 0 円の条件」は現状を記述していない**（条件 1「Workers Free のまま」を満たしていない）。同 §5.4「Paid へ移行した場合に失うもの」が現状に該当する側である。

#### Paid における実額の試算（一次情報・2026-08-20 取得）

| 項目 | Workers Paid | 出典 |
|---|---|---|
| 月額基本 | **$5** | [Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/) |
| 含まれるリクエスト | **10,000,000 / 月** | 同上 |
| 含まれる CPU 時間 | **30,000,000 CPU-ms / 月** | 同上 |
| 超過（リクエスト） | **$0.30 / 100 万** | 同上 |
| 超過（CPU 時間） | **$0.02 / 100 万 CPU-ms** | 同上 |
| 静的アセット・サブリクエスト | **課金対象外** | 同上 |

**撤退ライン $10（`D-19`）に到達する条件を逆算する**:

```
$10 = $5（基本） + $5（超過）
$5 ÷ $0.30/100万 ≒ 1,670 万リクエストの超過
含まれる 1,000 万 + 1,670 万 = 約 2,670 万リクエスト / 月
                              ≒ 890,000 リクエスト / 日 を継続
```

**判定**: 🟢 **リポジトリの公開そのものはコスト上限の脅威にならない。** 選考課題・ポートフォリオの想定トラフィックは含まれる 1,000 万/月を桁で下回る。加えて §7.2 のとおり **上流の GitHub API（30 req/分）が先に律速する** ため、正常な利用でこの水準へ到達する経路が存在しない。

⚠️ **残余リスク（意図的な濫用）**: 日 89 万リクエストを継続的に浴びせられれば撤退ラインに触れる。`*.workers.dev` は自分のゾーンに属さないため **Cloudflare の WAF レート制限ルールを適用できず**、アプリ内の `RATE_LIMITER` は Worker が起動した後に効くので **リクエスト数課金そのものは止められない**。`D-19` が約束した Billable Usage API の日次ポーリングは **まだ実装されていない**（`tools/` に該当スクリプトが存在しないことを確認済み）。

→ **公開の阻害要因ではない** が、`D-19` の約束が未履行であるため別 Issue で実装する。⚠️ 実装には **課金情報を読めるトークン** が要る（現行トークンは `subscriptions` エンドポイントで Authentication error）。

### 7.4. 🔴 公開先 URL の実挙動 — **本番が機能していない**（2026-08-20 実測）

「URL ごと公開する」判断の前提として、公開後に第三者が到達しうる URL を実際に叩いた。

| URL | HTTP | 実挙動 |
|---|---|---|
| `https://gem-hunter.kinamocchi-tech.workers.dev/` | 200 | 🔴 **本文に 404 が描画される**。`/?q=react` も検索結果を返さない（アバター URL が 1 件も出ない） |
| `https://gem-hunter.kinamocchi-tech.workers.dev/ja?q=react` | 200 | 🔴 `<title>404: This page could not be found.</title>` |
| `https://sp1-gem-hunter.kinamocchi-tech.workers.dev/ja?q=react` | 200 | 🔴 同上（本番と応答が完全に同一サイズ。**本番は `SP-1` 当時のビルドのまま** と考えられる） |
| `https://pr-183-gem-hunter.kinamocchi-tech.workers.dev/ja?q=react` | 200 | ✅ 正常。検索結果 40 件・ページネーションまで描画される |

**判定**: 🔴 **この状態で公開してはならない。** 選考課題・ポートフォリオとして公開する以上、リポジトリから辿れる本番 URL が 404 を返すのは、コードの中身を見る前に評価を損なう。**技術的な危険ではなく、成果物の見え方の問題** として最優先で潰す。

🟢 **これは既に別レーンで対処中である。** Issue #231 / PR #235（別セッション・`claude/sprint-env-cleanup-prod-deploy-77d8sb`）が「スプリント環境の退役と本番デプロイのレビューゲート」を実装しており、**マージ後に `main` HEAD での本番デプロイと、古いプレビュー alias の退役（本番と同じビルドへの張り替え）を実行する** と PR 本文に明記されている。`CP-4` に従い本レーンからは介入しない。

→ **公開の前提条件**: PR #235 のマージとその後の本番デプロイが完了し、上表の 4 URL がいずれも正常応答することを再確認する。

### 7.5. Issue #187: プレビューに secret が渡っていない — ⚠️ 未解消（公開の阻害要因ではない）

プレビュー version に secret が投入されておらず、**認証（GitHub App installation token）とレート制限がプレビューで動作しない**。

⚠️ **影響を正確に書く**: 未認証リクエストのレート枠は **IP 単位** であり、本番が使うアプリ共有トークンの枠（30 req/分）を食わない。したがって **コスト・セキュリティ上の危険はない**。実害は「プレビューを開いた人が体験する品質が落ちる」ことに限られる。§7.4 の退役（プレビューを本番と同じビルドへ張り替える）が完了すれば、この問題を抱えた古いプレビューは実質的に消える。


### 7.6. ブランチ削除がセッションから実行できない（実測 2026-08-20・再検証済み）

`M-5'`（マージ済み `claude/*` ブランチ 40 本の削除）は、**本セッションからは実行できない**。飼い主の指示で経路を変えて再検証し、遮断の性質を特定した。

#### 実測マトリクス

| # | 経路 | HTTP | 応答の出どころ |
|---|---|---|---|
| A | `GET /repos/{o}/{r}/git/refs/heads/main` | 200 | GitHub（**読み取りは通る**） |
| B | `POST /repos/{o}/{r}/git/refs`（ref 作成） | 403 | 🔴 **プロキシ** |
| C | `PATCH /repos/{o}/{r}/git/refs/heads/<b>`（ref 更新） | 403 | 🔴 **プロキシ** |
| D | `DELETE /repos/{o}/{r}/git/refs/heads/<b>`（ref 削除） | 403 | 🔴 **プロキシ** |
| E | `POST /repos/{o}/{r}/issues/{n}/comments`（対照） | 404 | GitHub（**書き込みでも通る**） |
| F | `git push origin --delete <b>` / `git push origin :<b>` | 403 | 🔴 プロキシ（`RPC failed; HTTP 403`） |
| G | `git push origin <b>`（通常の ref 更新・対照） | ✅ 成功 | — |
| H | GitHub MCP | — | 🔴 **ブランチ削除に相当するツールが存在しない**（`create_branch` はあるが対になる削除が無い） |

プロキシの応答本文は一貫して次のとおり。

```json
{"message":"Write access to this GitHub API path is not permitted through this proxy."}
```

#### 分かったこと

🔴 **「書き込みが全部ダメ」ではなく、`git/refs` への書き込みだけが経路単位で遮断されている。** 対照 E（Issue コメントの POST）は GitHub まで到達して 404 を返しており、直叩きの書き込みそのものは許可されている。B / C / D がすべて 403 なので、**遮断されているのは "ref の直接操作" という操作クラス** である（削除だけを狙った制限ではない）。

一方 G のとおり **`git push` による通常の ref 更新は通る**。つまり「git プロトコル経由の前進的な更新は許可、ref の直接操作と削除は不許可」という線引きになっている。サンクションされた書き込み口は GitHub MCP であり、そこに削除ツールが無いのは設計上の一貫性がある。

#### 🔴 迂回しない

GraphQL の `deleteRef` ミューテーション（`POST /graphql`）は理屈のうえでは別経路だが、**これは明示的なポリシー拒否を迂回する行為にあたるため試していない**。プロキシの運用ガイド（`/root/.ccr/README.md`）自身が *"do not retry organization policy denials (403/407) — report them instead"* と定めている。

→ **ユーザー作業として切り出す**（ローカルの `gh` / `git`、または GitHub の Branches 画面からは通常どおり削除できる）。手順は #241 `U-3`。

> ⚠️ **ブランチを消してもコミットは消えない**。GitHub は PR に紐づくコミットをブランチ削除後も PR ページから参照可能なまま保持する。削除の目的は「リポジトリの第一印象を整えること」であって、履歴の秘匿ではない（秘匿が必要な内容は §1.3 のスキャンでゼロ件だった）。
