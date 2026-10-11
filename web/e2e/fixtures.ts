import { test as base, expect } from '@playwright/test'

type FspFixtures = {
  assertNoStubs: void
}

export const test = base.extend<FspFixtures>({
  assertNoStubs: [
    async ({ page }, use) => {
      const stubs: string[] = []
      page.on('response', (response) => {
        if (response.headers()['x-stub'] === 'true') {
          stubs.push(`${response.request().method()} ${response.url()}`)
        }
      })
      await use()
      expect(stubs, 'MSW stub (X-Stub: true) responses detected — e2e must run against the real backend').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
