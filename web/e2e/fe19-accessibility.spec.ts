import { test, expect, loginCandidate } from './fixtures'
import AxeBuilder from '@axe-core/playwright'

const ROUTES = ['/candidate', '/candidate/offers', '/candidate/vacancies', '/candidate/microtasks', '/candidate/settings', '/lab']

test.describe('FE-19 accessibility (FE-18 device pass)', () => {
  test('no serious/critical violations on candidate routes', async ({ page, browserName }) => {
    if (browserName === 'webkit') return
    await loginCandidate(page)
    for (const route of ROUTES) {
      await page.goto(route)
      await page.getByRole('status').first().waitFor({ state: 'detached', timeout: 15_000 }).catch(() => {})
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
      const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
      expect(serious, `${route}: ${JSON.stringify(serious.map((v) => v.id))}`).toEqual([])
    }
  })
})
