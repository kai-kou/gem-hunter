import { chromium } from 'playwright'

const BASE = process.env.BASE_URL || 'http://localhost:3110'

const browser = await chromium.launch({ args: ['--ssl-version-max=tls1.2'] })
const page = await browser.newPage()
await page.goto(`${BASE}/en?q=react`, { waitUntil: 'networkidle' }).catch(() => {})
await page.waitForTimeout(500)

async function measureBySelector(selector, label, waitMs) {
  const handle = await page.$(selector)
  if (!handle) {
    console.log(`${label}: NOT FOUND (${selector})`)
    return
  }
  await handle.evaluate((el) => el.blur())
  await handle.evaluate((el) => el.focus())
  await page.waitForTimeout(waitMs)
  const info = await handle.evaluate((el) => {
    const cs = getComputedStyle(el)
    return {
      boxShadow: cs.boxShadow,
      transitionProperty: cs.transitionProperty,
      transitionDuration: cs.transitionDuration,
    }
  })
  console.log(`${label} (wait=${waitMs}ms):`, JSON.stringify(info))
}

for (const wait of [0, 50, 150, 300, 600]) {
  await measureBySelector('form[role="search"] button[type="submit"]', 'search-button', wait)
}
for (const wait of [0, 50, 300, 600]) {
  await measureBySelector('nav[aria-label] a', 'locale-switcher-link', wait)
}

await browser.close()
