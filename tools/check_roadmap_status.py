#!/usr/bin/env python3
"""check_roadmap_status.py — roadmap.md の状態記述と GitHub Issue 実態の乖離を機械検知する（Issue #572）

【背景】`docs/02_requirements/roadmap.md` §7 更新ルール 3 は「マイルストーンを通過したとき、
§3 の通過判定チェックを埋め、§5.1 の状態を更新する。通過判定を 1 つでも満たさないまま
「通過」と書かない」と定めているが、これは人間の運用規律であり機械強制されていなかった。
本スクリプトはこの規律のうち機械的に検証可能な 2 点だけを検査する。

【検査する違反】
  1. 違反3（全件 Closed なのに「未着手」）: §2 の「束ねるスプリント」列から `SP-n` 集合を
     展開し、対応する GitHub Issue が全件 Closed にもかかわらず §5.1 の状態欄に「未着手」が
     残っている場合。
  2. 違反4（達成宣言なのに未チェック残り）: §5.1 の状態欄に達成宣言キーワード
     （`ACHIEVEMENT_KEYWORDS` = 「達成済み」「通過済み」。`**` 強調や絵文字などの装飾を
     挟んでいても部分文字列一致で検出する。例: 「✅ **通過済み**（…）」）があるのに、
     §3 の該当マイルストーンの通過判定チェックボックス（`- [ ]`）に未チェックが残っている場合。

     🔵 **抑制マーカー**（意図して未達のまま通過させたことを記録した場合の除外手段）:
     `<!-- roadmap-status-ok:{件数}: {理由} -->`（件数付き構文・Issue #784）を、§5.1 の該当
     マイルストーン行 **または** §3 の該当マイルストーン節（`### M-n:` から次の `### M-` まで）
     の **どちらかに** 書けば違反4 の検出から除外される（両方に書く必要はない）。
     🔴 **{件数} は「このマーカーが対象とする未チェック項目数」を宣言する**。実際の未チェック件数
     （`checklist['unchecked']`）と一致するときだけ抑制し、**不一致なら「マーカーが想定していない
     未チェックが増えた」として `violation4_suppression_count_mismatch` を報告する**（マイルストーン
     単位で fail-open だった旧実装の穴を塞ぐ・背景は Issue #784）。理由が空のマーカーは無効
     （`<!-- roadmap-status-ok:1: -->` や `<!-- roadmap-status-ok: -->` は抑制しない＝無条件の
     握り潰しを防ぐ）。抑制が効いた場合は黙って消さず、`🔵` を付けた情報行として stderr に出す
     （`❌`＝違反 / `⚠️`＝判定不能・件数なし旧構文の移行推奨 と記号で区別する）。

     🟡 **後方互換（件数なし旧構文）**: `<!-- roadmap-status-ok: {理由} -->`（コロン直後が数字+コロン
     でない）も引き続き受理し、旧来どおり件数照合なしで無条件に抑制する。ただし `⚠️` 付きで
     「件数付き構文へ移行してください」と stderr に警告を出す（fail-open のまま残る唯一の経路
     であることを毎回可視化し、放置されないようにする）。新規に書くマーカーは必ず件数付き構文を使う。

     ⚠️ **既知の限界（YAGNI により簡易実装）**:
     - 達成宣言キーワードの判定（`_has_achievement_keyword`）は、キーワード直後に代表的な
       否定語尾（`_NEGATION_SUFFIXES` = 「ではない」「とは言えない」「ていない」等）が
       続く場合だけを否定文として除外する。それ以外の言い回し（二重否定・離れた位置の
       否定等）は拾えない可能性がある。完璧な自然言語処理は行わない。
     - 抑制マーカーの理由テキストには `>` を書けない（`_SUPPRESSION_MARKER_RE` が
       `[^>]` で理由を切り出すため。ReDoS 対策）。また検索対象は `_SUPPRESSION_SCAN_MAX_LEN`
       文字までに切り詰めて走査する（同じく ReDoS 対策。切り詰めの詳細はその定数のコメント）。

【§2「束ねるスプリント」列の 4 形態】
  - 範囲: `` `SP-1`〜`SP-5` ``
  - 列挙: `` `SP-14` → `SP-15` / `SP-16` ``
  - 開区間: `` `SP-12` 以降 ``
  - なし: 判断ゲート等、束ねる SP-n が無い

【タイトル正規表現と `sprint_backlog_sync.py`（Issue #542）との関係】
`sprint_backlog_sync.py` 側は #542 で `SP_TITLE_RE`（1 パターン）から独自の `SP_TITLE_PATTERNS`
（3 パターン）へ移行済みで、**共有はしていない**。理由: 同スクリプトは Ready 条件③（先行 SP-n が
すべて Closed か）の判定に使うため、`improvement: SP-1 の ...` のような「SP-n に言及するだけの
副次 Issue」を本体と誤認すると新規スプリント着手が永久にブロックされる。そのため向こうは
パターン 2・3 の type プレフィックスを `feat` に限定している。
本スクリプトは roadmap.md と Issue 実態の整合性検査が目的で要求が異なるため、type プレフィックスを
限定しない（`[A-Za-z]+`）。**この差は意図的な分岐であり、揃えてはならない**（本ファイル側の
偽陽性リスクの検討は Issue #628）。

【GitHub API アクセス】
`gh` コマンドはクラウド実行環境に存在しない前提のため使わない。`GH_TOKEN`（無ければ
`GITHUB_TOKEN`）環境変数 + `urllib.request` で REST API を直叩きする。Issue 番号が事前に
分からないため `GET /repos/{owner}/{repo}/issues?state=all` をページネーションしながら
全件取得し、タイトルから `SP-n` を抽出する（`search_issues` はレート枠が別で厳しいため
使わない）。`/issues` エンドポイントは PR も返すため `"pull_request" in item` で除外する。

【終了コード】
  0 = 違反なし
  1 = 違反あり（❌ を stderr 行頭に付ける）
  2 = 判定不能（GH_TOKEN 未設定 / API 到達不可 / roadmap.md のパース失敗。⚠️ を stderr 行頭に付ける）
判定不能を「違反なし」として黙殺しない（`docs/rules/datetime-rules.md` の
`check_datetime_tz.py` に倣い、解析不能と違反ありを記号で区別する）。

【`tools/run_checks.sh` への配線について（SD-3 の仮定記録）】
本判定（GitHub API 到達を伴う実行）は `check_prod_drift.py` / `trigger_workers_build.py` /
`measure_gem_coverage.py` / `triage_improvements.py` の既存前例と同じ理由（ネットワーク依存の
検査で PR 作成前チェックが赤くなるのを避けるため）で `run_checks.sh` へは配線しない。
`--self-test`（ネットワーク非依存）のみ配線する。これにより「判定不能で CI が赤くならないように」
という要求は、終了コード 2 の特別扱いを実装するのではなく、そもそも本判定を CI 経路に乗せない
という既存パターンへの追随で満たす。

日時: 表示・記録用は JST（`docs/rules/datetime-rules.md`）。API 呼び出しは JST 化しない。

使い方:
    python3 tools/check_roadmap_status.py
    python3 tools/check_roadmap_status.py --json
    python3 tools/check_roadmap_status.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_slug import resolve_repo_slug  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = "docs/02_requirements/roadmap.md"
DOC_ABS_PATH = REPO_ROOT / DOC_PATH

JST = timezone(timedelta(hours=9))


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械処理には使わない。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


# ──────────────────────────────────────────────
# タイトル正規表現（#542 と共有する候補となるモジュール定数）
# ──────────────────────────────────────────────

# 実在する 3 パターン（本 Issue #572 の親セッションが実測で確定）:
#   1. "SP-{n}: {ゴール}"          例: "SP-11: 何も知らない人が README だけで動かせ..."
#   2. "feat(SP-{n}): {ゴール}"    例: "feat(SP-14): キーワードを入力しなくても..."
#   3. "{type}: SP-{n} {ゴール}"   例: "feat: SP-17 候補プール生成を..."
# いずれも **タイトル先頭に固定** されるため `^` で厳密にアンカーする。「本文中に SP-n が
# 出てくるだけ」「SP-1 を含むが別の語（espSP-5 等）」を誤って拾わないための境界線でもある。
SP_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # パターン 2・3 は本ファイルが type プレフィックス無制限、sprint_backlog_sync.py 側は feat 限定
    # （#542 の偽陽性対策）と **意図的に分岐している** ため、機械的に揃えない
    # dup-ok: sprint_backlog_sync.py の SP_TITLE_PATTERNS[0] とのみ同一。統合は Issue #612 のスコープ外
    re.compile(r"^SP-(\d+):"),
    re.compile(r"^[A-Za-z]+\(SP-(\d+)\):"),
    re.compile(r"^[A-Za-z]+:\s*SP-(\d+)\b"),
)


def extract_sp_number_from_title(title: str) -> int | None:
    """Issue タイトルから `SP-n` 番号を抽出する（3 パターンのいずれにも一致しなければ None）。"""
    t = title.strip()
    for pat in SP_TITLE_PATTERNS:
        m = pat.match(t)
        if m:
            return int(m.group(1))
    return None


def filter_out_pull_requests(items: list[dict]) -> list[dict]:
    """`/issues` エンドポイントの応答から PR（`pull_request` キーを持つ要素）を除外する。"""
    return [i for i in items if "pull_request" not in i]


# ──────────────────────────────────────────────
# roadmap.md パーサ（純関数・self-test 対象）
# ──────────────────────────────────────────────

SECTION2_START_RE = re.compile(r"^## 2\.", re.MULTILINE)
SECTION2_END_RE = re.compile(r"^## 3\.", re.MULTILINE)
SECTION3_START_RE = re.compile(r"^## 3\.", re.MULTILINE)
SECTION3_END_RE = re.compile(r"^## 4\.", re.MULTILINE)
SECTION51_START_RE = re.compile(r"^### 5\.1\.", re.MULTILINE)
SECTION51_END_RE = re.compile(r"^## 6\.", re.MULTILINE)

_MILESTONE_HEADER_RE = re.compile(r"^### M-(\d+):", re.MULTILINE)
_CHECKBOX_RE = re.compile(r"^ {0,3}- \[([ xX])\]", re.MULTILINE)

_SP_REF_RE = re.compile(r"`SP-(\d+)`")
_SP_RANGE_RE = re.compile(r"`SP-(\d+)`\s*[〜~]\s*`SP-(\d+)`")
_SP_OPEN_RE = re.compile(r"`SP-(\d+)`\s*以降")

# 違反4 の達成宣言キーワード（部分文字列一致）。「達成済み」だけだと §5.1 で「通過済み」と
# 書く判断ゲート系マイルストーン（例: M-5 / M-6）が検査の穴に落ちるため両方を対象にする。
# `**強調**` や絵文字はキーワード自体を分断しない（例: "✅ **通過済み**（…）" は
# "通過済み" を連続した部分文字列として含む）ため、追加の装飾除去は不要。
ACHIEVEMENT_KEYWORDS: tuple[str, ...] = ("達成済み", "通過済み")

# 抑制マーカー（`docs/rules/datetime-rules.md` の `# tz-ok` に倣う HTML コメント形式）。
# 件数付き構文（Issue #784）: `<!-- roadmap-status-ok:{件数}: {理由} -->`。
# 第 1 キャプチャグループが件数（数字のみ・任意）、第 2 グループが理由。件数部分は
# `roadmap-status-ok:` 直後が「数字 + コロン」の形のときだけマッチし、それ以外
# （旧構文・理由が数字始まりでない）は件数グループが None のまま理由グループへ丸ごと落ちる
# （後方互換）。理由が空（コロン無し・コロン直後が空白のみ）は無効とするため、キャプチャ後に
# strip して非空であることを別途確認する（正規表現だけでは「空理由」を排除しきれないため）。
#
# 🔴 ReDoS 対策（レビュー WARNING2 対応）: 旧実装は `(.*?)` + `re.DOTALL` で「任意の文字を
# 何文字でも」許していたため、閉じられない `<!-- roadmap-status-ok: ` を大量に反復した
# 入力（本リポジトリはパブリックなので外部コントリビューターの PR 経由で混入しうる）に対し
# バックトラック量が入力長の 2 乗で増える（実測: 96KB で 4.4 秒）。理由部分を `>` を含まない
# 文字クラス `[^>]` へ変える（＝抑制理由に `>` を書けない制約と引き換えに、`-->` の外側へ
# 際限なく後方追跡させない）。DOTALL は `.`専用の挙動切り替えなので `[^>]` には効果が無く、
# 複数行にまたがる理由は元々サポートしない想定だったため付けない。件数部分の `(\d+)` は
# 固定長の数字クラスでバックトラック増幅の余地が無いため同じ対策で足りる。
_SUPPRESSION_MARKER_RE = re.compile(
    r"<!--\s*roadmap-status-ok\s*:\s*(?:(\d+)\s*:\s*)?([^>]*?)-->"
)

# 🔴 ReDoS 対策その2（多重防御）: 文字クラス変更だけでは「`>` を一切含まない巨大な反復入力」
# に対する最悪計算量（O(n^2)）を根本的には防げない。検索対象を一定長に切り詰めることで
# 絶対的な処理時間の上限を保証する。実 `roadmap.md` の §3 マイルストーン節は最大でも
# 約 2,700 文字（2026-08-24 実測・最長は `M-6`）なので、8,000 文字は十分な安全マージンを持つ
# （マーカー自体は数百文字で収まる運用を想定しており、この上限で切り詰められることは通常無い。
# 万一マイルストーン節がこの上限を超えて成長し、かつマーカーが末尾側に置かれた場合は
# 検出漏れになりうるが、それは「誤って違反として報告される」側の安全な失敗モードである）。
_SUPPRESSION_SCAN_MAX_LEN = 8000


def _extract_section(text: str, start_re: re.Pattern[str], end_re: re.Pattern[str]) -> str | None:
    m = start_re.search(text)
    if not m:
        return None
    m_end = end_re.search(text, m.end())
    return text[m.end():m_end.start()] if m_end else text[m.end():]


def _split_table_row(line: str) -> list[str]:
    """Markdown テーブル行 `| a | b | c |` をセル配列に分解する（表行以外は `[]`）。"""
    line = line.strip()
    if not line.startswith("|"):
        return []
    inner = line.strip("|")
    return [c.strip() for c in inner.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    """`|---|:--|` のような区切り行かどうか（値セルなら False）。"""
    if not cells:
        return False
    return all(re.fullmatch(r"[:\-]+", c) for c in cells if c)


def _find_suppression_marker(text: str) -> dict | None:
    """`text` 内に有効な抑制マーカー（理由が非空）があれば
    `{"count": int | None, "reason": str, "legacy": bool}` を、無ければ None を返す。

    `count` は件数付き構文（`roadmap-status-ok:{N}: ...`）を書いたときだけ int になり、
    件数なし旧構文（後方互換）のときは None（`legacy=True`）になる。

    ReDoS 対策として `text` は `_SUPPRESSION_SCAN_MAX_LEN` 文字までに切り詰めてから走査する
    （切り詰めの理由・トレードオフは `_SUPPRESSION_SCAN_MAX_LEN` のコメント参照）。
    """
    for m in _SUPPRESSION_MARKER_RE.finditer(text[:_SUPPRESSION_SCAN_MAX_LEN]):
        reason = m.group(2).strip()
        if reason:
            count_raw = m.group(1)
            return {
                "count": int(count_raw) if count_raw is not None else None,
                "reason": reason,
                "legacy": count_raw is None,
            }
    return None


# 達成宣言キーワード直後に続くと「否定文」とみなす代表的な語尾（簡易ヒューリスティック）。
_NEGATION_SUFFIXES: tuple[str, ...] = ("ではない", "とは言えない", "ていない", "していない", "できていない")
_NEGATION_LOOKAHEAD_LEN = 12  # キーワード直後、この文字数以内に否定語尾が始まれば否定文とみなす


def _has_achievement_keyword(state_text: str) -> bool:
    """達成宣言キーワード（`ACHIEVEMENT_KEYWORDS`）が肯定形で含まれるかを判定する。

    🔴 完璧な自然言語処理は行わない（YAGNI）。キーワード出現の **直後** に代表的な否定語尾
    （`_NEGATION_SUFFIXES`）が続く場合だけを否定文として除外する簡易チェックであり、
    それ以外の否定表現（二重否定・キーワードから離れた位置の否定・「まだ〜ではとても言えない」
    のような言い回し等）は拾えない可能性がある（既知の限界）。同じキーワードが複数回出現する
    場合は、いずれか 1 回でも肯定形なら True を返す（1 箇所が否定でも他が肯定なら達成宣言とみなす）。
    """
    for kw in ACHIEVEMENT_KEYWORDS:
        pos = 0
        while True:
            idx = state_text.find(kw, pos)
            if idx == -1:
                break
            after = state_text[idx + len(kw): idx + len(kw) + _NEGATION_LOOKAHEAD_LEN]
            if not any(after.startswith(neg) for neg in _NEGATION_SUFFIXES):
                return True
            pos = idx + len(kw)
    return False


def expand_sp_cell(cell: str) -> dict:
    """§2「束ねるスプリント」セルの生テキストを `SP-n` 集合の表現へ展開する。

    🔴 **早期 return しない**（レビュー CRITICAL の修正）。旧実装は範囲パターンが 1 つでも
    見つかった時点でセル全体を「範囲のみ」として `return` していたため、範囲の外にある
    単独参照（列挙表記との混在。実例: 実 `roadmap.md` §2 `M-6` 行
    `` `SP-14`・`SP-15`・`SP-17`〜`SP-19`（スライス `S-3`。`SP-16` は再設計元として履歴保持） ``）
    が丸ごと消えていた。本実装は ① セル内の全 `` `SP-n` `` 参照（列挙・範囲の端点・
    括弧内の参照を問わず全部）を集める → ② 範囲パターン（`` `SP-a`〜`SP-b` ``）を
    `re.finditer` で **全走査** し、区間内のギャップ番号（端点以外）を集合へ追加でマージする、
    という順で処理し、どちらのステップも早期 return しない。

    Returns:
        {"kind": "concrete"|"open"|"none", "numbers": set[int], "start": int | None}
        - concrete: 範囲・列挙のいずれも（混在していても）具体的な番号集合が確定する
        - open: 「`SP-n` 以降」— 上限が無いため呼び出し側が既知の SP-n 全体（`>= start`）と
          `numbers`（開区間の外＝`start` 未満の明示参照。混在していなければ `start` 自身のみ）
          を OR で合成する。開区間と単独参照が混在するケース（例: 「`SP-12` 以降。ただし
          `SP-9` の追加修正を含む」）でも `numbers` 経由で取りこぼさない
        - none: 「なし」等、束ねる SP-n が存在しない
    """
    if not _SP_REF_RE.search(cell):
        return {"kind": "none", "numbers": set(), "start": None}

    # ① セル内の全 `SP-n` 参照を集める（列挙・範囲端点・括弧内を問わず全部）
    numbers = {int(x) for x in _SP_REF_RE.findall(cell)}

    # ② 範囲パターンは全走査し、区間のギャップ番号を追加でマージする（早期 return しない）
    for a, b in _SP_RANGE_RE.findall(cell):
        lo, hi = min(int(a), int(b)), max(int(a), int(b))
        numbers.update(range(lo, hi + 1))

    m_open = _SP_OPEN_RE.search(cell)
    if m_open:
        return {"kind": "open", "numbers": numbers, "start": int(m_open.group(1))}

    return {"kind": "concrete", "numbers": numbers, "start": None}


def parse_section2(text: str) -> dict[int, str]:
    """§2 の表から `M-n -> 束ねるスプリント列の生テキスト` を取り出す。"""
    result: dict[int, str] = {}
    for line in text.splitlines():
        cells = _split_table_row(line)
        if len(cells) < 3 or _is_separator_row(cells):
            continue
        m = re.match(r"\*\*M-(\d+)\*\*", cells[0])
        if not m:
            continue
        result[int(m.group(1))] = cells[2]
    return result


def parse_section51(text: str) -> tuple[dict[int, str], dict[int, str]]:
    """§5.1 の表から `M-n -> 状態欄の生テキスト` と `M-n -> その行全体の生テキスト` を取り出す。

    後者（`raw_lines`）は抑制マーカー検出専用。マーカーは状態セル内に書かれても
    セル外（同じ行の末尾）に書かれても検出できるよう、セル分割前の行全体を保持する。
    """
    states: dict[int, str] = {}
    raw_lines: dict[int, str] = {}
    for line in text.splitlines():
        cells = _split_table_row(line)
        if len(cells) < 3 or _is_separator_row(cells):
            continue
        m = re.match(r"`M-(\d+)`", cells[0])
        if not m:
            continue
        n = int(m.group(1))
        states[n] = cells[2]
        raw_lines[n] = line
    return states, raw_lines


def _section3_blocks(text: str) -> dict[int, str]:
    """§3 を `M-n -> そのマイルストーン節の生テキスト`（次の `### M-` 直前まで）に分割する。"""
    headers = list(_MILESTONE_HEADER_RE.finditer(text))
    blocks: dict[int, str] = {}
    for i, hm in enumerate(headers):
        n = int(hm.group(1))
        start = hm.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        blocks[n] = text[start:end]
    return blocks


def parse_section3_checklists(text: str) -> dict[int, dict]:
    """§3 の各マイルストーン定義ブロックから通過判定チェックボックスの充足状況を取り出す。

    チェックボックス記法（`- [ ]` / `- [x]`）はこの文書内で通過判定リスト以外に
    使われていないため、マイルストーンのブロック全体から素直に数え上げてよい
    （「**通過判定**」マーカー以降だけに範囲を絞る必要はない）。
    """
    result: dict[int, dict] = {}
    for n, block in _section3_blocks(text).items():
        marks = _CHECKBOX_RE.findall(block)
        total = len(marks)
        checked = sum(1 for mk in marks if mk.lower() == "x")
        result[n] = {"total": total, "checked": checked, "unchecked": total - checked}
    return result


def parse_roadmap(md_text: str) -> dict:
    """`roadmap.md` 全体をパースする。

    Returns:
        {"ok": bool, "error": str | None,
         "milestones": {n: {"sp": expand_sp_cell(...), "raw_cell": str}},
         "states": {n: str}, "checklists": {n: {...}},
         "states_raw_lines": {n: str}, "section3_blocks": {n: str}}
    """
    s2 = _extract_section(md_text, SECTION2_START_RE, SECTION2_END_RE)
    s3 = _extract_section(md_text, SECTION3_START_RE, SECTION3_END_RE)
    s51 = _extract_section(md_text, SECTION51_START_RE, SECTION51_END_RE)
    if s2 is None or s3 is None or s51 is None:
        missing = [
            name for name, s in (("§2", s2), ("§3", s3), ("§5.1", s51)) if s is None
        ]
        return {
            "ok": False,
            "error": f"セクションが見つかりません: {'、'.join(missing)}",
            "milestones": {}, "states": {}, "checklists": {},
            "states_raw_lines": {}, "section3_blocks": {},
        }

    cells = parse_section2(s2)
    if not cells:
        return {
            "ok": False,
            "error": "§2 の表からマイルストーン行（`| **M-n** | ...`）を抽出できませんでした",
            "milestones": {}, "states": {}, "checklists": {},
            "states_raw_lines": {}, "section3_blocks": {},
        }

    milestones = {n: {"sp": expand_sp_cell(cell), "raw_cell": cell} for n, cell in cells.items()}
    states, states_raw_lines = parse_section51(s51)
    checklists = parse_section3_checklists(s3)
    section3_blocks = _section3_blocks(s3)
    return {
        "ok": True, "error": None, "milestones": milestones, "states": states,
        "checklists": checklists, "states_raw_lines": states_raw_lines,
        "section3_blocks": section3_blocks,
    }


def find_milestone_suppression_marker(n: int, parsed: dict) -> dict | None:
    """`M-n` の抑制マーカーを §5.1 の該当行 → §3 の該当節の順に探し、マーカー情報を返す。

    どちらかに有効な（理由が非空の）マーカーがあれば十分（両方に書く必要はない）。
    戻り値の形式は `_find_suppression_marker` を参照。
    """
    marker = _find_suppression_marker(parsed.get("states_raw_lines", {}).get(n, ""))
    if marker:
        return marker
    return _find_suppression_marker(parsed.get("section3_blocks", {}).get(n, ""))


# ──────────────────────────────────────────────
# 判定ロジック（純関数・self-test 対象）
# ──────────────────────────────────────────────

def build_sp_state_index(items: list[dict]) -> dict[int, list[str]]:
    """Issue 一覧（PR 除外済みでなくてよい）から `SP-n -> [state, ...]` の索引を作る。

    同じ番号に複数 Issue が存在する事故（想定外だが起こりうる）を安全側に倒すため、
    1 件でも Closed でなければ「全件 Closed」ではないと判定できるようリストで保持する。
    """
    index: dict[int, list[str]] = {}
    for item in filter_out_pull_requests(items):
        n = extract_sp_number_from_title(str(item.get("title", "")))
        if n is None:
            continue
        index.setdefault(n, []).append(str(item.get("state", "")).lower())
    return index


def evaluate_roadmap(
    parsed: dict, sp_state_index: dict[int, list[str]],
) -> tuple[list[dict], list[dict]]:
    """パース済み roadmap.md と Issue 状態索引から `(違反一覧, 抑制ノート一覧)` を返す（純関数）。

    抑制ノートは「達成宣言 + 未チェック残り」という違反4 の条件自体は満たしたが、有効な
    抑制マーカーにより検出から除外したケースを記録する（黙って消さないため）。
    """
    violations: list[dict] = []
    suppressed_notes: list[dict] = []

    # 違反3: 全件 Closed なのに §5.1 の状態欄が「未着手」のまま
    for n, m in parsed["milestones"].items():
        sp = m["sp"]
        if sp["kind"] == "none":
            continue
        if sp["kind"] == "concrete":
            numbers = sp["numbers"]
        else:  # open: `>= start` の全既知 SP-n と、開区間の外にある明示参照（混在ケース）を OR で合成
            numbers = {x for x in sp_state_index if x >= sp["start"]} | sp["numbers"]
        existing = sorted(x for x in numbers if x in sp_state_index)
        if not existing:
            continue  # 対応する Issue が 1 件も無ければ「全件 Closed」は判定できない
        all_closed = all(
            all(s == "closed" for s in sp_state_index[x]) for x in existing
        )
        state_text = parsed["states"].get(n, "")
        if all_closed and "未着手" in state_text:
            violations.append({
                "type": "violation3_all_closed_but_not_started",
                "milestone": f"M-{n}",
                "sp_numbers": existing,
                "state_text": state_text,
                "detail": (
                    f"M-{n} の対応 SP-n（{'、'.join(f'SP-{x}' for x in existing)}）が全件 Closed "
                    "なのに §5.1 の状態欄が「未着手」のままです。"
                ),
            })

    # 違反4: §5.1 が達成宣言（ACHIEVEMENT_KEYWORDS）なのに §3 の通過判定に未チェックが残っている
    for n, checklist in parsed["checklists"].items():
        state_text = parsed["states"].get(n, "")
        if not _has_achievement_keyword(state_text):
            continue
        if checklist["total"] == 0 or checklist["unchecked"] == 0:
            continue

        marker = find_milestone_suppression_marker(n, parsed)
        if marker:
            declared = marker["count"]
            actual = checklist["unchecked"]
            if marker["legacy"] or declared == actual:
                suppressed_notes.append({
                    "milestone": f"M-{n}",
                    "reason": marker["reason"],
                    "declared_count": declared,
                    "actual_unchecked": actual,
                    "legacy": marker["legacy"],
                    "would_have_flagged": "violation4_achieved_but_unchecked",
                    "detail": (
                        f"M-{n} は達成宣言 + 未チェック残り（{actual}/{checklist['total']}）"
                        f"に該当しましたが、抑制マーカーにより検出から除外しました"
                        f"（理由: {marker['reason']}）。"
                        + (
                            " ⚠️ 件数なし旧構文のため件数照合なしで抑制しています。"
                            "件数付き構文（`roadmap-status-ok:{件数}: {理由}`）へ移行してください。"
                            if marker["legacy"] else ""
                        )
                    ),
                })
                continue

            # 件数不一致: マーカーが想定していない未チェックが増えている（Issue #784）
            violations.append({
                "type": "violation4_suppression_count_mismatch",
                "milestone": f"M-{n}",
                "state_text": state_text,
                "declared_count": declared,
                "actual_unchecked": actual,
                "total": checklist["total"],
                "reason": marker["reason"],
                "detail": (
                    f"M-{n} の抑制マーカーは未チェック {declared} 件を宣言していますが、"
                    f"実際の未チェックは {actual}/{checklist['total']} 件です。"
                    "マーカーが想定していない未チェックが増えています。"
                    f"マーカーの件数を更新するか、増えた項目を別途検討してください（理由: {marker['reason']}）。"
                ),
            })
            continue

        violations.append({
            "type": "violation4_achieved_but_unchecked",
            "milestone": f"M-{n}",
            "state_text": state_text,
            "unchecked": checklist["unchecked"],
            "total": checklist["total"],
            "detail": (
                f"M-{n} は §5.1 で達成宣言（{'/'.join(kw for kw in ACHIEVEMENT_KEYWORDS if kw in state_text)}）"
                f"ですが §3 の通過判定に未チェックが {checklist['unchecked']}/{checklist['total']} 件残っています。"
            ),
        })

    return violations, suppressed_notes


# ──────────────────────────────────────────────
# GitHub API（GH_TOKEN 直叩き。gh コマンドは使わない）
# ──────────────────────────────────────────────

def _http_get(url: str, token: str, timeout: int = 30) -> tuple[bool, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gem-hunter-check-roadmap-status",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return True, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"接続失敗（{type(e).__name__}）"
    except TimeoutError:
        return False, "リクエストがタイムアウトしました"


def fetch_all_issues(repo: str, token: str, max_pages: int = 20) -> tuple[list[dict] | None, str | None]:
    """`GET /repos/{repo}/issues?state=all` を全ページ走査する（PR 込み。除外は呼び出し側）。"""
    items: list[dict] = []
    for page in range(1, max_pages + 1):
        ok, out = _http_get(
            f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100&page={page}",
            token,
        )
        if not ok:
            return None, f"GitHub API 取得に失敗しました（{out}）"
        try:
            batch = json.loads(out)
        except json.JSONDecodeError:
            return None, "GitHub API 応答の JSON パースに失敗しました"
        if not isinstance(batch, list):
            return None, "GitHub API 応答の形式が想定外です（配列でない）"
        items.extend(batch)
        if len(batch) < 100:
            return items, None
    return None, f"ページネーションが上限（{max_pages} ページ）に達しました"


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────

def _self_test_sp_cell_expansion() -> list[str]:
    failures = []

    r = expand_sp_cell("`SP-1`〜`SP-5`（スライス `S-0`）")
    if r["kind"] != "concrete" or r["numbers"] != {1, 2, 3, 4, 5}:
        failures.append(f"範囲展開: 期待 concrete/{{1..5}} だが {r}")

    r = expand_sp_cell("`SP-14` → `SP-15` / `SP-16`")
    if r["kind"] != "concrete" or r["numbers"] != {14, 15, 16}:
        failures.append(f"列挙展開: 期待 concrete/{{14,15,16}} だが {r}")

    r = expand_sp_cell("`SP-12` 以降（スライス `S-2`）")
    if r["kind"] != "open" or r["start"] != 12:
        failures.append(f"開区間展開: 期待 open/start=12 だが {r}")

    r = expand_sp_cell("なし")
    if r["kind"] != "none" or r["numbers"]:
        failures.append(f"なし展開: 期待 none/空集合 だが {r}")

    r = expand_sp_cell("なし（`M-6` が実装を束ねる）")
    if r["kind"] != "none":
        failures.append(f"なし+補足展開: 期待 none だが {r}")

    return failures


# 実 `roadmap.md` §2 `M-6` 行のセル文字列（2026-08-24 実測）。合成フィクスチャが実物から
# 乖離していたことが CRITICAL（早期 return による取りこぼし）の検出漏れの原因だったため、
# 加工せずそのまま self-test に使う。
_REAL_M6_CELL = (
    "`SP-14`・`SP-15`・`SP-17`〜`SP-19`"
    "（スライス `S-3`。`SP-16` は再設計元として履歴保持）"
)


def _self_test_expand_sp_cell_mixed_range_and_enum() -> list[str]:
    """CRITICAL 回帰テスト: 「列挙 + 範囲」混在セルで SP-n を取りこぼさないこと。

    両側アサート: ① 旧実装（範囲を最初に見つけた時点で早期 return するロジック）を
    このテスト内で再現し、それが実際に一部を取りこぼす（壊れている）ことを先に確認する
    → ② 現行の `expand_sp_cell` が全参照を正しく展開することを確認する。①が「壊れていない」
    結果を返してしまったら、このテスト自体が退行を検出できなくなっている合図として扱う。
    """
    failures = []

    def _old_buggy_expand(cell: str) -> set[int]:
        """旧実装（範囲マッチで早期 return）の再現。CRITICAL 修正前の挙動そのもの。"""
        m_range = _SP_RANGE_RE.search(cell)
        if m_range:
            a, b = int(m_range.group(1)), int(m_range.group(2))
            lo, hi = min(a, b), max(a, b)
            return set(range(lo, hi + 1))
        return {int(x) for x in _SP_REF_RE.findall(cell)}

    old_result = _old_buggy_expand(_REAL_M6_CELL)
    if old_result == {14, 15, 16, 17, 18, 19}:
        failures.append(
            "回帰確認: 旧ロジックの再現が『取りこぼしていない』結果を返した"
            f"（{old_result}）。このテストが CRITICAL の再発を検出できていない可能性がある"
        )

    result = expand_sp_cell(_REAL_M6_CELL)
    if result["kind"] != "concrete" or result["numbers"] != {14, 15, 16, 17, 18, 19}:
        failures.append(f"混在セル展開（実 M-6 セル）: 期待 concrete/{{14..19}} だが {result}")

    return failures


def _self_test_expand_sp_cell_multiple_ranges() -> list[str]:
    """1 セルに範囲が 2 つ以上あるケース（`SP-1`〜`SP-3` と `SP-7`〜`SP-9`）も落とさない。"""
    failures = []
    r = expand_sp_cell("`SP-1`〜`SP-3` と `SP-7`〜`SP-9`（統合予定）")
    if r["kind"] != "concrete" or r["numbers"] != {1, 2, 3, 7, 8, 9}:
        failures.append(f"複数範囲展開: 期待 concrete/{{1,2,3,7,8,9}} だが {r}")
    return failures


def _self_test_expand_sp_cell_open_mixed() -> list[str]:
    """開区間と単独参照が混在するケース（例:「`SP-12` 以降。ただし `SP-9` の追加修正を含む」）。

    open kind の `numbers` に開区間の外（`start` 未満）の明示参照も保持され、
    `evaluate_roadmap` 側の OR 合成で取りこぼさないことを確認する。
    """
    failures = []
    r = expand_sp_cell("`SP-12` 以降。ただし `SP-9` の追加修正を含む")
    if r["kind"] != "open" or r["start"] != 12 or r["numbers"] != {9, 12}:
        failures.append(f"開区間+単独参照混在展開: 期待 open/start=12/numbers={{9,12}} だが {r}")

    # evaluate_roadmap 側でも `SP-9`（開区間の外）が取りこぼされないことを確認する
    parsed = {
        "milestones": {1: {"sp": r, "raw_cell": ""}},
        "states": {1: "未着手"},
        "checklists": {},
        "states_raw_lines": {},
        "section3_blocks": {},
    }
    violations, _ = evaluate_roadmap(parsed, sp_state_index={9: ["closed"], 12: ["closed"], 13: ["closed"]})
    hit = [v for v in violations if v["milestone"] == "M-1"]
    if len(hit) != 1 or hit[0]["sp_numbers"] != [9, 12, 13]:
        failures.append(f"開区間+単独参照混在: evaluate_roadmap が SP-9 を取りこぼしている: {violations}")
    return failures


def _self_test_title_extraction() -> list[str]:
    failures = []
    cases_positive = [
        ("SP-11: 何も知らない人が README だけで動かせる", 11),
        ("feat(SP-14): キーワードを入力しなくても出会える", 14),
        ("feat: SP-17 候補プール生成を刷新する", 17),
        ("fix(SP-2): 直す", 2),
        ("docs: SP-100 テスト", 100),
        # 副次 Issue（type プレフィックス無制限は意図的な仕様・Issue #628）:
        # roadmap.md との整合性検査という用途では、本体 Issue に限らず SP-n に言及する
        # Issue を拾うことが正しい設計であり「誤判定」ではない。マッチすること自体を期待する。
        ("improvement: SP-1 の ADR 0001 確定後に shadcn MCP を追加する", 1),
        ("docs: SP-4 で増えた E2E 関連の環境変数を env-vars.md に記載する", 4),
    ]
    for title, want in cases_positive:
        got = extract_sp_number_from_title(title)
        if got != want:
            failures.append(f"タイトル抽出（陽性）: {title!r} → {got}（期待 {want}）")

    cases_negative = [
        "SP-1 は最高のマイルストーンです",          # コロンが無い
        "chore: something SP-3 related",           # コロン直後が SP-n でない
        "espSP-5: thing",                          # SP- の前に余分な文字
        "本文で SP-3 に触れているだけ",              # 先頭が SP- でない・type: でもない
        "SP-: 番号が無い",                          # 数字が無い
        "SPRINT-1: 紛らわしい語",                   # SP- ではなく SPRINT-
    ]
    for title in cases_negative:
        got = extract_sp_number_from_title(title)
        if got is not None:
            failures.append(f"タイトル抽出（陰性・誤検出）: {title!r} → {got}（期待 None）")

    return failures


def _self_test_pull_request_filter() -> list[str]:
    failures = []
    items = [
        {"title": "SP-11: a", "state": "closed"},
        {"title": "feat(SP-11): a", "state": "open", "pull_request": {"url": "x"}},
    ]
    got = filter_out_pull_requests(items)
    if len(got) != 1 or got[0]["title"] != "SP-11: a":
        failures.append(f"PR 除外: {got}")
    return failures


_FIXTURE_ROADMAP_OK = """
## 2. マイルストーン一覧

| ID | 名前 | 束ねるスプリント | 優先度ラベル | 種別 | 削減可否 |
|---|---|---|---|---|---|
| **M-1** | 歩く骨格 | `SP-1`〜`SP-3`（スライス `S-0`） | `P1-MVP` | 実装 | 削らない |
| **M-2** | 積み上げ | `SP-4` 以降（スライス `S-2`） | `P1-積み上げ` | 実装 | 削れる |
| **M-3** | 公開判断 | なし | — | 判断 | — |

## 3. マイルストーン定義

### M-1: 歩く骨格

- **通過判定**（すべて満たすこと）
  - [x] テストが通る
  - [x] プレビュー URL で確認できる

### M-2: 積み上げ

- **通過判定**: 存在しない

### M-3: 公開判断ゲート

- **通過判定**（公開するなら、すべて満たすこと）
  - [ ] 規約確認済み

## 4. 未決事項

（本文）

## 5. 期日

### 5.1. 目標日

| マイルストーン | 目標日 | 状態 |
|---|---|---|
| `M-1` 歩く骨格 | — | 達成済み（`SP-1`〜`SP-3` 完了） |
| `M-2` 積み上げ | — | 未着手 |
| `M-3` 公開判断 | — | 判断前 |

## 6. スコープ調整の規則

（本文）
"""


def _self_test_parse_roadmap_ok() -> list[str]:
    failures = []
    parsed = parse_roadmap(_FIXTURE_ROADMAP_OK)
    if not parsed["ok"]:
        failures.append(f"parse_roadmap: ok=True を期待したが {parsed}")
        return failures

    if parsed["milestones"][1]["sp"]["numbers"] != {1, 2, 3}:
        failures.append(f"parse_roadmap: M-1 の SP 集合が不一致: {parsed['milestones'][1]}")
    if parsed["milestones"][2]["sp"]["kind"] != "open" or parsed["milestones"][2]["sp"]["start"] != 4:
        failures.append(f"parse_roadmap: M-2 の開区間展開が不一致: {parsed['milestones'][2]}")
    if parsed["milestones"][3]["sp"]["kind"] != "none":
        failures.append(f"parse_roadmap: M-3 の なし展開が不一致: {parsed['milestones'][3]}")

    if parsed["states"].get(1) != "達成済み（`SP-1`〜`SP-3` 完了）":
        failures.append(f"parse_roadmap: M-1 状態欄の抽出が不一致: {parsed['states'].get(1)!r}")
    if parsed["states"].get(2) != "未着手":
        failures.append(f"parse_roadmap: M-2 状態欄の抽出が不一致: {parsed['states'].get(2)!r}")

    if parsed["checklists"][1] != {"total": 2, "checked": 2, "unchecked": 0}:
        failures.append(f"parse_roadmap: M-1 チェックリスト集計が不一致: {parsed['checklists'][1]}")
    if parsed["checklists"][3] != {"total": 1, "checked": 0, "unchecked": 1}:
        failures.append(f"parse_roadmap: M-3 チェックリスト集計が不一致: {parsed['checklists'][3]}")

    return failures


def _self_test_parse_roadmap_missing_section() -> list[str]:
    failures = []
    broken = "# 見出しだけの無関係なドキュメント\n\n本文。\n"
    parsed = parse_roadmap(broken)
    if parsed["ok"]:
        failures.append("parse_roadmap: セクション欠落時は ok=False を期待")
    return failures


def _self_test_violation3_detection() -> list[str]:
    """違反3（全件 Closed なのに『未着手』）— 壊す前は検出なし・壊した後は検出、の両方を確認する。"""
    failures = []
    parsed = parse_roadmap(_FIXTURE_ROADMAP_OK)

    # 壊す前（フィクスチャそのまま）: M-2 は open(start=4) で SP-4 の Issue が無いため対象外、
    # M-1 は「未着手」ではないので違反なし。
    violations_before, _ = evaluate_roadmap(parsed, sp_state_index={1: ["closed"], 2: ["closed"], 3: ["closed"]})
    if any(v["type"] == "violation3_all_closed_but_not_started" for v in violations_before):
        failures.append(f"違反3: 壊す前に誤検出: {violations_before}")

    # 壊す: M-1（`SP-1`〜`SP-3`）を全件 Closed にしたうえで、状態を「未着手」に差し替えたフィクスチャで検証
    broken_fixture = _FIXTURE_ROADMAP_OK.replace(
        "| `M-1` 歩く骨格 | — | 達成済み（`SP-1`〜`SP-3` 完了） |",
        "| `M-1` 歩く骨格 | — | 未着手 |",
    )
    parsed_broken = parse_roadmap(broken_fixture)
    violations_after, _ = evaluate_roadmap(
        parsed_broken, sp_state_index={1: ["closed"], 2: ["closed"], 3: ["closed"]},
    )
    hit = [v for v in violations_after if v["type"] == "violation3_all_closed_but_not_started"]
    if len(hit) != 1 or hit[0]["milestone"] != "M-1":
        failures.append(f"違反3: 壊した後に検出できていない: {violations_after}")

    # open 区間（M-2・`SP-4` 以降・状態は元から「未着手」）: Issue が無いうちは対象外（上の
    # violations_before で確認済み）だが、SP-4/5 が実在して全件 Closed になれば検出されるべき
    violations_open, _ = evaluate_roadmap(parsed, sp_state_index={4: ["closed"], 5: ["closed"]})
    hit_open = [v for v in violations_open if v["milestone"] == "M-2"]
    if len(hit_open) != 1:
        failures.append(f"違反3: open 区間で SP-4/5 が全件 Closed のケースを検出できていない: {violations_open}")

    return failures


def _self_test_violation4_detection() -> list[str]:
    """違反4（達成宣言なのに未チェック残り）— 壊す前は検出なし・壊した後は検出、の両方を確認する。"""
    failures = []

    # 壊す前（フィクスチャそのまま）: M-1 はチェックボックス 2/2 済みなので違反なし
    parsed = parse_roadmap(_FIXTURE_ROADMAP_OK)
    violations_before, _ = evaluate_roadmap(parsed, sp_state_index={})
    if any(v["type"] == "violation4_achieved_but_unchecked" for v in violations_before):
        failures.append(f"違反4: 壊す前に誤検出: {violations_before}")

    # 壊す: M-1 の 2 個目のチェックボックスを未チェックに戻す
    broken_fixture = _FIXTURE_ROADMAP_OK.replace(
        "  - [x] プレビュー URL で確認できる",
        "  - [ ] プレビュー URL で確認できる",
    )
    parsed_broken = parse_roadmap(broken_fixture)
    violations_after, _ = evaluate_roadmap(parsed_broken, sp_state_index={})
    hit = [v for v in violations_after if v["type"] == "violation4_achieved_but_unchecked"]
    if len(hit) != 1 or hit[0]["milestone"] != "M-1" or hit[0]["unchecked"] != 1:
        failures.append(f"違反4: 壊した後に検出できていない: {violations_after}")

    return failures


# フィクスチャ: M-5 相当の判断ゲート（§5.1 が「通過済み」・§3 に未チェックが残る）。
# 違反4 の「達成済み」以外のキーワード（通過済み）と、抑制マーカーの 2 パターン
# （§5.1 行 / §3 節）を独立に検証するために _FIXTURE_ROADMAP_OK とは別で持つ。
_FIXTURE_M5_GATE = """
## 2. マイルストーン一覧

| ID | 名前 | 束ねるスプリント | 優先度ラベル | 種別 | 削減可否 |
|---|---|---|---|---|---|
| **M-5** | Phase 2 着手判断ゲート | なし | `P2` | 判断 | — |

## 3. マイルストーン定義

### M-5: Phase 2 着手判断ゲート

- **通過判定**
  - [x] `M-2` を通過している
  - [ ] `RK-1`: ペルソナとペインの検証（現在 n=0）

## 4. 未決事項

（本文）

## 5. 期日

### 5.1. 目標日

| マイルストーン | 目標日 | 状態 |
|---|---|---|
| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） |

## 6. スコープ調整の規則

（本文）
"""


def _self_test_violation4_pass_keyword_and_decoration() -> list[str]:
    """違反4 が「達成済み」だけでなく「通過済み」（`**` 強調・絵文字付きも含む）で検出できることを確認する。"""
    failures = []

    # 「通過済み」（装飾なし）: 検出する
    parsed = parse_roadmap(_FIXTURE_M5_GATE)
    violations, _ = evaluate_roadmap(parsed, sp_state_index={})
    hit = [v for v in violations if v["type"] == "violation4_achieved_but_unchecked"]
    if len(hit) != 1 or hit[0]["milestone"] != "M-5" or hit[0]["unchecked"] != 1:
        failures.append(f"違反4（通過済み）: 検出できていない: {violations}")

    # 「✅ **通過済み**（…）」のように絵文字・強調記法で装飾されていても検出する
    decorated_fixture = _FIXTURE_M5_GATE.replace(
        "通過済み（`D-27`・2026-08-20）",
        "✅ **通過済み**（`D-27`・2026-08-20）",
    )
    parsed_decorated = parse_roadmap(decorated_fixture)
    violations_decorated, _ = evaluate_roadmap(parsed_decorated, sp_state_index={})
    hit_decorated = [v for v in violations_decorated if v["type"] == "violation4_achieved_but_unchecked"]
    if len(hit_decorated) != 1 or hit_decorated[0]["milestone"] != "M-5":
        failures.append(f"違反4（装飾つき通過済み）: 検出できていない: {violations_decorated}")

    return failures


def _self_test_achievement_keyword_negation() -> list[str]:
    """WARNING1 回帰テスト: 達成宣言キーワードの否定文を誤検出しないこと（陰性ケース最低 2 件）。"""
    failures = []

    for text in ("達成済みではない", "まだ通過済みとは言えない"):
        if _has_achievement_keyword(text):
            failures.append(f"否定文の誤検出: {text!r} で True になった（期待 False）")

    # 肯定文まで巻き込んで False にしてしまう退行も検出する（陰性対照）
    for text in ("達成済み（`SP-1`〜`SP-5` 完了）", "通過済み（`D-27`・2026-08-20）"):
        if not _has_achievement_keyword(text):
            failures.append(f"肯定文が検出されない（過剰に否定判定している）: {text!r}")

    return failures


def _self_test_suppression_marker() -> list[str]:
    """抑制マーカー（`<!-- roadmap-status-ok:{件数}: 理由 -->`）の 7 ケースを検証する（Issue #784）。"""
    failures = []

    # ① §5.1 の該当行に有効な件数付きマーカー（実際の未チェックと一致・状態セル内に追記）→ 検出しない
    fixture_51 = _FIXTURE_M5_GATE.replace(
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） |",
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20）"
        "<!-- roadmap-status-ok:1: 飼い主の明示意向によりRK-1未充足のまま通過（D-27） --> |",
    )
    parsed_51 = parse_roadmap(fixture_51)
    violations_51, suppressed_51 = evaluate_roadmap(parsed_51, sp_state_index={})
    if any(v["milestone"] == "M-5" for v in violations_51):
        failures.append(f"抑制①（§5.1 行・件数一致）: マーカーがあるのに違反として検出された: {violations_51}")
    if (
        len(suppressed_51) != 1 or suppressed_51[0]["milestone"] != "M-5"
        or not suppressed_51[0]["reason"] or suppressed_51[0]["legacy"] is not False
    ):
        failures.append(f"抑制①（§5.1 行・件数一致）: 抑制ノートが記録されていない: {suppressed_51}")

    # ② §3 の該当節内に有効な件数付きマーカー（別行として追記）→ 検出しない
    fixture_3 = _FIXTURE_M5_GATE.replace(
        "  - [ ] `RK-1`: ペルソナとペインの検証（現在 n=0）\n",
        "  - [ ] `RK-1`: ペルソナとペインの検証（現在 n=0）\n\n"
        "<!-- roadmap-status-ok:1: 飼い主の明示意向によりRK-1未充足のまま通過（D-27） -->\n",
    )
    parsed_3 = parse_roadmap(fixture_3)
    violations_3, suppressed_3 = evaluate_roadmap(parsed_3, sp_state_index={})
    if any(v["milestone"] == "M-5" for v in violations_3):
        failures.append(f"抑制②（§3 節内・件数一致）: マーカーがあるのに違反として検出された: {violations_3}")
    if len(suppressed_3) != 1 or suppressed_3[0]["milestone"] != "M-5":
        failures.append(f"抑制②（§3 節内・件数一致）: 抑制ノートが記録されていない: {suppressed_3}")

    # ③ 理由が空のマーカー（件数はあるが理由がコロン後空白のみ）→ 無効。抑制されず違反として検出する
    fixture_empty_reason = _FIXTURE_M5_GATE.replace(
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） |",
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） <!-- roadmap-status-ok:1:  --> |",
    )
    parsed_empty = parse_roadmap(fixture_empty_reason)
    violations_empty, suppressed_empty = evaluate_roadmap(parsed_empty, sp_state_index={})
    hit_empty = [v for v in violations_empty if v["milestone"] == "M-5"]
    if len(hit_empty) != 1:
        failures.append(f"抑制③（理由が空）: 抑制されず検出されるべきだが: {violations_empty}")
    if suppressed_empty:
        failures.append(f"抑制③（理由が空）: 空理由なのに抑制ノートが記録された: {suppressed_empty}")

    # ③' コロン自体が無い記法（`<!-- roadmap-status-ok -->`）も同様に無効
    fixture_no_colon = _FIXTURE_M5_GATE.replace(
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） |",
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） <!-- roadmap-status-ok --> |",
    )
    parsed_no_colon = parse_roadmap(fixture_no_colon)
    violations_no_colon, suppressed_no_colon = evaluate_roadmap(parsed_no_colon, sp_state_index={})
    hit_no_colon = [v for v in violations_no_colon if v["milestone"] == "M-5"]
    if len(hit_no_colon) != 1 or suppressed_no_colon:
        failures.append(f"抑制③'（コロンなし）: 無効なマーカーが抑制として働いてしまっている: "
                         f"violations={violations_no_colon} suppressed={suppressed_no_colon}")

    # ④ 陰性対照: マーカーがあってもチェックが全部埋まっていれば、そもそも違反4 の対象外
    #    （抑制ノートも記録されない＝「何も抑制していないのに抑制した」と誤報しない）
    fixture_all_checked = _FIXTURE_M5_GATE.replace(
        "  - [ ] `RK-1`: ペルソナとペインの検証（現在 n=0）",
        "  - [x] `RK-1`: ペルソナとペインの検証（現在 n=0）",
    ).replace(
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） |",
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20）"
        "<!-- roadmap-status-ok:1: 念のため --> |",
    )
    parsed_all_checked = parse_roadmap(fixture_all_checked)
    violations_ok, suppressed_ok = evaluate_roadmap(parsed_all_checked, sp_state_index={})
    if violations_ok or suppressed_ok:
        failures.append(
            f"抑制④（陰性対照・全チェック済み）: 違反もノートも無いはずが: "
            f"violations={violations_ok} suppressed={suppressed_ok}"
        )

    # ⑤ CRITICAL 回帰（Issue #784 本体）: 件数不一致（宣言 1 件だが実際は 2 件に増えた）
    #    → 抑制せず「マーカーが想定していない未チェックが増えた」ことを違反として報告する
    fixture_mismatch = _FIXTURE_M5_GATE.replace(
        "  - [x] `M-2` を通過している",
        "  - [ ] `M-2` を通過している",
    ).replace(
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） |",
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20）"
        "<!-- roadmap-status-ok:1: 飼い主の明示意向によりRK-1未充足のまま通過（D-27） --> |",
    )
    parsed_mismatch = parse_roadmap(fixture_mismatch)
    violations_mismatch, suppressed_mismatch = evaluate_roadmap(parsed_mismatch, sp_state_index={})
    hit_mismatch = [
        v for v in violations_mismatch
        if v["milestone"] == "M-5" and v["type"] == "violation4_suppression_count_mismatch"
    ]
    if len(hit_mismatch) != 1 or hit_mismatch[0]["declared_count"] != 1 or hit_mismatch[0]["actual_unchecked"] != 2:
        failures.append(f"抑制⑤（件数不一致・CRITICAL 回帰）: 検出できていない: {violations_mismatch}")
    if any(n["milestone"] == "M-5" for n in suppressed_mismatch):
        failures.append(f"抑制⑤（件数不一致）: 不一致なのに抑制ノートとして記録された: {suppressed_mismatch}")

    # ⑥ 後方互換（件数なし旧構文）: 件数照合なしで無条件に抑制するが、legacy フラグ + ⚠️ 相当の
    #    移行注意文言を detail に含める
    fixture_legacy = _FIXTURE_M5_GATE.replace(
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20） |",
        "| `M-5` Phase 2 着手判断 | — | 通過済み（`D-27`・2026-08-20）"
        "<!-- roadmap-status-ok: 飼い主の明示意向によりRK-1未充足のまま通過（D-27） --> |",
    )
    parsed_legacy = parse_roadmap(fixture_legacy)
    violations_legacy, suppressed_legacy = evaluate_roadmap(parsed_legacy, sp_state_index={})
    if any(v["milestone"] == "M-5" for v in violations_legacy):
        failures.append(f"抑制⑥（後方互換・旧構文）: マーカーがあるのに違反として検出された: {violations_legacy}")
    if (
        len(suppressed_legacy) != 1 or suppressed_legacy[0]["legacy"] is not True
        or "移行" not in suppressed_legacy[0]["detail"]
    ):
        failures.append(f"抑制⑥（後方互換・旧構文）: legacy フラグ・移行注意文言が正しくない: {suppressed_legacy}")

    return failures


def _self_test_suppression_marker_redos() -> list[str]:
    """WARNING2 回帰テスト: 閉じられない抑制マーカーの反復（病的入力）が実用的な時間で終わること。

    レビューの実測（旧実装）: 4000 回反復（約 96KB）で 4.4 秒。修正後は文字クラス変更
    （`[^>]`）+ 走査対象の長さ上限（`_SUPPRESSION_SCAN_MAX_LEN`）により、入力サイズに
    関わらず一定時間内に収まることを確認する。
    """
    failures = []
    malicious = "<!-- roadmap-status-ok: " * 4000  # 閉じる `-->` を含まない反復（約 96KB）
    start = time.monotonic()
    result = _find_suppression_marker(malicious)
    elapsed = time.monotonic() - start

    if result is not None:
        failures.append(f"病的入力で誤って抑制マーカーを検出してしまった: {result!r}")
    if elapsed > 1.0:
        failures.append(
            f"病的入力（約 96KB・閉じられないマーカーの反復）の処理が遅すぎる"
            f"（{elapsed:.3f} 秒。1 秒以内を期待。旧実装は同規模の入力で約 4.4 秒だった）"
        )
    return failures


def _self_test_secondary_issue_no_false_positive() -> list[str]:
    """副次 Issue（SP-n に言及するだけの Issue）が混入しても違反3/4 が偽陽性化しないことを確認する（Issue #628）。

    `SP_TITLE_PATTERNS` は type プレフィックス無制限のため、`improvement: SP-1 の...` のような
    副次 Issue もタイトル抽出でマッチする（これは意図的な仕様・`_self_test_title_extraction` 参照）。
    本テストは、その混入が `build_sp_state_index` を経由しても「本来違反でないものを違反ありと
    誤判定する」方向には作用しないことを検証する（`all()` による安全側判定のため、混入は
    見逃し方向にしか働かない）。
    """
    failures = []

    # M-1（SP-1〜SP-3）: 本体 Issue は全件 Closed だが、副次 Issue（同じ SP-1 に言及）が Open のまま
    # 残っている状態。build_sp_state_index はタイトル無制限マッチにより副次 Issue も SP-1 の索引に
    # 混ぜ込むため、all_closed 判定には Open が 1 件混じる。
    items = [
        {"title": "SP-1: 何も知らない人が README だけで動かせる", "state": "closed"},
        {"title": "improvement: SP-1 の ADR 0001 確定後に shadcn MCP を追加する", "state": "open"},
        {"title": "SP-2: 二番目のスプリント", "state": "closed"},
        {"title": "SP-3: 三番目のスプリント", "state": "closed"},
    ]
    index = build_sp_state_index(items)
    if sorted(index.get(1, [])) != ["closed", "open"]:
        failures.append(f"索引混入前提が崩れている: index[1]={index.get(1)}")

    # 🔴 状態欄が「達成済み」（未着手を含まない）のフィクスチャに対する検証は、violation3 の
    # 発火条件（all_closed and "未着手" in state_text）のうち "未着手" 側で必ず弾かれるため
    # index の中身（副次 Issue 混入の有無）を一切問わない恒真アサーションになる（偽陽性を主張
    # できない・レビュー指摘で削除）。実質的な検証は状態欄を「未着手」にした下記ブロックのみが
    # 担う: 副次 Issue（Open）混入により all_closed が False になり、violation3 は検出されない
    # （見逃し方向にしか作用しない＝偽陽性ではないことの確認）。
    broken_fixture = _FIXTURE_ROADMAP_OK.replace(
        "| `M-1` 歩く骨格 | — | 達成済み（`SP-1`〜`SP-3` 完了） |",
        "| `M-1` 歩く骨格 | — | 未着手 |",
    )
    parsed_broken = parse_roadmap(broken_fixture)
    violations_broken, _ = evaluate_roadmap(parsed_broken, sp_state_index=index)
    hit = [v for v in violations_broken if v["type"] == "violation3_all_closed_but_not_started"]
    if hit:
        failures.append(f"副次 Issue（Open）混入時は all_closed=False になるべきだが検出された: {hit}")

    return failures


def _self_test_no_false_positive() -> list[str]:
    """陰性対照: 違反の無いフィクスチャでは何も検出しない。"""
    failures = []
    parsed = parse_roadmap(_FIXTURE_ROADMAP_OK)
    # M-1（達成済み・チェック済み）と整合する Issue 状態: 違反ゼロを期待
    violations, suppressed = evaluate_roadmap(parsed, sp_state_index={1: ["closed"], 2: ["closed"], 3: ["closed"]})
    if violations or suppressed:
        failures.append(f"陰性対照: 違反・抑制ノートともゼロを期待したが violations={violations} suppressed={suppressed}")
    return failures


def run_self_test() -> int:
    groups = [
        ("SP セル展開（4 形態）", _self_test_sp_cell_expansion),
        ("SP セル展開: 列挙+範囲混在（実 M-6 セル・CRITICAL 回帰）", _self_test_expand_sp_cell_mixed_range_and_enum),
        ("SP セル展開: 範囲が 2 つ以上", _self_test_expand_sp_cell_multiple_ranges),
        ("SP セル展開: 開区間 + 単独参照混在", _self_test_expand_sp_cell_open_mixed),
        ("タイトル抽出（3 パターン + 紛らわしい非マッチ）", _self_test_title_extraction),
        ("PR 除外", _self_test_pull_request_filter),
        ("roadmap パース（正常系）", _self_test_parse_roadmap_ok),
        ("roadmap パース（セクション欠落）", _self_test_parse_roadmap_missing_section),
        ("違反3 検出（壊す前/後）", _self_test_violation3_detection),
        ("違反4 検出（壊す前/後）", _self_test_violation4_detection),
        ("違反4: 通過済みキーワード + 装飾つき表記", _self_test_violation4_pass_keyword_and_decoration),
        ("達成宣言キーワードの否定文（WARNING1 回帰）", _self_test_achievement_keyword_negation),
        ("抑制マーカー（§5.1 行/§3 節/空理由/陰性対照/件数不一致/後方互換・Issue #784）", _self_test_suppression_marker),
        ("抑制マーカーの ReDoS 耐性（WARNING2 回帰）", _self_test_suppression_marker_redos),
        ("陰性対照（誤検出なし）", _self_test_no_false_positive),
        ("副次 Issue 混入時の偽陽性なし（Issue #628）", _self_test_secondary_issue_no_false_positive),
    ]
    failed_groups = 0
    total_failures = 0
    for name, fn in groups:
        failures = fn()
        if failures:
            failed_groups += 1
            total_failures += len(failures)
            for f in failures:
                print(f"FAIL[{name}]: {f}")

    if total_failures:
        print(f"\nセルフテスト: {len(groups)} グループ中 {failed_groups} グループ失敗 "
              f"({total_failures} 件の不一致)")
        return 1
    print(f"セルフテスト: {len(groups)} グループ全て PASS")
    return 0


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="roadmap.md の状態記述と GitHub Issue 実態の乖離を機械検知する。"
                     "0=違反なし / 1=違反あり / 2=判定不能。",
    )
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument("--repo", default=None, help="owner/name（既定: git remote から解決）")
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    def emit_indeterminate(message: str) -> None:
        if args.json:
            print(json.dumps({"result": "indeterminate", "reason": message, "checked_at": now_jst_str()}, ensure_ascii=False))
        print(f"⚠️ 判定不能: {message}", file=sys.stderr)

    if not DOC_ABS_PATH.exists():
        emit_indeterminate(f"{DOC_PATH} が見つかりません")
        sys.exit(2)

    md_text = DOC_ABS_PATH.read_text(encoding="utf-8")
    parsed = parse_roadmap(md_text)
    if not parsed["ok"]:
        emit_indeterminate(f"{DOC_PATH} のパースに失敗しました（{parsed['error']}）")
        sys.exit(2)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        emit_indeterminate("GH_TOKEN/GITHUB_TOKEN が未設定のため GitHub API へ到達できません")
        sys.exit(2)

    repo = args.repo or resolve_repo_slug()
    items, err = fetch_all_issues(repo, token)
    if err is not None:
        emit_indeterminate(err)
        sys.exit(2)

    sp_state_index = build_sp_state_index(items)
    violations, suppressed_notes = evaluate_roadmap(parsed, sp_state_index)

    checked_at = now_jst_str()
    if args.json:
        print(json.dumps(
            {"result": "violations" if violations else "ok", "violations": violations,
             "suppressed": suppressed_notes, "checked_at": checked_at, "repo": repo},
            ensure_ascii=False,
        ))

    for note in suppressed_notes:
        symbol = "⚠️" if note.get("legacy") else "🔵"
        print(f"{symbol} {note['detail']}", file=sys.stderr)

    if violations:
        for v in violations:
            print(f"❌ {v['detail']}", file=sys.stderr)
        if not args.json:
            print(f"違反 {len(violations)} 件（{checked_at}）")
        sys.exit(1)

    if not args.json:
        print(f"違反なし（{checked_at}）")
    sys.exit(0)


if __name__ == "__main__":
    main()
