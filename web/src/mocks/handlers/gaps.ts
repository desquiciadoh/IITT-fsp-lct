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
  // G3 (closed) — the wire taxonomy is object-based ({id, name, ...});
  // useTaxonomy().select normalizes it to the flat view type.
  http.get('*/api/taxonomy', () =>
    json({
      specializations: [
        { id: 'backend', name: 'Backend', topics: ['python', 'sql', 'system_design'] },
        { id: 'frontend', name: 'Frontend', topics: ['javascript', 'react'] },
        { id: 'ml_data', name: 'ML/Data', topics: ['python', 'statistics'] },
      ],
      grades: [
        { id: 'intern', name: 'Intern', descriptor: 'Learning the fundamentals', rating_cut: 0 },
        { id: 'junior', name: 'Junior', descriptor: 'Solves tasks under supervision', rating_cut: 800 },
        { id: 'middle', name: 'Middle', descriptor: 'Delivers independently', rating_cut: 1400 },
        { id: 'senior', name: 'Senior', descriptor: 'Owns architecture and mentoring', rating_cut: 1900 },
      ],
      skills: [
        { id: 'python', name: 'Python', aliases: ['py'], topic: 'python' },
        { id: 'django', name: 'Django', aliases: [], topic: 'python' },
        { id: 'fastapi', name: 'FastAPI', aliases: [], topic: 'python' },
        { id: 'postgresql', name: 'PostgreSQL', aliases: ['postgres'], topic: 'sql' },
        { id: 'redis', name: 'Redis', aliases: [], topic: 'system_design' },
        { id: 'kafka', name: 'Kafka', aliases: [], topic: 'system_design' },
        { id: 'typescript', name: 'TypeScript', aliases: ['ts'], topic: 'javascript' },
        { id: 'react', name: 'React', aliases: [], topic: 'react' },
        { id: 'nodejs', name: 'Node.js', aliases: ['node'], topic: 'javascript' },
        { id: 'pytorch', name: 'PyTorch', aliases: [], topic: 'ml' },
        { id: 'pandas', name: 'Pandas', aliases: [], topic: 'ml' },
      ],
      decline_reasons: [
        { id: 'no_time', name: 'Нет времени' },
        { id: 'salary', name: 'Не подошла зарплата' },
        { id: 'other', name: 'Другое' },
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
  // POST /api/positions/parse (gap G6) is served by the stateful FE-09 mock
  // in employer.ts — do not shadow it with a static stub here.
  http.post('*/api/assessments/:id/finish', () =>
    problem(503, 'fallback_not_available', 'Finish fallback is not available yet.'),
  ),
  http.get('*/api/lab/report', () =>
    json({ id: 'lab-1', summary: 'Черновик отчёта', scores: {} }),
  ),
]
