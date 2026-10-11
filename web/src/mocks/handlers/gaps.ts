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
  // gap G11 — real shape mirrors validation/out/report.fixture.json; the page
  // shows a "фикстура" badge while synthetic_fixture is true.
  // gap BE-22 — two parallel forms per topic slot, candidate view only (no keys).
  http.get('*/api/lab/twins', ({ request }) => {
    const params = new URL(request.url).searchParams
    const specialization = params.get('specialization') ?? 'backend'
    const grade = params.get('grade') ?? 'middle'
    const positionId = params.get('position_id')
    const choice = (a: string, b: string, c: string, d: string) => [
      { id: 'o1a2b3c4', text_md: a },
      { id: 'o5d6e7f8', text_md: b },
      { id: 'o9a0b1c2', text_md: c },
      { id: 'o3d4e5f6', text_md: d },
    ]
    const twin = (
      family_id: string,
      topic: string,
      b: number,
      stem_a: string,
      stem_b: string,
      code: { lang: string; text: string } | null,
    ) => ({
      family_id,
      topic,
      level: 'middle',
      b,
      time_limit_s: 90,
      instance_a: { stem_md: stem_a, input: 'choice', code, options: choice('Вариант 1', 'Вариант 2', 'Вариант 3', 'Вариант 4') },
      instance_b: { stem_md: stem_b, input: 'choice', code, options: choice('Ответ A', 'Ответ B', 'Ответ C', 'Ответ D') },
    })
    const response: Record<string, unknown> = {
      specialization,
      grade,
      twins: [
        twin(
          'be.sql.group_having.v2',
          'sql',
          -0.4,
          'Что вернёт запрос: `SELECT count(*) FROM t GROUP BY k HAVING count(*) > 1`?',
          'Чему равно число групп, у которых больше одной строки в `GROUP BY k`?',
          { lang: 'sql', text: 'SELECT count(*)\nFROM t\nGROUP BY k\nHAVING count(*) > 1;' },
        ),
        twin(
          'be.py.dict_get.v1',
          'python',
          0.6,
          'Что напечатает `print({1: "a", 2: "b"}.get(3))`?',
          'Что вернёт `dict.get` для отсутствующего ключа без значения по умолчанию?',
          { lang: 'python', text: 'print({1: "a", 2: "b"}.get(3))' },
        ),
      ],
    }
    if (positionId) {
      response.position_id = positionId
      response.position_title = 'Backend-разработчик'
    }
    return json(response)
  }),
  http.get('*/api/lab/report', () =>
    json({
      generated_at: '2026-10-10T00:00:00+00:00',
      git_sha: 'fixture',
      synthetic_fixture: true,
      assessment: {
        simulees: 0,
        exact_acc: 0.5,
        adjacent_acc: 0.9,
        qwk: 0.5,
        retest_same_grade: 0.5,
        retest_r: 0.5,
        median_len: 14,
        max_family_exposure: 0.5,
        collision_rate: 0.0,
        generator_errors: 0,
        confusion: [
          [25, 0, 0, 0],
          [0, 25, 0, 0],
          [0, 0, 25, 0],
          [0, 0, 0, 25],
        ],
        tif: { theta: [-2.0, -1.0, 0.0, 1.0, 2.0], info: [1.0, 2.0, 3.0, 2.0, 1.0] },
        leak_attack: [
          { leak_share: 0.1, static_dtheta: 0.0, parametric_dtheta: 0.0 },
          { leak_share: 0.3, static_dtheta: 0.0, parametric_dtheta: 0.0 },
          { leak_share: 0.5, static_dtheta: 0.0, parametric_dtheta: 0.0 },
        ],
      },
      matching: {
        candidates: 0,
        needs: 0,
        non_fsp_parity: 1.0,
        pool_p95_ms: 0.0,
        systems: [
          { name: 'keyword', ndcg10: 0.5, p10: 0.5, r50: 0.5, mrr: 0.5 },
          { name: 'bm25', ndcg10: 0.5, p10: 0.5, r50: 0.5, mrr: 0.5 },
          { name: 'embeddings_only', ndcg10: 0.5, p10: 0.5, r50: 0.5, mrr: 0.5 },
          { name: 'ours_no_verified', ndcg10: 0.5, p10: 0.5, r50: 0.5, mrr: 0.5 },
          { name: 'ours', ndcg10: 0.5, p10: 0.5, r50: 0.5, mrr: 0.5 },
        ],
      },
    }),
  ),
]
