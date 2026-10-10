import { describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { employerHandlers } from './employer'

const server = setupServer(...employerHandlers)
describe('debug parse', () => {
  it('shows draft', async () => {
    const jd = `Senior Backend Developer
    Обязательны: python, django, postgresql, redis.
    Будет плюсом: kafka, celery. Опыт с Elasticsearch приветствуется.
    Формат: удалённо или гибрид, Москва. Зарплата от 250 000 ₽, gross.`
    const res = await fetch('http://localhost/api/positions/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: jd }),
    })
    const body = await res.json()
    console.log(JSON.stringify(body.draft.must_skills), JSON.stringify(body.draft.nice_skills))
    expect(true).toBe(true)
  })
})
