#!/bin/bash
# 安全なプロセス掃除ヘルパー（Issue #490 / L-134）
#
# `pkill -f <パターン>` は **フルコマンドライン照合** のため、パターン文字列を直書きした
# 自分自身のシェル（`bash -c "pkill -f 'next start --port 3100'"`）にもマッチし、
# セッションごと落ちる（実測 exit 144）。本ヘルパーは自分自身・祖先プロセス・
# **自分が fork した子孫プロセス**・PID 1 を除外してから終了シグナルを送る。
#
#   bash tools/safe_process_kill.sh 'next start --port 3100'          # 一致プロセスを終了
#   bash tools/safe_process_kill.sh --dry-run 'next start'            # 対象 PID を出すだけ
#   bash tools/safe_process_kill.sh --signal TERM 'vitest'            # 既定は KILL
#   bash tools/safe_process_kill.sh --self-test                       # 自己テスト
#
# 終了コード: 0 = 正常終了（対象 0 件でも 0）/ 1 = 引数不正・self-test 失敗
set -uo pipefail

SIGNAL="KILL"
DRY_RUN=0

# 自分自身・祖先プロセス（親・祖父…）・PID 1 の PID 集合を返す（1 行 1 件）。
# これらを除外しないと「掃除コマンド自身」や init を殺して自滅する。
excluded_pids() {
  # PID 1（init）は何があっても対象にしない。コンテナでは init を落とすと
  # セッションごと消える（祖先チェーンは pid > 1 で止まるため明示的に足す）。
  echo 1
  local pid=$$
  local guard=0
  while [ "$pid" -gt 1 ] && [ "$guard" -lt 32 ]; do
    echo "$pid"
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -z "$pid" ] && break
    guard=$((guard + 1))
  done
}

# PID が除外集合（空白区切り）に含まれるか。
# 🔴 `excluded_pids | grep -q` は使わない: `set -o pipefail` 下で grep の早期終了が
# 上流に SIGPIPE を送り、一致していてもパイプライン全体が非ゼロになる（実測）。
is_excluded() {
  local pid="$1" set_str="$2"
  case " $set_str " in
    *" $pid "*) return 0 ;;
    *) return 1 ;;
  esac
}

# PID が自分自身（$$）の子孫かどうかを ps スナップショットから判定する。
# 🔴 これが無いと自滅が残る: コマンド置換・パイプラインで fork した子シェルは
# 親と同じコマンドライン（＝パターン文字列を含む）を持つため、祖先除外だけでは
# 素通りして自分の一部を kill する（実測: 一致プロセスが無いパターンでも 2 件出る）。
is_descendant() {
  local pid="$1" snapshot="$2" guard=0 parent
  while [ "$pid" -gt 1 ] && [ "$guard" -lt 32 ]; do
    parent="$(printf '%s\n' "$snapshot" | awk -v p="$pid" '$1 == p { print $2; exit }')"
    [ -z "$parent" ] && return 1
    [ "$parent" = "$$" ] && return 0
    pid="$parent"
    guard=$((guard + 1))
  done
  return 1
}

# パターンに一致し、かつ除外集合・自分の子孫に含まれない PID を 1 行 1 件で出力する。
list_targets() {
  local pattern="$1"
  local snapshot excluded pid ppid args
  snapshot="$(ps -eo pid=,ppid=,args= 2>/dev/null)"
  excluded="$(excluded_pids | tr '\n' ' ')"
  # パイプではなく here-string で回す（パイプだと本体が subshell になり、
  # その subshell 自身が親と同じコマンドラインを持って自己マッチの温床になる）
  while read -r pid ppid args; do
    [ -z "$pid" ] && continue
    case "$args" in
      *"$pattern"*) ;;
      *) continue ;;
    esac
    # 除外集合（自分・祖先・PID 1）に一致したらスキップ
    is_excluded "$pid" "$excluded" && continue
    # 自分が fork した子孫（同じコマンドラインを持つ）もスキップ
    is_descendant "$pid" "$snapshot" && continue
    echo "$pid"
  done <<< "$snapshot"
}

# パターンが広すぎる（ほぼ全プロセスに当たる）指定を弾く。
# 照合は `*"$pattern"*` の部分一致なので、短すぎる語・空文字は無差別 kill になる。
validate_pattern() {
  local pattern="$1"
  if [ ${#pattern} -lt 3 ]; then
    echo "[safe-process-kill] パターンが短すぎます（3 文字以上）: '${pattern}'" >&2
    return 1
  fi
  return 0
}

# シグナル名・番号が実在するか（kill -l で解決できるか）を確認する。
validate_signal() {
  local sig="$1"
  kill -l "$sig" >/dev/null 2>&1 && return 0
  echo "[safe-process-kill] 不明なシグナルです: '${sig}'" >&2
  return 1
}

self_test() {
  local failures=0

  # ケース 1: 自分自身のコマンドラインに含まれる語では自分を対象にしない
  # （パターンはスクリプト名そのもの＝自分の args に必ず含まれる語を使う。
  #  ここを固定文字列にすると、ファイル名を変えたコピーで検査が空振りする）
  local self_pattern self_hits
  self_pattern="$(basename "$0")"
  self_hits="$(list_targets "$self_pattern" | tr '\n' ' ')"
  if is_excluded "$$" "$self_hits"; then
    echo "[FAIL] 自分自身の PID ($$) が対象に含まれた（自滅する）" >&2
    failures=$((failures + 1))
  else
    echo "[PASS] 自分自身の PID を対象から除外した"
  fi

  # ケース 2: 祖先プロセス（親シェル）を対象にしない
  local parent
  parent="$(ps -o ppid= -p $$ 2>/dev/null | tr -d ' ')"
  local excluded_set
  excluded_set="$(excluded_pids | tr '\n' ' ')"
  if [ -n "$parent" ] && ! is_excluded "$parent" "$excluded_set"; then
    echo "[FAIL] 親プロセス ($parent) が除外集合に入っていない" >&2
    failures=$((failures + 1))
  else
    echo "[PASS] 親プロセスを除外集合に含めた"
  fi

  # ケース 3: 無関係な他プロセスは正しく検出して終了できる
  local marker="safe-process-kill-selftest-$$"
  ( exec -a "$marker" sleep 30 ) &
  local victim=$!
  disown "$victim" 2>/dev/null || true
  sleep 0.3
  local found
  found="$(list_targets "$marker")"
  if ! is_excluded "$victim" "$(printf '%s' "$found" | tr '\n' ' ')"; then
    echo "[FAIL] テスト用プロセス ($victim) を検出できなかった" >&2
    failures=$((failures + 1))
    kill -9 "$victim" 2>/dev/null
  else
    printf '%s\n' "$found" | while read -r p; do [ -n "$p" ] && kill -9 "$p" 2>/dev/null; done
    sleep 0.3
    if kill -0 "$victim" 2>/dev/null; then
      echo "[FAIL] テスト用プロセス ($victim) を終了できなかった" >&2
      failures=$((failures + 1))
      kill -9 "$victim" 2>/dev/null
    else
      echo "[PASS] 対象プロセスを検出して終了した"
    fi
  fi

  # ケース 4: 広すぎるパターン・不正シグナルは実行前に弾く
  if bash "$0" --dry-run "ab" >/dev/null 2>&1; then
    echo "[FAIL] 短すぎるパターン 'ab' を弾けなかった" >&2
    failures=$((failures + 1))
  else
    echo "[PASS] 広すぎるパターンを実行前に拒否した"
  fi
  if bash "$0" --signal NOPE "safe-process-kill-nomatch" >/dev/null 2>&1; then
    echo "[FAIL] 不正シグナル 'NOPE' を弾けなかった" >&2
    failures=$((failures + 1))
  else
    echo "[PASS] 不正なシグナル名を実行前に拒否した"
  fi

  # ケース 5: 自分が fork した子シェル（親と同じコマンドラインを持つ）を対象にしない。
  # 子プロセスのコマンドラインにしか現れないパターンを渡し、対象 0 件になることを確かめる
  local phantom_probe phantom_out
  phantom_probe="safe-kill-phantom-probe-$$"
  phantom_out="$(bash "$0" --dry-run "$phantom_probe" 2>&1)"
  if printf '%s' "$phantom_out" | grep -q "dry-run"; then
    echo "[FAIL] 自分が fork した子シェルを対象に含めた（自滅する）: ${phantom_out}" >&2
    failures=$((failures + 1))
  else
    echo "[PASS] 自分が fork した子シェルを対象から除外した"
  fi

  # ケース 6: PID 1（init）を対象にしない
  if is_excluded 1 "$excluded_set"; then
    echo "[PASS] PID 1 を除外集合に含めた"
  else
    echo "[FAIL] PID 1 が除外集合に入っていない（init を落としうる）" >&2
    failures=$((failures + 1))
  fi

  # ケース 7: `--signal` の値省略は即エラー終了する（無限ループしない）
  local sig_rc=0
  timeout 5 bash "$0" --signal >/dev/null 2>&1 || sig_rc=$?
  if [ "$sig_rc" -eq 124 ]; then
    echo "[FAIL] '--signal' の値省略で無限ループした（タイムアウト）" >&2
    failures=$((failures + 1))
  elif [ "$sig_rc" -eq 0 ]; then
    echo "[FAIL] '--signal' の値省略をエラーにしなかった" >&2
    failures=$((failures + 1))
  else
    echo "[PASS] '--signal' の値省略を即エラーにした"
  fi

  if [ "$failures" -gt 0 ]; then
    echo "❌ self-test: ${failures} 件失敗" >&2
    return 1
  fi
  echo "✅ self-test: 全ケース PASS"
  return 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --self-test) self_test; exit $? ;;
    --dry-run) DRY_RUN=1; shift ;;
    --signal)
      # 🔴 `shift 2` は残り 1 引数だと失敗して $# が減らず、while が無限ループする（実測）
      if [ $# -lt 2 ]; then
        echo "[safe-process-kill] --signal には値が必要です（例: --signal TERM）" >&2
        exit 1
      fi
      SIGNAL="$2"; shift 2 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) break ;;
  esac
done

if [ $# -lt 1 ]; then
  echo "[safe-process-kill] パターンを指定してください（--help で使い方）" >&2
  exit 1
fi

PATTERN="$1"
validate_pattern "$PATTERN" || exit 1
validate_signal "$SIGNAL" || exit 1
TARGETS="$(list_targets "$PATTERN")"

if [ -z "$TARGETS" ]; then
  echo "[safe-process-kill] 一致するプロセスはありません: ${PATTERN}"
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[safe-process-kill] 対象 PID（dry-run）:"
  printf '%s\n' "$TARGETS"
  exit 0
fi

printf '%s\n' "$TARGETS" | while read -r pid; do
  [ -z "$pid" ] && continue
  kill "-${SIGNAL}" "$pid" 2>/dev/null && echo "[safe-process-kill] killed pid=${pid} (SIG${SIGNAL})"
done
exit 0
