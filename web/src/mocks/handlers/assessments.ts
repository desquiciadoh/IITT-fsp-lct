import { http, HttpResponse } from 'msw'
import type { MockAssessmentResult } from '@/api/types'

/**
 * `all` mode (no backend): result fixtures, history, eligibility and the
 * Player Card PDF. Real endpoints are never mocked in `missing` mode —
 * fixtures must not mix into live data (R4).
 *
 * Fixtures are typed as MockAssessmentResult: `percentile` is legal only on
 * MSW payloads (not in the OpenAPI schema — G5 residual), so the cast stays
 * inside this file instead of leaking into the DTO layer.
 */

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const json = (data: unknown) => stub(data)
const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail },
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
    },
  )

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
  claimed_grade: 'middle',
  kind: 'initial',
  mode: 'full',
  status: 'finished',
  theta: 0,
  se: 0.18,
  rating: null,
  rating_ci: 0,
  result_grade: 'middle',
  decision: 'confirmed',
  promotion_unlocked: false,
  counts_as_attempt: true,
  started_at: started,
  finished_at: finished,
  topics: TOPICS,
  evidence: EVIDENCE,
  fallback: null,
  next_attempt_at: null,
} satisfies Omit<MockAssessmentResult, 'id'>

const resultFixtures: Record<string, MockAssessmentResult> = {
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
    fallback: { mode: 'short_test', grade: 'middle', reason: 'doubtful_se' },
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

const MINIMAL_PDF = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 300 140] /Contents 4 0 R >> endobj
4 0 obj << /Length 78 >> stream
BT /F1 18 Tf 20 90 Td (FSP Draft - Player Card) Tj ET
endstream endobj
trailer << /Root 1 0 R >>
%%EOF`

export const assessmentHandlers = [
  http.get('*/api/assessments', () => json(fixtureHistory)),
  http.get('*/api/assessments/eligibility', () =>
    json({ can_start: true, active_session_id: null, promotion_available: false }),
  ),
  http.get('*/api/assessments/:id/result', ({ params }) => {
    const fixture = resultFixtures[String(params.id)]
    if (fixture) return json(fixture)
    return problem(404, 'not_found', 'Result not found.')
  }),
  http.get('*/api/candidates/me/card.pdf', () =>
    new HttpResponse(MINIMAL_PDF, {
      status: 200,
      headers: { 'Content-Type': 'application/pdf', 'X-Stub': 'true' },
    }),
  ),
]
