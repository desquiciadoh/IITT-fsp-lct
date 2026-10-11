import { http, HttpResponse } from 'msw'
import type {
  MicroTask,
  MicroTaskDropCandidate,
  MicroTaskSubmission,
  TalentShort,
} from '@/api/types'

/**
 * FE-16 · Micro-tasks — stateful MSW mock (BE-18 contract).
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

type MockMicroTask = MicroTask & { key?: unknown }

const seedTasks = (): MockMicroTask[] => [
  {
    id: '30000000-0000-4000-8000-000000000001',
    company: COMPANY,
    title: 'Оценка стоимости жилья',
    specialization: 'ml_data',
    grades: ['middle', 'senior'],
    format: 'auto',
    prompt_md:
      'Модель предсказывает стоимость квартиры по фичерам. Небольшая ошибка — нормально.\n\nОпишите подход и назовите выбор метрики.',
    key: { metric: 'rmse', tune: true },
    deadline: '2026-12-01T23:00:00Z',
    created_at: '2026-10-01T10:00:00Z',
  },
  {
    id: '30000000-0000-4000-8000-000000000002',
    company: COMPANY,
    title: 'Сервис коротких ссылок',
    specialization: 'backend',
    grades: ['junior', 'middle'],
    format: 'open',
    prompt_md:
      'Спроектируйте API сервиса коротких ссылок: какие эндпоинты, как храните mapping, как защищаете от злоупотреблений.',
    deadline: null,
    created_at: '2026-10-02T10:00:00Z',
  },
]

let tasks: MockMicroTask[] = seedTasks()
let seq = 0
const uid = () => `40000000-0000-4000-8000-${String(++seq).padStart(12, '0')}`

function candidateFor(task: MicroTask): TalentShort {
  return {
    public_id: `tp-${task.id.slice(-4)}-c`,
    display_name: 'Кандидат из отклика',
    city: 'Москва',
    league: {
      specialization: task.specialization,
      grade: 'middle',
      status: 'confirmed',
      rating: 1700,
    },
  } as TalentShort
}

const seedDrops = (): MicroTaskDropCandidate[] => [
  {
    id: '50000000-0000-4000-8000-000000000001',
    task: tasks[0],
    dropped_at: '2026-10-03T09:00:00Z',
    answer: null,
    score: null,
    employer_rating: null,
    submitted_at: null,
  },
]

let drops: MicroTaskDropCandidate[] = seedDrops()

function toSubmission(drop: MicroTaskDropCandidate): MicroTaskSubmission {
  const task = tasks.find((t) => t.id === drop.task.id) ?? drop.task
  return {
    id: drop.id,
    task_id: task.id,
    candidate: candidateFor(task),
    dropped_at: drop.dropped_at,
    answer: drop.answer,
    score: drop.score,
    employer_rating: drop.employer_rating,
    submitted_at: drop.submitted_at,
  }
}

function applyAuto(drop: MicroTaskDropCandidate, answer: unknown): MicroTaskDropCandidate {
  const found = tasks.find((t) => t.id === drop.task.id)
  const key = found?.key
  let score: number | null = 1
  if (key !== undefined) {
    if (typeof key === 'object' && key !== null && typeof answer === 'object') {
      score = JSON.stringify(answer) === JSON.stringify(key) ? 1 : 0
    } else {
      score = String(answer).trim() === String(key).trim() ? 1 : 0
    }
  }
  return { ...drop, answer, score, submitted_at: new Date().toISOString() }
}

export const microTasksHandlers = [
  http.post('*/api/_mock/micro-tasks/reset', () => {
    tasks = seedTasks()
    drops = seedDrops()
    return stub({ detail: 'ok' })
  }),

  // --- Employer: CRUD -----------------------------------------------------------
  http.get('*/api/micro-tasks', () => stub(tasks)),
  http.get('*/api/micro-tasks/:id', ({ params }) => {
    const task = tasks.find((t) => t.id === params.id)
    if (!task) return problem(404, 'not_found', 'Микрозадача не найдена.')
    return stub(task)
  }),
  http.post('*/api/micro-tasks', async ({ request }) => {
    const body = (await request.json()) as Partial<MockMicroTask>
    if (!body.title || !body.prompt_md) {
      return problem(422, 'validation_failed', 'Название и условие обязательны')
    }
    const task: MockMicroTask = {
      id: uid(),
      company: COMPANY,
      title: String(body.title ?? ''),
      specialization: (body.specialization ?? 'backend') as never,
      grades: (body.grades ?? []) as never[],
      format: (body.format ?? 'auto') as never,
      family_id: null,
      prompt_md: String(body.prompt_md ?? ''),
      key: body.key,
      deadline: (body.deadline as string | null) ?? null,
      created_at: new Date().toISOString(),
    }
    tasks.unshift(task)
    return stub(task, 201)
  }),
  http.delete('*/api/micro-tasks/:id', ({ params }) => {
    tasks = tasks.filter((t) => t.id !== params.id)
    return new HttpResponse(null, { status: 204, headers: { 'X-Stub': 'true' } })
  }),

  // --- Candidate: drops + submit -------------------------------------------------
  http.get('*/api/candidates/me/micro-tasks', () => stub(drops)),
  http.post('*/api/candidates/me/micro-tasks/:dropId/submit', async ({ request, params }) => {
    const index = drops.findIndex((d) => d.id === params.dropId)
    if (index === -1) return problem(404, 'not_found', 'Задача не найдена.')
    const drop = drops[index]
    if (drop.submitted_at) {
      return problem(422, 'already_submitted', 'Вы уже отправили решение этой задачи.')
    }
    const body = (await request.json().catch(() => ({}))) as { answer?: unknown }
    drops[index] = applyAuto(drop, body.answer)
    return stub(drops[index])
  }),

  // --- Employer: submissions ------------------------------------------------------
  http.get('*/api/micro-tasks/:id/submissions', ({ params }) => {
    const task = tasks.find((t) => t.id === params.id)
    if (!task) return problem(404, 'not_found', 'Микрозадача не найдена.')
    const list = drops
      .filter((d) => d.task.id === task.id && d.submitted_at)
      .map(toSubmission)
    if (list.length === 0 && task.format === 'open') {
      // demo: one reviewed submission so the reviewer has something to rate
      const reviewed: MicroTaskDropCandidate = {
        id: uid(),
        task,
        dropped_at: '2026-10-04T09:00:00Z',
        answer:
          String(task.prompt_md).length > 0
            ? 'Реализовал бы REST API: POST /links, GET /links/{code} с redirect. Хранил бы mapping в Postgres, кэш — Redis, лимиты — по IP и по аккаунту.'
            : 'Ряд шагов по решению',
        score: null,
        employer_rating: null,
        submitted_at: '2026-10-04T09:30:00Z',
      }
      return stub([toSubmission(reviewed)])
    }
    return stub(list)
  }),

  http.post('*/api/micro-tasks/submissions/:dropId/rate', async ({ request, params }) => {
    const body = (await request.json().catch(() => ({}))) as { employer_rating?: number }
    const rating = body.employer_rating
    if (typeof rating !== 'number' || rating < 1 || rating > 5) {
      return problem(422, 'validation_failed', 'Оценка должна быть от 1 до 5')
    }
    const drop = drops.find((d) => d.id === params.dropId)
    if (drop) {
      drop.employer_rating = rating
      return stub(toSubmission(drop))
    }
    // open-task demo submission is ephemeral — echo the preloaded data through.
    const task = tasks.find((t) => t.format === 'open') ?? tasks[0]
    const ephemeral = toSubmission(drops[0] ?? {
      id: String(params.dropId),
      task,
      dropped_at: new Date().toISOString(),
      answer: null,
      score: null,
      employer_rating: null,
      submitted_at: new Date().toISOString(),
    })
    ephemeral.employer_rating = rating
    return stub(ephemeral)
  }),

  http.post('*/api/micro-tasks/submissions/:dropId/prefill-offer', ({ params }) => {
    return stub({
      candidate_id: `cand-${String(params.dropId).slice(-4)}`,
      candidate_public_id: `tp-${String(params.dropId).slice(-4)}`,
      candidate_name: 'Кандидат из отклика',
      company_id: COMPANY.id,
      company_name: COMPANY.name,
      title: 'Разработчик (микрозадача)',
      description: 'На основе вашего решения микрозадачи.',
      salary_min: 200000,
      salary_max: 280000,
      salary_type: 'gross',
      contact_channel: 'platform',
    })
  }),
]