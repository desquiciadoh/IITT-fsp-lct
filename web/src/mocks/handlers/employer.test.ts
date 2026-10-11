import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { employerHandlers } from './employer'

/**
 * FE-09 · Company & position wizard — end-to-end QA of the stateful
 * employer mock (the same handler objects registered in mocks/server.ts
 * and browser.ts). Drives the wire contract:
 *   G17: GET /companies/me → 403 company_required until POST /companies;
 *   G6 : POST /positions/parse → {draft, unknown_terms, blueprint, source};
 *   salary validation mirrors BE.md B15 (`salary_invalid` error dict);
 *   positions CRUD is stateful so a sample JD becomes a saved position.
 */

const BASE = 'http://localhost'
const server = setupServer(...employerHandlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())

// The mock is stateful (single company, shared positions list). Scenarios run
// in order within each describe; the reset endpoint lets a suite seed itself
// independently of what previous suites left behind.
const reset = () => fetch(`${BASE}/api/_mock/employer/reset`, { method: 'POST' })

async function req<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<{ status: number; body: T }> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  return { status: res.status, body: (await res.json()) as T }
}

const post = <T = unknown>(path: string, body: unknown) =>
  req<T>(path, { method: 'POST', body: JSON.stringify(body) })

const put = <T = unknown>(path: string, body: unknown) =>
  req<T>(path, { method: 'PUT', body: JSON.stringify(body) })

type CompanyWire = {
  id: string
  name: string
  inn: string
  trust_level: string
  created_at: string
}
type PositionWire = {
  id: string
  title: string
  salary_min: number
  salary_max: number
  salary_type: string
  status: string
}
type ParseWire = {
  draft: {
    title?: string
    specialization?: string
    grades?: string[]
    must_skills?: string[]
    nice_skills?: string[]
    work_formats?: string[]
    salary_min?: number
    salary_max?: number
  }
  unknown_terms?: string[]
  blueprint?: { topic: string; weight: number }[]
  source?: string
}
type ProblemWire = { code: string; detail?: string; errors?: Record<string, string[]> }

describe('FE-09 employer mock: company (G17 branch)', () => {
  it('403 company_required before the company exists', async () => {
    const { status, body } = await req<ProblemWire>('/api/companies/me')
    expect(status).toBe(403)
    expect(body.code).toBe('company_required')
  })

  it('rejects creation without name/inn with field errors', async () => {
    const { status, body } = await post<ProblemWire>('/api/companies', { website: 'x' })
    expect(status).toBe(400)
    expect(body.errors).toHaveProperty('name')
    expect(body.errors).toHaveProperty('inn')
  })

  it('creates the company; GET returns it with read-only trust_level', async () => {
    const created = await post<CompanyWire>('/api/companies', {
      name: 'Ромашка',
      inn: '1234567890',
      contact_email: 'hr@romashka.ru',
      email_domain: 'romashka.ru',
    })
    expect(created.status).toBe(201)
    expect(created.body.trust_level).toBe('none')

    const fetched = await req<CompanyWire>('/api/companies/me')
    expect(fetched.status).toBe(200)
    expect(fetched.body.name).toBe('Ромашка')
  })

  it('PUT updates writable fields but keeps id/trust_level immutable', async () => {
    await reset()
    await post('/api/companies', { name: 'Ромашка', inn: '1234567890' })
    const updated = await put<CompanyWire>('/api/companies/me', {
      name: 'Ромашка 2',
      description: 'Финтех',
      trust_level: 'verified', // client tries to forge it — server must ignore
    })
    expect(updated.status).toBe(200)
    expect(updated.body.name).toBe('Ромашка 2')
    expect(updated.body.trust_level).toBe('none')
  })
})

describe('FE-09 employer mock: JD parse (G6 shape)', () => {
  it('parses a sample JD into the target shape', async () => {
    const jd = `Senior Backend Developer
    Обязательны: python, django, postgresql, redis.
    Будет плюсом: kafka, celery. Опыт с Elasticsearch приветствуется.
    Формат: удалённо или гибрид, Москва. Зарплата от 250 000 ₽, gross.`
    const { status, body } = await post<ParseWire>('/api/positions/parse', { text: jd })
    expect(status).toBe(200)
    expect(body.draft.specialization).toBe('backend')
    expect(body.draft.grades).toContain('senior')
    expect(body.draft.must_skills).toEqual(
      expect.arrayContaining(['python', 'django', 'postgresql', 'redis']),
    )
    expect(body.draft.nice_skills).toEqual(expect.arrayContaining(['kafka', 'celery']))
    expect(body.draft.work_formats).toEqual(expect.arrayContaining(['remote', 'hybrid']))
    expect(body.draft.salary_min).toBe(250000)
    expect(body.unknown_terms).toContain('elasticsearch')
    expect(body.blueprint?.length).toBeGreaterThan(0)
    expect(body.blueprint?.every((b) => b.weight > 0 && b.weight <= 1)).toBe(true)
    expect(body.source).toBeTruthy()
  })

  it('rejects too-short text with 400', async () => {
    const { status } = await post('/api/positions/parse', { text: 'junior dev' })
    expect(status).toBe(400)
  })
})

describe('FE-09 employer mock: positions CRUD', () => {
  const valid = {
    title: 'Senior Backend Developer',
    specialization: 'backend',
    grades: ['senior'],
    must_skills: ['python', 'django'],
    nice_skills: ['kafka'],
    work_formats: ['remote'],
    location: 'Москва',
    salary_min: 250000,
    salary_max: 350000,
    salary_type: 'gross',
    allow_adjacent: false,
    is_public: true,
  }

  it('rejects salary_min = 0 with the salary_invalid dict (BE.md B15)', async () => {
    await reset()
    await post('/api/companies', { name: 'Ромашка', inn: '1234567890' })
    const { status, body } = await post<ProblemWire>('/api/positions', {
      ...valid,
      title: 'Zero',
      salary_min: 0,
    })
    expect(status).toBe(400)
    expect(body.errors).toHaveProperty('salary_invalid')
  })

  it('rejects salary_max < salary_min', async () => {
    await reset()
    await post('/api/companies', { name: 'Ромашка', inn: '1234567890' })
    const { status, body } = await post<ProblemWire>('/api/positions', {
      ...valid,
      title: 'Inverted',
      salary_max: 100000,
    })
    expect(status).toBe(400)
    expect(body.errors).toHaveProperty('salary_invalid')
  })

  it('requires salary_type explicitly (no silent gross default, B15)', async () => {
    await reset()
    await post('/api/companies', { name: 'Ромашка', inn: '1234567890' })
    // strip salary_type and retry
    const noType = { ...valid, title: 'No salary type' } as Record<string, unknown>
    delete noType.salary_type
    const second = await post<ProblemWire>('/api/positions', noType)
    expect(second.status).toBe(400)
    expect(second.body.errors).toHaveProperty('salary_invalid')
  })

  it('saves a valid position, lists it, fetches and edits it', async () => {
    await reset()
    await post('/api/companies', { name: 'Ромашка', inn: '1234567890' })
    const created = await post<{ id: string }>('/api/positions', valid)
    expect(created.status).toBe(201)
    const id = created.body.id

    const list = await req<PositionWire[]>('/api/positions')
    expect(Array.isArray(list.body)).toBe(true)
    expect(list.body.some((p) => p.id === id)).toBe(true)

    const one = await req<PositionWire>(`/api/positions/${id}`)
    expect(one.body.title).toBe(valid.title)

    const edited = await put<PositionWire>(`/api/positions/${id}`, { salary_min: 300000 })
    expect(edited.status).toBe(200)
    expect(edited.body.salary_min).toBe(300000)

    const missing = await req(`/api/positions/nonexistent-id`)
    expect(missing.status).toBe(404)
  })
})
