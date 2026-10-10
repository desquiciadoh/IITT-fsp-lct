import { test as base, expect, type Page } from '@playwright/test'

export const test = base.extend<{ stubGuard: void }>({
  stubGuard: [
    async ({ page }, use) => {
      if (process.env.E2E_REQUIRE_REAL === '1') {
        page.on('response', (response) => {
          expect(
            response.headers()['x-stub'],
            `unexpected stubbed response: ${response.url()}`,
          ).toBeUndefined()
        })
      }
      await use()
    },
    { auto: true },
  ],
})

export async function loginCandidate(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /Анна \(ФСП\)/ }).click()
  await expect(page).toHaveURL(/\/candidate/)
}

export async function loginEmployer(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: /Работодатель/ }).click()
  await expect(page).toHaveURL(/\/employer/)
}

export { expect }
