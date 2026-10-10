import { test, expect, loginCandidate } from './fixtures'

test.describe('FE-18 device pass: no horizontal scroll at 375 px', () => {
  test('every route fits the viewport', async ({ page }) => {
    test.skip(!page.viewportSize() || page.viewportSize()!.width > 375, 'mobile-only')
    await loginCandidate(page)
    for (const route of ['/candidate', '/candidate/offers', '/candidate/vacancies', '/candidate/microtasks', '/candidate/settings', '/lab']) {
      await page.goto(route)
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth)
      expect(scrollWidth, `${route} scrollWidth=${scrollWidth} > clientWidth=${clientWidth}`).toBeLessThanOrEqual(clientWidth)
    }
  })
})
