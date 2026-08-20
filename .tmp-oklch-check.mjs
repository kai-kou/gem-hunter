import { chromium } from 'playwright'
const browser = await chromium.launch()
const page = await browser.newPage()
await page.setContent('<div id="d" style="color: oklch(0.6 0 0)"></div>')
const rgb = await page.$eval('#d', (el) => getComputedStyle(el).color)
console.log('oklch(0.6 0 0) rendered as:', rgb)
await browser.close()
