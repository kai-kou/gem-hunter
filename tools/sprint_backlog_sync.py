#!/usr/bin/env python3
"""sprint_backlog_sync.py — SP→Issue 同期（Ready な次の SP-n を 1 件だけ起票する）

【何をするスクリプトか】
`docs/02_requirements/user-story-map.md` §5.3 の `SP-n` 定義（ゴール / 含む / 対応 AC /
見積もり）をパースし、GitHub 上に対応する Issue（タイトル `SP-{n}: {ゴール}`）が
まだ存在しない最小番号の `SP-n` を見つけて **その 1 件だけ** 起票する。

【いつ起票しないか（Ready 条件③）】
`user-story-map.md` §7-9 の Ready 条件③「先行する `SP-n` の Issue がすべて Closed」を満たさない
あいだは **起票しない**（`noop`）。判定の詳細は `decide()` 内のコメントを正本とする。

【なぜ 1 件だけ起票するのか】
`docs/rules/session-concurrency-rules.md`（CP-4）の Issue 論理ロックと相性が悪いため。
先読みで複数 Issue を積むと、後続 `SP-n` に他セッションが着手できる余地を作ってしまい、
「着手順序 = 未 Closed の最小 `SP-N`」という決定論的な順序保証が崩れる。1 firing = 1 件が
CP-4 の多層防御（論理ロック・discover スクリプトの排他チェック）と整合する唯一の粒度。

【どこから呼ばれるか】
`.claude/skills/sprint-cycle-router/SKILL.md` の決定木 Step 3.5（SP→Issue 同期）。
1 firing で Step 0.0（API チャネル判定）→ Step 0.1（早期リターン）→ ... → Step 3.5 の
順に評価され、Ready な次の `SP-n` の Issue が無ければ本スクリプトが 1 件だけ起票する。

【設計上の注意（SD-3 の仮定記録）】
`SP-12 以降` セクションは `US-n` の列挙のみで `見積もり`（sp:N）フィールドを持たない
（「1 スプリント 1〜2 項目で順次追加する」という記述で、機械的に単一の次アイテムへ
分解できる構造ではない）。そのため本スクリプトは `SP-1`〜`SP-11`（§5.3 の標準フィールドを
持つ番号付きセクション）のみを「同期対象」とみなす。`SP-1`〜`SP-11` すべてに Issue が
揃った時点を「在庫枯渇」と判定し、`[Milestone] M-3 到達` Issue を 1 回だけ起票する
（A-5 相当・`docs/rules/user-notification-triage.md` §3 の必須要件に従う）。
`SP-12` 以降の個別 Issue 化は次のマイルストーンでの人間判断・セッション判断に委ねる
（無人 firing で機械分解しない、という BRIEF の判断木「無人 firing の仕様分岐」と同じ思想）。

【API チャネルの多段フォールバック】
`gh` があれば `gh` を使い、失敗（非 0 終了・例外）したら `urllib` + `GH_TOKEN`
（`https://api.github.com`）にフォールバックする。両方失敗したら **起票せず** exit code 2 で
理由を出力する（`docs/rules/github-mcp-fallback-patterns.md` §4「取れなかったことを正確に
伝える」原則に従う。呼び出し元の Claude セッションが `mcp__github__*` で引き取る）。

使い方:
    python3 tools/sprint_backlog_sync.py [--dry-run] [--json] [--repo owner/name]
    python3 tools/sprint_backlog_sync.py --self-test

終了コード:
    0 = 正常（起票した / 起票不要）
    1 = 起票すべきだが失敗した（API 到達はしたが作成が失敗した等）
    2 = API 到達不可（gh・REST 直接呼び出しの双方失敗。呼び出し元は MCP で引き取ること）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_slug import resolve_repo_slug  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = "docs/02_requirements/user-story-map.md"
DOC_ABS_PATH = REPO_ROOT / DOC_PATH

JST = timezone(timedelta(hours=9))

# §5.3 の同期対象は SP-1〜SP-11（見積もりフィールドを持つ番号付きセクションのみ。
# 上記 docstring 「設計上の注意」参照）。
MAX_SYNCABLE_SP = 11

# dup-ok: check_roadmap_status.py の SP_TITLE_PATTERNS[0] と同一パターン。統合は Issue #612 のスコープ外
SP_TITLE_RE = re.compile(r"^SP-(\d+):")
MILESTONE_ISSUE_TITLE = "[Milestone] M-3 到達"
BUG_ISSUE_TITLE = "[sprint_backlog_sync] user-story-map.md §5.3 のパースに失敗"


def now_jst_str() -> str:
    """表示・記録用の現在時刻（JST）。機械処理には使わない。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


# ──────────────────────────────────────────────
# §5.3 パーサ
# ──────────────────────────────────────────────

_SECTION_START_RE = re.compile(r"^### 5\.3\.", re.MULTILINE)
_SECTION_END_RE = re.compile(r"^### 5\.4\.", re.MULTILINE)
_SP_HEADER_RE = re.compile(r"^#### SP-(\d+):\s*(.+?)(?:（`S-\d+`）)?\s*$", re.MULTILINE)
_GOAL_RE = re.compile(r"-\s*\*\*ゴール\*\*:\s*(.+)")
_INCLUDES_RE = re.compile(r"-\s*\*\*含む\*\*:\s*(.+)")
_AC_RE = re.compile(r"-\s*\*\*対応\s*`AC`\*\*:\s*(.+)")
_SP_ESTIMATE_RE = re.compile(r"sp:(\d+)")
# ID 抽出は **プレフィックスを限定する**。`含む` / `対応 AC` の行には
# 「（OAuth のモックは `SP-8`）」「（`NFR-5` / `SP-4` のテストで担保する）」のような
# 補足が括弧書きで付くため、無差別に拾うと本来含まれない ID が Issue に混入する。
_INCLUDE_ID_RE = re.compile(r"`((?:US|E)-\d+)`")
_AC_ID_RE = re.compile(r"`(AC-\d+)`")
# 括弧書きの補足（全角・半角）は ID 抽出の前に落とす
_PARENTHETICAL_RE = re.compile(r"（[^（）]*）|\([^()]*\)")


def _slugify_heading(heading: str) -> str:
    """見出しテキストから GitHub 風アンカーを生成する（近似実装）。

    GitHub の slugger 完全互換は保証しない（Issue 本文の参照リンクを人が読みやすくする
    ための補助であり、リンクが 1 文字ずれても Ready 判定（§5.3 の ID 参照）自体は
    崩れないため、厳密な再実装コストに見合わない・SD-3 の仮定記録）。
    """
    t = heading.strip()
    t = t.replace("`", "")
    t = t.lower()
    # ASCII 記号・全角括弧等を除去し、英数字・アンダースコア・ハイフン・空白・
    # 日本語（ひらがな/カタカナ/漢字）だけを残す。
    t = re.sub(r"[^\w぀-ヿ一-鿿\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t.strip())
    t = re.sub(r"-{2,}", "-", t)
    return t


def _extract_ids(line: str, pattern: re.Pattern[str]) -> list[str]:
    """1 行から ID を抽出する。括弧書きの補足は対象外にし、出現順の重複を除く。"""
    cleaned = _PARENTHETICAL_RE.sub(" ", line)
    seen: list[str] = []
    for x in pattern.findall(cleaned):
        if x not in seen:
            seen.append(x)
    return seen


def parse_sprint_backlog(md_text: str) -> dict:
    """`user-story-map.md` §5.3 の `SP-n`（SP-1〜MAX_SYNCABLE_SP）定義をパースする。

    Returns:
        {
          "ok": bool,                    # §5.3 セクション自体が見つかったか
          "sprints": {n: {...}, ...},    # 正常にパースできた SP-n
          "parse_errors": [n, ...],      # ヘッダーは見つかったが必須フィールドを欠く SP-n
        }

        sprints[n] = {
          "number": n, "goal": str, "includes": [str, ...], "ac": [str, ...],
          "sp": int, "priority": "P1-MVP" | "P1-積み上げ", "anchor": str,
        }
    """
    start_m = _SECTION_START_RE.search(md_text)
    if not start_m:
        return {"ok": False, "sprints": {}, "parse_errors": []}
    end_m = _SECTION_END_RE.search(md_text, start_m.end())
    section = md_text[start_m.end():end_m.start()] if end_m else md_text[start_m.end():]

    headers = list(_SP_HEADER_RE.finditer(section))
    sprints: dict[int, dict] = {}
    parse_errors: list[int] = []

    for i, hm in enumerate(headers):
        n = int(hm.group(1))
        if n > MAX_SYNCABLE_SP:
            continue  # SP-12 以降は同期対象外（docstring 参照）
        block_start = hm.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(section)
        block = section[block_start:block_end]
        heading_text = hm.group(0).lstrip("#").strip()

        goal_m = _GOAL_RE.search(block)
        sp_m = _SP_ESTIMATE_RE.search(block)
        if not goal_m or not sp_m:
            parse_errors.append(n)
            continue

        includes_m = _INCLUDES_RE.search(block)
        ac_m = _AC_RE.search(block)
        includes = _extract_ids(includes_m.group(1), _INCLUDE_ID_RE) if includes_m else []
        ac = _extract_ids(ac_m.group(1), _AC_ID_RE) if ac_m else []

        sprints[n] = {
            "number": n,
            "goal": goal_m.group(1).strip(),
            "includes": includes,
            "ac": ac,
            "sp": int(sp_m.group(1)),
            "priority": priority_label(n),
            "anchor": _slugify_heading(heading_text),
        }

    return {"ok": True, "sprints": sprints, "parse_errors": parse_errors}


def priority_label(n: int) -> str:
    """SP 番号から優先度ラベルを決定する（`SP-1`〜`SP-11` = `P1-MVP`、以降 = `P1-積み上げ`）。"""
    return "P1-MVP" if n <= MAX_SYNCABLE_SP else "P1-積み上げ"


def determine_next_sp(existing_numbers: set[int], sprints: dict[int, dict]) -> int | None:
    """「Issue が存在しない最小番号の SP-n」を返す（数値昇順・§5.5 非解釈）。

    既に Issue が存在する SP-n は状態（open/closed）を問わず対象外にする
    （Closed 済みでも再起票しない。重複防止が目的）。

    ⚠️ 本関数は「次の候補番号」を返すだけで、**着手可能条件（Ready）は判定しない**
    （Ready 条件③の判定は `decide()` の責務・`user-story-map.md` §7-9 / §7-10）。
    """
    for n in sorted(sprints.keys()):
        if n not in existing_numbers:
            return n
    return None


def sp_numbers(issues: list[dict], *, open_only: bool = False) -> set[int]:
    """`SP-n` タイトル規約に一致する Issue の番号集合を返す。

    タイトルから番号を取り出す規則をここ 1 箇所に集約する（重複防止のための「既存番号」と
    Ready 条件③のための「未 Closed 番号」が別基準で動き出さないようにするため）。

    Args:
        open_only: True なら Closed 以外（= 未完了）に絞る。`state` は gh（`OPEN`/`CLOSED`）と
            REST（`open`/`closed`）で表記が異なるため小文字で比較する。`state` が欠落・空文字の
            ときは **未完了側に倒す**（誤って次を起票するより、止まって人が気づく方が安全）。

    ⚠️ 本関数は番号を集めるだけで「先行かどうか」は判定しない。Ready 条件③が言う
    「先行する `SP-n`」は §5.5 の順序制約＝番号昇順を指すため、起票候補より大きい番号を
    ブロック要因にしてはならない（その絞り込みは `decide()` の責務）。
    """
    numbers = set()
    for issue in issues:
        m = SP_TITLE_RE.match(str(issue.get("title", "")).strip())
        if not m:
            continue
        if open_only and str(issue.get("state", "")).lower() == "closed":
            continue
        numbers.add(int(m.group(1)))
    return numbers


# ──────────────────────────────────────────────
# Issue 本文の組み立て
# ──────────────────────────────────────────────

# Issue タイトルから落とす装飾（ゴール行は Markdown なので強調・絵文字・コード記法を含む）
_TITLE_DECORATION_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")
# GitHub の Issue タイトル上限は 256 文字。余裕を見て 120 文字で切る
TITLE_MAX_LEN = 120


def sanitize_goal_for_title(goal: str) -> str:
    """ゴール行を Issue タイトルに載る 1 行へ整える。

    ゴールは Markdown の本文なので `**強調**`・`` `コード` ``・絵文字・装飾が混ざる。
    そのままタイトルにすると `SP-2: 🔴 **後から...** — ...` のような読みにくい見出しになり、
    一覧で番号以外を判別できなくなる。記法だけを落とし、文言は変えない。
    """
    text = goal.replace("**", "").replace("`", "")
    text = _TITLE_DECORATION_RE.sub("", text)
    text = " ".join(text.split())
    if len(text) > TITLE_MAX_LEN:
        text = text[: TITLE_MAX_LEN - 1].rstrip() + "…"
    return text


def build_issue_title(sprint: dict) -> str:
    return f"SP-{sprint['number']}: {sanitize_goal_for_title(sprint['goal'])}"


def build_issue_labels(sprint: dict) -> list[str]:
    return ["type:feature", f"sp:{sprint['sp']}", sprint["priority"]]


def build_doc_url(repo: str, anchor: str) -> str:
    """Issue 本文へ埋めるドキュメントリンクを組み立てる。

    GitHub の Issue 本文はリポジトリ相対リンクを解決しない（`docs/...` と書くと
    `https://github.com/{owner}/{repo}/docs/...` になり 404）。したがって
    blob URL の絶対 URL を生成する。ブランチは既定ブランチ `main` に固定する
    （SP-n の定義はマージ済みの正本を指すため）。
    """
    return f"https://github.com/{repo}/blob/main/{DOC_PATH}#{anchor}"


def build_issue_body(sprint: dict, repo: str) -> str:
    includes = "、".join(f"`{x}`" for x in sprint["includes"]) or "（§5.3 参照）"
    ac = "、".join(f"`{x}`" for x in sprint["ac"]) or "（本スプリントに対応 AC なし。§5.3 参照）"
    anchor_link = build_doc_url(repo, sprint["anchor"])
    return (
        f"## ゴール\n\n{sprint['goal']}\n\n"
        f"## 含む\n\n{includes}\n\n"
        f"## 対応 AC\n\n{ac}\n\n"
        f"## 見積もり\n\n`sp:{sprint['sp']}`\n\n"
        f"## 参照\n\n"
        f"- {DOC_PATH} §5.3 SP-{sprint['number']}: {anchor_link}\n"
        "- 操作レビュー手順・受け入れ条件の本文はここにコピーしない（ID 参照が正本）\n\n"
        f"## Done の判定\n\n"
        "`docs/rules/sprint-development-rules.md` の `SD-1`（動作確認できる状態で終わる）・"
        "`SD-2`（TDD 主体・常に動作担保）の完了条件に従う。\n\n"
        f"---\n_起票: `tools/sprint_backlog_sync.py`（{now_jst_str()}）_\n"
    )


def build_bug_issue_body(parse_errors: list[int], section_missing: bool) -> str:
    if section_missing:
        detail = f"`{DOC_PATH}` の `### 5.3.` セクション自体が見つかりませんでした。"
    else:
        detail = "以下の `SP-n` セクションで必須フィールド（`ゴール` または `見積もり`）を抽出できませんでした:\n\n" + "\n".join(
            f"- `SP-{n}`" for n in parse_errors
        )
    return (
        "## 検出内容\n\n"
        f"{detail}\n\n"
        "## 影響\n\n"
        "`tools/sprint_backlog_sync.py` が該当 `SP-n` の起票をスキップしました"
        "（壊れた内容で Issue を起票しないため）。ドキュメントの見出し・箇条書き書式が"
        f"`{DOC_PATH}` §5.3 の想定パターンから逸脱している可能性があります。\n\n"
        "## 対応方針\n\n"
        f"- `{DOC_PATH}` §5.3 の該当セクションの書式を確認し、パーサ（`tools/sprint_backlog_sync.py` の "
        "`parse_sprint_backlog`）とドキュメントのどちらを合わせるべきか判断する\n\n"
        "## 完了条件\n\n"
        "- `python3 tools/sprint_backlog_sync.py --dry-run --json` が対象 `SP-n` を正常にパースする\n"
        f"\n---\n_起票: `tools/sprint_backlog_sync.py`（{now_jst_str()}）_\n"
    )


def build_milestone_issue_body() -> str:
    return (
        "## ユーザーが取るべき具体的アクション\n\n"
        f"`{DOC_PATH}` §5.3 の `SP-1`〜`SP-{MAX_SYNCABLE_SP}` すべてに対応する Issue が出揃いました"
        "（在庫枯渇）。`SP-12` 以降（積み上げ）に着手するかどうか、着手する場合はどの項目から"
        "1〜2 個ずつ Issue化するかを判断してください。\n\n"
        "## 該当境界\n\n"
        "A-5（新規マイルストーンの追加はプロジェクト計画の骨格に影響するため既約境界外）\n\n"
        "## 対応しない場合の結果\n\n"
        "`SP-12` 以降の新規 Issue が自動生成されないまま、ルーティンは Step 3.5 をスキップし続けます"
        "（他の Step は通常どおり自律実行されるため、既存タスクの消化自体は止まりません）。\n\n"
        "## Claude 側の状態\n\n"
        "`SP-1`〜`SP-11`（`S-0`＋`S-1`＝MVP 完成分）は本ルーティンが自律的に順次 Issue 化・実装済みです。"
        "本 Issue は 1 回だけ起票し、以後は本 Issue の有無で在庫枯渇状態を判定します"
        "（state ファイルは持ちません）。\n\n"
        f"---\n_起票: `tools/sprint_backlog_sync.py`（{now_jst_str()}）_\n"
    )


# ──────────────────────────────────────────────
# 意思決定（純関数・self-test 対象）
# ──────────────────────────────────────────────

def decide(md_text: str, existing_issues: list[dict], repo: str = "kai-kou/gem-hunter") -> dict:
    """今回の firing で何をすべきかを決定する。ネットワークに触れない純関数。

    Args:
        existing_issues: `{"title": str, "state": "open"|"closed"}` の一覧（PR は含めない）。

    Returns:
        {"action": "create_sp_issue" | "create_milestone_issue" | "create_bug_issue" | "noop",
         ...action 別の追加フィールド, "reason": str}
    """
    existing_issue_titles = [str(i.get("title", "")) for i in existing_issues]
    parsed = parse_sprint_backlog(md_text)

    if not parsed["ok"]:
        if BUG_ISSUE_TITLE in existing_issue_titles:
            return {"action": "noop", "reason": "§5.3 セクション欠落を検出済みで bug Issue も既存"}
        return {
            "action": "create_bug_issue",
            "title": BUG_ISSUE_TITLE,
            "body": build_bug_issue_body([], section_missing=True),
            "labels": ["type:bug"],
            "reason": "§5.3 セクション自体が見つからない",
        }

    if parsed["parse_errors"]:
        if BUG_ISSUE_TITLE in existing_issue_titles:
            return {
                "action": "noop",
                "reason": f"パース失敗 SP-n={parsed['parse_errors']} を検出済みで bug Issue も既存",
            }
        return {
            "action": "create_bug_issue",
            "title": BUG_ISSUE_TITLE,
            "body": build_bug_issue_body(parsed["parse_errors"], section_missing=False),
            "labels": ["type:bug"],
            "reason": f"SP-n={parsed['parse_errors']} のパースに失敗（該当 SP-n の起票はスキップ）",
        }

    existing_numbers = sp_numbers(existing_issues)
    next_n = determine_next_sp(existing_numbers, parsed["sprints"])

    # Ready 条件③（`user-story-map.md` §7-9): 先行する SP-n の Issue がすべて Closed。
    # 「先行する」は §5.5 の順序制約＝番号昇順を指すため、**起票候補 next_n より小さい番号だけ**を
    # ブロック要因にする。ドキュメント §5.3 の範囲外の番号（旧番号の残骸・先出しされた SP-12 等）で
    # 起票が恒久停止するのを防ぐ（そのまま数えると無人 firing がサイレントに止まり続ける）。
    # next_n が None（全 SP-n に Issue がある）の場合だけは全 open を数える —
    # 🔴 在庫枯渇（next_n is None）判定より前に置く: `sprint-cycle-router` SKILL.md §9 は
    # 「全 SP-n が Closed になった時点で在庫枯渇」と定めており、着手中の SP-n が残ったまま
    # `[Milestone] M-3 到達`（= プロダクト完成の通知）を発火させてはならない。
    still_open = {
        n for n in sp_numbers(existing_issues, open_only=True)
        if next_n is None or n < next_n
    }
    if still_open:
        return {
            "action": "noop",
            "reason": (
                f"先行する {'・'.join(f'SP-{n}' for n in sorted(still_open))} が未 Closed のため "
                f"Ready 条件③（先行 SP-n がすべて Closed）を満たさない"
            ),
            "blocked_by_open_sp": sorted(still_open),
            "next_sp_candidate": next_n,
        }

    if next_n is None:
        if MILESTONE_ISSUE_TITLE in existing_issue_titles:
            return {"action": "noop", "reason": "在庫枯渇済みでマイルストーン Issue も既存"}
        return {
            "action": "create_milestone_issue",
            "title": MILESTONE_ISSUE_TITLE,
            "body": build_milestone_issue_body(),
            "labels": [],
            "reason": f"SP-1〜SP-{MAX_SYNCABLE_SP} すべてに Issue が存在（在庫枯渇）",
        }

    sprint = parsed["sprints"][next_n]
    return {
        "action": "create_sp_issue",
        "sp_number": next_n,
        "title": build_issue_title(sprint),
        "body": build_issue_body(sprint, repo),
        "labels": build_issue_labels(sprint),
        "reason": f"SP-{next_n} の Issue が未存在（既存 SP 番号: {sorted(existing_numbers)}）",
    }


# ──────────────────────────────────────────────
# API チャネル（gh → urllib + GH_TOKEN の多段フォールバック）
# GH_TOKEN の値はログ・エラー出力に一切出さない。
# ──────────────────────────────────────────────

REPO = resolve_repo_slug()


def _validate_repo() -> None:
    owner, _, name = REPO.partition("/")
    if not owner or not name or "__" in REPO:
        print(
            f"ERROR: REPO の形式が不正です: '{REPO}'（owner/name 形式が必要。"
            "bootstrap.sh でプレースホルダを置換するか --repo で指定してください）",
            file=sys.stderr,
        )
        sys.exit(2)


def _run_gh(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return False, "gh コマンドが見つかりません"
    except subprocess.TimeoutExpired:
        return False, "gh コマンドがタイムアウトしました"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or f"gh 実行失敗: {' '.join(args)}"
    return True, result.stdout.strip()


def _http_request(url: str, token: str, payload: str | None = None) -> tuple[bool, str]:
    """GitHub REST を叩く（GET / POST）。

    🔴 token を **サブプロセスの引数に載せない**。`curl -H "Authorization: Bearer <token>"` は
    同一ホストの他プロセスから `ps` / `/proc/<pid>/cmdline` で読めてしまい、無人ルーティンで
    毎 firing 実行されるぶん露出機会が積み上がる。Python プロセス内でヘッダを組み立てる。
    """
    data = payload.encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gem-hunter-sprint-backlog-sync",
    }
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return True, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # 本文にトークンは含まれないが、念のため詳細は載せずステータスのみ返す
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"接続失敗（{type(e).__name__}）"
    except TimeoutError:
        return False, "リクエストがタイムアウトしました"


def list_all_issues() -> tuple[list[dict], str | None]:
    """全 Issue（state=all）の `{"title", "state"}` 一覧を取得する。gh → urllib+GH_TOKEN の順に試す。

    Returns (issues, error_reason)。取得失敗時は issues=[] で error_reason に理由を入れる
    （「取得失敗」を「0 件」と混同しない・github-mcp-fallback-patterns.md §4）。

    `state` は Ready 条件③（先行 `SP-n` がすべて Closed）の判定に使うため、タイトルだけに
    落とさずそのまま保持する（gh は `OPEN`/`CLOSED`、REST は `open`/`closed` を返すので
    比較側で小文字化する）。
    """
    ok, out = _run_gh([
        "issue", "list", "-R", REPO, "--state", "all",
        "--json", "number,title,state", "--limit", "300",
    ])
    if ok:
        try:
            issues = json.loads(out)
            return [
                {"title": i.get("title", ""), "state": i.get("state", "")} for i in issues
            ], None
        except json.JSONDecodeError:
            ok = False
            out = "gh の JSON 応答が不正"
    gh_err = out

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return [], f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"

    issues: list[dict] = []
    for page in range(1, 4):  # 100件 x 3ページ = 最大300件（gh 経路と同等の上限）
        ok2, out2 = _http_request(
            f"https://api.github.com/repos/{REPO}/issues?state=all&per_page=100&page={page}",
            token,
        )
        if not ok2:
            return [], f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
        try:
            batch = json.loads(out2)
        except json.JSONDecodeError:
            return [], f"gh 失敗（{gh_err}）・REST 応答のパースに失敗"
        if not batch:
            break
        # /issues エンドポイントは PR も含むため pull_request キーで除外する
        issues.extend(
            {"title": i.get("title", ""), "state": i.get("state", "")}
            for i in batch
            if "pull_request" not in i
        )
        if len(batch) < 100:
            break
    return issues, None


def create_issue(title: str, body: str, labels: list[str]) -> tuple[bool, str]:
    """gh → urllib+GH_TOKEN の順で Issue を起票する。成功時 (True, issue_url)。"""
    args = ["issue", "create", "-R", REPO, "--title", title, "--body", body]
    for label in labels:
        args += ["--label", label]
    ok, out = _run_gh(args)
    if ok:
        return True, out.strip()
    gh_err = out

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return False, f"gh 失敗（{gh_err}）かつ GH_TOKEN/GITHUB_TOKEN 未設定"

    payload = json.dumps({"title": title, "body": body, "labels": labels}, ensure_ascii=False)
    ok2, out2 = _http_request(f"https://api.github.com/repos/{REPO}/issues", token, payload)
    if not ok2:
        return False, f"gh 失敗（{gh_err}）・REST も失敗（{out2}）"
    try:
        data = json.loads(out2)
    except json.JSONDecodeError:
        return False, f"gh 失敗（{gh_err}）・REST 応答のパースに失敗"
    return True, data.get("html_url", "")


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────

_FIXTURE_MD_OK = """
### 5.3. スプリント一覧

#### SP-1: 検索して一覧が出る（`S-0`）

- **ゴール**: キーワードで GitHub を検索し、結果が一覧で見える
- **含む**: `US-6` / `US-11` / `E-1` / `E-2`
- **操作レビュー**:
  1. 検索欄に入力する
- **対応 `AC`**: `AC-1` / `AC-2`
- **見積もり**: `sp:8`（プロジェクト骨格）

#### SP-2: URL とロケールの形が決まる（`S-0`）

- **ゴール**: 後から変えると波及する境界を固定する
- **含む**: `US-1` / `US-9`
- **対応 `AC`**: `AC-2`
- **見積もり**: `sp:5`（不確実性）

#### SP-3: 詳細まで往復できる（`S-0`）

- **ゴール**: 一覧から詳細への往復が通る
- **含む**: `US-16`
- **対応 `AC`**: `AC-4`
- **見積もり**: `sp:3`

### 5.4. スプリント合計と負荷

| ダミー | 表 |
"""

# SP-2 の「見積もり」行が欠落（異常系）
_FIXTURE_MD_BROKEN = """
### 5.3. スプリント一覧

#### SP-1: 検索して一覧が出る（`S-0`）

- **ゴール**: キーワードで検索する
- **含む**: `US-6`
- **対応 `AC`**: `AC-1`
- **見積もり**: `sp:8`

#### SP-2: 見積もりが書かれていない（`S-0`）

- **ゴール**: 何かをする
- **含む**: `US-1`

### 5.4. スプリント合計と負荷
"""

_FIXTURE_MD_NO_SECTION = "# 見出しだけの無関係なドキュメント\n\n本文。\n"


def _self_test_parser_ok() -> list[str]:
    failures = []
    parsed = parse_sprint_backlog(_FIXTURE_MD_OK)
    if not parsed["ok"]:
        failures.append("parser正常系: ok=True を期待したが False")
    if parsed["parse_errors"]:
        failures.append(f"parser正常系: parse_errors が空を期待したが {parsed['parse_errors']}")
    if set(parsed["sprints"].keys()) != {1, 2, 3}:
        failures.append(f"parser正常系: sprints キーが {{1,2,3}} を期待したが {set(parsed['sprints'].keys())}")
    sp1 = parsed["sprints"].get(1, {})
    if sp1.get("goal") != "キーワードで GitHub を検索し、結果が一覧で見える":
        failures.append(f"parser正常系: SP-1 ゴール抽出が不一致: {sp1.get('goal')!r}")
    if sp1.get("sp") != 8:
        failures.append(f"parser正常系: SP-1 見積もりが 8 を期待したが {sp1.get('sp')!r}")
    if sp1.get("includes") != ["US-6", "US-11", "E-1", "E-2"]:
        failures.append(f"parser正常系: SP-1 含む が不一致: {sp1.get('includes')!r}")
    if sp1.get("ac") != ["AC-1", "AC-2"]:
        failures.append(f"parser正常系: SP-1 対応AC が不一致: {sp1.get('ac')!r}")
    if sp1.get("priority") != "P1-MVP":
        failures.append(f"parser正常系: SP-1 優先度が P1-MVP を期待したが {sp1.get('priority')!r}")
    return failures


def _self_test_parser_broken() -> list[str]:
    failures = []
    parsed = parse_sprint_backlog(_FIXTURE_MD_BROKEN)
    if not parsed["ok"]:
        failures.append("parser異常系: セクション自体は見つかる想定（ok=True）")
    if parsed["parse_errors"] != [2]:
        failures.append(f"parser異常系: parse_errors=[2] を期待したが {parsed['parse_errors']}")
    if 1 not in parsed["sprints"]:
        failures.append("parser異常系: SP-1 は正常パースされる想定")
    if 2 in parsed["sprints"]:
        failures.append("parser異常系: SP-2 はパース失敗のため sprints に含まれない想定")

    parsed2 = parse_sprint_backlog(_FIXTURE_MD_NO_SECTION)
    if parsed2["ok"]:
        failures.append("parser異常系: §5.3 セクション欠落時は ok=False を期待")
    return failures


def _self_test_next_sp() -> list[str]:
    failures = []
    parsed = parse_sprint_backlog(_FIXTURE_MD_OK)["sprints"]
    n = determine_next_sp(set(), parsed)
    if n != 1:
        failures.append(f"次SP決定: 既存なしで 1 を期待したが {n}")
    n = determine_next_sp({1}, parsed)
    if n != 2:
        failures.append(f"次SP決定: SP-1既存で 2 を期待したが {n}")
    n = determine_next_sp({1, 2}, parsed)
    if n != 3:
        failures.append(f"次SP決定: SP-1,2既存で 3 を期待したが {n}")
    n = determine_next_sp({1, 2, 3}, parsed)
    if n is not None:
        failures.append(f"次SP決定: 全既存で None（枯渇）を期待したが {n}")
    # Closed 済みでも既存扱い（再起票しない）
    n = determine_next_sp({1, 3}, parsed)
    if n != 2:
        failures.append(f"次SP決定: 歯抜け（1,3既存）で 2 を期待したが {n}")
    return failures


def _self_test_labels() -> list[str]:
    failures = []
    if priority_label(1) != "P1-MVP":
        failures.append("ラベル決定: SP-1 は P1-MVP を期待")
    if priority_label(11) != "P1-MVP":
        failures.append("ラベル決定: SP-11 は P1-MVP を期待")
    if priority_label(12) != "P1-積み上げ":
        failures.append("ラベル決定: SP-12 は P1-積み上げ を期待")
    if priority_label(30) != "P1-積み上げ":
        failures.append("ラベル決定: SP-30 は P1-積み上げ を期待")

    parsed = parse_sprint_backlog(_FIXTURE_MD_OK)["sprints"]
    labels = build_issue_labels(parsed[1])
    if labels != ["type:feature", "sp:8", "P1-MVP"]:
        failures.append(f"ラベル決定: SP-1 の Issue ラベルが不一致: {labels}")
    return failures


def _self_test_id_extraction() -> list[str]:
    """`含む` / `対応 AC` の ID 抽出が括弧書きの補足を拾わないことを検証する。"""
    failures = []
    cases = [
        # (行, パターン, 期待)
        ("`E-11`（**検索・詳細 API のモックのみ**。OAuth のモックは `SP-8`）/ `E-12`",
         _INCLUDE_ID_RE, ["E-11", "E-12"]),
        ("なし（`NFR-5` / `NFR-17` / `NFR-18`。`SP-4` のテストで担保する）",
         _AC_ID_RE, []),
        ("`US-6` / `US-11` / `E-1`", _INCLUDE_ID_RE, ["US-6", "US-11", "E-1"]),
        ("`AC-1` / `AC-2` / `AC-1`", _AC_ID_RE, ["AC-1", "AC-2"]),  # 重複は出現順で 1 回
    ]
    for line, pattern, want in cases:
        got = _extract_ids(line, pattern)
        if got != want:
            failures.append(f"ID 抽出: {line!r} → {got}（期待 {want}）")
    return failures


def _self_test_title() -> list[str]:
    """Issue タイトル整形（Markdown 記法・絵文字の除去と長さ制限）を検証する。"""
    failures = []
    cases = [
        ("🔴 **境界を固定する** — URL の形", "境界を固定する — URL の形"),
        ("`use cache` を入れる", "use cache を入れる"),
        ("普通のゴール", "普通のゴール"),
        ("  余白   が   多い  ", "余白 が 多い"),
    ]
    for src, want in cases:
        got = sanitize_goal_for_title(src)
        if got != want:
            failures.append(f"タイトル整形: {src!r} → {got!r}（期待 {want!r}）")

    long_title = sanitize_goal_for_title("あ" * 300)
    if len(long_title) != TITLE_MAX_LEN:
        failures.append(f"タイトル整形: 長文が {TITLE_MAX_LEN} 文字に収まっていない（{len(long_title)}）")
    if not long_title.endswith("…"):
        failures.append("タイトル整形: 切り詰め時に省略記号が付いていない")

    parsed = parse_sprint_backlog(_FIXTURE_MD_OK)["sprints"]
    title = build_issue_title(parsed[1])
    if not title.startswith("SP-1: "):
        failures.append(f"タイトル整形: 接頭辞が不正: {title!r}")
    if not SP_TITLE_RE.match(title):
        failures.append(f"タイトル整形: 既存判定用の正規表現に一致しない: {title!r}")
    return failures


def _issue(title: str, state: str = "closed") -> dict:
    """セルフテスト用の Issue スタブ（既定は Closed = Ready 条件③を満たす側）。"""
    return {"title": title, "state": state}


def _self_test_decide() -> list[str]:
    failures = []
    r = decide(_FIXTURE_MD_OK, existing_issues=[])
    if r["action"] != "create_sp_issue" or r.get("sp_number") != 1:
        failures.append(f"decide: 既存 Issue なしで SP-1 起票を期待したが {r}")

    r = decide(_FIXTURE_MD_OK, existing_issues=[_issue("SP-1: 検索して一覧が出る")])
    if r["action"] != "create_sp_issue" or r.get("sp_number") != 2:
        failures.append(f"decide: SP-1 が Closed なら SP-2 起票を期待したが {r}")

    all_issues = [_issue(f"SP-{n}: dummy") for n in (1, 2, 3)]
    r = decide(_FIXTURE_MD_OK, existing_issues=all_issues)
    if r["action"] != "create_milestone_issue":
        failures.append(f"decide: 全SP既存で在庫枯渇（マイルストーン起票）を期待したが {r}")

    r = decide(_FIXTURE_MD_OK, existing_issues=all_issues + [_issue(MILESTONE_ISSUE_TITLE)])
    if r["action"] != "noop":
        failures.append(f"decide: マイルストーン Issue 既存で noop を期待したが {r}")

    r = decide(_FIXTURE_MD_BROKEN, existing_issues=[])
    if r["action"] != "create_bug_issue" or r["title"] != BUG_ISSUE_TITLE:
        failures.append(f"decide: パース失敗で bug Issue 起票を期待したが {r}")

    r = decide(_FIXTURE_MD_BROKEN, existing_issues=[_issue(BUG_ISSUE_TITLE)])
    if r["action"] != "noop":
        failures.append(f"decide: bug Issue 既存で noop（重複起票しない）を期待したが {r}")

    r = decide(_FIXTURE_MD_NO_SECTION, existing_issues=[])
    if r["action"] != "create_bug_issue":
        failures.append(f"decide: セクション欠落で bug Issue 起票を期待したが {r}")

    return failures


def _self_test_ready_condition() -> list[str]:
    """Ready 条件③（先行 SP-n がすべて Closed）— `user-story-map.md` §7-9 / §7-10。"""
    failures = []

    # open な SP-1 がある間は SP-2 を先読み起票しない（本条件の中核・実測バグの回帰テスト）
    r = decide(_FIXTURE_MD_OK, existing_issues=[_issue("SP-1: 検索して一覧が出る", "open")])
    if r["action"] != "noop":
        failures.append(f"Ready③: SP-1 が open なら noop を期待したが {r}")
    elif r.get("blocked_by_open_sp") != [1] or r.get("next_sp_candidate") != 2:
        failures.append(f"Ready③: noop の内訳が不正: {r}")

    # 着手中（status:in-progress）も open なので同じ扱いになる
    r = decide(_FIXTURE_MD_OK, existing_issues=[
        _issue("SP-1: 検索して一覧が出る", "OPEN"),  # gh 経路の大文字表記
    ])
    if r["action"] != "noop":
        failures.append(f"Ready③: state の大文字表記（OPEN）を open と判定できていない: {r}")

    # 途中の SP-n が open でも止まる（SP-1 Closed / SP-2 open → SP-3 を起票しない）
    r = decide(_FIXTURE_MD_OK, existing_issues=[
        _issue("SP-1: a"), _issue("SP-2: b", "open"),
    ])
    if r["action"] != "noop" or r.get("blocked_by_open_sp") != [2]:
        failures.append(f"Ready③: SP-2 が open なら noop を期待したが {r}")

    # すべて Closed なら通常どおり次の 1 件を起票する
    r = decide(_FIXTURE_MD_OK, existing_issues=[_issue("SP-1: a", "CLOSED")])
    if r["action"] != "create_sp_issue" or r.get("sp_number") != 2:
        failures.append(f"Ready③: 全 Closed（大文字表記）で SP-2 起票を期待したが {r}")

    # SP-n 以外の open Issue はブロック要因にならない
    r = decide(_FIXTURE_MD_OK, existing_issues=[
        _issue("SP-1: a"), _issue("bug: 何かが壊れている", "open"),
    ])
    if r["action"] != "create_sp_issue" or r.get("sp_number") != 2:
        failures.append(f"Ready③: SP-n 以外の open Issue に反応してはいけない: {r}")

    # 在庫枯渇より Ready 条件③が先に効く（着手中の SP-n が残る限り M-3 到達を通知しない）
    r = decide(_FIXTURE_MD_OK, existing_issues=[
        _issue("SP-1: a"), _issue("SP-2: b"), _issue("SP-3: c", "open"),
    ])
    if r["action"] != "noop" or r.get("blocked_by_open_sp") != [3]:
        failures.append(
            f"Ready③: SP-3 が open のあいだは在庫枯渇（M-3 到達）と判定してはいけない: {r}"
        )

    # 全 SP-n が Closed になってはじめて在庫枯渇（SKILL.md §9）
    r = decide(_FIXTURE_MD_OK, existing_issues=[_issue(f"SP-{n}: x") for n in (1, 2, 3)])
    if r["action"] != "create_milestone_issue":
        failures.append(f"Ready③: 全 SP-n が Closed なら在庫枯渇判定を期待したが {r}")

    # 🔴 起票候補より大きい番号の open Issue はブロック要因にしない
    # （旧番号の残骸・先出しされた SP-12 等で無人 firing がサイレント停止するのを防ぐ）
    r = decide(_FIXTURE_MD_OK, existing_issues=[
        _issue("SP-1: a"), _issue("SP-2: b"), _issue("SP-99: 旧番号の残骸", "open"),
    ])
    if r["action"] != "create_sp_issue" or r.get("sp_number") != 3:
        failures.append(f"Ready③: 候補（SP-3）より後ろの SP-99 が open でも起票を止めない: {r}")

    # ドキュメント §5.3 の範囲外（SP-12 以降）の先出し Issue でも同じ
    r = decide(_FIXTURE_MD_OK, existing_issues=[
        _issue("SP-1: a"), _issue("SP-12: 先出しした積み上げスプリント", "open"),
    ])
    if r["action"] != "create_sp_issue" or r.get("sp_number") != 2:
        failures.append(f"Ready③: 範囲外の SP-12 が open でも SP-2 の起票を止めない: {r}")

    return failures


def run_self_test() -> int:
    # グループを追加したらこのリストに 1 行足すだけでよい（件数を別途手で数えない）
    groups = [
        ("パーサ（正常系）", _self_test_parser_ok),
        ("パーサ（異常系）", _self_test_parser_broken),
        ("次に着手する SP の決定", _self_test_next_sp),
        ("ラベル決定", _self_test_labels),
        ("タイトル整形", _self_test_title),
        ("ID 抽出", _self_test_id_extraction),
        ("decide 統合", _self_test_decide),
        ("Ready 条件③（先行 SP-n が Closed）", _self_test_ready_condition),
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

def _read_doc_text() -> str:
    return DOC_ABS_PATH.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SP→Issue 同期: Ready な次の SP-n の Issue が無ければ 1 件だけ起票する",
    )
    parser.add_argument("--dry-run", action="store_true", help="起票せず判定結果のみ出力する")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument("--repo", default=None, help="owner/name（既定: git remote から解決）")
    # selftest-wiring-ok: スプリント自走ルーティンの SP→Issue 同期でのみ起動する運用ツールで、PR 前の品質ゲートではない
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    global REPO
    if args.repo:
        REPO = args.repo
    _validate_repo()

    if not DOC_ABS_PATH.exists():
        msg = f"{DOC_PATH} が見つかりません"
        if args.json:
            print(json.dumps({"action": "error", "reason": msg}, ensure_ascii=False))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(2)

    md_text = _read_doc_text()
    issues, err = list_all_issues()
    if err is not None:
        if args.json:
            print(json.dumps({"action": "error", "reason": err}, ensure_ascii=False))
        else:
            print(f"ERROR: gh_unavailable: {err}", file=sys.stderr)
        sys.exit(2)

    decision = decide(md_text, issues, REPO)

    if args.dry_run:
        out = {**decision, "dry_run": True, "checked_at": now_jst_str(), "repo": REPO}
        if args.json:
            print(json.dumps(out, ensure_ascii=False))
        else:
            print(f"[dry-run] action={decision['action']}")
            if "title" in decision:
                print(f"  title: {decision['title']}")
            if "labels" in decision:
                print(f"  labels: {decision['labels']}")
            print(f"  reason: {decision['reason']}")
            print(f"  checked_at: {out['checked_at']}")
        sys.exit(0)

    if decision["action"] == "noop":
        if args.json:
            print(json.dumps({**decision, "checked_at": now_jst_str()}, ensure_ascii=False))
        else:
            print(f"起票不要: {decision['reason']}")
        sys.exit(0)

    ok, result = create_issue(decision["title"], decision["body"], decision.get("labels", []))
    if not ok:
        if args.json:
            print(json.dumps({**decision, "created": False, "error": result}, ensure_ascii=False))
        else:
            print(f"ERROR: Issue 起票に失敗しました: {result}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps({**decision, "created": True, "issue_url": result}, ensure_ascii=False))
    else:
        print(f"起票しました: {decision['title']}")
        print(f"  {result}")
    sys.exit(0)


if __name__ == "__main__":
    main()
