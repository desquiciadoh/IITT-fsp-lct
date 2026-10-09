import { http, HttpResponse } from 'msw'

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const json = (data: unknown) => stub(data)
const problem = (status: number, code: string, detail: string, errors?: unknown) =>
  HttpResponse.json({ type: 'about:blank', title: code, status, code, detail, errors }, {
    status,
    headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
  })

/** Registry stand-in for `all` mode (G17 is live on the backend). */
const ALL_COMPANIES = [
  { id: '00000000-0000-4000-8000-000000000001', name: 'Yandex Tech' },
  { id: '00000000-0000-4000-8000-000000000002', name: 'Ozon' },
  { id: '00000000-0000-4000-8000-000000000003', name: 'Avito' },
  { id: '00000000-0000-4000-8000-000000000004', name: 'Tinkoff' },
  { id: '00000000-0000-4000-8000-000000000005', name: 'Acme Systems' },
  { id: '00000000-0000-4000-8000-000000000006', name: 'DataForge' },
]

/**
 * `all`-mode stand-ins for endpoints that are **live on the backend** now
 * (G1 csrf, G2 verify-email, G3 taxonomy, G6 positions/parse, G7 leagues,
 * G11 lab/report, G14 finish). They exist only so `all` mode runs without a
 * backend and must never be used in `missing` mode (R24) — there they would
 * shadow the real responses with `X-Stub`.
 */
export const gapHandlers = [
  http.get('*/api/auth/csrf', () => json({ detail: 'ok' })),
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
  http.get('*/api/companies', ({ request }) => {
    const search = new URL(request.url).searchParams.get('search')?.trim().toLowerCase() ?? ''
    return json(ALL_COMPANIES.filter((c) => c.name.toLowerCase().includes(search)))
  }),
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
  http.get('*/api/lab/report', () =>
    json({ id: 'lab-1', summary: 'Черновик отчёта', scores: {} }),
  ),
]
