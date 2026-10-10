import { test, expect, loginCandidate } from './fixtures'

test.describe('FE-19 golden path (candidate, mocks)', () => {
  test('persona login lands on the dashboard', async ({ page }) => {
    await loginCandidate(page)
    await expect(page.getByText('Ваш статус')).toBeVisible()
    await expect(page.getByText('Ваши отклики')).toBeVisible()
  })

  test('offers inbox renders and opens an offer', async ({ page }) => {
    await loginCandidate(page)
    await page.getByRole('navigation').getByRole('link', { name: 'Офферы' }).click()
    await expect(page).toHaveURL(/\/candidate\/offers/)
    await expect(page.getByRole('heading', { name: 'Офферы' })).toBeVisible()
    await page.getByRole('link', { name: /Senior Backend Engineer/ }).first().click()
    await expect(page).toHaveURL(/\/candidate\/offers\/[\w-]+/)
  })

  test('vacancies: apply flips the card to sent', async ({ page }) => {
    await loginCandidate(page)
    await page.getByRole('navigation').getByRole('link', { name: 'Вакансии' }).click()
    await expect(page).toHaveURL(/\/candidate\/vacancies/)
    await expect(page.getByRole('heading', { name: 'Вакансии партнёров' })).toBeVisible()
    const applyButton = page.getByRole('button', { name: 'Откликнуться' }).first()
    await applyButton.click()
    await expect(page.getByText(/Отклик отправлен/)).toBeVisible()
  })

  test('micro-tasks: solve an auto task and get a score', async ({ page }) => {
    await loginCandidate(page)
    await page.getByRole('navigation').getByRole('link', { name: 'Задачи' }).click()
    await expect(page).toHaveURL(/\/candidate\/microtasks/)
    await expect(page.getByRole('heading', { name: 'Задачи' })).toBeVisible()
    await page.locator('a[href*="/candidate/microtasks/"]').first().click()
    await expect(page).toHaveURL(/\/candidate\/microtasks\/[\w-]+/)
    await page.getByPlaceholder(/Текст решения/i).fill('42')
    await page.getByRole('button', { name: /Отправить/i }).click()
    await expect(page.getByText(/Оценка|отправлено|проверено/i)).toBeVisible()
  })

  test('lab: report + Test Twins render', async ({ page }) => {
    await loginCandidate(page)
    await page.goto('/lab')
    await expect(page).toHaveURL(/\/lab/)
    await expect(page.getByRole('heading', { name: /Качество теста/ })).toBeVisible()
    await expect(page.getByText('Test Twins')).toBeVisible()
  })

  test('settings renders for the candidate', async ({ page }) => {
    await loginCandidate(page)
    await page.getByRole('navigation').getByRole('link', { name: 'Настройки' }).click()
    await expect(page).toHaveURL(/\/candidate\/settings/)
    await expect(page.getByRole('heading', { name: 'Настройки' })).toBeVisible()
  })
})
