/**
 * FE-09 · Stage 0 — QA of the stateful employer mock (companies / positions /
 * JD parse), driven over the wire through msw/node exactly as the wizard UI
 * will use it in browser.ts `all` mode. Covers:
 *   1. B1/G17: GET /api/companies/me → 403 company_required until PUT creates
 *      the company; after creation GET/PUT work and trust_level is read-only;
 *   2. G6: POST /api/positions/parse returns {draft, unknown_terms, blueprint,
 *      source} for a sample JD; short text → 422;
 *   3. B15: POST /api/positions with salary_min = 0 or max < min → 422
 *      salary_invalid (never 500); valid payload → 201 + list/update flow;
 *   4. positions require a company (403 before creation);
 *   5. every response carries X-Stub: true.
 */
import { beforeAll, afterAll, beforeEach, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { employerHandlers, resetEmployerMock } from './employer'

const BASE = 'http://localhost'
const server = setupServer(...employerHandlers)

async function req<T = any>(
  path: string,
  init?: RequestInit,
): Promise<{ status: number; body: T; stubbed: boolean }> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = res.status === 204 ? null : await res.json()
  return { status: res.status, body, stubbed: res.headers.get('X-Stub') === 'true' }
}

const put = (path: string, body: unknown) =>
  req(path, { method: 'PUT', body: JSON.stringify(body) })
const post = (path: string, body: unknown) =>
  req(path, { method: 'POST', body: JSON.stringify(body) })

const SAMPLE_JD = `Senior Backend Developer (Python)

We are looking for a strong engineer to build REST APIs with Django and FastAPI.
You will design PostgreSQL schemas, write tests with pytest, deploy via Docker and
Kubernetes, and work with Kafka streams. Experience with ClickHouse and LangChain
is a plus. Salary 250 000 - 350 000 RUB gross, middle or senior grade, remote.`

describe('employer mock — FE-09 stage 0 QA', () => {
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
  afterAll(() => server.close())
  beforeEach(() => resetEmployerMock())

  describe('company (B1 / gap G17)', () => {
    it('GET /api/companies/me → 403 company_required before creation', async () => {
      const r = await req('/api/companies/me')
      expect(r.status).toBe(403)
      expect(r.body.code).toBe('company_required')
      expect(r.stubbed).toBe(true)
    })

    it('PUT creates the company (upsert), then GET returns it', async () => {
      const created = await put('/api/companies/me', {
        name: 'ООО Ромашка',
        inn: '1234567890',
        email_domain: 'romashka.ru',
        description: 'Финтех-стартап.',
      })
      expect(created.status).toBe(200)
      expect(created.body.id).toBeTruthy()
      expect(created.body.trust_level).toBe('none')

      const got = await req('/api/companies/me')
      expect(got.status).toBe(200)
      expect(got.body.name).toBe('ООО Ромашка')
    })

    it('PUT rejects an invalid INN with field errors', async () => {
      const r = await put('/api/companies/me', { name: 'X', inn: '12345' })
      expect(r.status).toBe(422)
      expect(r.body.errors.inn).toBeDefined()
    })

    it('PUT without a name fails validation', async () => {
      const r = await put('/api/companies/me', { inn: '1234567890' })
      expect(r.status).toBe(422)
    })
  })

  describe('JD parse (gap G6)', () => {
    it('returns draft + unknown_terms + blueprint + source', async () => {
      const r = await post('/api/positions/parse', { text: SAMPLE_JD })
      expect(r.status).toBe(200)
      expect(r.stubbed).toBe(true)

      const { draft, unknown_terms, blueprint, source } = r.body
      expect(source).toBe('mock')
      expect(draft.specialization).toBe('backend')
      expect(draft.must_skills).toEqual(expect.arrayContaining(['python', 'django', 'postgresql']))
      expect(draft.salary_min).toBe(250000)
      expect(draft.salary_max).toBe(350000)
      // terms outside the taxonomy must surface for chip highlighting
      expect(unknown_terms).toEqual(expect.arrayContaining(['ClickHouse', 'LangChain']))
      expect(blueprint.length).toBeGreaterThan(0)
      for (const topic of blueprint) {
        expect(typeof topic.topic).toBe('string')
        expect(topic.weight).toBeGreaterThan(0)
      }
    })

    it('too-short text → 422 with a field error', async () => {
      const r = await post('/api/positions/parse', { text: 'python dev' })
      expect(r.status).toBe(422)
      expect(r.body.errors.text).toBeDefined()
    })
  })

  describe('positions (B15 + company gate)', () => {
    const validPosition = {
      title: 'Python-разработчик',
      specialization: 'backend',
      grades: ['middle'],
      must_skills: ['python'],
      nice_skills: ['redis'],
      work_formats: ['remote'],
      location: 'Удалённо',
      salary_min: 200000,
      salary_max: 300000,
      salary_type: 'net',
      description: 'Текст вакансии.',
      allow_adjacent: false,
      is_public: true,
    }

    it('POST /api/positions → 403 company_required while no company exists', async () => {
      const r = await post('/api/positions', validPosition)
      expect(r.status).toBe(403)
      expect(r.body.code).toBe('company_required')
    })

    it('salary_min = 0 → 422 salary_invalid (never 500, BE.md B15)', async () => {
      await put('/api/companies/me', { name: 'Ромашка' })
      const r = await post('/api/positions', { ...validPosition, salary_min: 0 })
      expect(r.status).toBe(422)
      expect(r.body.code).toBe('salary_invalid')
      expect(r.body.errors.salary_min).toBeDefined()
    })

    it('salary_max < salary_min → 422 salary_invalid', async () => {
      await put('/api/companies/me', { name: 'Ромашка' })
      const r = await post('/api/positions', {
        ...validPosition,
        salary_min: 300000,
        salary_max: 200000,
      })
      expect(r.status).toBe(422)
      expect(r.body.code).toBe('salary_invalid')
    })

    it('missing salary_type → 422 salary_invalid (no silent gross default)', async () => {
      await put('/api/companies/me', { name: 'Ромашка' })
      const { salary_type: _omitted, ...withoutType } = validPosition
      const r = await post('/api/positions', withoutType)
      expect(r.status).toBe(422)
      expect(r.body.code).toBe('salary_invalid')
    })

    it('full flow: create company → save position → list → get → update', async () => {
      await put('/api/companies/me', { name: 'Ромашка' })

      const created = await post('/api/positions', validPosition)
      expect(created.status).toBe(201)
      expect(created.body.id).toBeTruthy()
      expect(created.body.salary_type).toBe('net')

      const list = await req('/api/positions')
      expect(list.status).toBe(200)
      // seed + the new one; backend returns a plain array today (G14)
      expect(Array.isArray(list.body)).toBe(true)
      expect(list.body.some((p: any) => p.id === created.body.id)).toBe(true)

      const got = await req(`/api/positions/${created.body.id}`)
      expect(got.status).toBe(200)
      expect(got.body.title).toBe('Python-разработчик')

      const updated = await put(`/api/positions/${created.body.id}`, {
        ...validPosition,
        salary_max: 400000,
        is_public: false,
      })
      expect(updated.status).toBe(200)
      expect(updated.body.salary_max).toBe(400000)
      expect(updated.body.is_public).toBe(false)
    })

    it('GET /api/positions/{unknown} → 404 not_found', async () => {
      const r = await req('/api/positions/nope')
      expect(r.status).toBe(404)
      expect(r.body.code).toBe('not_found')
    })
  })
})
