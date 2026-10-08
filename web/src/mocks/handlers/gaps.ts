import { http, HttpResponse, passthrough } from 'msw'

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const json = (data: unknown) => stub(data)
const problem = (status: number, code: string, detail: string, errors?: unknown) =>
  HttpResponse.json({ type: 'about:blank', title: code, status, code, detail, errors }, {
    status,
    headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
  })

const TOPICS = [
  { key: 'architecture', label: 'Архитектура', correct: 3, total: 3 },
  { key: 'performance', label: 'Производительность', correct: 2, total: 3 },
  { key: 'testing', label: 'Тестирование', correct: 2, total: 2 },
  { key: 'security', label: 'Безопасность', correct: 1, total: 2 },
]

const EVIDENCE = [
  { seq: 1, correct: true },
  { seq: 2, correct: true },
  { seq: 3, correct: true },
  { seq: 4, correct: false },
  { seq: 5, correct: true },
  { seq: 6, correct: true },
  { seq: 7, correct: false },
  { seq: 8, correct: true },
]

const started = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
const finished = new Date(Date.now() - 60 * 60 * 1000).toISOString()
const in48h = new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString()

const base = {
  specialization: 'backend',
  kind: 'initial',
  mode: 'full',
  status: 'finished',
  se: 0.18,
  started_at: started,
  finished_at: finished,
  counts_as_attempt: true,
}

const resultFixtures: Record<string, Record<string, unknown>> = {
  'demo-confirmed': {
    ...base,
    id: 'demo-confirmed',
    claimed_grade: 'middle',
    theta: 4.21,
    rating: 1842,
    rating_ci: 42,
    percentile: 87,
    result_grade: 'middle',
    decision: 'confirmed',
    promotion_unlocked: false,
    topics: TOPICS,
    evidence: EVIDENCE,
    fallback: null,
    next_attempt_at: null,
  },
  'demo-unconfirmed': {
    ...base,
    id: 'demo-unconfirmed',
    claimed_grade: 'senior',
    kind: 'fallback',
    theta: 3.6,
    rating: 1720,
    rating_ci: 55,
    percentile: 71,
    result_grade: 'middle',
    decision: 'unconfirmed',
    promotion_unlocked: false,
    topics: TOPICS,
    evidence: EVIDENCE,
    fallback: { kind: 'short_test', reason: 'doubtful_se' },
    next_attempt_at: in48h,
  },
  'demo-promotion': {
    ...base,
    id: 'demo-promotion',
    claimed_grade: 'middle',
    kind: 'promotion',
    theta: 5.1,
    rating: 2020,
    rating_ci: 38,
    percentile: 96,
    result_grade: 'middle',
    decision: 'confirmed',
    promotion_unlocked: true,
    topics: TOPICS,
    evidence: EVIDENCE,
    fallback: null,
    next_attempt_at: in48h,
  },
}

const fixtureHistory = ['demo-promotion', 'demo-unconfirmed', 'demo-confirmed'].map(
  (id) => resultFixtures[id],
)

export const gapHandlers = [
  http.get('*/api/auth/csrf', () => json({ detail: 'ok' })),
  // --- FE-06: result fixtures (gap G5 — core fields exist on the backend,
  // these demo ids add rating_ci/percentile/topics/evidence/fallback and
  // pass real UUIDs through to the live backend) ---
  http.get('*/api/assessments/:id/result', ({ params }) => {
    const fixture = resultFixtures[String(params.id)]
    if (fixture) return json(fixture)
    return passthrough()
  }),
  http.get('*/api/assessments', async ({ request }) => {
    try {
      const res = await fetch(request)
      if (res.ok) {
        const data = (await res.json()) as unknown
        const items = Array.isArray(data) ? data : ((data as { items?: unknown[] })?.items ?? [])
        return json([...fixtureHistory, ...items])
      }
    } catch {
      /* no backend — fall through to fixtures */
    }
    return json(fixtureHistory)
  }),
  http.post('*/api/auth/verify-email', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { token?: string }
    if (!body.token) return problem(400, 'token_invalid', 'Token is required.')
    return json({ detail: 'ok' })
  }),
  http.get('*/api/taxonomy', () =>
    json({
      specs: ['backend', 'frontend', 'ml_data'],
      grades: ['intern', 'junior', 'middle', 'senior'],
      work_formats: ['office', 'hybrid', 'remote'],
      strength_topics: [
        'architecture',
        'performance',
        'testing',
        'security',
        'product_thinking',
        'mentoring',
      ],
      skills: [
        'python', 'django', 'fastapi', 'postgresql', 'redis', 'kafka',
        'typescript', 'react', 'node.js', 'pytorch', 'pandas',
      ],
    }),
  ),
  http.get('*/api/leagues', ({ request }) => {
    const spec = new URL(request.url).searchParams.get('specialization')
    return json({
      items: [
        { specialization: spec ?? 'backend', grade: 'middle', status: 'confirmed', rating: 1842 },
        { specialization: spec ?? 'backend', grade: 'senior', status: 'pending' },
      ],
      total: 2,
      page: 1,
    })
  }),
  http.post('*/api/positions/parse', () =>
    json({ skills: ['python', 'django', 'postgresql'], seniority: 'middle' }),
  ),
  http.post('*/api/assessments/:id/finish', () =>
    problem(503, 'fallback_not_available', 'Finish fallback is not available yet.'),
  ),
  http.get('*/api/lab/report', () =>
    json({ id: 'lab-1', summary: 'Черновик отчёта', scores: {} }),
  ),
]
