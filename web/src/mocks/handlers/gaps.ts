import { http, HttpResponse } from 'msw'

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const json = (data: unknown) => stub(data)
const problem = (status: number, code: string, detail: string, errors?: unknown) =>
  HttpResponse.json({ type: 'about:blank', title: code, status, code, detail, errors }, {
    status,
    headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
  })

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
