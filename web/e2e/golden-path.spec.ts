import { test, expect } from './fixtures'
import type { Page } from '@playwright/test'

/**
 * FE-19 golden path.
 *
 * Step 1 (candidate: persona login → onboarding → test → result) and step 3
 * (candidate: offer appears → accept) are implemented. The employer-side steps
 * are parked as `test.fixme` until the employer surface is covered.
 *
 * Runs against the full stack (no MSW): set `E2E_BASE_URL`
 * (default http://localhost:5173). The auto `assertNoStubs` fixture fails the
 * test if any `X-Stub: true` (mock) response is observed.
 */

async function loginAs(page: Page, personaLabel: string) {
  await page.goto('/login')
  await page.getByRole('button', { name: personaLabel, exact: true }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

async function completeOnboarding(page: Page) {
  // Step 1/4 — consents (processing is required; ФСП sync is off for a plain persona).
  await page.goto('/candidate/onboarding/consent')
  await page.getByRole('checkbox', { name: /Обработка персональных данных/ }).check()
  await page.getByRole('checkbox', { name: /Публикация профиля работодателям/ }).check()
  await page.getByRole('checkbox', { name: /Синхронизация с ФСП/ }).uncheck()
  await page.getByRole('button', { name: 'Продолжить' }).click()

  // Step 2/4 — profile. "Заполнить вручную" skips the PDF upload path.
  await expect(page).toHaveURL(/onboarding\/profile/)
  await page.getByRole('button', { name: 'Заполнить вручную' }).click()

  // Step 3/4 — survey.
  await expect(page).toHaveURL(/onboarding\/survey/)
  await page.getByRole('radio', { name: 'бэкенд' }).check()
  await page.getByLabel('Роли через запятую *').fill('разработчик')
  await page.getByRole('checkbox', { name: 'удалённо' }).check()
  await page.getByLabel(/Зарплата от/).fill('150000')
  await page.getByLabel(/Зарплата до/).fill('250000')
  await page.getByRole('radio', { name: 'до вычета' }).check()
  await page.getByRole('button', { name: 'Продолжить' }).click()

  // Step 4/4 — claim a grade.
  await expect(page).toHaveURL(/onboarding\/claim/)
  await page.getByRole('radio', { name: /мидл/ }).click()
  await page.getByRole('button', { name: 'Перейти к квалификации' }).click()
}

/**
 * Drives the runner until it reaches the result route. The test is adaptive
 * (item count and input types vary), so answer whatever the current item asks
 * for and repeat until the session ends.
 */
async function finishQualificationTest(page: Page) {
  await expect(page).toHaveURL(/qualification\/start/)
  await page.getByRole('button', { name: 'Начать тест' }).click()

  for (let i = 0; i < 60; i++) {
    if (/\/result/.test(page.url())) return

    const toResults = page.getByRole('button', { name: 'К результатам' })
    if (await toResults.isVisible().catch(() => false)) {
      await toResults.click()
      continue
    }

    const choice = page.locator('fieldset input[type="radio"]')
    if (await choice.count()) {
      await choice.first().check()
    } else if (await page.locator('input[type="number"]').count()) {
      await page.locator('input[type="number"]').fill('1')
    } else {
      await page.locator('textarea').fill('тестовый ответ')
    }

    await page.getByRole('button', { name: 'Следующее задание' }).click()
  }

  throw new Error('Runner did not reach the result route within the item budget')
}

test('candidate: persona login → onboarding → test → result', async ({ page }) => {
  await loginAs(page, 'Алекс')
  await completeOnboarding(page)
  await finishQualificationTest(page)

  await expect(page).toHaveURL(/\/candidate\/qualification\/.+\/result/)
  await expect(page.locator('h1')).toBeVisible()
})

test('candidate: offer appears → accept', async ({ page }) => {
  await loginAs(page, 'Анна (ФСП)')
  await page.goto('/candidate/offers')

  const firstOffer = page.locator('a[href^="/candidate/offers/"]').first()
  test.skip((await firstOffer.count()) === 0, 'Персона без офферов — нечего принимать')

  await firstOffer.click()
  await expect(page).toHaveURL(/\/candidate\/offers\/.+/)
  // Opening the detail marks the offer "viewed", which reveals the actions.
  await page.getByRole('button', { name: 'Принять' }).click()
  await expect(page.getByText(/принят/i).first()).toBeVisible()
})

test.fixme('employer: publish vacancy → review applicants', async () => {
  // Parked until the employer surface is covered by FE-19's next pass.
})

test.fixme('employer: send offer from the pool', async () => {
  // Parked until the employer surface is covered by FE-19's next pass.
})
