#!/bin/bash
set -euo pipefail
# PreToolUse ルーター: Bash ツール実行前のチェックを1つのフックに統合
# トークン最適化: 複数の PreToolUse(Bash) フック → 1つに統合
#
# stdin から JSON を受け取り、コマンド内容に応じて適切なチェックスクリプトに委譲する。
# 各チェックスクリプトは引き続き独立したファイルとして存在する（保守性維持）。
#
# プロジェクト固有のチェック（画像生成モデル制約・SNS 投稿クールダウン等）を
# 追加したい場合は、本ルーターに分岐を足してチェックスクリプトを呼び出す。

INPUT=$(cat)
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/hook_block.sh
source "$HOOK_DIR/lib/hook_block.sh"
# shellcheck source=lib/env_allowlist.sh
source "$HOOK_DIR/lib/env_allowlist.sh"

# ツール名を抽出（printf を使い、バックスラッシュを含む入力でも echo のエスケープ解釈に依存しない）
TOOL_NAME=$(printf '%s\n' "$INPUT" | jq -r '.tool_name // ""')

# MCP 経由の PR 作成（mcp__github__create_pull_request）も Bash の gh pr create と同じ
# 事前ゲート（未コミット検出 + セルフレビュー機械チェック + Layer 1 リマインダー）に通す。
# クラウド環境では gh pr create が proxy 403 で失敗し MCP 経由が PR 作成の主経路になるため、
# matcher 外だと Layer 0 ゲートを完全素通りしてしまう（再発防止・FAIR Layer 1 スキップの根本原因）。
if [ "$TOOL_NAME" = "mcp__github__create_pull_request" ]; then
  printf '%s\n' "$INPUT" | "$HOOK_DIR/pre-pr-create-check.sh"
  exit $?
fi

# Cloudflare MCP ツールのアローリスト化（Issue #56）
# `permissions.allow` / `deny` はツール名の列挙にすぎず、Cloudflare MCP サーバーに
# 新しいツールが増えると allow にも deny にも無いまま確認プロンプトなしで素通りする。
# 許可集合の正本（SSOT）は docs/03_design/infrastructure/cloudflare-infrastructure.md §7.4。
# 判定ロジックの実体は pre-cloudflare-mcp-allowlist-check.sh（正本を複製しない・fail-closed）。
case "$TOOL_NAME" in
  mcp__Cloudflare_Developer_Platform__*)
    "$HOOK_DIR/pre-cloudflare-mcp-allowlist-check.sh" "$TOOL_NAME"
    exit $?
    ;;
esac

# コマンド文字列を抽出（JSON の tool_input.command フィールド）
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# git push チェック（main/master 直接 push のブロック）
# 【注意】"git" と "push" が隣接する 'git\s+push' だけだと `git -C <path> push ...` を
# 取りこぼす（critical 1 の再発防止・pre-git-push-check.sh 側の再設計と対）。
# "git" と "push" が単語としてどちらもコマンド中に現れれば委譲し、精密な判定は
# pre-git-push-check.sh 側のセグメント解析に任せる（push でないなら向こうが allow で返す）。
if echo "$COMMAND" | grep -qE '\bgit\b' && echo "$COMMAND" | grep -qE '\bpush\b'; then
  echo "$INPUT" | "$HOOK_DIR/pre-git-push-check.sh"
  exit $?
fi

# PR 作成チェック（未コミット・未push 検出 + セルフレビュー機械チェック）
if echo "$COMMAND" | grep -qE '(gh\s+pr\s+create|poll_pr_reviews)'; then
  echo "$INPUT" | "$HOOK_DIR/pre-pr-create-check.sh"
  exit $?
fi

# Cloudflare Workers スクリプトへの破壊的操作チェック（Issue #613 / #615・本番 Worker 誤削除の再発防止）
# 🔴 "delete" は汎用語（コミットメッセージ・rm のコメント等にも出現しうる）なので、
# git push / PR 作成チェックと違い **ブロック時のみ** router を終了する（allow ならそのまま
# 下の機密ファイルチェックへフォールスルーする。誤って早期 exit すると以降の全チェックを
# 素通りさせてしまうため、無条件 `exit $?` にしない）。
if echo "$COMMAND" | grep -qiE 'delete'; then
  if ! echo "$INPUT" | "$HOOK_DIR/pre-cloudflare-destructive-check.sh"; then
    exit 2
  fi
fi

# 機密ファイルへの Bash 経由アクセスをブロックする共通判定（#384 / 下流監査で全面刷新）
#
# 🔴 なぜ permissions.deny があるのに必要か（射程差）:
#    `permissions.deny` の `Read(**/...)` は **cwd アンカー**でプロジェクトディレクトリの外を守らない。
#    公式仕様上、Read 系 deny は Bash の認識済みファイルコマンド（cat/head/tail/sed 等）にも適用される
#    ため **cwd 内は deny が効く**（下流リポジトリでの対照実験で確認）。一方 `~/.ssh/id_rsa` /
#    `/tmp/foo.pem` / `~/.aws/credentials` のような **cwd 外の実パスは deny の射程外**で、
#    本関数群だけが第2層としてそこを塞ぐ。
#
# 設計方針と限界（過信しないこと）:
#   - **コマンド列挙型のため完全防御ではない**。`python3 -c "open(...)"` 等の任意コードは塞げない。
#     残余リスクはコンテナ隔離が引き受けており、本層は「うっかり漏洩」の抑止が目的
#   - クォート（"file" / 'file'）・リダイレクト（`cmd < file`）・コマンド置換（`$(cat x)` /
#     `` `cat x` ``）・サブシェル（`(cat x)`）経由も対象にする。ただし **パス途中でクォートを割る
#     難読化**（`cat ~/.ss''h/id_rsa`）は塞げない。`eval` 経由と同じ「意図的な回避」の類であり、
#     字面から実パスを復元するにはシェルの語彙解析が要るため本層の射程外とする
#   - **grep / rg は「検索パターン以外の位置引数」を対象にする**: 検索パターンとファイル引数を
#     字面で区別できないため長らく対象外にしていたが、`Bash(grep:*)` / `Bash(rg:*)` を
#     `permissions.allow` に載せると静的評価で決着して classifier の審査にも到達しなくなるため、
#     第2層で見張る必要が生じた（Layer 1 セキュリティ指摘）。**`/` か `~` を含むトークンだけに
#     絞ると `grep secret .env` のような cwd 相対の機密ファイルが素通りする**（実測）ので、
#     `<cmd> [フラグ] <パターン> [ファイル...]` という呼び出し形を使い
#     **非フラグトークンの 2 個目以降**（＋パス様トークン）を候補にする。
#     `grep -rn "id_rsa" docs/` のような検索語は 1 個目なので誤ブロックしない
#   - **`.`（dot source）はコマンド位置に現れたときだけ対象にする**: `_sfa_cmds` に素で足すと
#     `find . -name credentials` / `git status . x` のカレントディレクトリ引数を誤ブロックするため、
#     行頭または `;` `&` `|` `(` 等の区切り直後の `.` に限定して抽出する（`source` と `.` は
#     POSIX 上の同義語であり、片方だけ守るのは片手落ちになる）
#   - コマンド名の直後の引数だけを見るため、"git commit -m '... .env ...'" は誤検知しない
#     （ただし読み取り元がフラグ値や第2引数以降に来やすい cp/install/tar/rsync/scp は例外。下記参照）

# 判定対象のファイル名トークンを列挙する（コマンド直後の第1引数 + リダイレクト先 + 下記の多引数コマンド）
# 引数 $1: 走査対象のコマンド文字列（省略時は $COMMAND・生の値）。
# 呼び出し側 _sfa_candidate_tokens_all が「生のコマンド」と「クォート・バックスラッシュを除去した
# 正規化コマンド」の両方でこの関数を呼び、候補トークンを合算する（Issue #1083）。
_sfa_candidate_tokens() {
  local _sfa_src="${1:-$COMMAND}"
  # curl はここに含めない: _sfa_multi_cmds（下記）の「呼び出しブロック全体から非フラグ位置引数を
  # 全て候補にする」抽出が、ここでの「フラグ後の第1トークンのみ」抽出を常に包含する強い上位互換
  # のため、二重登録は正規化前（@ 剥がし未適用）の重複トークンを生むだけで検知漏れの防止には
  # ならない（#417 Layer 1 レビューで指摘）。
  # `ln`（#1089）: `ln -s <target> <linkname>` は `-s` がフラグとして読み飛ばされ、既存の
  # 「コマンド直後の第1非フラグ引数」抽出パターンで <target>（読み取り対象）がそのまま拾える。
  # リンク先（第2引数・書き込み方向）が機密パスを指すケースは対象外とする: 本ガードの目的は
  # 「機密ファイルの内容が Claude の文脈へ漏洩すること」の防止であり、書き込み先の防止は
  # 元々対象外（`curl -o` の扱い・#419 と同じ設計思想）。理由はコメントに残す（完了条件）。
  _sfa_cmds='cat|less|head|tail|more|source|cp|mv|install|base64|xxd|od|strings|tar|rsync|scp|sftp|ln'
  printf '%s\n' "$_sfa_src" \
    | grep -oE "(^|[[:space:];|&(\`{])(${_sfa_cmds})([[:space:]]+-[^[:space:];|&]+)*[[:space:]]+['\"]?[^[:space:];|&'\")]+" \
    | sed -E "s/.*[[:space:]]['\"]?//" || true
  printf '%s\n' "$_sfa_src" \
    | grep -oE "<[[:space:]]*['\"]?[^[:space:];|&'\")]+" \
    | sed -E "s/^<[[:space:]]*['\"]?//" || true
  # dot source（`. file`）: コマンド位置（行頭 or 区切り直後）の `.` のみを対象にする。
  # `find . -name x` のように **引数位置** の `.` は直前が素の空白なので一致しない
  printf '%s\n' "$_sfa_src" \
    | grep -oE "(^|[;|&(\`{][[:space:]]*)\.[[:space:]]+['\"]?[^[:space:];|&'\")-][^[:space:];|&'\")]*" \
    | sed -E "s/.*[[:space:]]['\"]?//" || true
  # 読み取り元・アーカイブ対象が「値を取るフラグの値」や「第2引数以降」に来やすいコマンドは
  # 第1非フラグ引数だけでは取りこぼす（例: `install -m 600 ~/.ssh/id_rsa /tmp/x` の値は `600`、
  # `tar czf out.tgz ~/.ssh` / `cp -r src ~/.ssh` の機密パスは第2引数・#395）。
  # 対象をこの5コマンドに絞り、呼び出しブロック全体から非フラグ位置引数を全て候補にする。
  # 値を取るフラグの値そのもの（上記の `600`）や書き込み先も一緒に候補へ混じるが、
  # 実在の機密名パターンに一致しない限り誤検知は起きないため許容する。
  _sfa_multi_cmds='cp|install|tar|rsync|scp'
  printf '%s\n' "$_sfa_src" \
    | grep -oE "(^|[[:space:];|&(\`{])(${_sfa_multi_cmds})[[:space:]]+[^;|&\`)]*" \
    | sed -E "s/^[[:space:];|&(\`{]?(${_sfa_multi_cmds})[[:space:]]+//" \
    | _sfa_tokenize_block || true
  # grep / rg 系（検索コマンド）は、パターンとファイル引数を字面で区別できない。
  # 🔴 `/` か `~` を含むパス様トークンだけに絞ると **cwd 相対の機密ファイルが素通りする**
  #    （実測: `grep secret .env` / `rg secret .env` が rc=0 で通り、`rg . ./.env` だけが止まる。
  #    `Bash(grep:*)` / `Bash(rg:*)` を allow に載せた以上、静的評価で決着して classifier にも
  #    到達しないため、この穴は `.env` 全文がそのまま文脈へ入ることを意味する）。
  # そこで候補を **「非フラグトークンのうち 2 個目以降」＋「`/` か `~` を含むトークン」** にする。
  # grep / rg の呼び出し形は `<cmd> [フラグ...] <パターン> [ファイル...]` であり、`_sfa_tokenize_block`
  # がフラグを落とすので **1 個目の非フラグトークン = 検索パターン**、2 個目以降がファイル操作対象。
  # これで `grep -rn "id_rsa" docs/`（パターンが機密名）は従来どおり誤ブロックせず、
  # `grep secret .env`（ファイルが機密）は捕捉できる。
  _sfa_search_cmds='grep|egrep|fgrep|rg|ag|ack'
  printf '%s\n' "$_sfa_src" \
    | grep -oE "(^|[[:space:];|&(\`{])(${_sfa_search_cmds})[[:space:]]+[^;|&\`)]*" \
    | sed -E "s/^[[:space:];|&(\`{]?(${_sfa_search_cmds})[[:space:]]+//" \
    | _sfa_tokenize_block \
    | awk '
        { if (NF) a[++n] = $0 }
        END {
          if (n <= 1) {
            # トークンが 1 個だけのときは「パターンだけ」か「パターンが空文字で消えてファイルだけが
            # 残った」かを字面で区別できない（`grep -n "" ~/.ssh/id_rsa` は `""` が空になり
            # ファイルだけが残る）。パス様のときだけ候補にする（fail-closed 側）。
            if (n == 1 && a[1] ~ /[\/~]/) print a[1]
          } else {
            # 2 個以上あるなら 1 個目は検索パターン。2 個目以降がファイル操作対象。
            for (i = 2; i <= n; i++) print a[i]
          }
        }' || true
  # curl は上記5コマンドと違い「書き込み先（-o/--output/--output-dir）」を持つダウンロードが
  # 主用途のため別パイプラインにする（#419）。上記と同列に混ぜると書き込み先の値（ローカルへの
  # 保存先）が読み取り候補に混入し誤検知する（例: `curl -o /tmp/id_rsa https://example.com/file` は
  # ローカルの id_rsa を「読む」のではなくダウンロード結果で「上書きする」操作で、本ガードの目的
  # （機密ファイルの内容が Claude の文脈に漏洩することの防止）の対象外。書き込みによる上書き・
  # 破壊の防止は本ガードの守備範囲外＝`echo x > ~/.ssh/id_rsa` のような他のリダイレクト書き込みも
  # 元々対象外であり、curl -o だけを特別扱いしても防御水準は後退しない）。
  # 一方 `-T ~/.ssh/id_rsa`（アップロード＝読み取り）・`--data-binary @~/.aws/credentials`
  # （`@file` 構文でのローカル読み込み）は本物の読み取りなので候補に残す（#417）。
  # `-o` は `-sSfo <値>` のような結合短縮オプション（末尾が `o` で終わるクラスタ）でも次トークンを
  # 値として消費するため、フラグ側の正規表現は `-[A-Za-z]*o` で結合形も含めて拾う（`-O`〔大文字・
  # remote-name〕は値を取らない別フラグなので対象外のまま）。`--output-dir` は `--output` の
  # 前方一致で誤って途中一致しないよう、`[[:space:]]+`/`=` の直後境界チェックにより区別される。
  # 先頭の `@` はクォート同様に剥がし、ディレクトリベースの判定（`~/.aws/**` 等）が
  # `@` 付きトークンでも一致するようにする。クォート付き `"@path"` は先にクォートを剥がしてから
  # `@` を剥がす（1回の sed 置換に `['"@]` をまとめて詰めると `"@path"` の `@` が剥がれ残るため
  # 2段階にする、共通処理は `_sfa_tokenize_block` に集約）。
  # さらに URL（`scheme://...`）そのものは実在するローカルファイルパスではないため、
  # トークンの語尾がたまたま `credentials` 等に一致しても候補から除外する（例:
  # `curl https://api.example.com/v1/credentials` は API パスであり読み取り対象のローカル
  # ファイルではない・#419）。**ただし `file://` はローカルファイルを実際に読み出す curl 対応
  # スキームのため除外対象に含めない**（`curl file:///home/user/.ssh/id_rsa` を除外すると
  # 秘密鍵の内容が読み出され漏洩する。安全側に倒すため「除外してよいスキーム」を明示的な
  # ネットワーク系スキームの許可リストにし、未知のスキームは既定で候補に残す）。
  printf '%s\n' "$_sfa_src" \
    | grep -oE "(^|[[:space:];|&(\`{])curl[[:space:]]+[^;|&\`)]*" \
    | sed -E "s/^[[:space:];|&(\`{]?curl[[:space:]]+//" \
    | sed -E 's/(^|[[:space:]])(-[A-Za-z]*o|--output|--output-dir)=[^[:space:]]+/ /g; s/(^|[[:space:]])(-[A-Za-z]*o|--output|--output-dir)[[:space:]]+[^[:space:]]+/ /g' \
    | _sfa_tokenize_block \
    | grep -viE '^(https?|ftps?|sftp|scp|smtps?|imaps?|pop3s?|ldaps?|dicts?|telnets?|tftp|gophers?|rtsp|rtmp|mqtt|wss?)://' || true
}

# _sfa_multi_cmds / curl 抽出の共通後段（トークン化 → フラグ除外 → クォート/@ 剥がし）
_sfa_tokenize_block() {
  tr -s '[:space:]' '\n' \
    | grep -vE '^-|^$' \
    | sed -E "s/^['\"]//;s/^@//;s/['\")]\$//"
}

# クォート・バックスラッシュを除去した正規化コマンド文字列を作る（Issue #1083）。
# `_sfa_candidate_tokens` の抽出パターンはクォート文字（`'` `"`）を「トークンの終端」として
# 扱うため、判定対象の語の途中にクォートが挟まると語が分断されて判定をすり抜ける
# （例: `cat .en"v"` → 生トークンは `.env` にならず `.en` で切れる）。バックスラッシュも同様
# （`\.env` はシェル上 `.env` と等価だが、素の文字列比較では別語になる）。
# これらの文字を単純に取り除くと、シェルが実際に行う「隣接するクォート/非クォート断片の結合」を
# 近似できる（`.e"n"v` → `.env` / `\.env` → `.env`）。除去した正規化コピーに同じ抽出パターンを
# 再適用し、生トークンと正規化トークンの **両方** を判定対象にする（どちらか一方でも一致すれば
# ブロック＝fail-closed。正規化はあくまで「候補の追加」であり、既存の生トークン判定を置き換えない）。
#
# 🔴 **開きクォート（直前が空白・行頭・コマンド区切り）は消さない**（Layer 1 セルフレビューが
#    実測した誤発火の是正）。全クォートを無条件に消すと、引用テキストの中にあるコマンド名が
#    `_sfa_candidate_tokens` の「コマンド位置」パターン `(^|[[:space:];|&(\`{])` に一致するように
#    なり、実行されない言及まで遮断される（実測: `git commit -m "cat <対象> to check contents"` が
#    origin/main では rc=0 だったのに rc=2 へ退行した）。語の**途中**にあるクォートだけを消せば、
#    シェルの断片結合（`.e"n"v` → `.env`）は近似できるうえ、開きクォートが残るためコマンド位置は
#    生コマンドと同じまま保たれる（`cat ".e""nv"` は開き `"` が残り `".env` となって、抽出側の
#    `['\"]?` が剥がすので従来どおりブロックされる）。
# バックスラッシュは新しいコマンド位置を作らない（`\cat` は上記文字クラスに一致しない）ため
# 従来どおり全除去してよい。
_sfa_dequote_command() {
  printf '%s' "${1:-$COMMAND}" \
    | sed -e 's/\\//g' \
    | sed -E ':a; s/([^[:space:];|&(`{])["'"'"']/\1/; ta'
}

# コマンド置換（`$(...)` ・ `` ` ` ``）ブロック**全体**を中立プレースホルダ `~` へ畳み込む
# （Issue #1091・穴1）。`_sfa_candidate_tokens` の抽出パターンは終端文字クラスに `)` を含むため、
# `cat $(pwd)/<機密ファイル>` のように機密ファイルが置換ブロックの**外側**にあるケースでは
# `$(pwd` でトークンが切れて `/<機密ファイル>` に到達できない。置換ブロックの中身を静的に
# 実行せず短い中立文字列へ置き換えてから通常のトークン抽出にかければ、`)` による打ち切りが
# 起きなくなる（`cat $(pwd)/<機密ファイル>` → `cat ~/<機密ファイル>`）。
# 🔴 **プレースホルダは `X` ではなく `~` を使う**（Layer 1 セルフレビュー CRITICAL 指摘の是正・
#    実機再現）: `_sensitive_file_access` の「秘密ディレクトリそのもの」判定は
#    `^([~.]?/)?\.(ssh|aws|gnupg)(/|$)` のように **先頭アンカー**（`~` または `/` で始まる）を
#    要求する。`docs/.ssh/README.md` のようなプロジェクト内の同名ディレクトリを誤ブロックしない
#    ための意図的な設計であり、`X/.ssh` のようにプレースホルダが `~`/`/` 以外だとこのアンカーが
#    成立せず、`cp -r $(pwd)/.ssh /tmp` が fail-open した。置換の中身は静的に解決できず絶対パスの
#    可能性を排除できないため、fail-closed 側に倒して「絶対パス相当」として扱う `~` を使う。
# 🔴 **ネストした `$(...)`（例: `$(echo $(pwd))`）は変化が無くなるまで最大5回繰り返し適用して
#    解消する**（Layer 1 セルフレビュー CRITICAL 指摘・実機再現: `cat $(echo $(pwd))/.ssh/id_rsa`
#    が 1 回適用だと `cat $(echo ~)/.ssh/id_rsa` のまま外側の `$(` が残り、`_sfa_candidate_tokens`
#    が `$(echo` で打ち切られて機密ファイルを検知できなかった＝fail-open）。5 回で足りない深いネストは
#    実運用でまず出現しないため、`_sfa_flatten_incomplete` が残骸検知で fail-closed に倒す。
_sfa_flatten_substitutions() {
  _sfa_flat_src="${1:-$COMMAND}"
  _sfa_flat_i=0
  while [ "$_sfa_flat_i" -lt 5 ]; do
    _sfa_flat_next=$(printf '%s' "$_sfa_flat_src" | sed -E 's/\$\([^()]*\)/~/g; s/`[^`]*`/~/g')
    [ "$_sfa_flat_next" = "$_sfa_flat_src" ] && break
    _sfa_flat_src="$_sfa_flat_next"
    _sfa_flat_i=$((_sfa_flat_i + 1))
  done
  printf '%s' "$_sfa_flat_src"
}

# `_sfa_flatten_substitutions` が完全に畳み込めなかった残骸（未解決の `$(` / `` ` ``）が
# 残っていないかを検査する（Layer 1 セルフレビュー CRITICAL 指摘の是正）。クォート文字列内に
# リテラル `)` を含む置換（例: `$(echo "x)")`）は `[^()]*` がクォート規則を認識しないため
# 境界を誤判定し、繰り返し適用でも解消しない未閉じの `$(` が残ることがある。この残骸が
# 残ったまま通常判定に進むと、置換の外側にある機密ファイルが検知範囲外へ抜ける（fail-open）。
# 残骸を検出したら `_sfa_flatten_incomplete` が真を返し、呼び出し側は fail-closed でブロックする。
_sfa_flatten_incomplete() {
  _sfa_fi_flat=$(_sfa_flatten_substitutions "$COMMAND")
  case "$_sfa_fi_flat" in
    *'$('*) return 0 ;;
    *'`'*) return 0 ;;
    *) return 1 ;;
  esac
}

# クォート文字列内にリテラル `)` を含む置換（例: `$(echo "x)")`）は、`_sfa_flatten_incomplete`
# の残骸検知だけでは検知できない場合がある（Layer 1 セルフレビュー CRITICAL 指摘の是正・実機再現）。
# `[^()]*` はクォート内の `)` で境界を誤って早期に閉じるため、抽出された置換ブロックの中身に
# 開いたままのクォート（`"` / `'` の出現数が奇数）が残る。これを検出したら、境界誤判定が
# 起きている強いシグナルとして fail-closed でブロックする。
_sfa_quote_imbalance() {
  _sfa_qi_hit=1
  while IFS= read -r _sfa_qi_block; do
    [ -n "$_sfa_qi_block" ] || continue
    _sfa_qi_dq=$(printf '%s' "$_sfa_qi_block" | tr -cd '"' | wc -c)
    _sfa_qi_sq=$(printf '%s' "$_sfa_qi_block" | tr -cd "'" | wc -c)
    if [ $((_sfa_qi_dq % 2)) -ne 0 ] || [ $((_sfa_qi_sq % 2)) -ne 0 ]; then
      _sfa_qi_hit=0
      break
    fi
  done <<EOF
$(_sfa_substitution_blocks)
EOF
  return $_sfa_qi_hit
}

# コマンド置換（`$(...)` ・ `` ` ` ``）の中身だけを 1 階層分抽出する（Issue #1083 / #1091）。
# 対象を置換の中身だけに絞る理由: コマンド文字列全体を対象にすると
# `git commit -m 'update .env handling docs'` のような「.env について言及しているだけの
# 引用テキスト」まで誤ブロックする（#495 の誤発火の再発）。置換の中身（実際にファイル名の
# 一部として展開されうる箇所）だけに絞ることで、通常のコミットメッセージ・ドキュメント編集は
# 通しつつ、置換経由の展開だけを fail-closed で塞ぐ。
_sfa_substitution_blocks() {
  printf '%s\n' "$COMMAND" | grep -oE '\$\([^()]*\)' | sed -E 's/^\$\(//; s/\)$//'
  printf '%s\n' "$COMMAND" | grep -oE '`[^`]*`' | sed -E 's/^`//; s/`$//'
}

# コマンド置換の中身から候補トークンを抽出する（Issue #1091・穴2/穴3）。
# 旧実装（`_sfa_substitution_env_tokens`）は置換の中身を生の文字列のまま `.env` リテラルで
# grep しており、① 中身側のクォート分断（`echo .en"v"`）に対して正規化が未適用（穴2）、
# ② `.env` 以外の機密ファイル（`echo ~/.ssh/id_rsa` 等）を構造上検知できない（穴3）という
# 2つの欠陥があった。本関数は置換ブロックごとに ①`_sfa_dequote_command` で正規化してから
# ②`_sfa_tokenize_block` で空白分割・フラグ除外・クォート/@ 剥がしを行い、生の単語トークンを
# そのまま返す。`.env` 限定ではなく合流先の `_sfa_candidate_tokens_all` が両方の判定
# （`_sfa_env_access` / `_sensitive_file_access`）に渡すため、判定パターンの拡張はここでは
# 行わず候補トークンの提供に徹する。
_sfa_substitution_inner_tokens() {
  _sfa_substitution_blocks | while IFS= read -r _sfa_block; do
    [ -n "$_sfa_block" ] || continue
    printf '%s' "$(_sfa_dequote_command "$_sfa_block")" | _sfa_tokenize_block
  done
}

# 判定対象トークンの合算窓口（Issue #1083 / #1091）。生コマンド・正規化コマンド・置換ブロックを
# 中立プレースホルダへ畳んだ生コマンド／正規化コマンド・置換の中身のトークン、の
# 5系統から候補を集める。呼び出し側（_sfa_env_access / _sensitive_file_access）は本関数だけを使う。
_sfa_candidate_tokens_all() {
  _sfa_candidate_tokens "$COMMAND"
  _sfa_candidate_tokens "$(_sfa_dequote_command)"
  _sfa_candidate_tokens "$(_sfa_flatten_substitutions "$COMMAND")"
  _sfa_candidate_tokens "$(_sfa_flatten_substitutions "$(_sfa_dequote_command)")"
  _sfa_substitution_inner_tokens
}

# .env（本物のみ。.env.example 等のテンプレートは通す）
# 判定の実体は lib/env_allowlist.sh の hook_env_guard_verdict（SSOT・Issue #493）。
# pre-file-tool-env-guard.sh の _env_guard_verdict と同じ関数を source して使うことで、
# ひな形の種類を増やすときの片方だけ更新される drift を構造的に無くす。
_sfa_env_access() {
  _sfa_hit=1
  while IFS= read -r _sfa_tok; do
    [ -n "$_sfa_tok" ] || continue
    if hook_env_guard_verdict "$_sfa_tok"; then
      _sfa_hit=0; break
    fi
  done <<EOF
$(_sfa_candidate_tokens_all)
EOF
  return $_sfa_hit
}

# 鍵・証明書・認証情報
#
# 判定は **ベース名スコープ**で行う（`config/credentials/README.md` のような **ディレクトリ名の一致**で
# 誤発火させない）。逆にベース名の中では語境界（先頭 or `-_.` 区切り）を見るため、
# `gcp-service-account.json` / `backup-id_rsa` のような **前置語つきの実ファイル名**も捕捉する。
_sensitive_file_access() {
  _sfa_hit=1
  while IFS= read -r _sfa_tok; do
    [ -n "$_sfa_tok" ] || continue
    # 判定は小文字化した文字列に対して行う（`foo.PEM` / `ID_RSA` のような大文字表記で
    # 拡張子・語境界の判定だけがすり抜けるのを防ぐ）
    _sfa_lower=$(printf '%s' "$_sfa_tok" | tr '[:upper:]' '[:lower:]')
    _sfa_base="${_sfa_lower##*/}"
    # 公開鍵は秘密ではない（`id_rsa.pub` を語境界判定で捕まえないため先に通す）
    case "$_sfa_base" in
      *.pub) continue ;;
    esac
    # 秘密ディレクトリ配下はファイル名を問わず対象（`~/.ssh/**` ・ `~/.aws/**` ・ `~/.gnupg/**`）。
    # **ホーム基準・絶対パス・先頭要素のときだけ** 一致させる（`docs/.ssh/README.md` のような
    # プロジェクト内の同名ディレクトリを巻き込まないため）。ディレクトリ自体を渡す
    # `cp -r ~/.ssh /tmp` も捕捉する。文書拡張子の除外より **先に** 評価する
    # （秘密ディレクトリ配下は拡張子を `.md` にしただけで素通りしてはならない）
    if printf '%s' "$_sfa_lower" \
      | grep -qE '^([~.]?/)?\.(ssh|aws|gnupg)(/|$)|^[~/][^[:space:]]*/\.(ssh|aws|gnupg)(/|$)'; then
      _sfa_hit=0; break
    fi
    case "$_sfa_base" in
      # 解説ドキュメントは対象外（"credentials" を扱う記事・手順書で通常運用が止まるのを防ぐ）
      *.md|*.markdown|*.rst|*.adoc|*.html|*.htm) continue ;;
      # 鍵・証明書は拡張子で判定
      *.pem|*.key|*.p12|*.pfx|*.jks|*.keystore) _sfa_hit=0; break ;;
    esac
    # 認証情報はベース名の「語」で判定（語境界 = 先頭 or `-_.` 区切り）
    if printf '%s' "$_sfa_base" \
      | grep -qE '(^|[-_.])(git-credentials|netrc|credentials|service-accounts?|id_rsa|id_dsa|id_ecdsa|id_ed25519)([-_.][^/]*)?$'; then
      _sfa_hit=0; break
    fi
  done <<EOF
$(_sfa_candidate_tokens_all)
EOF
  return $_sfa_hit
}

# コマンド置換の構造が複雑すぎて安全に畳み込めない場合は fail-closed でブロックする
# （Layer 1 セルフレビュー CRITICAL 指摘の是正・実機再現: ネストした `$(...)` やクォート内に
# リテラル `)` を含む置換で、機密ファイルが置換ブロックの外側にあるケースを検知できなかった）。
if _sfa_flatten_incomplete || _sfa_quote_imbalance; then
  hook_block "BLOCK: コマンド置換の構造が複雑で安全性を検証できません（ネストした \$(...) またはクォート内に ) を含む置換の可能性）。
単純な形に書き直すか、置換結果を変数に代入してから使ってください。"
fi

# .env ファイルへのアクセスをブロック
if _sfa_env_access; then
  hook_block "BLOCK: .env ファイルへのアクセスは禁止されています"
fi

# 鍵・証明書・認証情報へのアクセスをブロック（#384）
if _sensitive_file_access; then
  hook_block "BLOCK: 機密ファイル（鍵・証明書・認証情報）への Bash 経由アクセスは禁止されています。
対象: *.pem / *.key / *.p12 / *.pfx / *.jks / *.keystore / ~/.ssh・~/.aws・~/.gnupg 配下 /
      ベース名が credentials・service-account・id_rsa 等の語に語境界で一致するファイル
      （.md 等の文書と .pub の公開鍵は対象外）
理由: permissions.deny は cwd アンカーのため cwd 外を守れず、本フックが第2層を担う。
デグレ検証: bash tools/test_sensitive_file_guard.sh"
fi

# 承認プロンプトに落ちる Bash を、プロンプトになる前に差し戻す（無人ルーティンの無限停止防止・#578）
#
# クラウド実行環境には bwrap / sandbox-exec が無く（実測: MISSING・Seccomp 0）、settings.json の
# sandbox.enabled は起動できない。そのため「作業ディレクトリ・セッション一時領域の外への書き込み /
# 削除」は auto モードの classifier が自動承認せず、無人セッションでは承認待ちのまま停止する。
# ここでブロックすると Claude にはツール失敗として返るため、代替経路へ自己修正できる。
if _wwg_reason=$(printf '%s' "$INPUT" | python3 "$HOOK_DIR/lib/workspace_write_guard.py" 2>/dev/null); then
  :
else
  _wwg_status=$?
  if [ "$_wwg_status" -eq 1 ] && [ -n "$_wwg_reason" ]; then
    hook_block "$_wwg_reason
デグレ検証: bash tools/test_workspace_write_guard.sh"
  fi
fi

# 該当なし: 許可
exit 0
