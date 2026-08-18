<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter スプリント開発プロセスの単一ルーティン化設計

- 議題ID: `sprint-cycle-design-20260818`
- 論点: 要求は5点: (1) リファインメントが常にスプリント開発に必要なエピック/Issue を供給し続ける (2) スプリントプランニング時点で必ず、ユーザーが画面操作してレビューできるように インフラ/バックエンド/フロントエンド を含む縦切りでエピック・Issue を選択する (3) スプリント開発ではプランニングにあった専門チームを組成して取り組む (4) TDD・クリーンアーキテクチャを意識し、単体テストだけでなく E2E テストでも動作担保する (5) 最終的に単一のルーティン設定内で N 時間ごとの開発が進行できるようにする。既存資産（docs/rules/sprint-development-rules.md の SD-1〜SD-4 / session-sprint-rules.md / user-story-map.md §5 の SP-n / roadmap.md の M-n / self-improvement-loop 等のスキル / hooks）を壊さず、SSOT を増やさずに実現する設計を出すこと。
- 参加者: `agile_flow`, `arch_tdd`, `automation_ops`, `rules_governance`
- 投稿数: 4
- 更新: 2026-08-18T09:11:57+09:00

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
