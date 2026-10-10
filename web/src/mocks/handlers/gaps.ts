import { http, HttpResponse } from 'msw'

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const json = (data: unknown) => stub(data)
const problem = (status: number, code: string, detail: string, errors?: unknown) =>
  HttpResponse.json({ type: 'about:blank', title: code, status, code, detail, errors }, {
    status,
    headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
  })

/** G5 — `POST /api/assessments/:id/finish` is not on the backend yet (503).
 *  In `all` mode the stateful store in qualification.ts serves it; MSW picks
 *  the FIRST matching handler, so gapHandlers must stay first in that list
 *  only for endpoints without a real mock. For finish we want the stateful
 *  one to win, hence it is registered via qualificationHandlers below and
 *  this fallback stays scoped to `missing` mode. */
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
  /**
   * gap G7 — scouting league shelves. Real backend serves the candidate's own
   * league; FE-10 needs per-grade counts (FE2.md §FE-10):
   * `[{specialization, grade, confirmed, unconfirmed, median_expectation?}]`.
   */
  http.get('*/api/leagues', ({ request }) => {
    const spec = new URL(request.url).searchParams.get('specialization') ?? 'backend'
    return json({
      items: [
        { specialization: spec, grade: 'intern', confirmed: 3, unconfirmed: 9, median_expectation: 100000 },
        { specialization: spec, grade: 'junior', confirmed: 14, unconfirmed: 21, median_expectation: 150000 },
        { specialization: spec, grade: 'middle', confirmed: 27, unconfirmed: 18, median_expectation: 250000 },
        { specialization: spec, grade: 'senior', confirmed: 12, unconfirmed: 7, median_expectation: 360000 },
      ],
      total: 4,
      page: 1,
    })
  }),
  // G6: JD parse shape ({draft, unknown_terms, blueprint}) is served by the
  // stateful employerHandlers (employer.ts); this static stub stays only as a
  // last-resort fallback for environments without the FE-09 mock.
  http.post('*/api/positions/parse', () =>
    json({ draft: {}, unknown_terms: [], blueprint: [], source: 'mock' }),
  ),
  http.post('*/api/assessments/:id/finish', () =>
    problem(503, 'fallback_not_available', 'Finish fallback is not available yet.'),
  ),
  http.get('*/api/lab/report', () =>
    json({ id: 'lab-1', summary: 'Черновик отчёта', scores: {} }),
  ),
]
