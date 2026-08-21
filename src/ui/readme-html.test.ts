import { describe, expect, it } from 'vitest'

import { README_TRUNCATE_LENGTH, sanitizeReadmeHtml } from './readme-html'

const BASE = {
  linkBaseUrl: 'https://github.com/facebook/react/blob/HEAD/',
  imageBaseUrl: 'https://raw.githubusercontent.com/facebook/react/HEAD/',
}

describe('sanitizeReadmeHtml — XSS ベクタの除去', () => {
  it('script タグを落とす（内容ごと）', () => {
    const { html } = sanitizeReadmeHtml('<p>hello</p><script>alert(1)</script>', BASE)

    expect(html).not.toContain('<script')
    expect(html).not.toContain('alert(1)')
  })

  it('style タグを落とす（内容ごと）', () => {
    const { html } = sanitizeReadmeHtml('<style>body{background:url(x)}</style><p>ok</p>', BASE)

    expect(html).not.toContain('<style')
  })

  it('iframe タグを落とす', () => {
    const { html } = sanitizeReadmeHtml('<iframe src="https://evil.example"></iframe>', BASE)

    expect(html).not.toContain('<iframe')
  })

  it('object / embed タグを落とす', () => {
    const { html } = sanitizeReadmeHtml(
      '<object data="evil.swf"></object><embed src="evil.swf">',
      BASE,
    )

    expect(html).not.toContain('<object')
    expect(html).not.toContain('<embed')
  })

  it('form / input タグを落とす', () => {
    const { html } = sanitizeReadmeHtml(
      '<form action="https://evil.example"><input type="text"></form>',
      BASE,
    )

    expect(html).not.toContain('<form')
    expect(html).not.toContain('<input')
  })

  it('on* 属性（onerror 等）を落とす', () => {
    const { html } = sanitizeReadmeHtml('<img src="a.png" onerror="alert(1)">', BASE)

    expect(html).not.toContain('onerror')
  })

  it('javascript: スキームの href を落とす（リンクは素のテキストとして残す）', () => {
    const { html } = sanitizeReadmeHtml('<a href="javascript:alert(1)">click me</a>', BASE)

    expect(html).not.toContain('javascript:')
    expect(html).not.toContain('<a')
    expect(html).toContain('click me')
  })

  it('data: スキームの href を落とす', () => {
    const { html } = sanitizeReadmeHtml(
      '<a href="data:text/html,<script>alert(1)</script>">click</a>',
      BASE,
    )

    expect(html).not.toContain('data:')
    expect(html).not.toContain('<script')
  })

  it('javascript: スキームの画像 src は画像ごと落とす', () => {
    const { html } = sanitizeReadmeHtml('<img src="javascript:alert(1)" alt="x">', BASE)

    expect(html).not.toContain('<img')
    expect(html).not.toContain('javascript:')
  })

  it('大文字・タブ混じりの javascript: スキームも落とす（ブラウザの URL 解釈に合わせる）', () => {
    const { html } = sanitizeReadmeHtml('<a href="java\tscript:alert(1)">click</a>', BASE)

    expect(html).not.toContain('<a')
  })
})

describe('sanitizeReadmeHtml — 相対 URL の解決', () => {
  it('相対リンク（docs/a.md）を linkBaseUrl から絶対 URL へ解決する', () => {
    const { html } = sanitizeReadmeHtml('<a href="docs/a.md">doc</a>', BASE)

    expect(html).toContain('href="https://github.com/facebook/react/blob/HEAD/docs/a.md"')
  })

  it('相対リンク（./x.png への画像）を imageBaseUrl から絶対 URL へ解決する', () => {
    const { html } = sanitizeReadmeHtml('<img src="./screenshot.png" alt="screenshot">', BASE)

    expect(html).toContain(
      'src="https://raw.githubusercontent.com/facebook/react/HEAD/screenshot.png"',
    )
  })

  it('フラグメントのみの href（#user-content-x）はページ内アンカーとして解決しない', () => {
    const { html } = sanitizeReadmeHtml('<a href="#user-content-toc">目次</a>', BASE)

    expect(html).toContain('href="#user-content-toc"')
  })

  it('絶対 URL（https）はそのまま通す', () => {
    const { html } = sanitizeReadmeHtml('<a href="https://example.com/">external</a>', BASE)

    expect(html).toContain('href="https://example.com/"')
  })

  it('外部リンクには target=_blank と rel=noopener noreferrer を付ける', () => {
    const { html } = sanitizeReadmeHtml('<a href="https://example.com/">external</a>', BASE)

    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('フラグメントのみの内部アンカーには target=_blank を付けない', () => {
    const { html } = sanitizeReadmeHtml('<a href="#user-content-toc">目次</a>', BASE)

    expect(html).not.toContain('target="_blank"')
  })

  it('href の無い a タグは素のテキストとして残す', () => {
    const { html } = sanitizeReadmeHtml('<a name="anchor">text</a>', BASE)

    expect(html).not.toContain('<a')
    expect(html).toContain('text')
  })

  it('src の無い img タグは丸ごと落とす', () => {
    const { html } = sanitizeReadmeHtml('<img alt="no src">', BASE)

    expect(html).not.toContain('<img')
  })
})

describe('sanitizeReadmeHtml — 見出しの降格（+2・h6 で cap）', () => {
  it('h1 は h3 へ降格する', () => {
    const { html } = sanitizeReadmeHtml('<h1 id="user-content-title">Title</h1>', BASE)

    expect(html).toContain('<h3')
    expect(html).not.toContain('<h1')
  })

  it('h2 は h4 へ降格する', () => {
    const { html } = sanitizeReadmeHtml('<h2 id="user-content-sub">Sub</h2>', BASE)

    expect(html).toContain('<h4')
  })

  it('h4・h5・h6 は h6 で打ち止め（cap）', () => {
    const h4 = sanitizeReadmeHtml('<h4>a</h4>', BASE).html
    const h5 = sanitizeReadmeHtml('<h5>a</h5>', BASE).html
    const h6 = sanitizeReadmeHtml('<h6>a</h6>', BASE).html

    expect(h4).toContain('<h6')
    expect(h5).toContain('<h6')
    expect(h6).toContain('<h6')
  })

  it('id="user-content-*" は保持する（README 内アンカーを機能させ続ける）', () => {
    const { html } = sanitizeReadmeHtml('<h1 id="user-content-title">Title</h1>', BASE)

    expect(html).toContain('id="user-content-title"')
  })

  it('見出しの降格はタグ名そのものを書き換える（CSS ではない）', () => {
    const { html } = sanitizeReadmeHtml('<h1>Title</h1>', BASE)

    expect(html).not.toMatch(/style=/)
    expect(html).toMatch(/<h3[ >]/)
  })
})

describe('sanitizeReadmeHtml — 切り詰め', () => {
  it('上限未満のテキストは切り詰めない（truncated: false）', () => {
    const { truncated } = sanitizeReadmeHtml('<p>short</p>', BASE)

    expect(truncated).toBe(false)
  })

  it('上限を超えるテキストは切り詰め、truncated: true を返す', () => {
    const longText = 'a'.repeat(README_TRUNCATE_LENGTH + 1000)
    const { html, truncated } = sanitizeReadmeHtml(`<p>${longText}</p>`, BASE)

    expect(truncated).toBe(true)
    expect(html.length).toBeLessThan(longText.length)
  })

  it('切り詰め後も整形式の HTML のまま（開いたタグは閉じられる）', () => {
    const longText = 'a'.repeat(README_TRUNCATE_LENGTH + 1000)
    const { html } = sanitizeReadmeHtml(
      `<ul><li>${longText}</li><li>after truncation</li></ul>`,
      BASE,
    )

    // 開いた <ul> <li> はすべて閉じタグを持つ（タグの途中で切れていない）
    expect((html.match(/<ul/g) ?? []).length).toBe((html.match(/<\/ul>/g) ?? []).length)
    expect((html.match(/<li/g) ?? []).length).toBe((html.match(/<\/li>/g) ?? []).length)
  })

  it('切り詰め位置より後のテキストは出力に含まれない', () => {
    const longText = 'a'.repeat(README_TRUNCATE_LENGTH + 1000)
    const { html } = sanitizeReadmeHtml(`<p>${longText}マーカー末尾</p>`, BASE)

    expect(html).not.toContain('マーカー末尾')
  })
})

describe('sanitizeReadmeHtml — 通常の README コンテンツはそのまま描画できる', () => {
  it('段落・強調・リスト・コードブロック・テーブルを保持する', () => {
    const raw = `
      <p>説明文です。<strong>強調</strong>もできます。</p>
      <ul><li>項目1</li><li>項目2</li></ul>
      <pre><code>const x = 1</code></pre>
      <table><thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>
    `
    const { html } = sanitizeReadmeHtml(raw, BASE)

    expect(html).toContain('<strong>強調</strong>')
    expect(html).toContain('<li>項目1</li>')
    expect(html).toContain('<code>const x = 1</code>')
    expect(html).toContain('<table>')
  })

  it('parseStyleAttributes を有効にしない（postcss 経路を切る）', () => {
    // 壊れた style 属性値でも例外を投げずに処理できること（postcss を通していれば
    // パースエラーが起きうる入力）。
    expect(() =>
      sanitizeReadmeHtml('<p style="not: valid; css{{{">text</p>', BASE),
    ).not.toThrow()
  })
})
