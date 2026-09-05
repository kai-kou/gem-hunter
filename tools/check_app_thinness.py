#!/usr/bin/env python3
"""check_app_thinness.py — `app/` 層が「薄い」かどうかの機械検査（Issue #612）

SSOT: `docs/03_design/architecture/application-architecture.md`
      「Server Component / Route Handler は composition root からユースケースを取り、
        結果を `src/ui/` に渡すだけ。ロジックを書かない」

## なぜこの検査が要るのか

既存の `tools/check_architecture_boundaries.py` は import の **向き**（どの層からどの層へ）
しか見ておらず、「向きは正しいが `app/` の中身が太っている」型の違反を検出できない。
実際に人手レビューでしか見つからなかった事故が 2 件ある（Issue #604 / #612）:

  1. 同じオーケストレーション手順が `app/[locale]/page.tsx` と `app/api/search/route.ts` に
     重複していた（ユースケース層へ寄せるべき手順が `app/` に 2 箇所書かれていた）。
  2. `app/[locale]/page.tsx` が、検索結果ポートと Gem バッジポートという **2 つのポートの
     結果を実行時に組み合わせて** 表示用データ（`badgedFullNames`）を算出していた
     （`.filter().map().slice()` のチェーンが `app/` に居座っていた＝本来ユースケース層の仕事）。

どちらも「import の向き」は正しいまま起きる。そこで本スクリプトは **量的な代理指標**
（ファイルが太っていく過程で必ず増える数値）を実測し、閾値超過を検出する。

## 4 つの指標と、それぞれが「薄さ」の代理指標になる理由

1. **ファイル行数**: ロジックが増えるほど行数は単調に増える。最も粗いが最も見逃しにくい指標。
2. **トップレベル関数・コンポーネント定義の数**（`export default` の 1 個は除く）:
   ヘルパー関数が `app/` に増えていくのは「本来ユースケース/UI 層に置くべき手続きを
   その場しのぎで `app/` に生やしている」兆候。1 ファイル 1 エントリポイントから離れるほど怪しい。
3. **`src/domain/` からの import 数**: `app/` がドメインの値オブジェクトを直接いくつも触っているなら、
   本来ユースケース層が返すべき「表示用に整形済みの結果」を `app/` 側で自分で組み立てている
   （ドメイン知識が `app/` に漏れている）可能性が高い。
4. **配列操作チェーンの数**（`.filter(` `.map(` `.reduce(` `.sort(` `.slice(` の出現数）:
   🔴 Issue #604 と #612 の両方を検出できる指標なので必須。複数ポートの結果をその場で
   `.filter().map().slice()` して整形するのは典型的な「薄くない `app/`」の症状。

## 既知の限界（ファイル分割による回避・Issue #619 セルフレビューで実測済み）

🔴 **本検査はファイル単位でしか 4 指標を評価しないため、`app/` 配下でファイルを分割するだけで
回避できる**（意図的に検査を欺こうとした場合の話であり、ふつうにリファクタしていて偶然踏む
類の話ではない）。実測された回避手口:

```
単一ファイルなら domain import 4 件（>3）・配列チェーン 2 件（>1）で Error になる量のロジックを、
  app/[locale]/page-split2.tsx（helperA/helperB を呼ぶだけの薄い皮）
  app/[locale]/_orchestration-a.ts（domain import 3 件・chain 1 件 = 単独では閾値以下）
  app/[locale]/_orchestration-b.ts（domain import 3 件・chain 1 件 = 単独では閾値以下）
の 3 ファイルへ分割すると、各ファイルは単独では閾値以下になり検出されない。
```

これに対して本スクリプトは、**`app/` 内の相対 import（`./…` `../…`）で解決できる依存関係だけを
辿り、依存先ファイルの 4 指標を依存元（エントリポイント）の実測値に合算してから閾値判定する**
（`rolled_up_metrics`）。上記の例は `page-split2.tsx` の合算値が domain_imports=6 / array_chains=2
となり検出できる（`SELF_TEST_CASES` に固定化済み）。

**それでもなお検出できないケース（意図的に残した限界）**:

- **相対 import で繋がっていない分割**（例: 共通ロジックを import せず、無関係な複数の
  route/page ファイルへコピー&ペーストで分散する。あるいは `app/` 外の `src/` エイリアス経由で
  読み込む形に偽装する）は依存グラフに辺が存在しないため合算されない。
- **依存グラフを辿れない import**（`@/…` エイリアス・パッケージ名・動的 `import()` 式）は対象外。
  `app/` から `app/` 内の別ファイルへは相対 import が実務上の標準であり（`ARCH-3` 前提と同じ）、
  エイリアス経由の app 内 import は現状の実測コードベースに存在しないため対象に含めていない。
- リポジトリ全体（`app/` の総量）を集計して閾値を設ける案（下記選択肢 (c)）は **意図的に不採用**。
  ページ数が増えるたびに正当な理由で総量が伸びる（1 ページ追加 = 総 domain import が +1〜数個）ため、
  「意図的な回避」と「素直な機能追加」を区別できず誤検知が避けられないと判断した。

**意図的な回避（上記の残存ケース）の抑止は人手レビューの担当**であり、本検査は「うっかりの
肥大化」と「単純な相対 import 分割での回避」を止めるところまでを守備範囲とする。

## allowlist の運用方針

🔴 **既存の違反を後追いで赤くしない**。初回導入時点で実測し、閾値を超えているファイルは
`ALLOWLIST` に「ファイルパス → 4 指標の現在の実測値」として登録し、検査を PASS させる。

- allowlist 登録ファイルは、登録時点の実測値が **そのファイル専用の上限** になる
  （デフォルト閾値ではなく実測値そのものが上限＝現状より 1 でも悪化したら検出する）
- allowlist 未登録ファイル（＝新規ファイル、または現状すでにデフォルト閾値以下のファイル）は
  `DEFAULT_THRESHOLDS` がそのまま上限になる
- allowlist 登録ファイルの実測値がデフォルト閾値を下回っている指標があっても構わない
  （そのファイルの「現状のスナップショット」を記録するのが目的であり、他ファイルとの
  比較のための一律の基準ではない）
- 是正が進んで allowlist 登録ファイルの実測値がデフォルト閾値以下になったら、
  allowlist から外してよい（棚卸しは人手判断）

## 重大度

既定は **Warning**（exit 0）。`--strict` を付けたときのみ Error 扱い（exit 1）にする。
`run_checks.sh` への配線・重大度の最終決定は別レーンが行う（本スクリプトは exit code の
仕様を提供するだけ）。

使い方:
  python3 tools/check_app_thinness.py              # app/ 配下を検査（既定 Warning・exit 0）
  python3 tools/check_app_thinness.py --strict      # 閾値超過を Error 扱いにする（exit 1）
  python3 tools/check_app_thinness.py path/a.tsx …  # 指定ファイルのみ検査
  python3 tools/check_app_thinness.py --self-test    # 検査ロジックの自己テスト
"""
from __future__ import annotations

import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# `strip_comments` は `tools/ts_source.py` の共通実装を使う（Issue #612）。
# フォールバックは持たない: 静かに劣化した実装へ落ちるより、import 失敗で明示的に落ちる方が安全。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ts_source import strip_comments  # 共通モジュール（#612）。フォールバックは持たない


def blank_string_literals(code: str) -> str:
    """コメント除去済みコードの、文字列 / テンプレートリテラルの **中身** を空白化する。

    `strip_comments` は「文字列内の `//` をコメントと誤認しない」ための引用符追跡はするが、
    文字列の中身自体は残す（import 指定子の検出に生の引用符内容が要るため）。
    一方 `count_function_defs` / `count_array_chains` は文字列リテラル内にたまたま含まれる
    `.filter(` 等の **見た目だけのコード** を拾ってしまうと誤検出になるため、これらの検査対象
    コードだけは文字列の中身も空白化してから渡す（domain import 検査は空白化前の
    `code`（= `strip_comments` の出力）をそのまま使う）。改行は保持し、行番号がずれないようにする。
    """
    out = list(code)
    i, n = 0, len(code)
    quote: str | None = None
    while i < n:
        ch = code[i]
        if quote:
            if ch == "\\":
                out[i] = " "
                if i + 1 < n and code[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if ch == quote:
                i += 1
                quote = None
                continue
            if ch != "\n":
                out[i] = " "
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        i += 1
    return "".join(out)


REPO_ROOT = Path(__file__).resolve().parent.parent

CODE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
EXCLUDE_DIR_PARTS = {"node_modules", ".next", "dist", "build", ".git", "__tests__", "e2e"}
MAX_FILE_BYTES = 1_000_000  # 生成物・巨大ファイルは読まない（ゲート全体のハングを防ぐ）
APP_PREFIX = "app/"

# --------------------------------------------------------------------------- 指標 1: 行数
# splitlines() の件数をそのまま使う（末尾改行の有無で ±1 揺れないよう splitlines を使う）

# --------------------------------------------------------------------------- 指標 2: 関数定義
# トップレベル（行頭・インデント無し）の関数宣言 / アロー関数代入のみを数える。
# ネストした関数（コンポーネント内のローカル関数・useMemo コールバック等）は行頭に来ないため
# 自然に除外される（同種の正規表現ヒューリスティックは check_architecture_boundaries.py に前例あり）。
FUNC_DECL_RE = re.compile(
    r"^(?P<export>export\s+)?(?P<default>default\s+)?(?:async\s+)?function\s+(?P<name>\w+)?",
    re.MULTILINE,
)
# アロー関数代入: `const foo = (...) => ` または `const foo: Type = async (...) => `
# 「=> が閉じ括弧の直後にある」ことまで要求し、`const x = (1 + 2)` のような非関数の丸括弧を
# 誤検出しないようにする。
ARROW_CONST_RE = re.compile(
    r"^(?:export\s+)?const\s+\w+\s*(?::[^=\n]*)?=\s*(?:async\s*)?\([^)]*\)\s*(?::[^{=\n]*)?=>",
    re.MULTILINE,
)


def count_function_defs(code: str) -> int:
    """`export default` の 1 個を除いたトップレベル関数・コンポーネント定義の数。"""
    count = 0
    for m in FUNC_DECL_RE.finditer(code):
        if m.group("default"):
            continue  # `export default function Foo(...)` は数えない
        count += 1
    count += len(ARROW_CONST_RE.findall(code))
    return count


# --------------------------------------------------------------------------- 指標 3: domain import 数
# tsconfig.json の `"@/*": ["./*"]` により `@/src/domain/...` は `src/domain/...` を指す。
# app/ から src/domain/ への相対 import は実務上ほぼ存在しない（ARCH-3 でも app/ の内向き import は
# alias 経由が前提）ため、alias 形だけを対象にする。
DOMAIN_IMPORT_RE = re.compile(
    r"""(?:^|[\s;])(?:import|export)\s[^'"();]*?from\s*['"]@/src/domain/[^'"]*['"]"""
    r"""|(?:^|[\s;])import\s*['"]@/src/domain/[^'"]*['"]""",
    re.MULTILINE,
)


def count_domain_imports(code: str) -> int:
    return len(DOMAIN_IMPORT_RE.findall(code))


# --------------------------------------------------------------------------- 指標 4: 配列操作チェーン数
ARRAY_CHAIN_RE = re.compile(r"\.(?:filter|map|reduce|sort|slice)\(")


def count_array_chains(code: str) -> int:
    return len(ARRAY_CHAIN_RE.findall(code))


@dataclass(frozen=True)
class Metrics:
    lines: int
    func_defs: int
    domain_imports: int
    array_chains: int

    def exceeds(self, ceiling: "Metrics") -> list[str]:
        problems = []
        if self.lines > ceiling.lines:
            problems.append(f"行数 {self.lines} が上限 {ceiling.lines} を超えています")
        if self.func_defs > ceiling.func_defs:
            problems.append(
                f"トップレベル関数・コンポーネント定義数 {self.func_defs} が"
                f"上限 {ceiling.func_defs} を超えています"
            )
        if self.domain_imports > ceiling.domain_imports:
            problems.append(
                f"`src/domain/` からの import 数 {self.domain_imports} が"
                f"上限 {ceiling.domain_imports} を超えています"
            )
        if self.array_chains > ceiling.array_chains:
            problems.append(
                f"配列操作チェーン（.filter/.map/.reduce/.sort/.slice）の数 {self.array_chains} が"
                f"上限 {ceiling.array_chains} を超えています"
            )
        return problems


# --------------------------------------------------------------------------- app/ 内合算（ロールアップ）
# `app/` 内の相対 import（`./…` `../…`）で解決できる依存だけを辿り、依存先ファイルの 4 指標を
# 依存元（エントリポイント）の実測値へ合算する。これにより「ロジックを別ファイルへ切り出して
# import するだけ」の回避を閾値判定の土俵に乗せる（詳細はモジュール docstring の
# 「既知の限界」節）。エイリアス（`@/…`）・パッケージ名・動的 `import()` は対象外（相対 import のみ）。
RELATIVE_IMPORT_RE = re.compile(
    r"""(?:^|[\s;])(?:import|export)\s[^'"();]*?from\s*['"](\.[^'"]*)['"]"""
    r"""|(?:^|[\s;])import\s*['"](\.[^'"]*)['"]""",
    re.MULTILINE,
)

# 拡張子省略・index 解決を試す候補サフィックス（TS/TSX ソースのみ対象）。
_RESOLVE_SUFFIXES = ("", ".ts", ".tsx", ".mts", ".cts", "/index.ts", "/index.tsx")


def extract_relative_import_specs(code: str) -> list[str]:
    """コメント除去済みコードから `./…` `../…` で始まる import 指定子を抽出する。"""
    specs: list[str] = []
    for m in RELATIVE_IMPORT_RE.finditer(code):
        spec = m.group(1) or m.group(2)
        if spec:
            specs.append(spec)
    return specs


def resolve_relative_import(from_rel: str, spec: str, known: set[str]) -> str | None:
    """`from_rel` にある相対 import 指定子 `spec` を、`known`（既知ファイル集合）の中の
    リポジトリルート相対パスへ解決する。解決できなければ None（`known` に無い＝`app/` 外や
    未読み込みのファイルは合算対象にしない）。
    """
    base_dir = posixpath.dirname(from_rel)
    joined = posixpath.normpath(posixpath.join(base_dir, spec))
    for suffix in _RESOLVE_SUFFIXES:
        candidate = joined + suffix
        if candidate in known:
            return candidate
    return None


def local_import_targets(rel: str, text: str, known: set[str]) -> list[str]:
    """`rel` のソースが `app/` 内の他ファイルへ相対 import している解決済みパスの一覧。"""
    code = strip_comments(text)
    targets: list[str] = []
    for spec in extract_relative_import_specs(code):
        resolved = resolve_relative_import(rel, spec, known)
        if resolved and resolved != rel:
            targets.append(resolved)
    return targets


def rolled_up_metrics(rel: str, file_texts: dict[str, str]) -> Metrics:
    """`rel` 自身の指標 + 相対 import で到達できる `app/` 内ファイル群の指標の合計。

    BFS で辿る（循環 import があっても `visited` で無限ループしない）。`file_texts` に無い
    依存（`app/` 外・読み込み失敗ファイル）は無視する。
    """
    known = set(file_texts.keys())
    own = measure(file_texts[rel])
    lines, func_defs, domain_imports, array_chains = (
        own.lines,
        own.func_defs,
        own.domain_imports,
        own.array_chains,
    )

    visited: set[str] = {rel}
    queue: list[str] = local_import_targets(rel, file_texts[rel], known)
    while queue:
        cur = queue.pop()
        if cur in visited:
            continue
        visited.add(cur)
        cur_text = file_texts.get(cur)
        if cur_text is None:
            continue
        m = measure(cur_text)
        lines += m.lines
        func_defs += m.func_defs
        domain_imports += m.domain_imports
        array_chains += m.array_chains
        queue.extend(local_import_targets(cur, cur_text, known))

    return Metrics(
        lines=lines, func_defs=func_defs, domain_imports=domain_imports, array_chains=array_chains
    )


def measure(text: str) -> Metrics:
    """1 ファイルのソース全文（コメント除去前）から 4 指標を実測する。"""
    code = strip_comments(text)
    # domain import 検査は生の引用符内容が要るので `code` をそのまま使う。
    # 関数定義数・配列チェーン数は文字列リテラル内の見た目だけのコードを拾わないよう、
    # さらに文字列の中身を空白化したものを使う。
    code_no_strings = blank_string_literals(code)
    return Metrics(
        lines=len(text.splitlines()),
        func_defs=count_function_defs(code_no_strings),
        domain_imports=count_domain_imports(code),
        array_chains=count_array_chains(code_no_strings),
    )


# --------------------------------------------------------------------------- 閾値・allowlist

# 新規ファイル・allowlist 未登録ファイルに適用する既定の上限。
# 実測分布（2026-08-24 時点・Issue #612）: 行数は 8〜547 の間で 108→144 と 301→422 に
# 大きな段差があり、問題視されている 2 ファイル（422 行 / 547 行）だけが突出している。
# 段差の手前（≒200 行）を新規ファイルの上限として採用した。関数定義数・domain import 数・
# 配列チェーン数も同様に「問題のない既存ファイル群の最大値」を基準に線を引いている。
DEFAULT_THRESHOLDS = Metrics(lines=200, func_defs=2, domain_imports=3, array_chains=1)

# ファイルパス（リポジトリルート相対）→ 登録時点の実測値（= そのファイル専用の上限）。
# 登録理由は各コメントを参照。実測は 2026-08-24（Issue #612 着手時点）。
ALLOWLIST: dict[str, Metrics] = {
    # Issue #604 の重複箇所・Issue #612 で例示された `.filter().map().slice()` チェーン
    # （検索結果ポートと Gem バッジポートの結果をここで組み合わせている）を含む最大のファイル。
    # 2026-09-01: Issue #287（ライセンスリンクの sr-only 告知）で i18n ラベルを 1 個渡すため
    # `labels` が複数行に折れ 547 → 550 行。機能追加に伴う最小増分として実測値を更新した。
    # 2026-09-05: Issue #167 で `labels.linkPending`（読み上げ文言）を 2 一覧へ渡すため 550 → 552 行。
    # 2026-09-05: Issue #355 で hero-idle（未検索画面の LCP 要素・実測）へ `fetchPriority="high"` を
    # 付与したため 552 → 554 行（属性 1 行 + 実測の根拠を指す注記 1 行の最小増分）。
    "app/[locale]/page.tsx": Metrics(lines=554, func_defs=3, domain_imports=7, array_chains=4),
    # Gem 一覧ページ。ドメインの値オブジェクト（locale/page-number/per-page/sort-order/errors）を
    # 直接 5 つ import しており、表示用の整形が app/ 側に残っている疑いがあるが、行数以外は
    # 大きく逸脱していないため現状維持で allowlist する。
    # 2026-09-01: Issue #287 で `opensInNewTab` ラベルを 1 行渡すため 422 → 423 行。
    # 2026-09-05: Issue #167 で `labels.linkPending` を渡すため 423 → 424 行。
    "app/[locale]/gems/page.tsx": Metrics(lines=424, func_defs=1, domain_imports=5, array_chains=0),
    # リポジトリ詳細ページ。domain import 4 個がデフォルト上限 3 を超える。
    "app/[locale]/repos/[owner]/[repo]/page.tsx": Metrics(
        # 2026-09-05: Issue #167 の Layer 1 レビュー指摘（冒頭コメントが実態と食い違い、
        # 実装側 JSDoc と互いに古い記述を指し合う循環になっていた）を直すため 301 → 304 行。
        # 圧縮できる冗長箇所は同時に削ったうえでの最小増分。
        lines=304, func_defs=1, domain_imports=4, array_chains=0
    ),
    # 検索 API Route Handler。トップレベル関数定義が 3 個（デフォルト上限 2 を超える）。
    "app/api/search/route.ts": Metrics(lines=144, func_defs=3, domain_imports=1, array_chains=0),
}


def ceiling_for(rel: str) -> Metrics:
    return ALLOWLIST.get(rel, DEFAULT_THRESHOLDS)


# --------------------------------------------------------------------------- ファイル収集


def is_test_file(rel: str) -> bool:
    name = Path(rel).name
    if ".test." in name or ".spec." in name:
        return True
    return bool(EXCLUDE_DIR_PARTS & set(Path(rel).parts))


def collect_targets(argv: list[str]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    explicit = [a for a in argv if not a.startswith("-")]
    if explicit:
        candidates = explicit
    else:
        candidates = []
        root = REPO_ROOT / "app"
        if root.is_dir():
            for p in root.rglob("*"):
                if p.suffix in CODE_SUFFIXES:
                    candidates.append(p.relative_to(REPO_ROOT).as_posix())
        candidates.sort()

    targets: list[str] = []
    for rel in candidates:
        if not rel.startswith(APP_PREFIX):
            continue
        if is_test_file(rel):
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        if path.is_symlink():
            warnings.append(f"{rel} はシンボリックリンクのため検査をスキップしました")
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                warnings.append(f"{rel} が {MAX_FILE_BYTES} バイトを超えるため検査をスキップしました")
                continue
        except OSError as exc:
            warnings.append(f"{rel} の情報を取得できませんでした: {exc}")
            continue
        targets.append(rel)
    return targets, warnings


def check_file(rel: str, text: str, file_texts: dict[str, str] | None = None) -> list[str]:
    """1 ファイルを検査して問題メッセージのリストを返す（I/O を持たない・self-test の注入口）。

    `file_texts`（rel → ソース全文の辞書）を渡すと、`app/` 内の相対 import で到達できる
    依存ファイルの指標を合算してから判定する（`rolled_up_metrics`）。省略時は自ファイル単独の
    指標で判定する（後方互換・既存の単体 self-test ケースはこの経路のまま）。
    """
    if file_texts is not None and rel in file_texts:
        actual = rolled_up_metrics(rel, file_texts)
    else:
        actual = measure(text)
    ceiling = ceiling_for(rel)
    problems = actual.exceeds(ceiling)
    if file_texts is not None and problems and actual != measure(text):
        problems = [f"{p}（app/ 内の相対 import で取り込んだ依存ファイル分を合算した値）" for p in problems]
    return [f"{rel}: {p}" for p in problems]


# --------------------------------------------------------------------------- self-test

SELF_TEST_CASES: list[tuple[str, str, int]] = [
    # (rel, text, expected_problem_count)
    # --- 正当に薄いファイルを誤検出しない ---
    (
        "app/api/health/route.ts",
        "export async function GET() {\n  return new Response('ok')\n}\n",
        0,
    ),
    (
        "app/[locale]/loading.tsx",
        "export default function Loading() {\n  return null\n}\n",
        0,
    ),
    # コメント・文字列リテラル中の `.filter(` `.map(` は数えない
    (
        "app/[locale]/comment-only.tsx",
        "// items.filter((x) => x).map((x) => x).slice(0, 1).sort().reduce((a) => a)\n"
        "export default function Page() {\n  return null\n}\n",
        0,
    ),
    (
        "app/[locale]/string-literal.tsx",
        "const label = 'array.filter(x).map(x).sort(x).slice(0).reduce(x)'\n"
        "export default function Page() {\n  return label\n}\n",
        0,
    ),
    # --- 新規ファイル（allowlist 未登録）がデフォルト閾値を超えたら検出する ---
    (
        "app/[locale]/new-fat-page.tsx",
        "\n".join(f"const x{i} = {i}" for i in range(DEFAULT_THRESHOLDS.lines + 1)) + "\n",
        1,  # 行数超過のみ
    ),
    (
        "app/[locale]/new-many-funcs.tsx",
        "".join(f"function helper{i}() {{ return {i} }}\n" for i in range(DEFAULT_THRESHOLDS.func_defs + 1))
        + "export default function Page() { return null }\n",
        1,  # 関数定義数超過のみ
    ),
    (
        "app/[locale]/new-domain-heavy.tsx",
        "".join(
            f"import {{ x{i} }} from '@/src/domain/model/x{i}'\n"
            for i in range(DEFAULT_THRESHOLDS.domain_imports + 1)
        ),
        1,  # domain import 数超過のみ
    ),
    (
        "app/[locale]/new-chain-heavy.tsx",
        "const y = items.filter((x) => x).map((x) => x)\n",
        1,  # array chain 数超過のみ（filter + map で 2 件・上限 1）
    ),
    # 複合違反（行数 + チェーン数の 2 件）
    (
        "app/[locale]/new-fat-and-chained.tsx",
        "\n".join(f"const x{i} = {i}" for i in range(DEFAULT_THRESHOLDS.lines + 1))
        + "\nconst y = items.filter((x) => x).map((x) => x)\n",
        2,
    ),
    # --- allowlist 登録ファイルが「登録時の実測値」からさらに悪化したら検出する ---
    (
        "app/[locale]/page.tsx",
        # allowlist の array_chains 上限は 4。5 個のチェーンを持つ最小コードを用意する。
        "\n".join(
            [
                "const a = items.filter((x) => x)",
                "const b = items.map((x) => x)",
                "const c = items.reduce((acc) => acc, 0)",
                "const d = items.sort()",
                "const e = items.slice(0, 1)",
            ]
        )
        + "\n",
        1,  # array_chains: 5 > 4（他指標はこの短いコードなら上限内）
    ),
    # --- allowlist 登録ファイルが登録時の実測値「以下」なら検出しない（回帰していない） ---
    (
        "app/api/search/route.ts",
        # allowlist の func_defs 上限は 3。2 個ならセーフ。
        "export async function GET() { return null }\n"
        "async function helper() { return null }\n",
        0,
    ),
]


# --- ロールアップ（app/ 内相対 import の合算）専用ケース ---
# (entry_rel, file_texts, want_count) — 複数ファイルの依存関係を検査するため file_texts 辞書で渡す。
ROLLUP_TEST_CASES: list[tuple[str, dict[str, str], int]] = [
    # 🔴 セルフレビューで実測された回避手口そのものを固定化する回帰テスト（Issue #619）。
    # page-split2.tsx 自体は空っぽの薄い皮（0 件）だが、helperA/helperB（各単独では domain_imports=3・
    # array_chains=1 で閾値以下）を相対 import しており、合算すると domain_imports=6 / array_chains=2 で
    # 両方が閾値超過になる＝この 2 件を検出できることを固定化する。
    (
        "app/[locale]/page-split2.tsx",
        {
            "app/[locale]/page-split2.tsx": (
                "import { helperA } from './_orchestration-a'\n"
                "import { helperB } from './_orchestration-b'\n"
                "export default function Page() {\n"
                "  return helperA() ?? helperB()\n"
                "}\n"
            ),
            "app/[locale]/_orchestration-a.ts": (
                "import { a1 } from '@/src/domain/model/a1'\n"
                "import { a2 } from '@/src/domain/model/a2'\n"
                "import { a3 } from '@/src/domain/model/a3'\n"
                "export function helperA() {\n"
                "  return [a1, a2, a3].filter((x) => x)\n"
                "}\n"
            ),
            "app/[locale]/_orchestration-b.ts": (
                "import { b1 } from '@/src/domain/model/b1'\n"
                "import { b2 } from '@/src/domain/model/b2'\n"
                "import { b3 } from '@/src/domain/model/b3'\n"
                "export function helperB() {\n"
                "  return [b1, b2, b3].map((x) => x)\n"
                "}\n"
            ),
        },
        2,  # domain_imports 超過 + array_chains 超過
    ),
    # 単独では閾値以下の helper 1 個だけを import する場合は合算しても閾値以下（過剰検出しない）。
    (
        "app/[locale]/page-split-safe.tsx",
        {
            "app/[locale]/page-split-safe.tsx": (
                "import { helperA } from './_orchestration-a-safe'\n"
                "export default function Page() {\n  return helperA()\n}\n"
            ),
            "app/[locale]/_orchestration-a-safe.ts": (
                "import { a1 } from '@/src/domain/model/a1'\n"
                "export function helperA() {\n  return [a1].filter((x) => x)\n}\n"
            ),
        },
        0,
    ),
    # 実例に相当する回帰: 小さな co-located データファイル（自動生成の定数等）を相対 import しても
    # 誤検出しない（`app/[locale]/opengraph-image.tsx` → `./og-background-data` を模したケース）。
    (
        "app/[locale]/image-with-data.tsx",
        {
            "app/[locale]/image-with-data.tsx": (
                "import { DATA_URI } from './local-data'\n"
                "export default function Image() {\n  return DATA_URI\n}\n"
            ),
            "app/[locale]/local-data.ts": "export const DATA_URI = 'data:image/png;base64,AAAA'\n",
        },
        0,
    ),
    # 循環 import があっても無限ループしない（visited による打ち切り）。
    (
        "app/[locale]/cycle-a.tsx",
        {
            "app/[locale]/cycle-a.tsx": (
                "import { b } from './cycle-b'\nexport default function A() {\n  return b\n}\n"
            ),
            "app/[locale]/cycle-b.ts": (
                "import { a } from './cycle-a'\nexport const b = a\n"
            ),
        },
        0,
    ),
]


def run_self_test() -> int:
    failures: list[str] = []
    for rel, text, want_count in SELF_TEST_CASES:
        problems = check_file(rel, text)
        if len(problems) != want_count:
            failures.append(
                f"  {rel}: want {want_count} 件, got {len(problems)} 件 :: {problems}"
            )

    for rel, file_texts, want_count in ROLLUP_TEST_CASES:
        problems = check_file(rel, file_texts[rel], file_texts=file_texts)
        if len(problems) != want_count:
            failures.append(
                f"  [rollup] {rel}: want {want_count} 件, got {len(problems)} 件 :: {problems}"
            )

    # ceiling_for の allowlist 参照が exact path match であること（誤って部分一致しない）
    if ceiling_for("app/[locale]/page2.tsx") != DEFAULT_THRESHOLDS:
        failures.append("  allowlist が部分一致してしまっています（exact path match ではない）")

    if failures:
        print("❌ check_app_thinness --self-test FAILED")
        print("\n".join(failures))
        return 1
    total_cases = len(SELF_TEST_CASES) + len(ROLLUP_TEST_CASES) + 1
    print(f"✅ check_app_thinness --self-test PASSED（{total_cases} ケース）")
    return 0


# --------------------------------------------------------------------------- main


def main() -> int:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        return run_self_test()
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]

    targets, warnings = collect_targets(argv)
    if not targets:
        print("ℹ️ 検査対象の app/ コード（.ts/.tsx）がありません")
        return 0

    file_texts: dict[str, str] = {}
    for rel in targets:
        try:
            file_texts[rel] = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"{rel} を読めませんでした: {exc}")

    problems: list[str] = []
    for rel in targets:
        text = file_texts.get(rel)
        if text is None:
            continue
        problems.extend(check_file(rel, text, file_texts=file_texts))

    for w in warnings:
        print(f"⚠️ {w}")

    if problems:
        label = "❌" if strict else "⚠️"
        for p in problems:
            print(f"{label} {p}")
        severity = "Error" if strict else "Warning"
        print(
            f"\napp/ 薄さ検査: {severity} {len(problems)} 件 / 検査 {len(targets)} ファイル。"
            "SSOT: docs/03_design/architecture/application-architecture.md（Frameworks & Drivers 層）"
        )
        return 1 if strict else 0

    print(f"✅ app/ 薄さ検査 OK（{len(targets)} ファイル・Warning 0 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
