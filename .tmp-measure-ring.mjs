import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://localhost:3110'

const browser = await chromium.launch({ args: ['--ssl-version-max=tls1.2'] })
const page = await browser.newPage()
await page.goto(`${BASE}/en?q=react`, { waitUntil: 'networkidle' }).catch(() => {})
await page.waitForTimeout(500)

async function measureBySelector(selector, label) {
  const handle = await page.$(selector)
  if (!handle) {
    console.log(`${label}: NOT FOUND (${selector})`)
    return
  }
  await handle.evaluate((el) => el.focus())
  await page.waitForTimeout(50)
  const info = await handle.evaluate((el) => {
    const cs = getComputedStyle(el)
    return {
      tag: el.tagName,
      id: el.id,
      boxShadow: cs.boxShadow,
      outlineColor: cs.outlineColor,
      outlineStyle: cs.outlineStyle,
      outlineWidth: cs.outlineWidth,
      backgroundColor: cs.backgroundColor,
      matchesFocusVisible: el.matches(':focus-visible'),
    }
  })
  console.log(`${label}:`, JSON.stringify(info))
}

await measureBySelector('input[type="search"]', 'search-input')
await measureBySelector('form[role="search"] button[type="submit"]', 'search-button')
await measureBySelector('#results-heading', 'results-heading')
await measureBySelector('nav[aria-label] a', 'locale-switcher-link')
await measureBySelector('select', 'first-select (sort-picker)')
await measureBySelector('select + select, select ~ select', 'second-select')
await measureBySelector('a.text-primary', 'detail-link-or-backlink')

await browser.close()
