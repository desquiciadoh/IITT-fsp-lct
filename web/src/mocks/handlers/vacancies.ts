import { http, HttpResponse } from 'msw'
import type { Application, ApplicationStatus, Vacancy } from '@/api/types'

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json({ type: 'about:blank', title: code, status, code, detail }, {
    status,
    headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
  })

/**
 * Vacancies & applications (FE-15). Shared in-memory store so an employer's
 * status change and a candidate's list stay in sync while the page is open.
 * Live backend contract: BE.md §2.3 G18 (BE-17).
 */

const COMPANY_A = { id: '00000000-0000-4000-8000-000000000001', name: 'Yandex Tech', trust_level: 'verified' as const }
const COMPANY_B = { id: '00000000-0000-4000-8000-000000000002', name: 'Ozon', trust_level: 'domain' as const }
const COMPANY_C = { id: '00000000-0000-4000-8000-000000000005', name: 'Acme Systems', trust_level: 'none' as const }

const STORE: Vacancy[] = [
  {
    id: 'pos-1',
    company: COMPANY_A,
    title: 'Backend-инженер, Python/Go',
    specialization: 'backend',
    grades: ['middle', 'senior'],
    salary_min: 260000,
    salary_max: 380000,
    salary_type: 'gross',
    work_formats: ['hybrid', 'remote'],
    location: 'Москва',
    team_context: 'Платформа офферов, PostgreSQL + Redis, до 5 млн rps.',
    is_applied: false,
  },
  {
    id: 'pos-2',
    company: COMPANY_A,
    title: 'Frontend-инженер, React',
    specialization: 'frontend',
    grades: ['middle'],
    salary_min: 240000,
    salary_max: 320000,
    salary_type: 'gross',
    work_formats: ['remote'],
    team_context: 'Дизайн-система и клиентские сценарии прода.',
    is_applied: false,
  },
  {
    id: 'pos-3',
    company: COMPANY_B,
    title: 'ML-инженер, ранжирование',
    specialization: 'ml_data',
    grades: ['senior'],
    salary_min: 350000,
    salary_max: 450000,
    salary_type: 'gross',
    work_formats: ['office', 'hybrid'],
    location: 'Москва',
    team_context: 'Сервисы рекомендаций, A/B и честный офлайн-бенчмарк.',
    is_applied: false,
  },
  {
    id: 'pos-4',
    company: COMPANY_B,
    title: 'Backend-инженер, джун',
    specialization: 'backend',
    grades: ['junior', 'middle'],
    salary_min: 140000,
    salary_max: 190000,
    salary_type: 'gross',
    work_formats: ['hybrid'],
    location: 'Санкт-Петербург',
    team_context: 'Команда авторизации, менторство от мидлов.',
    is_applied: false,
  },
  {
    id: 'pos-5',
    company: COMPANY_C,
    title: 'Backend-инженер, интеграции',
    specialization: 'backend',
    grades: ['middle', 'senior'],
    salary_min: 220000,
    salary_max: 300000,
    salary_type: 'net',
    work_formats: ['remote'],
    team_context: 'API для внешних ATS.',
    is_applied: false,
  },
  {
    id: 'pos-6',
    company: COMPANY_A,
    title: 'Аналитик данных (черновик, не опубликовано)',
    specialization: 'ml_data',
    grades: ['middle'],
    salary_min: 180000,
    salary_max: 240000,
    salary_type: 'gross',
    work_formats: ['hybrid'],
    location: 'Москва',
    team_context: '',
    is_applied: false,
  },
]

const CANDIDATES = [
  { public_id: 'C-47D2BD', display_name: 'anna.dev', city: 'Москва' },
  { public_id: 'C-91A3F0', display_name: 'ivan.fe', city: 'Санкт-Петербург' },
  { public_id: 'C-12E8C7', display_name: 'maria.ml', city: 'Казань' },
]

const mkApplication = (
  id: string,
  positionId: string,
  status: ApplicationStatus,
  candidate_public_id: string,
): Application => {
  const vacancy = STORE.find((v) => v.id === positionId)!
  const candidate = CANDIDATES.find((c) => c.public_id === candidate_public_id)!
  return {
    id,
    vacancy: {
      id: vacancy.id,
      title: vacancy.title,
      company: vacancy.company,
      specialization: vacancy.specialization,
      grades: vacancy.grades,
      salary_min: vacancy.salary_min,
      salary_max: vacancy.salary_max,
      salary_type: vacancy.salary_type,
    },
    candidate,
    status,
    created_at: '2026-10-07T09:00:00Z',
    updated_at: '2026-10-08T12:30:00Z',
  }
}

const APPLICATIONS: Application[] = [
  mkApplication('app-1', 'pos-1', 'reviewing', 'C-47D2BD'),
  mkApplication('app-2', 'pos-4', 'applied', 'C-12E8C7'),
  mkApplication('app-3', 'pos-1', 'applied', 'C-91A3F0'),
]

export const vacancyHandlers = [
  http.get('*/api/vacancies', () =>
    HttpResponse.json(
      STORE.filter((v) => v.is_public !== false).map((v) => ({
        ...v,
        is_applied: APPLICATIONS.some((a) => a.vacancy.id === v.id),
      })),
    ),
  ),

  http.get('*/api/positions/:id', ({ params }) => {
    const vacancy = STORE.find((v) => v.id === String(params.id))
    return vacancy
      ? HttpResponse.json(vacancy)
      : problem(404, 'not_found', 'Position is not found.')
  }),

  http.post('*/api/vacancies/:id/apply', async ({ params, request }) => {
    const positionId = String(params.id)
    const vacancy = STORE.find((v) => v.id === positionId)
    if (!vacancy || vacancy.is_public === false) return problem(404, 'not_found', 'Vacancy is not found.')
    const body = (await request.json().catch(() => ({}))) as { note?: string }
    const existing = APPLICATIONS.find((a) => a.vacancy.id === positionId)
    if (existing) return HttpResponse.json(existing, { status: 200 })
    const application = mkApplication(
      `app-${APPLICATIONS.length + 1}`,
      positionId,
      'applied',
      'C-47D2BD',
    )
    if (body.note) application.note = body.note
    APPLICATIONS.push(application)
    return HttpResponse.json(application, { status: 201 })
  }),

  http.get('*/api/candidates/me/applications', () => HttpResponse.json(APPLICATIONS)),

  http.get('*/api/positions/:id/applications', ({ params }) =>
    HttpResponse.json(APPLICATIONS.filter((a) => a.vacancy.id === String(params.id))),
  ),

  http.put('*/api/applications/:id', async ({ params, request }) => {
    const application = APPLICATIONS.find((a) => a.id === String(params.id))
    if (!application) return problem(404, 'not_found', 'Application is not found.')
    const body = (await request.json().catch(() => ({}))) as { status?: ApplicationStatus }
    if (!body.status) return problem(400, 'validation_failed', 'Status is required.')
    application.status = body.status
    application.updated_at = new Date().toISOString()
    return HttpResponse.json(application)
  }),

  http.put('*/api/positions/:id', async ({ params, request }) => {
    const vacancy = STORE.find((v) => v.id === String(params.id))
    if (!vacancy) return problem(404, 'not_found', 'Position is not found.')
    const body = (await request.json().catch(() => ({}))) as { is_public?: boolean }
    if (typeof body.is_public === 'boolean') vacancy.is_public = body.is_public
    return HttpResponse.json(vacancy)
  }),
]