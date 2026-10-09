// @vitest-environment node
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { microtaskHandlers } from './microtasks'
import { offerHandlers } from './offers'

/**
 * FE-16 end-to-end on mocks: create → solve → review → invite (draft offer
 * with microtask evidence) → the drop shows in the candidate's list.
 */
const server = setupServer(...microtaskHandlers, ...offerHandlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const post = (url: string, body: unknown) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

describe('FE-16 micro-task pipeline (mocks)', () => {
  it('create → solve (auto) → review → invite works', async () => {
    const inbox = await fetch('http://127.0.0.1/api/microtasks')
    expect(inbox.status).toBe(200)
    const tasks = (await inbox.json()) as Array<{ id: string }>
    expect(tasks.length).toBeGreaterThan(0)

    const solved = await post('http://127.0.0.1/api/microtasks/mt-1/submit', {
      answer: 'O(n) — алгоритм Кадане с обоснованием',
    })
    expect(solved.status).toBe(201)
    const drop = (await solved.json()) as {
      id: string
      score: number | null
      task: { id: string }
    }
    expect(drop.task.id).toBe('mt-1')
    expect(drop.score).not.toBeNull()

    const reviewed = await fetch(`http://127.0.0.1/api/microtasks/drops/${drop.id}/review`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ employer_rating: 5, shared: true }),
    })
    expect(reviewed.status).toBe(200)
    const shared = (await reviewed.json()) as { shared: boolean }
    expect(shared.shared).toBe(true)

    const made = await post('http://127.0.0.1/api/offers', {
      candidate_public_id: 'c-47D2BD',
      title: 'Оффер по итогам микрозадачи',
      description: 'Прекрасное решение',
      salary_min: 250000,
      salary_max: 350000,
      salary_type: 'gross',
      contact_channel: 'platform',
      contact_value: '',
    })
    expect(made.status).toBe(201)
    const offer = (await made.json()) as {
      status: string
      why_you: Array<{ source: string }>
    }
    expect(offer.status).toBe('sent')
    expect(offer.why_you.some((w) => w.source === 'microtask')).toBe(true)

    const mine = await fetch('http://127.0.0.1/api/microtasks/drops/me')
    const myDrops = (await mine.json()) as Array<{ id: string }>
    expect(myDrops.some((d) => d.id === drop.id)).toBe(true)
  })

  it('rejects a blank answer with validation_failed', async () => {
    const bad = await post('http://127.0.0.1/api/microtasks/mt-3/submit', { answer: '   ' })
    expect(bad.status).toBe(400)
    const problem = (await bad.json()) as { code: string }
    expect(problem.code).toBe('validation_failed')
  })

  it('employer can create a task', async () => {
    const created = await post('http://127.0.0.1/api/employer/microtasks', {
      title: 'Витрина по продажам',
      specialization: 'backend',
      grades: ['middle'],
      format: 'open',
      prompt_md: 'Напишите SQL-запрос.',
      deadline: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString(),
    })
    expect(created.status).toBe(201)
    const task = (await created.json()) as { id: string; title: string }
    expect(task.title).toBe('Витрина по продажам')

    const list = await fetch('http://127.0.0.1/api/employer/microtasks')
    const employerTasks = (await list.json()) as Array<{ id: string; submissions: unknown[] }>
    expect(employerTasks.some((t) => t.id === task.id)).toBe(true)
  })
})