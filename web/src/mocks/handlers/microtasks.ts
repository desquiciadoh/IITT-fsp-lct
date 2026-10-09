import { http, HttpResponse } from 'msw'
import type { EmployerMicroTask, MicroTask, MicroTaskDrop } from '@/api/types'

/**
 * FE-16 micro-task store (G19): candidate inbox/solve + employer
 * create/review. Auto tasks get a deterministic mock score, open ones need
 * an employer review. The `shared` flag gates the "invite" action.
 */

const json = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail },
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
    },
  )

const in10d = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString()
const in7d = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()

const ACCOUNT = { public_id: 'c-47D2BD', display_name: 'Анна Иванова', city: 'Москва' }

const TASKS: MicroTask[] = [
  {
    id: 'mt-1',
    company: { id: 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
    title: 'Сложность алгоритма',
    specialization: 'backend',
    grades: ['middle', 'senior'],
    format: 'auto',
    prompt_md: [
      'Дан массив из **n** целых чисел.',
      '',
      '1. Напишите псевдокод, который возвращает максимальную сумму непрерывного подмассива.',
      '2. Укажите сложность по времени (Big-O).',
      '',
      'Пример ответа: `O(n) — алгоритм Кадане` — и один-два абзаца обоснования.',
    ].join('\n'),
    deadline: in10d,
  },
  {
    id: 'mt-2',
    company: { id: 'comp-3', name: 'Ozon Tech', trust_level: 'verified' },
    title: 'Декомпозиция задачи на пайплайн',
    specialization: 'ml_data',
    grades: ['middle', 'senior'],
    format: 'open',
    prompt_md: [
      'Разбейте поток «заказы → прогноз спроса» на этапы.',
      '',
      'Опишите:',
      '- входные данные и качество;',
      '- какие модели/правила вы бы использовали;',
      '- метрики на каждом шаге.',
      '',
      'Формат: свободный, до 3000 знаков.',
    ].join('\n'),
    deadline: in7d,
  },
  {
    id: 'mt-3',
    company: { id: 'comp-2', name: 'DataForge', trust_level: 'domain' },
    title: 'SQL: витрина по продажам',
    specialization: 'backend',
    grades: ['junior', 'middle'],
    format: 'auto',
    prompt_md: [
      'Есть таблицы `orders` и `order_items`.',
      '',
      'Напишите SQL-запрос: сумма продаж по дням за последние 30 дней с названием продукта.',
      '',
      'Укажите, какие индексы вы бы добавили.',
    ].join('\n'),
    deadline: in10d,
  },
]

const DROPS: MicroTaskDrop[] = [
  {
    id: 'drop-1',
    task: TASKS[1],
    candidate: ACCOUNT,
    answer: 'Шаг 1: сырые заказы → дедупликация → витрина фактов…',
    score: null,
    employer_rating: null,
    shared: false,
    submitted_at: yesterday,
  },
]

let dropSeq = DROPS.length + 1
let taskSeq = TASKS.length + 1

export const microtaskHandlers = [
  http.get('*/api/microtasks', () => json(TASKS)),

  http.get('*/api/microtasks/drops/me', () => json(DROPS)),

  http.get('*/api/microtasks/:id', ({ params }) => {
    const task = TASKS.find((t) => t.id === params.id)
    if (!task) return problem(404, 'not_found', 'Micro-task not found.')
    return json(task)
  }),

  http.post('*/api/microtasks/:id/submit', async ({ params, request }) => {
    const task = TASKS.find((t) => t.id === params.id)
    if (!task) return problem(404, 'not_found', 'Micro-task not found.')
    if (new Date(task.deadline).getTime() < Date.now()) {
      return problem(409, 'deadline_passed', 'The micro-task deadline has passed.')
    }
    const body = (await request.json().catch(() => ({}))) as { answer?: unknown }
    const raw = typeof body.answer === 'string' ? body.answer : JSON.stringify(body.answer ?? '')
    if (!raw.trim()) return problem(400, 'validation_failed', 'Answer is required.')

    const exists = DROPS.find((d) => d.task.id === task.id)
    if (exists) return existingDrop(exists)

    const drop: MicroTaskDrop = {
      id: `drop-${dropSeq++}`,
      task,
      candidate: ACCOUNT,
      answer: raw,
      score: task.format === 'auto' ? Number((raw.length % 3) + 3) : null,
      employer_rating: null,
      shared: false,
      submitted_at: new Date().toISOString(),
    }
    DROPS.push(drop)
    return json(drop, 201)
  }),

  http.post('*/api/employer/microtasks', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      title?: string
      specialization?: string
      grades?: string[]
      format?: string
      prompt_md?: string
      deadline?: string
    }
    if (!body.title?.trim() || !body.prompt_md?.trim()) {
      return problem(400, 'validation_failed', 'Title and prompt are required.')
    }
    const task: MicroTask = {
      id: `mt-${taskSeq++}`,
      company: { id: 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
      title: body.title.trim(),
      specialization: (body.specialization as MicroTask['specialization']) ?? 'backend',
      grades: (body.grades as MicroTask['grades']) ?? ['junior'],
      format: body.format === 'open' ? 'open' : 'auto',
      prompt_md: body.prompt_md.trim(),
      deadline: body.deadline ?? in10d,
    }
    TASKS.push(task)
    return json(task, 201)
  }),

  http.get('*/api/employer/microtasks', () => {
    const list: EmployerMicroTask[] = TASKS.map((task) => ({
      ...task,
      submissions: DROPS.filter((d) => d.task.id === task.id),
    }))
    return json(list)
  }),

  http.put('*/api/microtasks/drops/:id/review', async ({ params, request }) => {
    const drop = DROPS.find((d) => d.id === params.id)
    if (!drop) return problem(404, 'not_found', 'Submission not found.')
    const body = (await request.json().catch(() => ({}))) as {
      employer_rating?: number
      shared?: boolean
    }
    drop.employer_rating = body.employer_rating ?? null
    drop.shared = body.shared ?? false
    return json(drop)
  }),
]

function existingDrop(drop: MicroTaskDrop) {
  return json({ ...drop, duplicate: true })
}