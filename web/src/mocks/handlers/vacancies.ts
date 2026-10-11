import { http, HttpResponse } from 'msw'
import type {
  ApplicationCandidate,
  ApplicationEmployer,
  ApplicationStatus,
  TalentShort,
  Vacancy,
} from '@/api/types'

/**
 * FE-15 · Vacancies & applications — stateful MSW mock (BE-17 contract).
 * Only used in `all` mode; `missing` mode passes through to the backend.
 */

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, {
    status,
    headers: { 'X-Stub': 'true' },
  })

const problem = (status: number, code: string, detail: string, errors?: unknown) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail, errors },
    { status, headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' } },
  )

const COMPANY = {
  id: '00000000-0000-4000-8000-0000000000a1',
  name: 'Ozon Tech',
  trust_level: 'verified' as const,
}

const seedVacancies = (): Vacancy[] => [
  {
    id: '10000000-0000-4000-8000-000000000001',
    title: 'Backend-разработчик (Python)',
    company: COMPANY,
    specialization: 'backend',
    grades: ['middle', 'senior'],
    must_skills: ['python', 'postgresql'],
    nice_skills: ['kafka'],
    work_formats: ['remote', 'hybrid'],
    location: 'Москва',
    salary_min: 250000,
    salary_max: 350000,
    salary_type: 'gross',
    salary: { min: 250000, max: 350000, type: 'gross', currency: 'RUB' },
    description: 'Платформа заказов: высоконагруженные сервисы на Python и PostgreSQL.',
    created_at: '2026-10-01T10:00:00Z',
  },
  {
    id: '10000000-0000-4000-8000-000000000002',
    title: 'Frontend-разработчик (React)',
    company: COMPANY,
    specialization: 'frontend',
    grades: ['junior', 'middle'],
    must_skills: ['typescript', 'react'],
    work_formats: ['office'],
    location: 'Санкт-Петербург',
    salary_min: 150000,
    salary_max: 220000,
    salary_type: 'net',
    salary: { min: 150000, max: 220000, type: 'net', currency: 'RUB' },
    description: 'Личный кабинет продавца: React, TypeScript, дизайн-система.',
    created_at: '2026-10-02T10:00:00Z',
  },
]

const TRANSITIONS: Record<ApplicationStatus, ApplicationStatus[]> = {
  applied: ['reviewing', 'invited', 'rejected'],
  reviewing: ['invited', 'rejected'],
  invited: ['hired', 'rejected'],
  rejected: [],
  hired: [],
  withdrawn: [],
}

let vacancies: Vacancy[] = seedVacancies()
const applications: ApplicationCandidate[] = []
let seq = 0
const uid = () => `20000000-0000-4000-8000-${String(++seq).padStart(12, '0')}`

function toEmployer(app: ApplicationCandidate): ApplicationEmployer {
  const candidate: TalentShort = {
    public_id: `tp-${app.id.slice(-4)}`,
    display_name: 'Кандидат из отклика',
    city: 'Москва',
    salary_min: 200000,
    salary_max: 260000,
    salary_type: 'gross',
    league: { specialization: app.position.specialization, grade: 'middle', status: 'confirmed', rating: 1700 },
    work_formats: ['remote'],
    skills: [],
  } as TalentShort
  return {
    id: app.id,
    candidate,
    status: app.status,
    note: app.note,
    created_at: app.created_at,
    updated_at: app.updated_at,
  }
}

export const vacanciesHandlers = [
  http.post('*/api/_mock/vacancies/reset', () => {
    vacancies = seedVacancies()
    applications.length = 0
    return stub({ detail: 'ok' })
  }),

  http.get('*/api/vacancies', ({ request }) => {
    const params = new URL(request.url).searchParams
    const spec = params.get('specialization')
    const search = (params.get('search') ?? '').toLowerCase().trim()
    let items = vacancies.filter((v) => !spec || v.specialization === spec)
    if (search) items = items.filter((v) => v.title.toLowerCase().includes(search))
    return stub({ items, total: items.length, page: 1, pages: 1 })
  }),

  http.get('*/api/vacancies/:id', ({ params }) => {
    const found = vacancies.find((v) => v.id === params.id)
    if (!found) return problem(404, 'not_found', 'Вакансия не найдена.')
    return stub(found)
  }),

  http.post('*/api/vacancies/:id/apply', async ({ request, params }) => {
    const vacancy = vacancies.find((v) => v.id === params.id)
    if (!vacancy) return problem(404, 'not_found', 'Вакансия не найдена.')
    if (applications.some((a) => a.position.id === vacancy.id)) {
      return problem(409, 'already_applied', 'Вы уже откликнулись на эту вакансию.')
    }
    const body = (await request.json().catch(() => ({}))) as { note?: string }
    const now = new Date().toISOString()
    const application: ApplicationCandidate = {
      id: uid(),
      position: vacancy,
      status: 'applied',
      note: body.note ?? '',
      created_at: now,
      updated_at: now,
    }
    applications.unshift(application)
    return stub(application, 201)
  }),

  http.get('*/api/candidates/me/applications', () => stub(applications)),

  http.post('*/api/candidates/me/applications/:id/withdraw', ({ params }) => {
    const application = applications.find((a) => a.id === params.id)
    if (!application) return problem(404, 'not_found', 'Отклик не найден.')
    if (['withdrawn', 'rejected', 'hired'].includes(application.status)) {
      return problem(422, 'invalid_transition', 'Нельзя отозвать отклик в этом статусе.')
    }
    application.status = 'withdrawn'
    application.updated_at = new Date().toISOString()
    return stub(application)
  }),

  http.get('*/api/positions/:id/applications', ({ params }) =>
    stub(applications.filter((a) => a.position.id === params.id).map(toEmployer)),
  ),

  http.patch('*/api/positions/:positionId/applications/:id/status', async ({ request, params }) => {
    const application = applications.find((a) => a.id === params.id)
    if (!application) return problem(404, 'not_found', 'Отклик не найден.')
    const body = (await request.json().catch(() => ({}))) as { status?: ApplicationStatus }
    const next = body.status
    if (!next || !TRANSITIONS[application.status].includes(next)) {
      return problem(422, 'invalid_transition', 'Недопустимый переход статуса.')
    }
    application.status = next
    application.updated_at = new Date().toISOString()
    return stub(toEmployer(application))
  }),
]
