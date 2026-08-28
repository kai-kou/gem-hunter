# 日時表記ルール（Datetime Rules・JST 統一 SSOT）

> **このファイルは「日時を表示・記録するときのタイムゾーン基準」の唯一の正本（SSOT）である。**（飼い主の明示決定・Issue #75）

## 0. 大原則: 日時は JST で統一する

**ユーザーに見える、または記録（コミットメッセージ・Issue / PR コメント・ログ・通知・スナップショット）に残る日時は、すべて JST（Asia/Tokyo・UTC+9）で表記する。**

- チャットでユーザーに日時を伝えるときも **必ず JST**（UTC で答えない）。システム注入の時刻が UTC 由来でも **JST に換算** して示す（UTC = JST − 9 時間）。
- フォーマットは `YYYY-MM-DD HH:MM JST`（日付のみで足りる場合は `YYYY-MM-DD`）。

## 1. 唯一の例外: 機械処理用の UTC は維持する

以下は **JST 化してはならない**（人間が読む日時ではなく、機械が解釈する値・内部計算用）。

- 外部 API に渡す ISO 8601（GitHub API の `after_timestamp` 等・`date -u +"%Y-%m-%dT%H:%M:%SZ"`）— API 仕様が UTC `Z` を要求。JST 化すると壊れる
- 内部の経過時間・stale 判定（`datetime.now(timezone.utc)` の差分）— 表示しないため基準が一貫していれば正しい
- エポック秒・mtime 差分（`date +%s`）— TZ 非依存
- UTC↔JST↔PT 換算表（`token-optimization-rules.md`）— 換算が目的なので UTC 併記が正しい
- テスト実行プロセスの TZ（`vitest.config.mts` の `test.env.TZ` / `playwright.config.ts` の `process.env.TZ`・`use.timezoneId`・`webServer.env.TZ`）— 本番 Workers（UTC）と同条件で走らせ、`timeZone: 'Asia/Tokyo'` 明示指定漏れによる JST 表示退行を検知するため（Issue #175・詳細は §2）

**判定基準**: 「その日時を **人間が読む / 記録として残す** か？」→ YES なら JST。「機械が解釈する / 内部計算にのみ使う（表示しない）」→ UTC 維持で可。

## 2. 実装パターン

Python は表示・記録用に `datetime.now(timezone(timedelta(hours=9)))`、機械処理用は `datetime.now(timezone.utc)`。`datetime.utcnow()` / TZ 未指定の `datetime.now()` は表示・記録用途で使わない。シェルは表示・記録用に `TZ="${PROJECT_TZ:-Asia/Tokyo}" date '+%Y-%m-%d %H:%M %Z'`（リテラル `JST` の直書きは禁止・`%Z` を使う・#79）、機械処理用は `date -u +"%Y-%m-%dT%H:%M:%SZ"`。コード例全文は `datetime-rules-detail.md`。

日時テンプレートに時刻を含めるときは必ず ` JST` を付ける（`{YYYY-MM-DD HH:MM JST}`）。日付のみのテンプレートは `$(TZ=Asia/Tokyo date +%Y-%m-%d)` で生成し、コンテナ TZ に依存させない。

**テスト実行環境は本番と同じ UTC に固定する（表示は JST・実行環境は UTC・§1 参照・Issue #175）**: コンテナ既定 TZ が `Asia/Tokyo` のため、`timeZone: 'Asia/Tokyo'` の明示指定漏れがローカル/CI では検知できず、UTC で動く本番 Workers だけ 9 時間ずれる退行を見逃す。`vitest.config.mts` の各 project に `test.env.TZ = 'UTC'`、`playwright.config.ts` に **`process.env.TZ = 'UTC'`（テストランナー自身の Node プロセス。config 評価時点で設定する）** + `use.timezoneId = 'UTC'`（ブラウザコンテキスト）+ `webServer.env.TZ = 'UTC'`（アプリの子プロセス）を設定し、テストプロセス全体を UTC で走らせる。

**レビュー済みの例外（`# tz-ok`）**: `tools/check_datetime_tz.py` が誤検出する、あるいは意図的に naive datetime を使う正当な理由がある場合、該当する呼び出しの **開始行〜終了行のいずれかの行** に `# tz-ok` を書くと検査から除外できる。複数行にまたがる呼び出しなら閉じ括弧の行に書いても抑制される（同じ行に書かないと効かない、という制約ではない・Issue #445）。乱用しない（レビュー済みの正当な例外のみ）。

## 3. 完了・成功の定義

- [ ] ユーザーに伝える日時・表示/記録系コードの日時が JST 基準（API 用 UTC を除く）
- [ ] ハーネス（hooks）の既定 TZ が `Asia/Tokyo`、シェル `date` が `%Z`（リテラル直書きでない）
- [ ] 機械処理用 UTC（API・内部計算）は維持されている
- [ ] `python3 tools/check_datetime_tz.py` が PASS（表示・記録系の TZ 未指定 `datetime` 残存ゼロ・#80）

> **新しい失敗モード（Issue #445）**: `python3 tools/check_datetime_tz.py` は、対象 `.py` が構文解析・読み込みできない場合（構文エラー・非 UTF-8・NUL バイト混入・病的に深いネスト等）も「違反なし」として黙殺せず **非ゼロ終了** にする（stderr に `⚠️` 付きで対象ファイルを明示）。この exit 1 は「TZ 違反が残っている」（`❌`）とは限らない — stderr の先頭記号で区別する（`❌` = TZ 違反 / `⚠️` = 解析不能）。運用者は明示されたファイル自体（無関係な `.py` の構文エラー等）を直すか、意図的に検査対象外とする場合は理由をコミットメッセージか Issue に残す。

> 関連: `tools/check_datetime_tz.py`（機械チェック）/ `tools/generate_project_context.py`（スナップショット時刻）/ `datetime-rules-detail.md`（実装パターン全文）/ `session-safety-rules.md`（JST 明示の模範テンプレート）
