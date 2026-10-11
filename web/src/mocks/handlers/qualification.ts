import { http, HttpResponse } from 'msw'
import type {
  AnswerOutcome,
  AssessmentItem,
  AssessmentSession,
  MockAssessmentResult,
} from '@/api/types'
import { completeCandidateQualification } from '@/mocks/handlers/core'

/**
 * FE-05 · Test runner — stateful in-memory CAT session store (`all` mode).
 *
 * Mirrors the MK3 stub contract (docs/TASKS.md): 8 items from the sample
 * families, θ = (correct − 4) / 2, decision against the claimed cut.
 * The backend today serves only 3 items with no adaptivity, so the runner
 * can be built and demoed against these 8 before BE-05 lands.
 *
 * Contract (FE2.md §FE-05):
 * - POST /api/assessments            → 201 session (+ first item served),
 *                                      409 `assessment_in_progress`,
 *                                      429 `cooldown_active`.
 * - GET  /api/assessments/{id}       → session with `current`; refresh resumes.
 * - POST /api/assessments/{id}/answers
 *                                    → {done:false,next} | {done:true,result},
 *                                      409 `item_not_current`,
 *                                      409 `assessment_expired`.
 * - POST /api/assessments/{id}/finish → finalizes early (G5 shipped on the BE).
 *
 * SECURITY: answers carry no per-item correctness; the key never leaves here.
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

/** Same shape as `problem`, but with an extra payload (e.g. active_session_id). */
const problemWith = (
  status: number,
  code: string,
  detail: string,
  extra: Record<string, unknown>,
) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail, ...extra },
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
    },
  )

// --- item bank (sample families: python loop / sql group-by / js event loop) ---

/** Wire shape of a served item (schema ItemView): `format` and
`max_items` are readonly on the schema — the mock keeps them so the
fixtures match the generated contract. */
type BankItem = Omit<AssessmentItem, 'deadline_at' | 'served_at'> & {
  /** item family label from the BE bank (python/sql/javascript) */
  format: string
  /** total items in this session mode; mirrors GET session.max_items */
  max_items: number
}

/** 8 sample items (python/sql/javascript families); keeps BANK free of a TDZ self-reference. */
const BANK_SIZE = 8

const BANK: BankItem[] = [
  {
    item_id: 'q-py-1',
    seq: 1,
    stem_md: 'Что напечатает этот код? **Python, базовый цикл.**',
    code: { lang: 'python', text: 'total = 0\nfor i in range(1, 4):\n    total += i\nprint(total)' },
    options: [
      { id: 'a', text_md: '`3`' },
      { id: 'b', text_md: '`6`' },
      { id: 'c', text_md: '`10`' },
    ],
    input_type: 'choice',
    time_limit_s: 60,
    level: 1,
    format: 'python',
    max_items: BANK_SIZE,
  },
  {
    item_id: 'q-py-2',
    seq: 2,
    stem_md: 'Какой будет результат? **Срез списка.**',
    code: { lang: 'python', text: 'xs = [1, 2, 3, 4, 5]\nprint(xs[1:4])' },
    options: [
      { id: 'a', text_md: '`[1, 2, 3]`' },
      { id: 'b', text_md: '`[2, 3, 4]`' },
      { id: 'c', text_md: '`[2, 3, 4, 5]`' },
    ],
    input_type: 'choice',
    time_limit_s: 60,
    level: 1,
    format: 'python',
    max_items: BANK_SIZE,
  },
  {
    item_id: 'q-sql-1',
    seq: 3,
    stem_md:
      'Сколько строк вернёт запрос? **SQL, group-by.** В таблице `orders` — 3 строки с `user_id` ∈ {1, 1, 2}.',
    code: {
      lang: 'sql',
      text: 'SELECT user_id, COUNT(*)\nFROM orders\nGROUP BY user_id',
    },
    options: null,
    input_type: 'number',
    time_limit_s: 90,
    level: 2,
    format: 'sql',
    max_items: BANK_SIZE,
  },
  {
    item_id: 'q-js-1',
    seq: 4,
    stem_md: 'В каком порядке попадут в консоль `A`/`B`? **JS, event loop.**',
    code: {
      lang: 'javascript',
      text: "console.log('A');\nsetTimeout(() => console.log('B'), 0);",
    },
    options: [
      { id: 'a', text_md: '`A`, затем `B` (macrotask)`' },
      { id: 'b', text_md: '`B`, затем `A`' },
      { id: 'c', text_md: 'Одновременно' },
    ],
    input_type: 'choice',
    time_limit_s: 60,
    level: 2,
    format: 'javascript',
    max_items: BANK_SIZE,
  },
  {
    item_id: 'q-py-3',
    seq: 5,
    stem_md: 'Что выведет `print(len(set([1, 2, 2, 3, 3, 3])))`? **Множества.**',
    code: null,
    options: null,
    input_type: 'number',
    time_limit_s: 45,
    level: 2,
    format: 'python',
    max_items: BANK_SIZE,
  },
  {
    item_id: 'q-sql-2',
    seq: 6,
    stem_md:
      'Какой оператор фильтрует **группы** после `GROUP BY`? **SQL, агрегация.**',
    code: null,
    options: [
      { id: 'a', text_md: '`WHERE`' },
      { id: 'b', text_md: '`HAVING`' },
      { id: 'c', text_md: '`LIMIT`' },
    ],
    input_type: 'choice',
    time_limit_s: 45,
    level: 3,
    format: 'sql',
    max_items: BANK_SIZE,
  },
  {
    item_id: 'q-js-2',
    seq: 7,
    stem_md: 'Кратко опиши, чем `debounce` отличается от `throttle`. **Открытый вопрос.**',
    code: null,
    options: null,
    input_type: 'text',
    time_limit_s: 120,
    level: 3,
    format: 'javascript',
    max_items: BANK_SIZE,
  },
  {
    item_id: 'q-py-4',
    seq: 8,
    stem_md: 'Какое исключение возникнет? **Python, словари.**',
    code: { lang: 'python', text: "d = {'a': 1}\nprint(d['b'])" },
    options: [
      { id: 'a', text_md: '`KeyError`' },
      { id: 'b', text_md: '`IndexError`' },
      { id: 'c', text_md: '`TypeError`' },
    ],
    input_type: 'choice',
    time_limit_s: 60,
    level: 3,
    format: 'python',
    max_items: BANK_SIZE,
  },
]

/** Oracle keys are mock-only (never serialized to the client). */
const KEY: Record<string, string> = {
  'q-py-1': 'b', // 6
  'q-py-2': 'b', // [2, 3, 4]
  'q-sql-1': '2', // two groups
  'q-js-1': 'a',
  'q-py-3': '3',
  'q-sql-2': 'b',
  'q-js-2': '', // open question — graded by length > 0
  'q-py-4': 'a',
}

// --- session store -----------------------------------------------------------

type StoredAnswer = { itemId: string; correct: boolean }

type MockSession = {
  id: string
  specialization: string
  claimed_grade: string
  kind: string
  mode: string
  status: 'in_progress' | 'finished' | 'abandoned' | 'expired'
  startedAt: string
  finishedAt: string | null
  /** index into BANK of the served item; equals max_items once done */
  cursor: number
  servedAt: string | null
  /** ISO deadline of the currently served item, snapshotted at serve time
   *  (null once the session is done). `currentOf` re-derives the item from
   *  BANK + this anchor so a refresh/resume keeps the ORIGINAL deadline. */
  deadlineAt: string | null
  answers: StoredAnswer[]
}

let sessions: MockSession[] = []
let seqCounter = 0
/** QA seam: freeze/override mock time (defaults to the real clock). */
let nowOverride: (() => Date) | null = null
export function setMockNow(fn: (() => Date) | null): void {
  nowOverride = fn
}
/** QA seam: raw stored session (cursor/servedAt/answers) for assertions. */
export function __getMockSession(id: string): MockSession | undefined {
  return sessions.find((x) => x.id === id)
}
const mockNow = () => (nowOverride ? nowOverride() : new Date())

/** Jury-mode helper: wipe in-progress sessions between demos. */
export function resetQualificationMock(): void {
  sessions = []
  seqCounter = 0
  nowOverride = null
}

/** Items served per mode (FE2.md §FE-05: full/express choice on the start
 *  screen). The mock truncates its 8-item bank per mode so the runner can be
 *  exercised in both modes without a full item bank. */
function maxItemsFor(s: MockSession): number {
  return s.mode === 'express' ? Math.ceil(BANK.length / 2) : BANK.length
}

/** BE.md H5: an answer may land up to 3 s past the item deadline and still
 *  count. The stored `deadlineAt` snapshot is already grace-included. */
const GRACE_MS = 3_000

/** Grace-included grading deadline for an item served at `at`. */
function serveDeadlineIso(tpl: BankItem, at: Date): string {
  return new Date(at.getTime() + tpl.time_limit_s * 1000 + GRACE_MS).toISOString()
}

function serveItem(s: MockSession, at: Date): AssessmentItem {
  const tpl = BANK[s.cursor]
  return { ...tpl, deadline_at: new Date(at.getTime() + tpl.time_limit_s * 1000).toISOString(), served_at: at.toISOString() }
}

function currentOf(s: MockSession): AssessmentItem | null {
  if (s.status !== 'in_progress' || s.cursor >= maxItemsFor(s)) return null
  // Served item keeps its ORIGINAL deadline — refresh/resume must not buy
  // extra time; the candidate spends the remaining budget (QA case 2b).
  return serveItem(s, new Date(s.servedAt ?? s.startedAt))
}

function toSessionDto(s: MockSession): AssessmentSession {
  return {
    id: s.id,
    specialization: s.specialization,
    claimed_grade: s.claimed_grade,
    kind: s.kind,
    mode: s.mode,
    status: s.status,
    current: currentOf(s),
    max_items: maxItemsFor(s),
    theta: null,
    se: null,
    rating: null,
    started_at: s.startedAt,
    finished_at: s.finishedAt,
  } as unknown as AssessmentSession
}

function isCorrect(answer: StoredAnswer): boolean {
  return answer.correct
}

/** MK3 scoring: θ = (correct − max/2) / 2; confirmed when θ ≥ 1 for the claim. */
function finalize(s: MockSession, now: Date = mockNow()): MockAssessmentResult {
  s.status = 'finished'
  s.finishedAt = now.toISOString()
  completeCandidateQualification()
  const maxItems = maxItemsFor(s)
  const correct = s.answers.filter(isCorrect).length
  const theta = Math.round(((correct - maxItems / 2) / 2) * 100) / 100
  const rating = 1000 + 200 * theta
  const confirmed = theta >= 1
  const evidence = BANK.slice(0, maxItems).map((item, i) => ({
    seq: item.seq,
    correct: s.answers[i] ? s.answers[i].correct : null,
  }))
  const topics = ['python', 'sql', 'javascript'].map((key) => {
    const own = s.answers.filter((a) => a.itemId.startsWith(`q-${key.slice(0, 2)}-`))
    return {
      key,
      label: key === 'python' ? 'Python' : key === 'sql' ? 'SQL' : 'JavaScript',
      correct: own.filter(isCorrect).length,
      total: own.length,
    }
  })
  return {
    id: s.id,
    specialization: s.specialization,
    claimed_grade: s.claimed_grade,
    kind: s.kind,
    mode: s.mode,
    status: 'finished',
    theta,
    se: 0.4,
    rating: Math.round(rating),
    rating_ci: 40,
    percentile: Math.min(99, Math.max(1, Math.round(50 + theta * 20))),
    result_grade: confirmed ? s.claimed_grade : 'junior',
    decision: confirmed ? 'confirmed' : 'unconfirmed',
    promotion_unlocked: false,
    counts_as_attempt: true,
    started_at: s.startedAt,
    finished_at: s.finishedAt,
    topics,
    evidence,
    fallback: null,
    next_attempt_at: new Date(now.getTime() + 48 * 60 * 60 * 1000).toISOString(),
  } as unknown as MockAssessmentResult
}

function gradeAnswer(item: AssessmentItem, optionId?: string, value?: string): boolean {
  if (item.input_type === 'choice') return optionId === KEY[item.item_id]
  if (item.input_type === 'number') return String(value ?? '').trim() === KEY[item.item_id]
  return String(value ?? '').trim().length > 0 // open question
}

/** Index into BANK of the item the candidate is currently answering: while a
 *  session is in progress `cursor` points at the served item; once the last
 *  answer lands (`cursor === maxItems`) the session is finalized, so clamp to
 *  the bank length defensively. */
function currentItemIndex(s: MockSession): number {
  return Math.min(s.cursor, BANK.length - 1)
}

/** Deadline of the currently served item, anchored at serve time. The stored
 *  snapshot is `deadline_at` + the 3 s grace (BE.md H5) so late grading is a
 *  single comparison; falls back to served_at + the current item's budget +
 *  grace when no snapshot was stored. */
function currentDeadlineMs(s: MockSession): number | null {
  if (s.deadlineAt) return new Date(s.deadlineAt).getTime()
  if (!s.servedAt) return null
  return new Date(s.servedAt).getTime() + BANK[currentItemIndex(s)].time_limit_s * 1000 + GRACE_MS
}

/** Late answer past deadline + 3 s grace counts as incorrect (BE.md H5).
 *  Graded against the deadline snapshotted when the current item was served —
 *  never recomputed from a bank entry the cursor may no longer point at.
 *  Exported only so the QA suite can pin session timestamps and prove the
 *  lateness rule without sleeping in tests. */
export function isLate(s: MockSession, at: Date = mockNow()): boolean {
  const deadline = currentDeadlineMs(s)
  if (deadline === null) return false
  // The +3 s grace is baked into `deadline` (see serveItem), so a request
  // landing within it is still on time; strictly after → late.
  return at.getTime() > deadline
}

function activeInProgress(): MockSession | undefined {
  return sessions.find((s) => s.status === 'in_progress')
}

// --- handlers ----------------------------------------------------------------

/** Cooldown after a counted attempt: 48 h (FE2.md §FE-05). */
const COOLDOWN_MS = 48 * 60 * 60 * 1000

export const qualificationHandlers = [
  /**
   * GET /api/assessments/eligibility?specialization= — stateful, drives the
   * FE-05 start screen: cooldown countdown + resume button. Registered BEFORE
   * the static fixture handler in assessments.ts (browser.ts puts this list
   * first), because MSW is first-match-wins and the wildcard session route
   * also matches `/api/assessments/eligibility` — without this ordering the
   * live eligibility would be dead code shadowed by a fixed `can_start:true`.
   */
  http.get('*/api/assessments/eligibility', () => {
    const active = activeInProgress()
    if (active) {
      return json({
        can_start: false,
        reason: 'session_in_progress',
        active_session_id: active.id,
        promotion_available: false,
        next_attempt_at: null,
      })
    }
    const lastCounted = [...sessions]
      .reverse()
      .find((s) => s.status === 'finished' && s.finishedAt)
    if (lastCounted?.finishedAt) {
      const until = new Date(new Date(lastCounted.finishedAt).getTime() + COOLDOWN_MS)
      if (until.getTime() > mockNow().getTime()) {
        return json({
          can_start: false,
          reason: 'cooldown_active',
          active_session_id: null,
          promotion_available: false,
          next_attempt_at: until.toISOString(),
        })
      }
    }
    return json({
      can_start: true,
      active_session_id: null,
      promotion_available: false,
      next_attempt_at: null,
    })
  }),

  http.post('*/api/assessments', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      specialization?: string
      claimed_grade?: string
      mode?: string
      kind?: string
    }
    const active = activeInProgress()
    if (active) {
      return problemWith(409, 'assessment_in_progress', 'A test session is already running.', {
        active_session_id: active.id,
      })
    }
    const now = mockNow()
    const s: MockSession = {
      id: `mock-as-${++seqCounter}`,
      specialization: body.specialization ?? 'backend',
      claimed_grade: body.claimed_grade ?? 'middle',
      kind: body.kind === 'promotion' ? 'promotion' : 'initial',
      mode: body.mode ?? 'full',
      status: 'in_progress',
      startedAt: now.toISOString(),
      finishedAt: null,
      cursor: 0,
      servedAt: now.toISOString(),
      deadlineAt: serveDeadlineIso(BANK[0], now),
      answers: [],
    }
    sessions.push(s)
    return json(toSessionDto(s), 201)
  }),

  http.get('*/api/assessments/:id', ({ params }) => {
    const s = sessions.find((x) => x.id === String(params.id))
    if (!s) return problem(404, 'not_found', 'Assessment session not found.')
    return json(toSessionDto(s))
  }),

  http.post('*/api/assessments/:id/answers', async ({ params, request }) => {
    const s = sessions.find((x) => x.id === String(params.id))
    if (!s) return problem(404, 'not_found', 'Assessment session not found.')
    if (s.status === 'finished') {
      return problem(409, 'invalid_transition', 'This assessment is already finished.')
    }
    if (s.status === 'expired') {
      return problem(409, 'assessment_expired', 'The assessment has expired.')
    }
    const body = (await request.json().catch(() => ({}))) as {
      item_id?: string
      option_id?: string
      value?: string
      integrity?: unknown
    }
    const current = BANK[currentItemIndex(s)]
    if (!body.item_id || body.item_id !== current.item_id) {
      return problem(409, 'item_not_current', 'Answered item is not the current one.')
    }

    const now = mockNow()
    const late = isLate(s, now)
    const correct = !late && gradeAnswer(current as AssessmentItem, body.option_id, body.value)
    s.answers.push({ itemId: current.item_id, correct })
    s.cursor += 1

    if (s.cursor >= maxItemsFor(s)) {
      // Done — no live item anymore; clear the serve anchors so nothing can
      // be graded as "late" against a stale cursor position.
      s.servedAt = null
      s.deadlineAt = null
      const result = finalize(s, now)
      const outcome: AnswerOutcome = { done: true, result }
      return json(outcome)
    }
    s.servedAt = now.toISOString()
    s.deadlineAt = serveDeadlineIso(BANK[s.cursor], now)
    const outcome: AnswerOutcome = { done: false, next: currentOf(s)! }
    return json(outcome)
  }),

  /** Early finish (G5 shipped on the BE). The stateful mock lets the
   *  runner's "Завершить досрочно" flow be tested end-to-end offline. */
  http.post('*/api/assessments/:id/finish', ({ params }) => {
    const s = sessions.find((x) => x.id === String(params.id))
    if (!s) return problem(404, 'not_found', 'Assessment session not found.')
    if (s.status !== 'in_progress') {
      return problem(409, 'invalid_transition', 'Only an in-progress session can be finished.')
    }
    // BE.md R9: <50% of the mode's items answered → abandoned. The check
    // runs BEFORE padding, otherwise the padded tail always passes it
    // (QA case 4b).
    const maxItems = maxItemsFor(s)
    if (s.cursor * 2 < maxItems) {
      s.status = 'abandoned'
      s.finishedAt = mockNow().toISOString()
      return problem(409, 'not_enough_answers', 'Less than half of the items were answered.')
    }
    // Current item was never submitted — record it as unanswered/incorrect
    // before padding the rest of the tail (keeps `answers` aligned with BANK).
    if (s.answers.length < s.cursor) {
      s.answers.push({ itemId: BANK[s.answers.length].item_id, correct: false })
    }
    // Unanswered tail counts as incorrect.
    while (s.answers.length < maxItems) {
      s.answers.push({ itemId: BANK[s.answers.length].item_id, correct: false })
    }
    const result = finalize(s)
    return json(result)
  }),
]
