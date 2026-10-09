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

/** Schema-complete stand-in for `all` mode (G11 is live on the backend). */
const LAB_REPORT_FIXTURE = {
  generated_at: '2026-10-09T12:00:00Z',
  git_sha: '0000000',
  synthetic_fixture: true,
  assessment: {
    simulees: 2048,
    exact_acc: 0.73,
    adjacent_acc: 0.94,
    qwk: 0.81,
    retest_same_grade: 0.77,
    retest_r: 0.72,
    median_len: 12,
    max_family_exposure: 4,
    collision_rate: 0.03,
    generator_errors: 2,
    confusion: [
      [612, 96, 22, 8],
      [74, 558, 84, 14],
      [31, 88, 419, 32],
      [9, 18, 54, 188],
    ],
    tif: {
      theta: [-3, -2.5, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3],
      info: [2.1, 3.4, 5.2, 7.8, 10.1, 11.4, 11.9, 11.1, 9.4, 7.0, 4.8, 3.1, 2.0],
    },
    leak_attack: [
      { leak_share: 0.02, static_dtheta: 0.4, parametric_dtheta: 0.9 },
      { leak_share: 0.05, static_dtheta: 1.1, parametric_dtheta: 3.2 },
      { leak_share: 0.1, static_dtheta: 2.0, parametric_dtheta: 7.5 },
      { leak_share: 0.25, static_dtheta: 3.9, parametric_dtheta: 12.8 },
    ],
  },
  matching: {
    candidates: 320,
    needs: 12,
    non_fsp_parity: 0.96,
    pool_p95_ms: 180,
    systems: [
      { name: 'exact-phrase', ndcg10: 0.61, p10: 0.3, r50: 0.74, mrr: 0.55 },
      { name: 'parse+expand', ndcg10: 0.72, p10: 0.38, r50: 0.83, mrr: 0.64 },
      { name: 'semantic', ndcg10: 0.81, p10: 0.44, r50: 0.87, mrr: 0.73 },
      { name: 'blended', ndcg10: 0.87, p10: 0.5, r50: 0.9, mrr: 0.79 },
    ],
  },
}

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
  http.get('*/api/lab/report', () => json(LAB_REPORT_FIXTURE)),
]
