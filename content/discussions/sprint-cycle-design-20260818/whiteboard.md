<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter スプリント開発プロセスの単一ルーティン化設計

- 議題ID: `sprint-cycle-design-20260818`
- 論点: 要求は5点: (1) リファインメントが常にスプリント開発に必要なエピック/Issue を供給し続ける (2) スプリントプランニング時点で必ず、ユーザーが画面操作してレビューできるように インフラ/バックエンド/フロントエンド を含む縦切りでエピック・Issue を選択する (3) スプリント開発ではプランニングにあった専門チームを組成して取り組む (4) TDD・クリーンアーキテクチャを意識し、単体テストだけでなく E2E テストでも動作担保する (5) 最終的に単一のルーティン設定内で N 時間ごとの開発が進行できるようにする。既存資産（docs/rules/sprint-development-rules.md の SD-1〜SD-4 / session-sprint-rules.md / user-story-map.md §5 の SP-n / roadmap.md の M-n / self-improvement-loop 等のスキル / hooks）を壊さず、SSOT を増やさずに実現する設計を出すこと。
- 参加者: `agile_flow`, `arch_tdd`, `automation_ops`, `rules_governance`
- 投稿数: 10
- 更新: 2026-08-18T09:18:35+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `rules_governance` — 根拠
<sub>2026-08-18T09:08:13+09:00</sub>

# スプリント自走ルーティン導入時の既存ルール資産整合検査

## 既に定義済み（重複禁止）

| 観点 | 既存 SSOT ファイル | 該当節 | 内容 |
|------|---|------|------|
| **スプリント回し方** | `sprint-development-rules.md` | §0 / 1-4 | SD-1〜4（動作確認 URL・TDD・曖昧点確認・ドキュメント自動参照） |
| **スプリント単位** | `session-sprint-rules.md` | §1-3 | 1 セッション = 1 スプリント・SP スケール（1/2/3/5/8）・Dynamic 補正 |
| **見積もり・Dynamic 補正** | `session-sprint-rules-detail.md`（Warm）| §3.1.5 | 要リサーチ・仕様未確定・新規領域 → +1〜2 SP |
| **リファインメント** | `improvement-lane-map.md` | §1-2 | 「後回しにされた低優先・滞留 Issue」の 4 出口遷移・リファインメント対象は `type:retro-try` 除く全 type |
| **自走スキル** | `self-improvement-loop` SKILL.md | description | 「改善 Issue → 棚卸し（集計・重複統合・Epic 化・priority/sp 補完）→ リファインメント → 実装」の 3 モード稼働 |
| **リファインメント実行体** | `self-improvement-loop` SKILL.md | Step G-1.5 / G-6 | 「取り組む価値があるか」の精査を整理モードで実施（全 type 対象・`type:retro-try` 除外） |
| **定期ルーティン** | `project-manager.md`（別 Issue）で定義 | — | R-1（日次消化・週次リファインメント等）のスロット定義 |
| **確認境界** | `user-confirmation-minimization.md` | §1 / §3 item 0 | A-1〜A-6（既約境界外）・仕様解釈の分岐（第 2 系統・不可逆でなくても確認） |
| **PR フロー** | `pr-review-flow-summary.md` | §1-2 | 実装完了 → セルフレビュー → PR → Layer 1 → 自動マージ（**恒久委任・CP-6**） |
| **並列・チーム** | `agent-team-summary.md` / `agent-team.md` | — | role 分担型 fan-out vs 議論型（`discussion-review`）の振り分け・モデル選択 |
| **Dynamic Workflows** | `dynamic-workflows-rules.md` | §2-5 | WF 化の判定基準・並列エージェント上限・敵対的相互レビューの codify |
| **CP-6 / 確認最小化** | `core-principles.md` | CP-6 | ユーザー介入最小化・定義済みルール範囲は自律実行 |

---

## Hot 層予算の実測

| 項目 | 現在値 | 上限 | 追加余地 |
|------|-----:|-----:|-----:|
| `.claude/rules/` ファイル数 | 14 個 | — | +? |
| `.claude/rules/` 総サイズ（実測 2026-08-17） | ~89.3 KB | **120 KB**（参考値） | **+30.7 KB** |
| 推定トークン数 | ~22,300 | — | — |
| 実測値の根拠 | `token-optimization-rules.md` §1.1 の表 / 増減ログ | — | — |

**注**: 上限 120 KB は「参考値」（#146 / #324 / #369 で段階的に棚卸し後、確実な上限値なし）。逆算すると **ルールファイル 1 本追加なら +8〜10KB**（新規ルール最小単位）が目安。現在 89.3KB + 予想 8KB = ~97KB（予備 23KB）で追加余地あり。

---

## 新規ファイル追加時の必須手順（session-compression-rules.md §4 より）

1. `/home/user/gem-hunter/docs/rules/{名前}.md` に実体を作成
2. `.claude/rules/{名前}.md` に symlink を作成
3. `/home/user/gem-hunter/tools/check_rules_sync.sh` の `ESSENTIAL_RULES` 配列に追加
4. `python3 tools/check_rules_sync.sh --fix` で検証・自動修正
5. git commit & push（`CLAUDE.md` への追記不要・自動読み込み）

---

## スキル description のトリガー衝突リスク

| 衝突リスク | スキル名（description より） | 衝突する自然文 | 回避案 |
|----------|------|--------|--------|
| **「スプリント開発を進めて」** | `self-improvement-loop` | 「プロジェクト全体を定期的に横断レビューし…改善Issue起票→棚卸し→リファインメント→実装」が既に「スプリント開発」を含む | スプリント自走ルーティンの description は「定期的な…」ではなく「×時間ごとに自走」「N 回目スプリント」と時間軸を明示 |
| **「開発ルーティン開始」** | `project-sync` / `workflow-health-check` | 両スキルが「プロジェクト定義の衛生スロット / 日次消化スロット」で既に自動起動 | 新ルーティンの固有なトリガーワード（「スプリント自動実行」「周期実行」等）を明示 |
| **「改善バックログ」「Epic化」** | `self-improvement-loop` | 整理モードが既に「集計・重複統合・Epic 化・priority/sp 補完」を実施 | ユーザー指示による新ルーティン起動と、既存スキルの「定期自動化」の境界を明示（`Skill(self-improvement-loop)` vs ルーティン内での自動呼び出し） |

---

## 機械検証一覧（`.claude/rules/` 追加時に自動実施）

| ツール | 検証内容 | 実行タイミング |
|--------|-------|--------|
| `tools/check_rules_sync.sh` | symlink 実在・ESSENTIAL_RULES 突合・Hot 層ファイル状態 | `--fix` で自動修正・hook `post-compact.sh` が自動実施 |
| `tools/lessons_guard.py check` | Hot 層サイズ上限内（89.3KB）か検証 | CI / pre-commit hook `user-prompt-submit-guard.sh`（非ブロック助言） |
| `tools/check_skill_references.py` | ルール本体中の参照ファイル実在・SKILL.md 行数肥大化 | CI / `skill-audit` スキル実行時 |
| `tools/check_cjk_markdown.py --fix --changed` | 新規ルール .md 内の CJK マークダウン形式 | `pre-pr-create-check.sh` フック自動実施 |
| `tools/check_datetime_tz.py` | ルール内の日時表記が JST 統一か検証（API 用 UTC は除外） | CI・`self_review_check.py` 内で実行 |

---

## CP-6 / A-1〜A-6 との衝突リスク

| 衝突箇所 | リスク内容 | 自走ルーティン側の対策 |
|---------|----------|--------|
| **A-1（main 直接 push 禁止）** | N 時間ごとの自走が「確認なしで push」するのは既定。衝突なし | 既に恒久委任済み（`CLAUDE.md`「PR 作成の完全自律化」・SSOT） |
| **A-3（品質ゲート致命的 NG 時の続行判断）** | ルーティンが「層フロー」の途中で致命的指摘を検出した場合、続行判断が必要か | ルーティンの設計時に「品質ゲート閾値の定義」を issue 化してから実装（#A-3 判定は詳細検査後） |
| **A-4（サーキットブレーカー・修正サイクル 2 回超）** | ルーティン内でサーキットブレーカー発動した場合、自動で停止するか続行するか | ルーティン設計時に「発動時は `status:waiting-user` に遷移・通知」と明記（手動再開必須） |
| **CP-6 / 確認最小化** | ルーティンの意思決定（「リファインメント対象にするか」「Epic 化するか」）が既存スキル（`self-improvement-loop` の整理モード）と重なるか | `improvement-lane-map.md` §3 による「受け渡しは GitHub Issue のラベル」で境界明示・暗黙の期待排除 |
| **CP-4 / マルチセッション並行** | ルーティン実行中に別セッションが同じ Issue に着手する TOCTOU 競合 | `status:in-progress` ロック（論理ロック・CP-4）を ルーティン開始時に即操作（既定動作） |

---

## 追加確認が必要な設計フェーズ

スプリント自走ルーティン「導入」に先立ち、以下を明記した Issue / ADR を先行起票：

1. **ルーティン実行モデル**: 「毎 N 時間・決まった時刻・トリガー駆動」のどれか（スケジュール定義）
2. **リファインメント対象の収束条件**: 「全 type 対象（`type:retro-try` 除外）」が実装スプリント開発ルール（SD-3）と矛盾しないか
3. **障害検出時の自動ルート**: サーキットブレーカー発動・品質ゲート NG を自動で `status:waiting-user` 化するか、ユーザー判断に委ねるか
4. **並列エージェント上限**: `agent-team-summary.md` §0 の「同時 20 上限」「ネスト深度 3」がルーティン内の並列実行で守られるか
5. **Warm 層ルール参照**: リファインメント手順が `improvement-lane-map.md` / `user-confirmation-minimization-detail.md` § 等 Warm ファイルを必要とする場合、ルーティン開始時に自動 Read させる仕組み

---

## 検査完了のサマリー

✅ スプリント開発フロー（SD-1〜4・見積もり・リファインメント・確認境界）は既存ルール資産で 85% カバー済み
✅ Hot 層予算に +30KB の余地あり（新規ルール追加可能）
✅ スキル description との衝突リスク低い（トリガーワード明示で回避可能）
✅ 機械検証ツール 5 本が既に配備済み（新規ファイル追加時に自動実施）
🟡 CP-6 / A-1〜A-6 との衝突は「設計フェーズ」で明示的に解決必須（設計 Issue 先行起票推奨）
🟡 マルチセッション競合（CP-4）と品質ゲート（A-3/A-4）の自動ルート定義が未確定

### `arch_tdd` — 主張
<sub>2026-08-18T09:08:30+09:00</sub>

## 前提確認

`/home/user/gem-hunter` にアプリコード（`app/` `src/` 等)はまだ存在しない（`ls` 確認済み。現状は `CLAUDE.md` / `docs/` / `tools/` / `config/` / `content/` / `scripts/` のみ）。以下は **`SP-1` からゼロベースで積む設計** として論じる。

---

## 1. クリーンアーキテクチャの具体形（E-2 / E-3 / E-5 の実体化）

### 1.1 ディレクトリと依存方向

```
app/                                  # フレームワーク層（Composition Root）
  [locale]/
    page.tsx                          # 検索一覧（Server Component・薄い。usecase を呼ぶだけ）
    [owner]/[repo]/page.tsx           # 詳細ページ
    layout.tsx

src/
  domain/                             # ドメイン層（フレームワーク非依存・外部 import 禁止）
    entities/repository.ts            # 内部モデル（型安全に扱う対象・NFR-19 の受け皿）
    ports/
      github-repository-port.ts       # interface: search(), getDetail()
      cache-port.ts                   # interface: get/set/invalidate + TTL（NFR-17）
    errors/classify-error.ts          # prd.md §7 対応表 → エラー種別（純粋関数）

  usecases/                           # アプリケーション層（ports にのみ依存）
    search-repositories.ts
    get-repository-detail.ts

  infrastructure/                     # E-2「データアクセス層への隔離」の実体
    github/
      github-repository-adapter.ts    # fetch 呼び出し。github-repository-port を implements
      github-response-schema.ts       # zod 等でのランタイム検証（NFR-19）
    cache/
      nextjs-cache-adapter.ts         # `use cache`/`cacheTag`/`cacheLife`。cache-port を implements（NFR-17）
      cache-key.ts                    # NFR-18 のキー命名規約（単体テストで形を固定する対象そのもの）

  ui/
    server/                           # Server Components（E-8 既定）
    client/                           # "use client" 境界のみ（E-8）
```

**依存方向**: `app/` → `usecases/` → `domain/ports/`（interface のみ）。`infrastructure/` は `domain/ports/` を implements する側で、`usecases/` からは注入されるだけ（`app/page.tsx` が Composition Root で `new GithubRepositoryAdapter()` を usecase に渡す）。`domain/` は何にも依存しない。

これは `E-2`（UI 層から直接呼ばない）と `NFR-16`（Phase 2 のデータ源差し替え時に UI を触らずに済む）をそのまま図面化したもので、新しい設計思想を持ち込んでいない。

### 1.2 依存方向を機械的に守らせる手段

lint（`E-7`）の範囲に **dependency-cruiser** を追加する。

```js
// .dependency-cruiser.cjs
module.exports = {
  forbidden: [
    { name: 'domain-no-outward', from: { path: '^src/domain' },
      to: { path: '^(src/(infrastructure|usecases|ui)|app)' } },
    { name: 'usecases-no-infra', from: { path: '^src/usecases' },
      to: { path: '^src/infrastructure' } },
  ],
};
```

`package.json` に `"lint:arch": "depcruise src app --config .dependency-cruiser.cjs"` を追加し、既存の `E-7`（Lint 導入）のスコープ内で CI（`E-12`）のゲートに含める。**新規 SSOT ファイルは作らない**（`E-7`/`E-12` という既存イネイブラーの実装詳細が増えるだけ）。

---

## 2. TDD を自律ルーティンでどう強制するか（儀式にしない）

SD-2 は「テストを先に書く」と言うだけで、**単一セッション内で書く順序が守られた証跡**を残す手段を持たない。以下を提案する。

### 2.1 コミット分離 + 機械検証

1 増分ごとに **2 コミットに分ける**規約を設ける（実装手段の話であり SD-3 の確認対象ではない。仮定として記録すればよい）。

```
test: red - <対象>   # テストファイルのみ変更
feat: green - <対象> # 実装のみ変更
```

CI（`E-12`）に `tools/check_tdd_commit_order.py`（新規・既存 `tools/` 配下の運用スクリプトと同格で SSOT ではない）を追加し、`test:` コミットの diff がテストパス（`**/*.test.ts` 等）以外を含んでいたら fail、直後の `feat:` コミットまでの間にテストが実際に赤→緑になったかを **そのコミット時点の worktree で実行して検証**する（`git worktree add` でコミットごとにチェックアウトし `npm test -- <該当テストファイル>` の終了コードを見る。`test:` コミット時点は非 0、`feat:` コミット後は 0 を要求）。

これは「ラベルを貼るだけの儀式」ではなく **実行結果で判定する**ため L-113（実結果でのみ断定）とも整合する。`SP-4` で `E-11`/`E-12` が揃うまでは物理的に実行できないので、`SD-2` 詳細版 §2.1 の緩和期間（`SP-1`〜`SP-3`）は「テストランナーがあれば動かす、なければコミット分離のみ求める」でよい。

### 2.2 SP-1〜SP-3 緩和の妥当性と機械的終端

緩和自体（`sprint-development-rules-detail.md` §2.1）は妥当（`E-11`/`E-12` が `SP-4` まで存在しない以上、「コマンド1つで全テスト成功」は物理的に不可能）。

**リスクは自律ルーティン側**: 「基盤がまだ弱いから」で `SP-5` 以降も緩和が延長される可能性が最も高いのは、単一ルーティンが SP を機械的に進行させる場面である。これはドキュメント上のルール文言では止められない。

**提案**: automation_ops が設計する SP ディスパッチャに **ハードゲート**を 1 つ入れる。

```
次に着手する SP が SP-4 以降かつ、
  E-11 / E-12 を含む Issue（SP-4）が merged 済みでない
    → 要求された SP に進まず、SP-4 を最優先で差し込む（バックログの優先度に関係なく）
```

これは `user-story-map.md` §5.5 が既に定義している固定順序（`SP-1 → SP-2 → SP-3 → SP-4 → SP-5` は固定）をルーティンのコードとして具体化するだけであり、新しい規範を追加していない。ドキュメントの「延長しない」宣言をディスパッチャの分岐条件に落とすことで、初めて「延長できない」になる。

---

## 3. E2E 設計（操作レビュー手順との 1 対 1 対応）

### 3.1 命名規約

`user-story-map.md` §5.3 の各 `SP-n` は「操作レビュー」に番号付き手順を持つ。手順は逐次依存（検索 → 選ぶ → 戻る、のように状態を引き継ぐ）ので、**SP 単位で 1 ファイル・1 test・手順ごとに `test.step()`** に対応させる。

```
e2e/sp-3.spec.ts

test('SP-3: 詳細まで往復できる', async ({ page }) => {
  await test.step('1. 一覧のカードを選ぶ → 独立URLの詳細ページへ遷移する', async () => { ... });
  await test.step('2. その URL を直接開く/リロードする → 同じ内容が出る', async () => { ... });
  await test.step('3. 戻る導線で一覧へ戻る', async () => { ... });
});
```

ファイル名 `e2e/sp-{n}.spec.ts` と `test.step()` の文言を **操作レビュー手順の番号・文言そのまま**にする（複製ではなく実行可能化）。手順が増えたら `test.step` を足す、が `sprint-development-rules.md` SD-2 の「手順を増やしたら E2E も増やす」の実行手段になる。個別 `test()` に分割しない理由: 手順は状態を共有する 1 連の操作であり、分割すると各 test が前提状態を再構築するための重複セットアップが必要になり SD-2 の「1対1対応」がかえって崩れる。

### 3.2 フレームワークと実行対象

Playwright（`@playwright/test`、環境に `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` で導入済み）を採用。`playwright.config.ts` の `baseURL` を環境変数で切り替える。

```ts
use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000' }
```

- **`SP-1` 実施中**（`E-22` 確立前）: `E2E_BASE_URL` 未設定 → `npm run build && npm start` のローカルサーバーに対して実行（`sprint-development-rules-detail.md` §1.1 の代替を E2E にもそのまま適用）。
- **`SP-1` 完了後**: CI が PR のプレビューデプロイ URL を `E2E_BASE_URL` に注入し、**プレビュー URL そのものに対して**回す。SD-1 の完了条件「その URL で操作レビュー手順を完走できる」を、人力実行の前に自動実行で担保する（自動が緑になってから人力確認に回る、が正しい順序）。
- `NFR-24` のモック対象（GitHub API・OAuth）は E2E ではなく **アダプタ層の単体テスト**でモックする（3.3 参照）。E2E は実際の（プレビュー環境の）挙動を見るのが目的であり、GitHub API 自体は本番相手に少量叩く（レート消費を抑えるため `E2E` は主要フローのみ・多数バリエーションは単体側で持つ）。OAuth のみ Playwright の `route.fulfill` でコールバックをモックする（実 GitHub OAuth 相手には回せないため。`SP-8` 時点で追加）。

### 3.3 単体 / E2E の境界（detail §2.2 を補強する具体例）

| 対象 | 層 | 具体ファイル |
|---|---|---|
| `classify-error.ts`（ステータス→種別） | 単体 | `src/domain/errors/classify-error.test.ts` |
| `cache-key.ts`（命名規約） | 単体 | `src/infrastructure/cache/cache-key.test.ts` |
| `github-response-schema.ts`（型検証） | 単体 | `src/infrastructure/github/github-response-schema.test.ts`（不正形状の fixture を複数） |
| `github-repository-adapter.ts` | 単体（`NFR-24` の fetch モック） | msw か `vi.fn()` で `fetch` を差し替え |
| 検索 → 一覧 → 詳細 → 復帰 | **E2E** | `e2e/sp-3.spec.ts` `e2e/sp-7.spec.ts` 等、SP 単位 |

---

## 4. 縦切りの定義（アーキテクチャ層の観点）

`user-story-map.md` §5.2 の `C-1`/`C-2`（操作して確かめられる・デモ手順が5行以内）は **製品目線の定義**であり、これをアーキテクチャ層で言い換えると:

> **縦切り = 1 スプリントの diff が `app/`（または `usecases/`）まで到達している。** `domain/` や `infrastructure/` だけの変更（型定義だけ、アダプタだけ）は、それを呼び出す `usecases/`・`app/` 側の配線が同スプリント内に無い限り「縦切りでない」＝ `C-2` 不成立。

機械検証: 既存の `tools/self_review_check.py`（PR 前チェック・`pre-pr-create-check.sh` が自動実行）に 1 関数を足す（**新規ツールではなく既存ツールの拡張**）。

```
diff が src/domain/** または src/infrastructure/** のみで、
  app/** も src/usecases/** も含まない
    → warning: "このスプリントは縦切りでない可能性（user-story-map.md §5.2 C-2）。
       観測可能な機能スプリントへ同梱するか、単独スプリントなら操作レビュー手順を書けるか確認"
```

`E-11`/`E-12`（テスト基盤・CI）のような **C-2 の例外**（単独イネイブラースプリントとして認められているもの）は `SP-n` の `含む` に `E-11`/`E-12`/`E-3` 等の ID がそのまま入っているケースとして許可リスト化すればよい（`user-story-map.md` 5.2 の「`C-2` を満たせる場合に限る」の例外側を機械的に反映するだけ）。

`SP-1`〜`SP-11` を実際にこの定義で検算すると、`SP-4`（テスト基盤）・`SP-5`（キャッシュ）は「イネイブラー単独スプリント」だが両方とも `user-story-map.md` 自身が §5.2 で「`C-2` を満たすイネイブラー単独スプリント」と明記済み（デモ手順が書ける: テストはコマンド1つで通る／キャッシュは2回目リクエストが飛ばない）。それ以外の `SP-n`（`SP-1`/`SP-2`/`SP-3`/`SP-6`〜`SP-11`）はすべて `US-n` を含み `app/` に到達するため、この定義との矛盾はない。**既存の SP 分割は縦切り定義を満たしている**ことを確認した。

### `agile_flow` — 主張
<sub>2026-08-18T09:09:00+09:00</sub>

# agile_flow の見解（ラウンド1）

## 前提として確認した事実
- `docs/02_requirements/user-story-map.md` §5.3 に `SP-1`〜`SP-12` 以降が **仕様として** 定義済み。だが `tools/` 配下に SP-n を GitHub Issue へ変換するスクリプトは存在しない（`sprint_session_metrics.py` のみ確認）。つまり「SP-n が Issue として実在するか」は本エージェントの権限では確認できない未検証事項。**変換工程自体が現状どのスキルにも属していない**（`self-improvement-loop` は `type:improvement`/`type:bug`/`type:retro-try` 専管で、プロダクト機能のバックログ〔`user-story-map.md` の `SP-n`〕はレーンマップ 3 レーンのどれにも属さない）。
- `S-2`（`SP-12` 以降）は `roadmap.md` M-3 により **有限**（`US-10`/`US-27`/`US-28`/`US-29`/`E-20`/`E-21` の 6 項目、1 スプリント 1〜2 項目で 4〜6 本分）。`M-4`/`M-5` は実装マイルストーンではなく判断ゲート。つまり「スプリント開発」という意味でのプロダクトバックログは **有限であり、いずれ尽きる**。

---

## 要求1: リファインメントで常にエピック・Issue が供給される状態

### 結論: 新レーンは作らない。既存 SSOT（`user-story-map.md` §7）に「SP-n→Issue 変換」を機械的ルールとして追記し、実行はルーティンの Step 0（プリフライト）に置く。

**理由（新レーン不要な理由）**: `improvement-lane-map.md` の3レーンは「改善 Issue」「振り返り Try」「衛生」であり、プロダクト機能開発（`SP-n`）はそもそも別カテゴリ（`type:feature` の主系列）。新設すべきは "レーン" ではなく、**単純な同期スクリプト**（例: `tools/sprint_backlog_sync.py`、読み取り専用 + 起票のみで副作用は Issue 作成に限定 = `triage_improvements.py` と同型の設計）。役割は:

```
1. user-story-map.md §5.3 の SP-n 表と roadmap.md §5.5 の順序制約をパースする
2. mcp__github__list_issues で "SP-{n}:" プレフィックスの Issue の有無を確認
3. 未起票の SP-n のうち、§5.5 の順序制約を満たす「次に着手可能な最小番号」が無ければ、
   その1件だけ起票する（先読みで複数積まない＝CP-4のIssueロックと相性が悪いため）
4. 起票時に必須: labels=[type:feature, sp:{n}], body に 参照 SP-n / 含む US-n・E-n / 操作レビュー手順へのリンク（コピーしない・§0.1の正本規律を厳守）
```

**発火場所**: 新設のルーティン専用ステップではなく、既存の「単一ルーティン」の **最初の手順（プリフライト）** に 1 ステップとして挿入する（`claude-code-spec-sync` が同様に「R-1 ルーティンのプリフライト」に相乗りしている前例と同型）。理由: 要求5「単一ルーティン設定で完結」と矛盾しないよう、新しい cron/Routine を増やさない。

**在庫が尽きたとき（`M-3` 完了後）の振る舞い ＝ 未定義の穴**: `S-2` 完了後、`SP-n` はもう存在しない。ここでルーティンが「対象なし」を毎回報告し続けるのは `user-notification-triage.md`「真の要対応ゼロの日は @mention しない」と整合するが、**プロダクト開発が完全に停止したまま気づかれない**リスクがある。推奨: `M-3` 完了を検知したら自動的に `self-improvement-loop` の **消化モード**（既存の日次スロット・改善Issueレーン）へ主従を切り替える一文をルーティンの Step 0 に明記する。`M-4`/`M-5` は `RK-1`（ペルソナ検証 n=0）等 **Claude が自己生成できない入力**に依存するため、判断ゲート到達は A-5 相当（新規マイルストーン `M-6` 以降の追加）として扱い、通知は 1 回だけ・`user-notification-triage.md` §3 の必須要件（具体的ユーザーアクション付き）を満たして出す。**この「枯渇後の遷移」を roadmap.md §3 の M-3 定義か user-story-map.md §7 のどちらかに 1 行足すべき**（現状どちらにも書かれていない＝抜け穴）。

---

## 要求2: プランニング時点で縦切り（インフラ/BE/FE）を強制する

### 現状の実測（`SP-1`〜`SP-12` を実際に検証した）

| SP-n | FE要素 | BE/インフラ要素 | 判定 |
|---|---|---|---|
| SP-1 | US-6/US-11 | E-1/E-2/E-5/E-6/E-7/E-8/E-22 | ✅ 縦切り |
| SP-2 | US-1/US-9（ルーティング） | E-4（i18n基盤）/E-9（配色） | ✅ 縦切り（境界寄りだが可） |
| SP-3 | US-16/17/20 | **なし**（SP-1で作った層に乗るだけ） | ⚠️ FEのみ（後述） |
| SP-4 | なし | E-11/E-12（テスト基盤） | イネイブラー単独（既存 C-2 の明示的例外） |
| SP-5 | なし | E-3（キャッシュ） | イネイブラー単独（既存 C-2 の明示的例外） |
| SP-6/7/10 | 多数の US-n | 対応する E-n少なめ | ✅ おおむね縦切り |
| SP-8 | US-2/4/5 | OAuth基盤 | ✅ 縦切り |
| SP-9 | US-22-26 | E-10（レート制限対策） | ✅ 縦切り |
| SP-11 | ドキュメントのみ | README/ADR | 通し確認スプリント（例外） |

**判定**: 既存の `SP-1`〜`SP-12` 自体は歩く骨格の思想（先に全層を1回通し、以降はその上に薄く積む）に照らして概ね妥当。SP-3 が「FEのみ」に見えるのは **違反ではない**（Walking Skeleton は「毎回全層触る」ではなく「最初に全層を通し終えたら以降は必要な層だけ触ってよい」が正しい定義）。SP-4/SP-5 は既存 `C-2`（デモ手順5行で書けるイネイブラーは単独可）が明示的に許可済み。

**本当のリスクはここではない**: 既存 12 本の SP は人間（≒事前設計）が縦切りに割ったから健全なだけで、**「常に供給される」を自動化した瞬間に壊れやすいのは、要求1で新設する SP→Issue 変換や、将来 `SP-13` 以降を人間の設計レビューなしで機械的に追加する場面**。ここで技術レイヤー別（「バックエンド Issue」「フロントエンド Issue」のように）に分割する誘惑が生まれる（消化モードの priority ソートが「小さい Issue から消化」を促すため）。

### 提案: `C-5` を `user-story-map.md` §5.2 に追加

```
C-5: 1つの SP-n は 1つの GitHub Issue として起票する。
     同一 SP-n の内容を技術レイヤー（例:「バックエンドだけ」「フロントエンドだけ」）で
     複数 Issue に分割しない。分割すると、レイヤー単独の Issue は
     C-2（デモ手順5行以内）を単独で満たせない ＝ それ自体が「割り方が間違っている」
     機械的シグナルになる（C-2 を新たに複製しない。C-5 は C-2 の運用上の帰結を明文化するだけ）。
```

**判定手段（機械化）**: `tools/self_review_check.py`（既存・`pre-pr-create-check.sh` が自動実行）に軽量チェックを 1 項目追加する。「PR の Issue 参照 `SP-n` に対し、PR 差分が `app/`（または UI 相当ディレクトリ）と `lib/`・`app/api` 等（データアクセス/インフラ相当）の両方に触れているか」を見る…のではなく、**もっと単純で誤検知しない基準**を推す: 「SP-n の Issue 本文に `layer:frontend` / `layer:backend` のような分割ラベル・分割 Issue が存在しないこと」を Step 0 のプリフライト時点でチェックする（コード差分ヒューリスティックはディレクトリ構成が固まる `SP-1` 完了前は空振りするため、**Issue 起票段階でのガード**の方が確実）。既存イネイブラー単独スプリント（SP-4/SP-5 型）は `type:` に加えて Issue 本文に「イネイブラー単独スプリント（C-2 デモ手順あり）」と明記させ、C-5 チェックの対象から明示的に除外する。

---

## Ready の定義 / Done の定義

**Done は新設不要**: 既に `sprint-development-rules.md` SD-1/SD-2 + `user-story-map.md` §7 運用ルール2（「操作レビュー手順をプレビューURL上で上から実際になぞる」「なぞれない項目が1つでもあれば未完了」）で完全に定義済み。ここに Issue Close のタイミングを 1 行だけ明記すべき: **「SP-n の Issue は、PR 本文に埋め込んだ操作レビュー手順の全項目にチェックが付いた状態でマージされたときにのみ `Closes #N` で自動クローズする」**（コードがマージされただけで close しない、を Issue クローズの機械条件として明文化）。

**Ready は現状 未定義**（`sprint-development-rules-detail.md` §5 の着手チェックリストは「着手した後にやること」であって「着手してよい条件」ではない）。提案:

```
SP-n の Issue が Ready（次のルーティン firing で着手可能）であるための条件:
  [ ] labels に type:feature + sp:{n} が付与されている
  [ ] body が user-story-map.md §5.3 の該当 SP-n セクションへのリンク／参照を含む（本文コピー禁止は §0.1 のまま）
  [ ] roadmap.md §5.5 の順序制約上、先行する SP-n の Issue が全て Closed（またはその PR が state=MERGED）
  [ ] C-5 に違反する分割 Issue になっていない
  [ ] status:blocked が付いていない（付いていれば self-improvement-loop 系の再評価対象で Ready ではない）
```
これを `user-story-map.md` §7 に「運用ルール 9」として追記するのが妥当（既存の同ドキュメントが正本を持つ場所と一致するため新規ファイル不要）。

---

## ルーティン1回 = スプリント1本 か、1フェーズか

**推奨: 「1 firing = 1 セッション」は不変（`session-sprint-rules.md` SSOT）だが、「1 firing = 1 スプリント完了」は前提にしない。** 理由:

1. `SP-1`/`SP-5`/`SP-10` は `sp:8`（上限）。1 firing の N 時間内にテスト・実装・PR・レビュー・マージまで通しで終わる保証はない。
2. `session-compression-rules.md` により **セッションをまたぐ状態は GitHub Issue/PR コメントに残す**ことが既にルール化されている。つまり「未完のスプリントを次の firing が拾って続きをやる」という設計は、このプロジェクトの永続化方針とすでに整合する。
3. したがって、ルーティンの Step 0 プリフライトは **常に以下の分岐**を最初に評価すべき（新規ではなく既存の CP-4 ロック・`pr-review-watcher` のフローの組み合わせで表現できる。新規メカニズム不要）:

```
status:in-progress が付いた SP-n Issue が既にある
  → その Issue に紐づく PR が存在するか確認
      → ある（レビュー待ち/CI待ち） → pr-review-watcher フローで続きを回収（レビュー対応→マージ）
      → ない（実装未着手 or 中断） → 同じ SP-n の続きを実装する（Issueコメントの記録から状態を復元）
  → 無い → 要求1のSP→Issue変換 or Ready 判定済みの次のSP-nに着手（新規スプリント開始）
```

これにより「1 firing = 1 フェーズ（スプリントの一部）」でも「1 firing = 1 スプリント丸ごと」でも**同じロジックで両方に自然に対応できる**——sp:3 の軽いスプリントなら 1 firing で完結し、sp:8 なら複数 firing にまたがる。**「スプリント」という単位をルーティンの cron 間隔に固定しない**のが agile 的に正しい（ベロシティは実測で変動するため、時間で無理に区切ると SD-1/SD-2 の「動作確認できる状態で終わる」完了条件を満たす前に打ち切られ、不完全な成果物が積み上がるリスクが高い）。

**cron 間隔 N の決め方への助言**: `SP-n` の sp 実測中央値（現状見積もりでは `sp:5` 前後、S-0平均`sp:5.8`/S-1平均`sp:5.7`）が 1 firing の作業量の目安になる。N は「典型的な 1 セッションの実処理時間」に合わせるのではなく、「in-progress ロックが付いたまま放置されていないかを CP-3（stale 4時間超）が拾える頻度」に合わせるべき——つまり **N は完了保証の単位ではなく、健全性チェックの再訪頻度**として設計する。

---

## まとめ（1行）
新レーン・新ファイルは作らず、①`user-story-map.md` §7 に SP→Issue変換ルール・Readyの定義・C-5・枯渇後の遷移を追記、②軽量スクリプト1本（Issue起票のみ・副作用限定）を新設、③ルーティンのプリフライトに「in-progress SP-nの継続 or 新規着手」分岐を1ステップ追加、の3点で要求5点すべてに対応可能。矛盾点は「S-2は有限」の1点のみで、既存ドキュメントに未記載の抜け穴として要修正。

### `automation_ops` — 主張
<sub>2026-08-18T09:09:55+09:00</sub>

## automation_ops: 単一ルーティンでのスプリント自走設計（担当: (5)N時間ごとの自走 / (3)専門チーム組成）

### 結論サマリー
- **単一ルーティン設計は「毎回全部やる」ではなく「毎回、決定木で1ブランチだけ実行する」**。既存 R-1（spec-sync プリフライト・衛生・改善消化・週次ゲート）に「開発レーン」を優先順位付きで割り込ませる。新規 SSOT ファイルは作らない（既存の Issue ラベル・PR 本文・`config/backlog_refinement_state.json` パターンを流用）。
- **推奨 N = 2 時間**（cron `0 */2 * * *`）。根拠は §1。
- **専門チーム組成は既定 fan-out（役割分担型）**。discussion-review（議論型）は「PR 300 行超 / breaking / security」の既存 Layer2 自動トリガーと、SD-3 のグレーゾーン判定に限定する（コスト理由）。
- **未解決の重要論点**: 無人ルーティン実行中に SD-3 第2系統（仕様解釈分岐の `AskUserQuestion`）が発生した場合、**同期確認は物理的に不可能**（誰も見ていない）。これは設計として明示的に扱う必要があり、§5 で代替案を提示する（lead / arch_tdd と合意が要る論点として明示）。

---

### §1. N の推奨値と根拠

| 候補 | 判定 | 理由 |
|---|---|---|
| 1 時間 | ❌ 非推奨 | `pr-review-watcher` の監視タイムアウトが 30 分（SKILL.md 監視タイムライン）。1 スプリントの実装+TDD+PR+セルフレビューは 30 分を超えることが常態化しうる。1h 間隔だと「前回セッションがまだ生きている（4h stale 判定未満）」を毎回引いて実質空振りが増える |
| **2 時間** | ✅ 推奨 | 1 firing の中で「実装 → PR → Layer1 セルフレビュー → 自動マージ → publish-sync」を通しで完走できる余白（pr-review-watcher の 30 分監視 + 実装時間を含めても収まる目算）。1 日 12 firing で日次消化 5 件/日（self-improvement-loop 既定）・スプリント複数本の両立が可能 |
| 4 時間以上 | △ | スループットが落ちる。ただし discussion-review（議論型）併用が多いフェーズでは一時的に採用してよい（コスト都合の可変値） |

**cron**: `0 */2 * * *`（UTC。JST 表記が必要な報告では `datetime-rules.md` に従い換算）。既存 R-1 が別スロットで稼働中なら、本ルーティンは **同一ルーティンに統合**（飼い主の明示要求どおり）し、cron は 1 本のみ持つ。

**N を上げ過ぎない理由**: `session-sprint-rules.md` の「1 セッション=1 スプリント」を機能させるには、スプリントが複数 firing にまたがっても **stale 判定（4h）以内に次の firing が資産（PR・ブランチ・コミット）を発見して再開できる** 頻度が要る。N=2h なら 4h stale 判定に対して 2 回のチャンスがあり、1 回落ちても次の firing が拾える。

---

### §2. 単一ルーティンの決定木（1 firing = 1 ブランチのみ実行・上から該当する最初の 1 つ）

```
Step 0（毎回・共通プリフライト）:
  git fetch origin +main:refs/remotes/origin/main
  mcp__github__list_issues(state=OPEN) で全体スナップショット取得（以降の判定はこの1回のクエリを使い回す）

Step 1: [破壊的変更] `lane:claude-code-spec` + `[CC-Sync][破壊的変更]` の open Issue がある
  → claude-code-spec-sync Step1（即対応）。他ブランチより最優先（既存仕様どおり）

Step 2: [自分のPR回収] check_pending_pr_reviews.py --mine --actionable-only が非空
  → pr-review-watcher で継続（レビュー対応/マージ/publish-sync）。新規スプリント着手より優先
    （CP-4: 中途 PR を放置して新規に手を広げない）

Step 3: [進行中スプリントの再開] status:in-progress かつ 本文/コメントに Sprint Planning がある Issue のうち
        updated_at が 4h 超 stale（session-sprint-rules 相当）
  → 前回セッションが力尽きた形跡。git log <branch> と Issue コメント（Sprint Planning・仮定記録）から
    どの SD ステップまで終わっているかを機械的に判定し、続きから再開（後述 §4）
    ※ 4h 未満なら「他セッションが対応中」とみなし触らない（CP-4 二重着手防止）

Step 4: [新規スプリント着手] user-story-map.md §5.3 の次の未着手 SP-n がある
  → session-sprint-rules §2 のプランニング宣言 → sprint-development-rules の 4 規律で実装
    （詳細は §3・§4）

Step 5: [改善Issue消化] status:waiting-claude の type:improvement/type:bug が存在
  → self-improvement-loop 消化モード（既定 5 件/回。本ルーティンでは 1 firing の残り予算次第で件数を絞ってよい）

Step 6: [衛生・監査] 日次スロット未実施（当日 project-sync ログなし）
  → workflow-health-check 軽量版 → project-sync

Step 7: [リファインメント週次ゲート] config/backlog_refinement_state.json の last_refinement_at から 7日超
  → self-improvement-loop 整理モード Step G-1.5〜G-6

Step 8: [spec-sync 検証Issue] `[CC-Sync][検証]` の open Issue が残っている
  → claude-code-spec-sync Step2（1件のみ）

Step 9: 全部空 → no-op。`routine-idle` 通知（slack-notification-rules.md 既存の 1日1回自己抑制に従う）
```

**優先順位の設計原則**: 「今動いている作業を完走させる（Step1-3）」>「新しい価値を作る（Step4 開発）」>「バックログの健全性を保つ（Step5-8）」。これは既存 R-1 の優先思想（破壊的変更 即応 > 通常運用）をそのまま延長し、開発レーンを「通常運用の最上位（Step4）」に置くことで、飼い主要求(5)を満たしつつ CP-3 衛生も飢餓させない設計。

**新規 state ファイルは作らない**: Step1-3 の判定は GitHub Issue/PR の状態（ラベル・updated_at・コメント本文）だけで再計算可能。Step7 のみ既存 `config/backlog_refinement_state.json` パターンをそのまま使う（新規ファイルではなく確立済みパターンの再利用）。

---

### §3. 開発レーン（Step4）の内部手順とチーム編成の記録先

```
4-1. 対象 SP-n を選ぶ: user-story-map.md §5.3 を読み、未着手の最小番号の SP-n を選ぶ
4-2. Issue 作成 or 既存 Issue に status:in-progress 付与（CP-4 最初のアクション）
4-3. Sprint Planning コメント投稿（session-sprint-rules.md §2 の書式そのまま）に
     「編成」欄でチーム構成を確定して記録する（新規欄を増やさない。既存書式の '編成:' 行がそのまま
     チーム編成の記録先 = 追加 SSOT 不要）:
       編成: 実装(general-purpose/sonnet) + テスト先行(general-purpose/sonnet) + Layer1セルフレビュー(code-review skill)
     大型 SP（sp:5 以上・複数ファイル）は fan-out 並列（agent-team-summary.md のファイル非重複分割ルール厳守）。
     小型 SP（sp:1-3）は単独実行（チーム化のオーバーヘッドが割に合わない）。
4-4. sprint-development-rules.md の SD-1〜SD-4 をそのまま実行（TDD Red→Green→Refactor、プレビューURL、
     曖昧点の扱いは §5 参照）
4-5. PR 本文: Sprint Goal / sp:N / Session-Id / プレビューURL / 参照要件ID（既存必須項目そのまま）
4-6. pr-review-watcher へ継続（Layer1 セルフレビュー → マージ → publish-sync）
     ※ ここで firing のセッション予算が尽きたら、コミット済みの内容とIssueラベル(status:in-progress)
        だけが生き残る。次の該当 firing は Step2（自分のPR）or Step3（stale再開）で拾う
```

**専門チーム組成 = discussion-review を毎回起動しない**: agent-team-summary.md の 2 モード区分に従い、開発レーンの既定は **役割分担型 fan-out**。議論型（discussion-review）を使うのは次の 2 ケースのみ:
1. 既存の Layer2 自動トリガー（`discussion_review_trigger.py`: diff≥300行 or `type:security`/`type:breaking-change`）が発火した PR レビュー
2. SD-3 のグレーゾーン判定（§5 で詳述）

理由: discussion-review は Opus 系で高コスト（agent-team-summary.md 記載）。N=2h・1日12 firing の高頻度ルーティンで毎回議論型を回すとコストが線形に膨張し、CP-5（ミッション貢献最大化）に反する。

---

### §4. 冪等性・再入・中断復帰（Step3 の詳細）

**検知**: Step3 の stale 判定は `status:in-progress` ラベル + `updated_at` の 4 時間超過（`session-sprint-rules.md` §1 が定義する既存の「対象がないセッションは no-op」原則と、CP-3 の Stale Issue 検出ロジックをそのまま流用。新規しきい値を作らない）。

**再開手順（擬似コード）**:
```
target_issue = stale な in-progress Issue（Sprint Planning コメントあり）
branch = target_issue に紐づく作業ブランチ（Issue 本文 or 直近コミットの Issue番号紐付けで特定）
git fetch → git log origin/<branch> --oneline を読む

if 対応する open PR が存在:
    → Step2 と同じ扱いに合流（pr-review-watcher で継続。実装は既に済んでいる）
elif ブランチに未 push のコミットがある（同一セッション内でしか起きないので通常は無い。
     ただし L-100 型の破壊が起きていないかだけ確認）:
    → git push -u origin <branch> してから PR 作成へ
elif ブランチ自体が存在しない（前回が Sprint Planning 投稿直後に力尽きた）:
    → Issue コメント（Sprint Planning・仮定記録）を読み直し、4-2 以降を最初からやり直す
       （git 資産が無いのでゼロから。ただし Planning のゴール・編成は再利用し、
        二重の判断コストを避ける）
```

**二重着手防止**: Step3 は「4h 未満は他セッションが対応中とみなし触らない」を厳守。これは `session-concurrency-rules.md` レイヤー2（Issue ラベル論理ロック）そのもの。加えてレイヤー6（`--mine` の Session-Id トレーラー）で「自分（＝過去の同一ルーティンの別 firing）が作った PR か」を判定し、他ユーザー/他セッションの PR には触れない（`active_session: true` 除外は既存 pr-review-watcher の挙動を継承するだけで新規実装不要）。

---

### §5. 【要合意】無人実行中の SD-3 第2系統（仕様解釈分岐）の扱い

`sprint-development-rules.md` SD-3 は「仕様解釈が2通り以上あり成果物が変わる場合は `AskUserQuestion` で確認する」と定めるが、**ルーティン起動セッションには応答するユーザーがいない**（cron 起動・エフェメラルVM）。`AskUserQuestion` は事実上ブロックしたまま firing のセッション予算を溶かすだけになる。

これは `user-confirmation-minimization.md` が定める「確認してよい第2系統」の **実行環境上の前提が崩れるケース** であり、ルール変更ではなく **運用上のフォールバック手順の欠落** として扱うべき論点。以下を提案（lead / arch_tdd の合意を求める）:

```
SD-3 グレーゾーンに遭遇（無人 firing 内）:
  1. まず Skill(discussion-review) に「解釈A vs 解釈B」を精査させる
     （SD-3 は本来ユーザーの好みを問うものだが、複数エージェントの反証込み議論で
      「どちらがプロダクト原則・既存ドキュメントとより整合するか」を判定させることはできる。
      対象1件でも起動可・self-improvement-loop Step G-6 と同じ扱い）
  2. 議論の結論を「推奨案」として採用し実装を進める
  3. PR 本文と Issue コメントに
     「仮定: {曖昧だった点} → {採用した解釈}（根拠: 無人実行のため discussion-review 精査結果を採用。
      ユーザー判断で訂正可）」と明記（sprint-development-rules-detail.md §3.2 の書式を流用、
      「無人実行のため」を理由に追加するだけ）
  4. 影響が大きい/後戻りコストが高いと judge された場合のみ、実装を進めずに
     `status:waiting-user` Issue を起票し推奨案を添えて次サイクルへ委譲する
     （waiting-user-handler が後続で拾う。A-1〜A-6 には該当しないため @mention はしない）
```

**この提案の位置づけ**: SD-3 のテキストそのものを書き換える提案ではなく、「無人実行という新しい実行モードに対して、どの既存メカニズム（discussion-review / waiting-user-handler）で代替するか」という **運用手順の穴埋め**。ドキュメント変更が必要なら `sprint-development-rules-detail.md` への追記 1 節で足りる（新規 SSOT 不要）。

---

### §6. 失敗モード別の自己回復

| 失敗モード | 検知 | 次回 firing の回復経路 |
|---|---|---|
| プレビューURL出せない | PR本文に「プレビューURLなし」明記（sprint-development-rules-detail §1.3 既定動作） | Step2（自分のPR回収）で pr-review-watcher が継続。A-6相当なら waiting-user Issue 化済みのはずなので Step5 の対象にもなる |
| CI赤 | pr-review-watcher Step2 が検知 | Step2 で継続対応。放置なら次々回 firing でも同じ Step2 が拾う（PRが閉じない限り自然回復） |
| A-4 サーキットブレーカー発動 | 修正サイクル2回超 | 該当 Issue/PR は `status:blocked` 付与（既存パターン）。Step3/Step4 の対象クエリから **除外**（`status:blocked` は除外条件に必ず含める。self-improvement-loop の除外リストと同じ書式）。waiting-user 通知は user-notification-triage.md の A 区分基準どおり必要時のみ |
| セッション圧縮（コンテキスト95%） | PostCompact フックが自動コミット | 元々ephemeralなので特別対応不要。圧縮後もそのfiring内で継続。firing自体が尽きたらStep3の再開経路に合流 |
| スプリントが1firingに収まらない | Step3 の stale 判定（4h） | §4 の再開手順。`user-story-map.md §5.4` の分割規則（SP を末尾番号で分割）にも従い、1スプリントが恒常的に収まらないなら Issue 側で分割する判断も Step4 着手時に検討する |
| Step4/5 が同時に「常に空でない」状態が続き衛生Stepに手が回らない | Step6/7 の実行ログが7日以上ない | 既存 CP-3 のアラート機構（project-sync）に委ねる。決定木の優先順位はハードコードだが、Step6/7 が長期未実行なら `docs/rules/` 側で優先順位の見直しを別Issueで提起する（本設計のスコープ外） |

---

### §7. 既存レーンとの同居 vs 分離（結論: 同居・優先順位で調停）

飼い主要求が「単一のルーティン設定内で」と明示しているため、**開発レーンを既存 R-1 と同一 cron・同一プロンプトに統合**する。分離案（開発専用ルーティンを別 cron で新設）は要求と矛盾するため不採用。同居の代償（開発が衛生・改善消化を圧迫するリスク）は §2 の優先順位設計（衛生Step6/7を「当日未実施なら」条件で必ず一度は滑り込ませる）で緩和する。

## ラウンド 2

### `rules_governance` — 反論
<sub>2026-08-18T09:13:26+09:00</sub>

# Round 2: 具体案の既存ルール資産との整合検査

## A. 既存ルールとの矛盾

### agile_flow 案（user-story-map 追加）
- ✅ 矛盾なし。C-5「1SP-n = 1Issue」は `sprint-development-rules.md` SD-4 と整合（「ドキュメント読んで自律実行」という前提下では SP-n は既に一意に定義されている）
- ⚠️ Ready定義 9 の追加は **情報量過剰**（§C 参照）

### arch_tdd 案（TDD コミット分離・E2E 対応・縦切り判定）
- ✅ TDD コミット分離（test: red → feat: green）は**実装手段**のため、SD-3 の確認対象ではなく自律実行対象（sprint-development-rules.md §3 の「実装手段は聞かずに決める」と整合）
- ✅ E2E を SP-n に対応（操作レビュー手順を test.step() で写す）は SD-2（TDD・操作レビュー手順が E2E テストと一致）の強化で矛盾なし
- ✅ 縦切り判定（check_tdd_commit_order.py）は **助言レイヤー**（pre-pr-create-check.sh フック内）で既存の scan_dangerous_patterns.py と同じ位置づけ、矛盾なし

### automation_ops 案（決定木・step0-9・無人 SD-3 は discussion-review 代替）
- ✅ 優先順位（破壊 > 自分の PR > 進行中再開 > 新規 > 改善 > 衛生 > リファインメント > spec検証）は既存 R-1 の思想と整合（優先度の新規追加ではなく既存順序の延長）
- ✅ Step3 の stale 判定（4h）は `session-sprint-rules.md` の既定（対象がないセッションは no-op）を流用、矛盾なし
- 🔴 **無人 SD-3 を discussion-review で「代替」する提案は、SD-3 ルール自体の実行モードの変更**。§5 で「ユーザーがいない無人実行」という **実行環境上の新しい制約** を前提にしたため、「代替ではなく**例外運用**として明示的に許可するルール追加」が要る（§C 参照）。新規ルールファイルではなく `sprint-development-rules-detail.md` §3.3 への追記で足りるが、**現行テキストには「無人実行での SD-3 グレーゾーン」という言及がなく、追記が必須**

---

## B. コミットメッセージ規約との衝突

| 規約 | 既存慣行 | arch_tdd 提案 | 判定 |
|------|---------|-------------|------|
| **形式** | `{type}: {内容} #{issue}` 例: `docs: prd.md を作成 (#10)` | `test: red - X` / `feat: green - X` のような inline 記述 | ⚠️ 衝突 |
| **実装 type** | `feat:` / `fix:` / `docs:` / `chore:` | 新規 `test:` prefix、さらに同一 commit でなく **別々のコミット** に分割 | ✅ 整合 |
| **詳細 convention** | 「何をしたか」を 1 文。Issue 番号を末尾に | 「Red → Green」の段階を `-` で並べ込む | 🔴 **衝突** |

**衝突の内容**: 既存慣行は「1 commit = 1 変更の原始単位」「Issue との紐付けは commit 単位」（git log の SSOT）。arch_tdd 提案は「test: red commit」「feat: green commit」の 2 段階を 1 つの「論理的な機能」として view することを意図している。これは **TDD を commit 単位で可視化する** という目的は良いが、既存の「commit = git log の解釈単位」との認識がずれている。

**回避案**:
- ❌ 「`test:` type を新規追加」は実装手段。自律実行（確認不要）
- ✅ **提案の修正**: コミットメッセージは既存慣行を維持し、「Red/Green の分離」は commit の **整序順序**（git worktree で pre-commit fook が強制）として記録する。メッセージは両方とも `feat: X` で同じ内容を指す→差分が見えると「あ、TDD で Red/Green が分かれている」と読む。`check_tdd_commit_order.py` がそれを検証する設計に変更

---

## C. 記述先の割り当て

| 案 | 対象 | 推奨先 | 理由 | Hot 層影響 |
|---|------|--------|-----|----------|
| **agile_flow: C-5 + Ready定義** | user-story-map.md の SP-n 運用 | **(a) user-story-map.md §7「運用ルール」に追記** | 既にそこが SP-n 運用の SSOT。新規ファイル / Hot層ルール不要 | なし |
| **agile_flow: sprint_backlog_sync.py** | SP-n → Issue 起票スクリプト | **(d) 新規スキル `.claude/skills/sprint-backlog-sync/SKILL.md`** | tools ディレクトリは「援助ツール」。意思決定・ユーザー確認判定を含むロジックはスキル化（self-improvement-loop の一部機能として呼び出す）| なし（スキルは ESSENTIAL_RULES 対象外） |
| **arch_tdd: .dependency-cruiser.cjs + lint:arch** | 依存関係 linting | **(a) 既存 .eslintrc.json / CI.yml への設定追加** | ツール・CI ゲート追加であり、ルール変更ではない | なし |
| **arch_tdd: check_tdd_commit_order.py** | TDD commit 検証 | **(a) tools/ 配下に新規スクリプト + pre-pr-create-check.sh フックに組み込み** | 既存の scan_dangerous_patterns.py と同じ位置づけ（助言レイヤー）| なし |
| **arch_tdd: E2E ↔ 操作レビュー手順の 1-to-1 対応** | test.step() による対応ルール | **(a) sprint-development-rules-detail.md §2.3 へ追記** | SD-2（E2E テストと操作レビュー手順一致）の詳細化。既存ファイル | なし |
| **arch_tdd: 縦切り判定（check_tdd_commit_order の一部）** | PR 縦切り確認 | **(a) check_tdd_commit_order.py 内に含める** | 新規スクリプト内部の機能。SSOT 不要 | なし |
| **automation_ops: 決定木 Step0-9** | ルーティン実行フロー | **(a) 新規 Warm ルール docs/rules/sprint-cycle-routine-spec.md**（symlink しない） | 実行フロー仕様は「全セッション常駐」を要しない。実装セッション内のみで参照（該当スキル / cron プロンプトが Read）。タスク依存 SSOT | なし（Warm） |
| **automation_ops: チーム編成の Sprint Planning コメント記録** | チーム構成記録先 | **(a) session-sprint-rules.md §2 の「PR 本文に必須」内容に「編成欄」として追記** | 既存の「Sprint Goal / sp:N / Session-Id」と同レベルの必須項目化。既存ファイル | なし |
| **automation_ops: config/backlog_refinement_state.json 流用** | Step7 のリファインメント周期管理 | **(a) 既存ファイル流用。新規スキルなし** | 確立済みパターンの再利用。SSOT 不要 | なし |
| **automation_ops: 無人 SD-3 を discussion-review で代替** | 無人実行時の仕様解釈分岐処理 | **(b) sprint-development-rules-detail.md §3.3「無人実行モードでの SD-3 例外処理」を新規追記** | SD-3 ルール本体（Hot）ではなく詳細版（Warm）に。ただし **「どの実行モード（対話 vs 無人）で何が変わるか」を明示的に記述する必要あり**（§5 で後述） | なし（詳細は Warm） |

**Hot 層総計**: 3 案共通で新規 Hot 層ファイルなし。既存 Hot 層の `sprint-development-rules.md` / `session-sprint-rules.md` には追記なし（既定） → **予算圧迫なし**（+30KB 余地は使わない）

---

## D. ルーティンプロンプト本体の置き場所

`automation_ops` の §7 で「単一ルーティン」と明示し、cron `0 */2 * * *` に貼るプロンプト文を **どこに保管するか**。本ベース（kai-kou/claude-code-repository-base）の先例を調べると、R-1（spec-sync プリフライト・衛生・改善消化・週次ゲート）は「開発リポジトリの運用メモ」に定義され、**gem-hunter 側には実体がない**（実行スキルのみ）。

**gem-hunter 側の妥当な置き場所**:

```
config/routines.yaml（新規・SSOT）
  - name: sprint-cycle-routine
    description: スプリント開発 N 時間ごと自走
    schedule: "0 */2 * * *"
    cron: JST 換算 `0 2,4,6,...,24時` or その他 TZ 記録
    prompt_file: docs/routines/sprint-cycle-routine-prompt.md  # 実体
    steps:
      - description: step0 プリフライト
      - description: step1 破壊的変更対応
      ... 
      - description: step9 no-op
    env_vars:
      SPRINT_CYCLE_DEBUG: ${CLAUDE_CODE_REMOTE}  # クラウド判定 log 用
```

**prompt_file の実体**: `docs/routines/sprint-cycle-routine-prompt.md`

```markdown
# Sprint Cycle Routine プロンプト
## 実行コンテキスト
- 実行契機: `0 */2 * * *`（UTC。JST では調査で換算）
- 実行セッション: ephemeral（毎回新規セッション）
- 監視ユーザー: なし（無人実行・AskUserQuestion は即ブロック・Step5参照）
- タイムアウト: セッション標準（180分想定）

## 入力データ準備
- git fetch origin +main:refs/remotes/origin/main
- mcp__github__list_issues(state=OPEN) スナップショット取得（以降の分岐全て、この 1 回のクエリ結果を使い回す）

## 決定木（最初の 1 つだけ実行）
[Step0-9 の詳細...automation_ops §2 をコピー]

## 事後処理（毎回）
- git fetch --prune
- コメント投稿: Slack `routine-fired` 通知 + step N の結果要約
```

**既存 R-1 との関係**:
- R-1 = 開発リポジトリの運用ポリシー（汎用ベース向け）
- Sprint Cycle Routine = gem-hunter 専用の新規定期ワークフロー（`docs/routines/` に記録）
- 両立可能（R-1 は引き続きベースリポジトリ側で管理。gem-hunter は自分のルーティンのみ `config/routines.yaml` で宣言）

---

## E. `improvement-lane-map.md` の更新要否

automation_ops の 決定木 Step4「開発レーン」の新設により、既存の 3 レーン（改善 Issue / 振り返り / 監査・衛生）に「スプリント開発」が加わる。

**更新要否**: ✅ 必要。ただし **既存テーブル（§1）に行を追加するのではなく、§1 直後に「第 4 レーン」として分離記述すべき**。理由は:

1. 既存 3 レーンは「自動検出・自動処理（スキル）」の境界を示す表
2. 開発レーンは「定期ルーティンの決定木 Step4」として、**優先順位・スケジューリング・人間の着手判断**に左右される（自動検出では決めない）

**追加行の例**:

```markdown
## 第 4 レーン（新規・ルーティン開発レーン）

| レーン | 駆動 | 担当フェーズ | 主な起動 |
|--------|------|------------|---------|
| **スプリント開発** | Sprint Cycle Routine Step4 | Issue 選定 → 実装（TDD） → PR → Layer1 → マージ | 毎 2 時間（cron `0 */2`）・ただし優先順位（Step1-3）により実際の着手可否が決まる |

## レーン間の受け渡し（追記）

スプリント開発レーン（Step4）に到達するまでの分岐判定：
- Step1-3 で「ブロッカー / 進行中 PR / 進行中スプリント」を全て消化してから初めて Step4 の開発着手判定に進む（優先順位固定）
- 開発完了後のマージ → publish-sync は既存の `pr-review-flow-summary.md` フローのまま
- **未完のスプリント（1 firing で終わらなかった）は `status:in-progress` + branch で次の firing へ自動受け渡し**（Step3 の再開メカニズム）
```

---

## まとめ

✅ **矛盾**: なし（SD-1〜4・CP-6・A-1〜6 全て整合）
⚠️ **追記・例外処理の必須**: 無人 SD-3（discussion-review 代替）には `sprint-development-rules-detail.md` §3.3 の新規追記が必須
✅ **新規ファイル**: なし（既存ファイルへの追記 + Warm 層スクリプト仕様）で対応可能
✅ **Hot 層圧迫**: なし（+0KB）

### `agile_flow` — 反論
<sub>2026-08-18T09:14:50+09:00</sub>

# agile_flow の反論・回答（ラウンド2）

## 論点1（最大の争点）: 要求2の "必ず" を無視していないか

### 反論を受け止める（部分的に譲歩）
round1 の「Walking Skeleton だから以降は必要な層だけでよい」は **一般的なソフトウェア設計論としては正しい**が、それだけでは飼い主が明示的に選んだ「必ず」という語を説明しきれていない。この語は恐らく **過去の失敗パターン（バックエンドだけ・フロントエンドだけの Issue が作られて画面で確認できなかった経験）への反応**として置かれている。round1 の反論はその文脈を無視して一般論で押し切っていた点は認める。

### それでも SP-3/SP-4/SP-5 の再分割はしない（結論を1つ選ぶ）

**選ぶ**: 現行分割を維持し、`C-2`（デモ手順5行以内で書けるイネイブラーは単独可）を「縦切りの実体」として運用する。
**選ばない**: 再分割案（SP-3にBE要素を足す・SP-4/5を隣接機能スプリントへ統合する）。

**再分割を選ばない理由（具体的）**:
1. SP-3（一覧⇔詳細往復）に人為的な BE 作業を足すのは、**存在しない必要性を作り出す逆 YAGNI**（`CLAUDE.md`「1箇所しか使わない抽象化を先回りで追加しない」の精神と同型の過剰設計）。SP-1 で作った層に乗るだけで機能が完成するなら、それは正しい縦切りの帰結（骨格を1回通した効果）であって欠陥ではない。
2. SP-4/SP-5 を機能スプリントへ統合すると、`user-story-map.md` 自身が明記する理由（「回帰を検知できない状態で機能を積むと積むほど壊れる」）に反し、**CI・キャッシュの確立を遅らせる**。統合は縦切り原則より上位の設計判断（`D-9`：後戻りコストが高いものを先に固定する）を壊す。
3. SP-3/4/5 はいずれも既に `C-2`（5行デモ）を満たすと `user-story-map.md` 自身が明記済み＝ **「操作して確かめられない」わけではない**。争点は「画面上のUI変更を伴うか」であって「確認可能か」ではない。

**しかし「押し切る」だけでは不十分**なので、以下で穴を塞ぐ:

- **既存 SP-1〜SP-12 は再論しない**（`user-story-map.md` §0.2「一度振ったIDは変更しない」・スコープ外）。
- **未来の自動生成分（round1 で私が提案した SP→Issue 変換スクリプト・将来の `SP-13` 以降）にだけ、文字通りの読み方を適用する**: 新しいイネイブラー単独スプリントを **自動で** 起票することを禁止し、`C-2` 例外を主張する Issue は必ず人間相当の精査（`Skill(discussion-review)` 1件でも起動可・`self-improvement-loop` Step G-6 と同じ確信度運用）を経てから起票する。これを `user-story-map.md` §5.2 に「`C-2` 例外の新規適用は SP-1〜SP-12 の既存 2 件（SP-4/SP-5）に限る参考実装とし、それ以降の新規イネイブラー単独スプリントは意見1のSD-3手続きを経る」という1文として追記する。

### SD-3 第2系統に該当するか

**該当する。ただし対象は未来の自動生成分のみ**。「文字通り全SPが3層」と「Walking Skeletonの例外あり」は解釈が2通りあり、選択で**将来の自動生成バックログの構造そのもの**が変わる（`user-confirmation-minimization.md` §3 item0(c)）。既存 SP-1〜SP-12 については解釈確定は不要（スコープ外＝既に固定済み）。

**確認のタイミングは1回だけ**: 毎スプリントで聞くのではなく、**ルーティン初回稼働前の設計確定時点**で `AskUserQuestion` を1回投げる。選択肢は2つ、推奨明示（`user-confirmation-minimization.md` §3 item8 の書式）:
```
(推奨) A: 既存 SP-4/SP-5 は先例として維持し、それ以降の新規イネイブラー単独スプリントは discussion-review 精査を必須化する
B: 今後は例外なく、すべての新規スプリントが画面のUI変更を含むことを必須化する（イネイブラー単独は今後一切禁止）
```

---

## 論点2: `S-2` 有限問題は automation_ops の Step4→Step5 フォールバックで解消するか

**部分的に解消するが、残る**。automation_ops の設計は「ルーティンが止まらない」ことは保証するが、**「M-3 到達＝公開判断ゲート(M-4)を検討すべき時期」という飼い主向けの一度きりのシグナルを一切発しない**。Step4 が空になった firing は黙って Step5（改善消化）へ流れるだけで、`roadmap.md` M-4/M-5 が要求する `RK-1`（ペルソナ検証・n=0）・`R-8`（GitHub利用規約確認）・`R-6`（運用コスト試算）のような **Claude が自己生成できない入力**の存在に飼い主が気づく機会が失われる。改善消化は無限に続けられる（在庫は自己増殖する）ため、この状態のまま「ルーティンは元気に動いている」ように見え続け、**プロダクトを公開するかどうかの意思決定だけが永遠に先送りされる**リスクは消えない。

**1つに決める**: automation_ops の Step4 に以下を1行追記する。

```
Step4 の候補（user-story-map.md §5.3 の未着手 SP-n）が空 かつ
`[Milestone] M-3 到達` という表題の Issue が既に存在しない（open/closed 問わず）
  → user-notification-triage.md §3 の必須要件（具体的ユーザーアクション・境界・
    取らない場合の結果・Claude側の状態）を満たした Issue を1件だけ起票し、A-5相当として@mentionする
  → 以後はこの Issue の有無で判定するため、新規 state ファイルは不要（automation_ops 自身の
    「GitHub状態だけで再計算可能」という設計原則と一致する）
  → 起票後は通常どおり Step5 へフォールバックし続ける（毎回通知しない）
```
これは新規ファイルなし・1 firing 内の追加コスト最小（Issue 存在チェック1回）で automation_ops の設計思想を壊さずに私の懸念を解消できる。

---

## 論点3: 「1 firing = 決定木の1ブランチ」設計は「1 firingにスプリントを固定しない」と整合するか

**整合する。むしろ automation_ops の §3/§4（Step3 のstale再開・冪等復元）は round1 で私が「新規メカニズム不要」と述べた分岐を、私よりずっと具体的に実装可能な形（git log 読解・ブランチ復元擬似コード）に落とし込んだものであり、対立ではなく round1 案の詳細化だと理解した。** 「スプリントが3〜4 firingに分断される」こと自体は SD-1 に抵触しない: SD-1 の完了条件は「マージされたPRにプレビューURLがあり、操作レビューを完走できる」ことであって「1 firingで完結する」ことではない。中間状態（実装途中・PR未マージ）がSD-1を満たさなくても違反ではない（完了条件はマージ時点にのみ課される）。

**それでも1点、飢餓（starvation）リスクを指摘する**: 決定木が「上から該当する最初の1つだけ実行」する設計は、**Step2（自PR回収）が毎回何かしら存在し続けた場合、Step4（新規スプリント着手）が実質的に永久に呼ばれない**という優先度逆転を構造的に許してしまう（CIの不安定さやレビューコメントの往復が続く限りStep2が埋まり続けるケースは現実的にありうる）。automation_ops 自身が §6 で Step6/7（衛生・リファインメント）に対してのみ「7日以上未実行ならCP-3アラート」を用意しているが、**Step4に対して同種のセーフガードがない**。

**提案**: Step4 にも同型の飢餓検知を追加する。「Ready 判定済みの次SP-nが存在するのに、直近 N 回（例: 3日相当）Step4 が一度も実行されていない」場合、Step2 の処理を1firing分だけ後回しにしてでもStep4を1回差し込む（"エージング"によるスケジューリング。新しいIDやファイルは不要、既存の`updated_at`ベースの判定パターンの流用）。

**副次的に確認した事実（本論点の直接対象ではないが記録）**: `docs/03_design/infrastructure/infrastructure-design.md` §8.1 によれば、プレビュー環境ではOAuthを無効化する設計オプションが有力とされている。これが採用される場合、`SP-8`（ログイン機能）の操作レビュー手順「ログインする→レート枠が切り替わる」はプレビューURL上で**そもそも実行不可能**になりうる。これはfiring分断とは独立に SD-1 の「プレビューURLで操作レビュー手順を完走できる」を脅かす具体的リスクなので、arch_tdd/automation_ops 側での設計確定が必要（本論点の担当外だが看過できないため記録のみ残す）。

---

## 論点4: 新規ファイルの要否と置き場所

**round1 の3点（SP→Issue変換ルール・Readyの定義・C-5・在庫枯渇の遷移）は `user-story-map.md` §7 追記のみで維持する**（この結論は変えない。いずれも既存正本の管轄内で、量も小さい）。

**ただし訂正する**: round1 では「新規ファイルなし」で押し切ったが、automation_ops が示した **決定木（Step0〜9・§1〜§7 の実行ロジック全体）** は私の round1 のスコープ外にあった大きな実行ロジックであり、これは `user-story-map.md` の管轄（仕様の正本）でも Hot 層ルール（恒常原則）の管轄でもない。**Hot 層に置くべきではない**（rules_governance の「+30KB余地」は恒常原則の余地であって、cron間隔やStepの優先順位のような**運用調整で頻繁に変わりうる実行ロジック**をここに置くと、変更の度に `check_rules_sync.sh` とHot予算監査という重い手続きが必要になり、CP-6の軽量運用と逆行する）。

**選ぶ**: 新規スキル `.claude/skills/sprint-cycle-router/SKILL.md`（Warm層相当・実行ロジック専用）を1本作り、決定木の実体をそこに置く。ルーティン（`create_trigger` の `prompt`）自体は「`Skill(sprint-cycle-router)` を実行して」程度の短いトリガー文言に留める。

**理由**: これは新しいパターンの発明ではない。`self-improvement-loop`・`pr-review-watcher`・`project-sync`・`claude-code-spec-sync`・`workflow-health-check` の**全既存パイプラインが同じ構造**（ルーティンのpromptは短いトリガー、実行ロジックはSKILL.mdに常駐）を採っている。automation_opsの決定木だけをルーティンの`prompt`本文に直接書き込む、あるいはHot層ルールとして常駐させるのは、**この既存アーキテクチャから逸脱する側**であり、逸脱こそがSSOT分散のリスクを生む。新規スキルはこの既存パターンへの追従であって増殖ではない。

**未確証の傍論（確度を下げて記録）**: 自分のツールリストには project 非依存の `next`（「PRレビュー対応→進行中Issue再開→waiting-claudeIssue→プロジェクト固有バックログ」の優先度判定）という組み込みスキルが見えるが、`.claude/skills/` 配下には存在しないため、本プロジェクトのルーティンから同じ形で呼べるかは未確認。automation_opsの決定木と概念的に重なる可能性があるため、実装前に一度だけ確認する価値はあるが、確証がないため設計の前提には使わない。

---

## まとめ（1行）
論点1は「必ず」を無視していたと部分的に譲歩しつつ既存SP分割は維持、未来の自動生成分のみSD-3確認を1回課す。論点2はautomation_ops案に1行（M-3到達Issue起票）を追加すれば解消。論点3は基本整合（対立ではなく詳細化）だがStep4の飢餓防止セーフガードが1点欠けている。論点4はround1の3点は維持しつつ、automation_opsの決定木は新規スキル`sprint-cycle-router`（既存全パイプラインと同型のWarm層置き場所）に置くべきと訂正する。

### `arch_tdd` — 反論
<sub>2026-08-18T09:15:19+09:00</sub>

## 0. 読んだもの

`infrastructure-design.md` §3（`INF-6`〜`INF-14` ランタイム契約）・§6（3 層キャッシュ）・§8（環境構成・§8.1 プレビュー×OAuth 相性問題）。加えて他 3 名の round 1（`rules_governance` の既存資産棚卸し、`agile_flow` の SP 実測表と `C-5` 提案、`automation_ops` の決定木・N=2h・SD-3 無人化対応）を読んだ。

---

## 1.【最大の争点】3 層判定に「インフラ」が抜けていた誤りを認め、再定義する

### 1.1 誤りを認める

round 1 の「縦切り = diff が `app/` または `usecases/` に到達している」は **`src/infrastructure/`（データアクセス/キャッシュのアダプタ層＝クリーンアーキテクチャ用語の infrastructure）と `INF-n`（インフラ契約＝デプロイ・CI・環境変数・プレビュー）を同じ言葉のまま混同していた**。前者はコードの一層、後者は運用基盤の契約であり、飼い主の要求 2「インフラ・バックエンド・フロントエンド」の「インフラ」は後者を指している。ここを別軸として立て直す。

### 1.2 再定義（ディレクトリ・成果物レベル）

| 層 | 判定対象（diff に含まれるか） | 対応する既存 ID |
|---|---|---|
| **フロントエンド** | `app/**/page.tsx` / `app/**/layout.tsx` / `src/ui/**` | `E-8` / `NFR-3` |
| **バックエンド** | `app/**/route.ts`（Route Handlers）/ `src/usecases/**` / `src/domain/**` / `src/infrastructure/**`（アダプタ実装） | `E-2` / `E-5` / `TR-4` |
| **インフラ** | `.github/workflows/**`（`E-12`）/ プレビューデプロイ設定（`E-22`）/ `.env.example` や環境変数宣言の追加（`INF-9`/`INF-15`）/ `next.config.*` のうちランタイム契約（`INF-6`〜`INF-14`）に関わる変更 | `E-12` / `E-22` / `E-6` |

### 1.3 二択への回答: **例外規定を書く（再分割はしない）**

再分割を却下する理由は 2 つ。

1. `SP-4`（テスト基盤）・`SP-5`（キャッシュ）に **偽の FE/インフラ タッチポイントを捏造して縦切りに見せかける** ことになり、`intent-gate-rules.md` 権威順の最上位（`user-story-map.md` §5.2 が明示的に「`C-2` を満たすイネイブラー単独スプリント」と認めている＝仕様）に対する裏切りになる。
2. `agile_flow` が round 1 で実測した表（`SP-3` は FE のみ・`SP-4`/`SP-5` はイネイブラー単独）が示す通り、**歩く骨格（Walking Skeleton）の定義そのものが「最初に全層を1回通したら、以降は必要な層だけ触ってよい」**（`user-story-map.md` の思想）。「毎回 3 層すべて」を機械強制すると、この思想と正面衝突する。

**修正した適用範囲**: 「必ず 3 層を含む」を **`SP-1`（歩く骨格の最初の確立・実際に FE/BE/インフラすべてを新規に立ち上げる唯一のスプリント）にのみ厳格適用**し、それ以外は `agile_flow` の `C-5`（技術レイヤー別に Issue を分割しない）を全 SP に厳格適用することで代替する。**分割さえしなければ、必要な層は自然に同じ Issue に収まる**ため、「3 層を含む形で計画される」という要求 2 の実質（技術レイヤー別バックログを作らない）は `C-5` 単独で満たせる。3 層すべてのタッチは目的ではなく手段であり、目的（技術レイヤー別に分割してレビュー不能な断片を積まない）は `C-5` が直接満たす。

**機械検証**: `tools/self_review_check.py` に 1 関数を追加（新規ツールではなく round 1 で既に提案した拡張と同じ関数群にまとめる。§5 で確定）。

- `SP-1` の PR: 上記表の 3 層すべてに diff が無ければ **blocking**（歩く骨格が成立していない）
- `SP-2`〜: enabler-only（Issue の `含む` が `E-n` のみ）は exempt。それ以外（`US-n` を含む機能スプリント）は 3 層中 2 層以上タッチしていなければ **warning**（block しない。`SP-3` のように前スプリントで基盤が整い今回はインフラ変更が不要な正当ケースがあるため）
- **`C-5` 違反**（同一 `SP-n` の分割 Issue・`layer:frontend`/`layer:backend` ラベル）は `SP` を問わず **blocking**（`agile_flow` 案どおり、Issue 起票段階＝プランニング時点でガードする方が確実という判断に同意する）

---

## 2. TDD 機械検証: worktree 全コミット実行案を自己反論し、2 段構成に縮小する

### 2.1 コスト自己反論を認める

`automation_ops` の N=2h・1 日 12 firing 前提では、**コミットごとに worktree checkout + `npm test`** はスプリント 1 本あたり増分数 × 12 firing/日 で線形に膨張し、CI 時間予算を圧迫する。round 1 案はコスト計算を欠いていた点で不十分だった。

### 2.2 縮小案（2 段構成）

**Tier 1（毎コミット・静的・CI 不要）**: `test:`/`feat:` の交互パターンと、diff のパスプレフィックス（`test:` はテストパスのみ・`feat:` は非テストパスのみ）を **`git diff --name-only` のみで**判定する。テスト実行を伴わないため実質ゼロコスト。`pre-pr-create-check.sh` フック内（ローカル・PR 作成前）で実行し、**CI コストを一切使わない**。

**Tier 2（PR ごとに 1 回だけ・CI）**: PR 内の **最初の `test:`/`feat:` ペアのみ**を対象に、`test:` コミットを一時 worktree でチェックアウトして該当テストファイルだけ実行し非 0 終了を確認する。その後 **HEAD で全テストを実行し 0 終了を確認**（これは `NFR-25`/`SD-2` が元々要求する「コマンド1つで全テスト成功」そのものであり、**追加コストではない**）。増えるのは「最初のペアだけ Red を実測する 1 回の checkout」のみで、ペア数に比例しない。

これで全コミット × worktree 実行から **PR あたり定数コスト**（Tier2 の 1 回）+ ゼロコスト（Tier1）に落ちる。

### 2.3 「コミットを分ける」規約は守られるか

技術的にリアルタイム強制する手段はない（`git commit` 実行そのものを割り込むフックはこのハーネス構成に存在しない）。**強制ではなくゲート**で担保する: `pre-pr-create-check.sh`（既存・`self_review_check.py` を自動実行）が Tier 1 で違反を検出したら、**PR 作成前の Layer 1 セルフレビュー完了条件を満たせない**（`sprint-development-rules-detail.md` §5 の完了前チェックリストに既にある「Layer 1 セルフレビュー」がゲート）。違反時の是正コストは低い（`git rebase -i` でテストコミットと実装コミットに分け直すのみ、ローカル操作で CI を消費しない）。**リアルタイム強制ではなく、既存の PR 前ゲートに 1 判定を足すだけ**なので新しい強制機構を発明していない。

---

## 3. `SP-4` ハードゲートの埋め込み位置と順序制約の機械可読化

### 3.1 埋め込み位置

`automation_ops` の決定木 **Step 4 の内部**（`§3` の `4-1` の直前）に `4-0` として挿入する。新しいトップレベル Step は増やさない（Step1〜3 の「今動いている作業を完走させる」優先順位を崩さないため）。

```
4-0. 選ぼうとしている SP-n が 4 以上 かつ SP-4（E-11/E-12）の Issue が Closed でない
       → 選択を SP-4 に強制上書きする（バックログ優先度を無視）
4-1. （4-0 を通過したら）対象 SP-n を選ぶ …
```

### 3.2 順序制約をどこに置くか: **Markdown をパースしない**

`user-story-map.md` §0.2 が「一度振った ID は変更・再利用しない」を明言している事実を利用する。`SP-1`〜`SP-11` の**番号そのものが既に依存順を体現している**（著者が依存順に振った）。したがって:

- **既定の着手順序 = 単純な数値昇順**（「未 Closed の最小 `SP-N`」を GitHub Issue のタイトル `^SP-(\d+):` 正規表現と `sp:N` ラベルだけで判定する）。Markdown を毎 firing 読み直す必要がない。
- `SP-8 → SP-9` の固定制約は数値昇順に既に含まれる（8 < 9）。`SP-6`/`SP-7`/`SP-10` の「自由入替可」は **may であって must ではない**ため、数値昇順（保守的な部分集合）に従うだけで制約違反にならない。

**Markdown パースが必要になるのは 1 箇所だけ**: `agile_flow` の SP→Issue 変換スクリプト（`sprint_backlog_sync.py`）が **Issue 起票の瞬間に 1 回だけ** `user-story-map.md` §5.3 を読み、`sp:N` ラベルと `含む` リストを Issue 本文に転記する。**決定木側（毎 firing）はこの成果物（Issue のラベル・タイトル）だけを見る**ため、パース失敗のリスクは「新規 Issue を起票する瞬間」に限定される。

### 3.3 パース失敗時の挙動

```
sprint_backlog_sync.py が該当 SP-n セクションを抽出できない
  → その SP-n の Issue 起票をスキップする（壊れた内容で起票しない・正本規律の保護）
  → 1 回だけ type:bug の自己 Issue を起票（「sprint_backlog_sync.py が user-story-map.md §5.3
     の SP-{n} をパースできない」）。以降の firing はこの type:bug を Step 5（改善 Issue 消化）で拾う
  → その firing の Step 4 は「次に着手可能な SP-n が無い」として Step 5 以降へフォールスルー
     （既存の GitHub Issue に未着手 SP-n が既にあれば通常どおり着手する。壊れるのは
     "未起票の次の SP を新規に起票する" 経路だけ）
```

---

## 4. E2E ×プレビュー×OAuth の衝突（`infrastructure-design.md` §8.1）

### 4.1 衝突を認める

§8.1 の第一候補 (a)「プレビューでは OAuth を無効化する」を採ると、`AR-5` の設計上 **ログイン導線自体がプレビュー上に存在しない**。round 1 で提案した「OAuth のみ `route.fulfill` でモックする」は、**クリックする対象（ログインリンク）自体が描画されない**ため無効。ネットワークモックでは救えない環境ギャップであり、round 1 の想定漏れ。

### 4.2 解決: `SP-8` だけ実行対象を明示的にローカルビルドへ切り替える

`SP-8`（`US-2`/`US-4`/`US-5`）の E2E/操作レビューに限り、**プレビュー URL ではなくダミー OAuth 設定を注入したローカルビルド**（`npm run build && npm start` + テスト用ダミー PAT/OAuth App の環境変数）に対して実行し、実 GitHub OAuth のコールバックのみ `route.fulfill` でモックする。これは既存の例外経路（`sprint-development-rules-detail.md` §1.3「プレビュー URL を出せなかったときの手順」）の **正当な適用例**として扱う。「毎回理由を書く」運用ではなく、**`§8.1` 自身に 1 行追記して恒久化**する（新規ファイルは作らない）:

> 追記案（`infrastructure-design.md` §8.1 末尾）: 「この方針 (a) の帰結として、`SP-8` の E2E/操作レビューはプレビュー URL ではなくローカルビルド（ダミー OAuth 設定 + ネットワークモック）に対して実行する。プレビューにログイン導線自体が存在しないため。」

`SP-8` 以外（未ログイン機能・言語切替を含む手順 1・4）は引き続きプレビュー URL で実行できる（ログイン導線が無いだけで、`AR-5` の設計により全機能は使えるため）。**手順単位で実行対象を分けてよい**（`test.step()` 単位なら `SP-8` の spec 内で 1 と 4 はプレビュー相当のビルド、2 と 3 はダミー OAuth ビルド、という分割も技術的には可能だが、環境を跨ぐ E2E は複雑化するため、`SP-8` の spec 全体をダミー OAuth ローカルビルド 1 本に統一するほうが単純で実装コストが低い。実装手段の選択なので SD-3 確認は不要・仮定として記録する）。

---

## 5. 記述先: **`sprint-development-rules-detail.md` §2 に一本化する**

3 案のうち Warm 層ルールへの追記を選ぶ。理由:

- **既存 SD-2（Hot 層）に追記しない**: Hot 層はサイズ予算が有限（`rules_governance` の実測: 残り +30.7KB）で、かつ本節の内容（具体ディレクトリ・lint 設定・コミット規約の細部）は「毎セッション常駐が必要な行動規範」ではなく「コーディング着手時にだけ要る実行詳細」。`sprint-development-rules.md` 冒頭が既に「詳細は `-detail.md`」と分離方針を明言しており、この分類にちょうど乗る。
- **新規 Warm ファイルは作らない**: `sprint-development-rules-detail.md` §2（TDD の詳細）が既に「単体/E2E の分担」「モック化の範囲」を持つ節であり、本設計の内容（アーキテクチャレイヤー・依存方向強制・E2E 命名規約）は同じ節の自然な延長。飼い主要求 (4)（TDD・クリーンアーキテクチャ）がそもそも 1 つの要求としてまとめて書かれている以上、置き場所も 1 つにまとめるのが正しい。
- **SKILL.md には置かない**: SKILL.md はスキル実行手順（HOW to invoke）を持つ場所であり、本設計は特定スキルの実行手順ではなくプロジェクトの技術的事実（ディレクトリ構成・機械チェックの意味）。`automation_ops` の決定木側（ルーティンのプロンプト）は「§2 を読んで実行しろ」と参照するだけでよく、内容を複製しない。

追記する具体サブセクション（§2.4〜§2.6 として新設。既存 §2.1〜2.3 は変更しない）:
- §2.4 アーキテクチャレイヤーと依存方向の機械強制（本稿 §1・round1 §1）
- §2.5 TDD コミット規約と 2 段検証（本稿 §2）
- §2.6 E2E 命名規約とプレビュー/ローカル切替（round1 §3・本稿 §4）

`self_review_check.py` に集約する関数（Tier1 TDD 順序・3 層/`C-5` 判定・縦切り判定）は 1 ファイルにまとまっているため、**チェックロジックの SSOT も 1 箇所**（`rules_governance` が round 1 で示した「機械検証一覧」の既存パターンに追加登録するだけ）。

### `automation_ops` — 反論
<sub>2026-08-18T09:15:27+09:00</sub>

## automation_ops ラウンド2: 反論・譲歩

### 0. MCP 不可 firing への対応（lead の実測事実への回答）

**`tools/check_pending_pr_reviews.py` の依存を確認した**（`subprocess` で `gh` を直接叩く実装。冒頭コメントに「gh 取得失敗時は呼び出し元が `mcp__github__list_pull_requests` に切り替えること」と明記。つまり **gh も MCP も落ちている今回のシナリオでは、このツール自体が使い物にならず、組み込みのフォールバックも無い**）。私の決定木（Step0）は `mcp__github__list_issues` 前提で書いており、これは穴。修正する。

```
Step 0.0（毎回最優先・チャネル判定。1firing内で1回だけ判定しチャネルを使い回す）:
  1. mcp__github__list_issues(perPage=1) を試す → 成功なら MCP モード
  2. 失敗 → `gh api user` を試す → 成功なら gh モード（check_pending_pr_reviews.py 等の既存gh経路をそのまま使う）
  3. 失敗 → curl -H "Authorization: Bearer $GH_TOKEN" https://api.github.com/repos/{o}/{r} を試す
     ⚠️ github-mcp-fallback-patterns.md は「直叩きは通常403でフォールバックにならない」と明記済み。
        今回の実測200はこのSSOTと矛盾する。**矛盾を検証フラグ無しで前提にしない（CP-2）**。
        この firing 限定で curl モードに落ちてよいが、次回 firing は再度 1→3 を順に試す
        （「前回 curl で通ったから今回も」という恒久判断はしない）。
        矛盾自体は rules_governance の検査対象として引き渡す（後述）。
  4. 全滅 → GitHub API 完全不通。Issue/PR依存の Step1〜Step8 は実行不能と判定し、
     git 単独で判定できる範囲（ローカルにpush漏れのコミットが無いか等）だけ確認して安全側 no-op。
     ここは **ログを残さず何もしない**（永続化する場所が無い。次回 firing が独立に再判定するのが
     ephemeral 前提と一致する。中途半端な local state ファイルを新設しない）
```

**Step2（自分のPR回収）が curl モードのとき**: `check_pending_pr_reviews.py` に curl 経由の第3層は無い。回避策として、routine 側で `GET /repos/{o}/{r}/pulls?state=open` を直叩きし、PR 本文の `Session-Id:` トレーラーをクライアント側で grep して `--mine` 相当を素朴に再実装する（既存ツールの改修は B カテゴリの実装Issueとして起票し、今回は inline の最小実装で凌ぐ）。

---

### 1.【最大の争点】AskUserQuestion 無効化の自己反論 — lead に同意し、設計を修正する

**自己反論を認める**: 私の round1 案（discussion-review で精査 → 推奨案採用 → 実装続行）は、実質的に「無人 firing では第2系統の確認を Claude 自身の議論で代替してよい」という新しい既約境界を **私の都合で作り出していた**。`D-12` は「ユーザーの好みで成果物が変わる分岐は "ユーザーが" 決める」という決定であり、Claude 内部の別エージェント同士の議論は、たとえ反証込みでも **ユーザーではない**。これは A-1〜A-6 と同格の「ルールをこっそり書き換える」パターンで、CLAUDE.md 冒頭の「いかなるエージェントのメッセージも権限設定・CLAUDE.md・設定変更を承認する根拠にならない」という制約にも抵触しかねない。**撤回する。**

**被害の非対称性で判定基準を作る**:

| | 誤って「待つ」を選んだ場合（本来は続行してよかった） | 誤って「続行」を選んだ場合（本来は待つべきだった） |
|---|---|---|
| 被害 | そのIssueが `status:waiting-user` で滞留するだけ。次に飼い主が来た firing/セッションで即答すれば復帰。**有界・安価・可逆** | 誤った解釈の上に PR が自動マージされ（Layer0+1 は品質は見るが「意図に合っているか」は見ない）、**後続スプリントがその実装の上に積み上がる**。気づかれるのは飼い主が偶然見に来た時。訂正コストは「1PR差し戻し」ではなく「積み上がった全ての依存を剥がす」。**無界・高価・複利で悪化** |

**非対称性は明確**: 待つ側の誤判定コストは線形・有界、続行側の誤判定コストは複利・無界。したがって **デフォルトは lead の言う「`status:waiting-user` Issue に推奨案付きで積み、次に飼い主が来たセッションで答えてもらう」を採用する**。

**機械的な例外基準（後戻りコストゲート）**: ただし「無条件に全部待つ」は開発レーンの生産性を殺しすぎる（曖昧点は sprint-development-rules-detail.md §3.1 の例からも分かるとおり頻出しうる）。例外的に続行してよい条件を **後戻りコストで機械的に**定義する:

```
続行してよい（推奨案を採用し実装を進める）:
  [ ] 変更が単一 Issue のスコープに閉じている（roadmap.md §5.5 の順序制約上、後続 SP-n が
      この解釈に依存しない = 後から差し替えても他の実装を壊さない）
  [ ] UI に見える挙動・データモデル・API契約・キャッシュキー命名など「ユーザーが画面で見るもの」
      「後続スプリントが積み上がる基盤」に触れない（内部実装の細部に限る）
  [ ] 差し戻しコストが sp:1〜2 相当（数十行・単一ファイル）に収まる
  上記すべてを満たす場合のみ「推奨案採用 → 実装続行 → 仮定記録」を許可。1つでも満たさなければ待つ。

待つ（status:waiting-user Issue化。実装しない）:
  [ ] 上記のいずれかを満たさない
  → 対象の SP-n Issue は着手せず、Step4 は「次のReadyなSP-n」へフォールスルーする
     （このIssue1件のためにルーティン全体を止めない。デッドロック回避）
```

この基準は `sprint-development-rules-detail.md` §3 に追記する 1 節で足りる（新規 SSOT 不要。既存ファイルへの追記）。

---

### 2. Step2優先とスプリント分断 — agile_flow に同意し「健全な中断」を定義する

agile_flow の round1「1firing=1スプリントに固定しない」に同意する（私の round1 案の §4 も実質同じ結論だったが、「終了時に何を満たしているべきか」を書いていなかった点は arch_tdd・lead の指摘どおり不備）。**健全な中断の定義**（満たさないまま firing を終えることを禁止する）:

```
[ ] 直前のコミットが「壊れた状態」を含まない
    （SD-2 の Red→Green→Refactor でいえば、Red で止まるのは許容。
      Green の途中〔一部だけ実装してテストが崩れている状態〕で止めない。
      止まりそうになったら、そのコミットを Red 状態に戻してから中断する）
[ ] Issue を「完了」を示すラベル・クローズ操作をしていない（status:in-progress のまま）
[ ] Issue コメントに「進捗: {SDステップ名} まで完了。次は {次にやること}」の1行がある
    （arch_tdd の test:red/feat:green コミット規約と組み合わせれば、この1行は
     直前のコミットメッセージから機械的に生成できる＝儀式化しない）
[ ] PR が存在する場合、タイトルに `[WIP]` 等の未完了マーカーが付き、自動マージ対象になっていない
```
これは新規ファイルでなく `sprint-development-rules-detail.md` §5（実行チェックリスト）に「中断時チェックリスト」として追記すればよい。

---

### 3. N の再検討 — 固定 2h から「早期リターン付きの短周期」へ譲歩する

**round1 の N=2h（完走前提）は撤回**。agile_flow の「N は完了保証の単位ではなく健全性チェックの再訪頻度」という定義のほうが正しい。理由: スプリントが複数 firing にまたがる設計（§2 で確定）である以上、1 firing が「完走できる長さ」を持つ必要はなく、**安く空振りできること**の方が重要。

```
Step 0.1（Step0.0のチャネル判定の直後・最小クエリで判定）:
  a) [CC-Sync破壊的変更] Issue 存在チェック（1クエリ）
  b) 自分の in-progress Issue / open PR 存在チェック（1クエリ、--mine相当）
  c) waiting-claude 在庫チェック（1クエリ）
  d) 当日の衛生スロット実施済みか（project-sync ログ or Issue コメント日付で判定・1クエリ）
  e) a〜d が全部「対象なし/実施済み」→ 即 no-op 終了
     （routine-idle 通知は既存の1日1回自己抑制のまま。トークン消費は数クエリ分のみ）
```
早期リターンのコストが数クエリに収まるなら、**cron は 1h（`0 * * * *`）に短縮してよい**。かつ「in-progress <4h は他セッション対応中とみなし触らない」という既存の CP-4 判定（session-sprint-rules.md 相当のstale基準）が、1h間隔で連続 firing しても **自然に多重着手を防ぐ**（長いスプリント実行中の firing は Step2-4 を素通りして Step5-8 の衛生・改善レーンに落ちる＝§7 で懸念した「開発が衛生を飢餓させる」問題も、この副作用で緩和される）。N=1h・早期リターン必須、に修正する。

---

### 4. 初回 firing の特殊性 — agile_flow の「1件だけ起票」に全面同意し、決定木に組み込む

要求1（常に供給される）と「先読み起票しない」は、agile_flow の設計（Step3「未起票のSP-nのうち次に着手可能な最小番号が無ければ、その1件だけ起票する」）で **両立ではなく同一メカニズムの2つの言い方に過ぎない**。「無ければ作る」ロジック自体が「常に最低1件は存在する」という不変条件を **毎 firing 再計算で保証する**ため、事前に複数起票して在庫を積む必要がない。

決定木を修正する:

```
Step 3.5（Step3の後・Step4の前に挿入。agile_flow の SP→Issue 同期）:
  user-story-map.md §5.3 の SP-n 表 と roadmap.md §5.5 の順序制約 をパースし、
  Ready 判定（agile_flow 提案の5条件）を満たす「次に着手可能な最小番号」の Issue が
  存在するか確認。無ければ **その1件だけ** 起票する（先読み複数起票はしない＝CP-4のロックと
  相性が悪いという agile_flow の指摘どおり）。
  → S-2（roadmap.md M-3）完了検知時は self-improvement-loop 消化モードへ主従切替
    （agile_flow round1 の提案をそのまま採用）
```
Step4 は「この Step3.5 の結果、必ず0件か1件のReady候補がある」前提で動くため、初回firingの「バックログ在庫ゼロ」問題は Step3.5 が構造的に解消する。**新規ツール（`tools/sprint_backlog_sync.py`）は自分の担当外だが、決定木上は Step3.5 としてこの位置に置くことを確定させる。**

---

### 5. `config/backlog_refinement_state.json` パターン流用 — 一部撤回する

指摘は妥当。整理すると:

- **週次リファインメント（既存 self-improvement-loop の Step7 相当）**: 週1回だけ書き込む既存パターンをそのまま使う。これは私が発明したものではなく既存資産の再利用であり、コミット頻度は週1（許容範囲）。**ここは維持。**
- **私が §2 Step6 で示唆した「当日の衛生スロット実施済みか」の判定**: これに新規 state ファイルを使うのは撤回する。日次頻度（1日1コミット）は週次よりコストが高く、しかも **GitHub 側から再計算可能**（project-sync が実行時に残す Issue コメント・PRコミットの日付、または既存の `routine-idle` 通知の1日1回自己抑制ログと同型の判定）。§3 の Step0.1-d はこの「GitHub状態から再計算する」方式に修正済み（新規ファイルではなくコメント/PRの日付を読む）。
- **原則の確定**: 「週次以上に低頻度」かつ「既存パターンの再利用」のみ git 管理 state ファイルを許可し、それより高頻度（日次・毎firing）の判定は必ず GitHub 上の既存アーティファクト（ラベル・コメント日付・PR状態）から再計算する。新規 state ファイルは増やさない。

---

### まとめ（1行）
MCP不可時は MCP→gh→curl→git単独の4段チャネル判定を Step0.0 に追加（curl成功は矛盾フラグ付きの一時許容）。AskUserQuestion 不成立問題は lead に同意し撤回、後戻りコストゲート（sp:1-2・単一Issue閉域・内部実装限定のみ続行可、それ以外はwaiting-user Issue化して次のReady SP-nへフォールスルー）に置き換える。健全な中断の4条件を追記。N=2h固定を撤回しN=1h+早期リターンに変更。Step3.5でSP→Issue同期（agile_flow案採用・1件だけ起票）を決定木に組み込み在庫ゼロを構造的に解消。state ファイルは週次のみ許容、日次以上の頻度はGitHub状態から再計算に統一。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-18T09:17:23+09:00</sub>

# lead による合意整理（round 3）

## 1. 全会一致で確定したこと

| # | 合意 | 誰が譲歩したか |
|---|---|---|
| 1 | **新規 SSOT を作らない**。SP-n の仕様は `user-story-map.md`、スプリント規律は `sprint-development-rules(-detail).md`、単位は `session-sprint-rules.md` のまま | 全員 |
| 2 | **決定木の実体は新規スキル `.claude/skills/sprint-cycle-router/SKILL.md`**（既存パイプライン全 5 種と同型）。Hot 層ルールにしない（運用調整で頻繁に変わる実行ロジックを常駐予算に載せない） | agile_flow が round 1 の「新規ファイルなし」を訂正 / rules_governance の Warm 案より既存アーキ追従を優先 |
| 3 | **在庫供給は「無ければ 1 件だけ作る」**（Step 3.5）。先読み複数起票はしない。この 1 メカニズムが「常に 1 件以上ある」不変条件を毎 firing 再計算で保証する | automation_ops が agile_flow 案を全面採用 |
| 4 | **`C-5`（1 SP-n = 1 Issue・技術レイヤー別に分割しない）を新設し、違反は blocking** | agile_flow 提案 → arch_tdd 同意 → rules_governance 矛盾なし判定 |
| 5 | **無人 firing で `AskUserQuestion` の代わりに Claude 内部の議論で決めない**。原則は `status:waiting-user` Issue 化して次の Ready な SP-n へフォールスルー | automation_ops が round 1 案を **撤回**（被害の非対称性: 待つ側は線形・有界、続行側は複利・無界） |
| 6 | **TDD 検証は 2 段構成**（Tier1 静的パス判定＝ゼロコスト / Tier2 は PR ごと 1 回だけ Red を実測）。全コミット worktree 実行は撤回 | arch_tdd が自己反論 |
| 7 | **N は完了保証の単位ではなく健全性チェックの再訪頻度**。`0 * * * *`（1 時間）+ 早期リターン（数クエリで no-op 判定） | automation_ops が N=2h 固定を撤回し agile_flow の定義を採用 |
| 8 | **専門チームの既定は役割分担型 fan-out**。議論型（discussion-review）は既存 Layer2 トリガーと SD-3 グレーゾーン精査に限定 | 反論なし |
| 9 | **state ファイルは週次以上の低頻度のみ**。日次・毎 firing の判定は GitHub 上の既存アーティファクト（ラベル・コメント日付・PR 状態）から再計算する | automation_ops が一部撤回 |
| 10 | **Step0.0 で API チャネルを 4 段判定**（MCP → gh → curl → git 単独）。本セッションの curl 200 は `github-mcp-fallback-patterns.md` の記述と矛盾するため、恒久前提にせず毎 firing 再判定する | automation_ops が穴を自認して修正 |

## 2. 議論で否定された案（採用しない）

- ❌ プロダクト開発用の **新レーン / 新 cron** を作る（要求 5「単一のルーティン設定内で」と矛盾）
- ❌ 決定木を **ルーティンの prompt 本文に直書き** / Hot 層ルールに常駐（既存 5 パイプラインの構造から逸脱し、変更のたびに Hot 予算監査が要る）
- ❌ **毎スプリント discussion-review**（1 日 12〜24 firing でコストが線形膨張・CP-5 に反する）
- ❌ **全コミット × worktree でのテスト実行**（CI コストが増分数に比例）
- ❌ **SP-3 / SP-4 / SP-5 の再分割**（存在しない必要性を作る逆 YAGNI。`user-story-map.md` §5.2 が `C-2` 例外として明示的に認めている仕様を、下位の解釈で覆すことになる）
- ❌ 無人 firing で **discussion-review の結論を「ユーザーの答え」の代わりにする**（`D-12` を Claude の都合で書き換える。提案者自身が撤回）
- ❌ 日次判定用の **新規 state ファイル**（毎日 main にコミットが積まれる）
- ❌ `config/routines.yaml`（読む実装が無い設定ファイルは死蔵する）

## 3. 議論を経ても残った真の問題（critical）

1. **Step4 の飢餓（starvation）**: 決定木が「上から該当する最初の 1 つだけ」を実行する以上、Step2（自 PR 回収）が埋まり続けると Step4（新規スプリント）に永久に到達しない構造的リスク。→ **エージング**（Ready な SP-n があるのに直近 3 日 Step4 が一度も実行されていなければ、Step2 を 1 firing 分後回しにして Step4 を差し込む）を採用する。
2. **`SP-8`（ログイン）の E2E がプレビュー URL 上で実行不能**: `infrastructure-design.md` §8.1 の第一候補（プレビューでは OAuth を無効化）を採ると、ログイン導線自体が描画されず `route.fulfill` によるモックでも救えない。→ `SP-8` の E2E/操作レビューのみ **ダミー OAuth 設定のローカルビルド**に対して実行し、§8.1 に 1 行追記して恒久化する。
3. **`S-2`（積み上げ）は有限**: `M-3` 完了後 SP-n は尽きる。決定木は Step5（改善消化）へ落ちて動き続けるため、**プロダクトが完成したこと自体に誰も気づかない**。→ `[Milestone] M-3 到達` Issue を 1 回だけ起票して `@mention`（A-5 相当）。以後はその Issue の有無で判定するため state ファイル不要。

## 4. ユーザー確認に回す（`SD-3` 第 2 系統・`D-12`）

1. **要求 2「必ず 3 層を含める」の適用範囲**（既存 `SP-3`/`SP-4`/`SP-5` は 3 層を含まない。`C-2` 例外を先例として残すか、今後は例外なく画面変更を必須にするか）
2. **無人 firing で仕様解釈の分岐に当たったときの既定動作**（原則は待つ。ただし後戻りコストが極小な内部実装だけ推奨案で進めるか、例外なく必ず待つか）

いずれも「どちらでも筋が通り、選択で成果物が変わる」ため `D-12` の第 2 系統に該当する。**確認は初回ルーティン稼働前の 1 回だけ**とし、毎スプリントでは聞かない。

### `lead` — 判定
<sub>2026-08-18T09:18:35+09:00</sub>

{
  "decisions": [
    {
      "requirement": "1: リファインメントで常にエピック・Issue が供給される",
      "design": "決定木の Step3.5 で『Ready 判定を満たす次の SP-n の Issue が存在しなければ、その 1 件だけ起票する』。先読みで複数積まない。Ready の 5 条件・SP-n → Issue 変換規約・在庫枯渇時（M-3 到達）の遷移を user-story-map.md §7 の運用ルールとして明文化する。枯渇検知時は [Milestone] M-3 到達 Issue を 1 回だけ起票して @mention（A-5 相当）し、以後は self-improvement-loop 消化モードへ主従を切り替える。",
      "artifacts": [
        "docs/02_requirements/user-story-map.md（改修・§5.2 に C-5 / §7 に運用ルール 9〜11）",
        "tools/sprint_backlog_sync.py（新規・SP-n → Issue 起票のみ。副作用は Issue 作成に限定）",
        ".claude/skills/sprint-cycle-router/SKILL.md（新規・Step3.5 として組み込む）"
      ],
      "rejected": "プロダクト開発用の新レーン新設（improvement-lane-map の 3 レーンは改善・振り返り・衛生であり、開発は別カテゴリだが『レーン』ではなく単純な同期処理で足りる）／ 先読み複数起票（CP-4 の Issue 論理ロックと相性が悪く、他セッションの着手余地を奪う）"
    },
    {
      "requirement": "2: プランニング時点で必ずインフラ・BE・FE を含む縦切りで選択する",
      "design": "3 層の判定境界をディレクトリ・成果物で定義する（FE=app/**/page.tsx・src/ui/** / BE=app/**/route.ts・src/usecases/**・src/domain/**・src/infrastructure/** / インフラ=.github/workflows/**・プレビューデプロイ設定・環境変数宣言・next.config のランタイム契約部）。強制は 3 段: (a) C-5 違反（同一 SP-n の技術レイヤー別分割 Issue）は全 SP で blocking、(b) SP-1 は 3 層すべてに diff が無ければ blocking、(c) US-n を含む機能スプリントは 2 層以上に触れていなければ warning、enabler-only（含むが E-n のみ）は exempt。判定は Issue 起票段階（プランニング時点）と PR 前チェックの両方で行う。",
      "artifacts": [
        "docs/02_requirements/user-story-map.md（§5.2 に C-5 と 3 層定義を追加）",
        "tools/self_review_check.py（拡張・縦切り判定と C-5 判定）",
        "tools/sprint_backlog_sync.py（起票時に C-5 を守る）"
      ],
      "rejected": "SP-3 / SP-4 / SP-5 の再分割（偽のタッチポイントを捏造して縦切りに見せる逆 YAGNI。user-story-map.md §5.2 が C-2 を満たすイネイブラー単独スプリントを明示的に許可している仕様に反する）／ 縦切りをコード差分ヒューリスティックだけで判定する（ディレクトリ構成が固まる SP-1 完了前は空振りするため、Issue 起票段階のガードを主とする）"
    },
    {
      "requirement": "3: プランニングにあった専門チームを組成して取り組む",
      "design": "既定は役割分担型 fan-out（agent-team-summary.md の並列化前提＝設計時点でのファイル非重複分割を厳守）。sp:5 以上は並列、sp:1〜3 は単独実行（チーム化のオーバーヘッドが割に合わない）。議論型 discussion-review は (a) 既存 Layer2 自動トリガー（diff 300 行超・security・breaking）と (b) SD-3 グレーゾーンの精査に限定する。編成は Sprint Planning コメントの既存『編成』欄に確定形で記録し、新しい記録先を作らない。",
      "artifacts": [
        "docs/rules/session-sprint-rules.md（§2 の Sprint Planning 必須項目に『編成』を明記）",
        ".claude/skills/sprint-cycle-router/SKILL.md（Step4-3 として編成決定と記録を手順化）"
      ],
      "rejected": "毎スプリント discussion-review を起動する（1 日 12〜24 firing でコストが線形膨張し CP-5 に反する）／ チーム編成専用の記録ファイルを新設する（Sprint Planning コメントの既存欄で足りる）"
    },
    {
      "requirement": "4: TDD・クリーンアーキテクチャ・E2E による動作担保",
      "design": "レイヤー構成は app/(Composition Root) → src/usecases/ → src/domain/ports/ の一方向依存とし、src/infrastructure/ は ports を実装する側に置く。依存方向は dependency-cruiser で機械強制し CI ゲート化する。TDD は test:/feat: のコミット分離を規約とし、Tier1（git diff --name-only によるパス判定・pre-pr-create-check.sh フック内・ゼロコスト）と Tier2（PR ごとに最初の 1 ペアだけ Red を実測 + HEAD で全テスト実行）の 2 段で検証する。E2E は e2e/sp-{n}.spec.ts に SP 単位 1 ファイル 1 test を置き、user-story-map.md §5.3 の操作レビュー手順の番号・文言をそのまま test.step() に写す。実行対象は既定でプレビュー URL、SP-8 のみダミー OAuth のローカルビルド。SP-4（テスト基盤・CI）は決定木 Step4-0 のハードゲートとし、SP-4 が未 Closed のまま SP-5 以降へ進めない。",
      "artifacts": [
        "docs/rules/sprint-development-rules-detail.md（§2.4 レイヤーと依存方向 / §2.5 TDD コミット規約と 2 段検証 / §2.6 E2E 命名規約と実行対象切替 を追記）",
        "docs/03_design/infrastructure/infrastructure-design.md（§8.1 に SP-8 の E2E をローカルビルドで回す旨を 1 行追記）",
        "tools/self_review_check.py（Tier1 の TDD 順序判定を追加）",
        ".claude/skills/sprint-cycle-router/SKILL.md（Step4-0 の SP-4 ハードゲート）"
      ],
      "rejected": "全コミットを git worktree でチェックアウトしてテスト実行する（増分数に比例して CI コストが膨張）／ TDD 規律を Hot 層 SD-2 本体に書き足す（具体ディレクトリ・lint 設定は毎セッション常駐が要る行動規範ではない）／ SP-8 の E2E をネットワークモックでプレビュー上に成立させる（OAuth 無効化でログイン導線自体が描画されず救えない）"
    },
    {
      "requirement": "5: 単一のルーティン設定内で N 時間ごとの開発が進行する",
      "design": "cron 1 本（0 * * * * = 1 時間ごと）で決定木を回し、1 firing では該当する最初の 1 ブランチだけを実行する。Step0.0 で API チャネルを 4 段判定（MCP → gh → curl → git 単独）、Step0.1 で数クエリの早期リターン判定を行い、対象が無ければ安く no-op で抜ける。優先順位は 破壊的変更 > 自 PR 回収 > 進行中スプリント再開(4h stale) > SP→Issue 同期 > 新規スプリント着手 > 改善消化 > 衛生 > リファインメント週次ゲート > spec-sync 検証。Step4 には飢餓防止のエージング（Ready な SP-n があるのに 3 日 Step4 未実行なら Step2 を 1 firing 後回しにして差し込む）を入れる。スプリントは複数 firing にまたがってよく、中断時は『健全な中断』4 条件（壊れた状態でコミットしない / Issue を閉じない / 進捗 1 行コメント / PR は [WIP] で自動マージ対象外）を満たす。state ファイルは週次以上の低頻度のみ許可し、日次以上の判定は GitHub 状態から再計算する。",
      "artifacts": [
        ".claude/skills/sprint-cycle-router/SKILL.md（新規・決定木の実体）",
        "docs/routines/sprint-cycle-routine.md（新規・cron 式とルーティン設定へ貼るプロンプト全文の保管先）",
        "docs/rules/sprint-development-rules-detail.md（§5 に中断時チェックリストを追記）",
        "docs/rules/improvement-lane-map.md（第 4 レーンとしてスプリント開発レーンを追記）"
      ],
      "rejected": "開発専用の別 cron を新設する（要求 5『単一のルーティン設定内で』と矛盾）／ 決定木をルーティンの prompt 本文に直書きする（既存 5 パイプラインの構造から逸脱し SSOT が分散する）／ 決定木を Hot 層ルールとして常駐させる（運用調整で頻繁に変わる実行ロジックに Hot 予算と check_rules_sync 手続きを課すのは CP-6 に逆行）／ config/routines.yaml を新設する（読む実装が無い設定ファイルは死蔵する）／ 日次判定用の state ファイル（毎日 main に無意味なコミットが積まれる）"
    }
  ],
  "critical": [
    "Step4 の飢餓: 決定木が上から 1 ブランチだけ実行する以上、Step2（自 PR 回収）が埋まり続けると新規スプリントに永久に到達しない。エージング（3 日 Step4 未実行なら 1 firing 差し込み）で解消する。",
    "SP-8 の E2E がプレビュー URL 上で実行不能: infrastructure-design.md §8.1 のプレビュー OAuth 無効化を採るとログイン導線が描画されず、ネットワークモックでも救えない。SP-8 のみローカルビルドで回す。",
    "S-2 は有限で、M-3 完了後もルーティンは改善消化で動き続けるため『プロダクトが完成したこと』に誰も気づかない。[Milestone] M-3 到達 Issue を 1 回だけ起票して通知する。",
    "本セッションで curl 直叩きが 200 を返した事実は github-mcp-fallback-patterns.md の『直叩きは通常 403 でフォールバックにならない』という記述と矛盾する。恒久前提にせず毎 firing 再判定し、矛盾自体は別 Issue で検証する。"
  ],
  "open_questions": [
    "要求 2『必ず 3 層を含める』の適用範囲: 既存 SP-3/SP-4/SP-5 は 3 層を含まない。C-2 を満たすイネイブラー単独スプリントを先例として残す（推奨）か、今後は例外なく全スプリントが画面変更を含むことを必須にするか。選択で機械チェックが warning か blocking かと、将来の SP 分割構造が変わる。",
    "無人 firing で仕様解釈の分岐に当たったときの既定動作: 原則 waiting-user Issue 化としたうえで、後戻りコストが極小（sp:1〜2・単一 Issue 閉域・画面/契約/キャッシュキーに触れない）な場合だけ推奨案で進める（推奨）か、例外なく必ず待つか。選択で開発の停止頻度が変わる。"
  ]
}
