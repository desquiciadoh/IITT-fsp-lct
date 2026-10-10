import { test, expect, loginEmployer } from './fixtures'

test.describe('FE-19 employer surfaces (mocks)', () => {
  test('micro-tasks: employer creates a task', async ({ page }) => {
    await loginEmployer(page)
    await page.getByRole('navigation').getByRole('link', { name: 'Задачи' }).click()
    await expect(page).toHaveURL(/\/employer\/microtasks/)
    await expect(page.getByRole('heading', { name: 'Задачи и решения' })).toBeVisible()
    await page.getByRole('button', { name: 'Новая задача' }).click()
    await page.getByLabel('Название').fill('E2E test task')
    await page.getByRole('button', { name: /Опубликовать|Создать/ }).click()
    await expect(page.getByText('E2E test task')).toBeVisible()
  })

  test('pool preview renders the ranked list', async ({ page }) => {
    await loginEmployer(page)
    await page.goto('/dev/pool')
    await expect(page.getByRole('heading', { name: /Senior Backend Engineer/ })).toBeVisible()
    await expect(page.getByText(/кандидат/i).first()).toBeVisible()
  })

  test('vacancy preview links to Test Twins', async ({ page }) => {
    await loginEmployer(page)
    await page.goto('/dev/vacancies-employer')
    await expect(page.getByRole('link', { name: /Test Twins/ })).toBeVisible()
  })

  test.fixme('FE-05/10/11: test runner, vacancy detail, employer offers (FE2)', async () => {})
})
