/**
 * FE-05 · Stage 4 — end-to-end QA of the stateful qualification mock.
 *
 * Drives the real MSW handlers (the same objects registered in browser.ts
 * `all` mode) over HTTP via msw/node, i.e. exactly the wire behavior the
 * runner UI relies on. Covers the manual QA checklist:
 *   1. full pass of all 8 items → {done:true,result} + cooldown eligibility;
 *   2. refresh mid-test → GET resumes at the right item with the ORIGINAL
 *      deadline (a reload must not buy extra time);
 *   3. late answer past deadline+3s grace → graded incorrect (BE.md H5);
 *   4. early finish ≥50% → result; <50% → 409 not_enough_answers + abandoned;
 *   5. integrity payload accepted and never echoed back to the client;
 *   6. edge cases: item_not_current, double start (409), re-finish (409).
 */
import { afterEach, beforeAll, afterAll, beforeEach, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import type { AssessmentResult } from '@/api/types'
import {
  qualificationHandlers,
  resetQualificationMock,
  setMockNow,
  isLate,
  __getMockSession,
} from './qualification'

const BASE = 'http://localhost'
const server = setupServer(...qualificationHandlers)

async function req<T = unknown>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  return { status: res.status, body: (await res.json()) as T }
}

const post = (path: string, body: unknown) =>
  req(path, { method: 'POST', body: JSON.stringify(body) })

/** Loose wire shapes for the mock-only QA suite (the DTOs above are stricter). */
type ServedItem = { item_id: string; seq: number; input_type: string; deadline_at: string }
type SessionBody = { id: string; status: string; current: ServedItem; max_items: number }
type EligibilityBody = {
  can_start: boolean
  reason?: string
  active_session_id?: string | null
  next_attempt_at?: string | null
}
type ProblemBody = { code: string; detail?: string; active_session_id?: string }
type AnswerOutcomeBody = {
  done: boolean
  next?: ServedItem
  result?: AssessmentResult
}
type FinishBody = {
  status: string
  theta: number
  counts_as_attempt: boolean
  evidence: { correct: boolean | null }[]
}

// Mirrors the mock-only key (q-js-2 is an open question → any non-empty text).
const KEY = ['b', 'b', '2', 'a', '3', 'b', null, 'a'] as const
const INTEGRITY = { focus_loss: 1, paste: 2 }

async function startSession(): Promise<string> {
  const r = await post('/api/assessments', {
    specialization: 'backend',
    claimed_grade: 'middle',
    mode: 'full',
  }) as { status: number; body: SessionBody }
  expect(r.status).toBe(201)
  return r.body.id
}

describe('qualification mock — FE-05 e2e QA', () => {
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
  afterEach(() => server.restoreHandlers())
  afterAll(() => server.close())

  // Fresh store per test.
  beforeEach(() => resetQualificationMock())

  it('1) full pass of all 8 items with correct answers → confirmed result + cooldown', async () => {
    const id = await startSession()

    let cur = ((await req(`/api/assessments/${id}`)) as { body: SessionBody }).body.current
    expect(cur.seq).toBe(1)
    expect(cur.item_id).toBe('q-py-1')

    const seen: string[] = []
    let outcome: { status: number; body: AnswerOutcomeBody } | null = null
    for (let i = 0; i < 8; i++) {
      seen.push(cur.item_id)
      const k = KEY[i]
      const ansBody =
        k === null
          ? { item_id: cur.item_id, value: 'debounce ждёт паузу, throttle ограничивает частоту', integrity: INTEGRITY }
          : cur.input_type === 'choice'
            ? { item_id: cur.item_id, option_id: k, integrity: INTEGRITY }
            : { item_id: cur.item_id, value: String(k), integrity: INTEGRITY }
      outcome = (await post(`/api/assessments/${id}/answers`, ansBody)) as {
        status: number
        body: AnswerOutcomeBody
      }
      expect(outcome.status).toBe(200)
      if (i < 7) {
        expect(outcome.body.done).toBe(false)
        cur = outcome.body.next!
        expect(cur.seq).toBe(i + 2)
      }
    }
    expect(seen).toHaveLength(8)
    expect(new Set(seen).size).toBe(8) // all distinct bank items served in order

    expect(outcome!.body.done).toBe(true)
    const result = outcome!.body.result!
    expect(result.status).toBe('finished')
    expect(result.theta).toBe(2) // 8/8 correct → (8−4)/2
    expect(result.rating).toBe(1400)
    expect(result.decision).toBe('confirmed')
    expect(result.evidence?.every((e) => e.correct)).toBe(true)

    // Eligibility now reports the graded cooldown (FE-05 start screen §2).
    const el = (await req('/api/assessments/eligibility?specialization=backend')) as {
      body: EligibilityBody
    }
    expect(el.body.can_start).toBe(false)
    expect(el.body.reason).toBe('cooldown_active')
    expect(el.body.next_attempt_at).toBeTruthy()
  })

  it('2) refresh mid-test resumes at the served item with the ORIGINAL deadline', async () => {
    const id = await startSession()
    const first = ((await req(`/api/assessments/${id}`)) as { body: SessionBody }).body.current
    await post(`/api/assessments/${id}/answers`, { item_id: first.item_id, option_id: 'b', integrity: INTEGRITY })

    const stored2 = __getMockSession(id)!
    // Simulated page reload: fresh GET only.
    const resumed = (await req(`/api/assessments/${id}`)) as {
      status: number
      body: SessionBody
    }
    expect(resumed.status).toBe(200)
    expect(resumed.body.current.item_id).toBe('q-py-2')
    expect(resumed.body.current.seq).toBe(2)
    expect(resumed.body.status).toBe('in_progress')
    expect(resumed.body.max_items).toBe(8)
    // Reload must NOT reset the timer: deadline anchored to the original serve.
    expect(resumed.body.current.deadline_at).toBe(new Date(Date.parse(stored2.servedAt!) + 60_000).toISOString())

    // Double start while in progress → 409 with the active session id.
    const dup = (await post('/api/assessments', { specialization: 'backend' })) as {
      status: number
      body: ProblemBody
    }
    expect(dup.status).toBe(409)
    expect(dup.body.code).toBe('assessment_in_progress')
    expect(dup.body.active_session_id).toBe(id)

    // Eligibility exposes resume instead of cooldown/form.
    const el = (await req('/api/assessments/eligibility?specialization=backend')) as {
      body: EligibilityBody
    }
    expect(el.body.active_session_id).toBe(id)
    expect(el.body.reason).toBe('session_in_progress')
  })

  it('3) auto-submit arriving past deadline+3s grace is graded incorrect (BE.md H5)', async () => {
    const id = await startSession()
    const s = __getMockSession(id)!
    // Jump the mock clock 64 s ahead of q-py-1's 60 s window — strictly past
    // the +3 s grace (BE.md H5: ≤63 s still counts, >63 s is late).
    setMockNow(() => new Date(Date.parse(s.servedAt!) + 64_000))
    // `isLate` defaults to the (shifted) mock clock — no real-clock leak.
    expect(isLate(s)).toBe(true)

    // The candidate's tab was frozen; the expired draft (empty choice) lands late.
    const r = (await post(`/api/assessments/${id}/answers`, {
      item_id: 'q-py-1',
      option_id: '', // empty auto-submit counts as incorrect too
      integrity: INTEGRITY,
    })) as { status: number; body: AnswerOutcomeBody }
    expect(r.status).toBe(200)
    expect(r.body.done).toBe(false)
    const stored = __getMockSession(id)!
    expect(stored.answers[0]).toEqual({ itemId: 'q-py-1', correct: false })
    expect(stored.cursor).toBe(1)
  })

  it('3b) lateness is judged by the CURRENTLY served item, not a stale bank entry', async () => {
    // Regression: after answering q-py-1 (60 s), the served item is q-py-2
    // (also 60 s) — but q-sql-1 (90 s) used to be read from BANK[cursor] and
    // gave the candidate phantom time. Pin the deadline snapshot instead.
    const id = await startSession()
    await post(`/api/assessments/${id}/answers`, { item_id: 'q-py-1', option_id: 'b' })
    const s = __getMockSession(id)!
    // 64 s after q-py-2 was served → strictly past its own 60 s deadline
    // plus the 3 s grace.
    setMockNow(() => new Date(Date.parse(s.servedAt!) + 64_000))
    expect(isLate(s)).toBe(true)
    // Inside the grace window (deadline+3 s inclusive) it is not late yet;
    // phantom time from the 90 s q-sql-1 bank entry would also pass here —
    // that is exactly what the snapshot prevents at 64 s above.
    setMockNow(() => new Date(Date.parse(s.servedAt!) + 63_000))
    expect(isLate(s)).toBe(false)
  })

  it('4a) early finish with ≥50% answered → finalizes; tail padded as incorrect', async () => {
    const id = await startSession()
    // Answer items 1–4 correctly, then click "Завершить досрочно" on item 5.
    for (const [i, itemId] of (['q-py-1', 'q-py-2', 'q-sql-1', 'q-js-1'] as const).entries()) {
      const k = KEY[i]
      await post(
        `/api/assessments/${id}/answers`,
        typeof k === 'string' && itemId !== 'q-sql-1'
          ? { item_id: itemId, option_id: k }
          : { item_id: itemId, value: '2' },
      )
    }
    const fin = (await post(`/api/assessments/${id}/finish`, {})) as {
      status: number
      body: FinishBody
    }
    expect(fin.status).toBe(200)
    expect(fin.body.status).toBe('finished')
    expect(fin.body.counts_as_attempt).toBe(true)
    // 4 correct out of 8 → θ = 0; evidence aligned: first 4 true, rest false.
    expect(fin.body.theta).toBe(0)
    expect(fin.body.evidence.map((e) => e.correct)).toEqual([
      true, true, true, true, false, false, false, false,
    ])

    // Second finish → invalid_transition (already finished).
    const again = (await post(`/api/assessments/${id}/finish`, {})) as {
      status: number
      body: ProblemBody
    }
    expect(again.status).toBe(409)
    expect(again.body.code).toBe('invalid_transition')

    // Answers on a finished session are rejected too.
    const lateAns = (await post(`/api/assessments/${id}/answers`, {
      item_id: 'q-py-5',
      value: '3',
    })) as { status: number; body: ProblemBody }
    expect(lateAns.status).toBe(409)
    expect(lateAns.body.code).toBe('invalid_transition')
  })

  it('4b) early finish with <50% answered → 409 not_enough_answers, attempt abandoned', async () => {
    const id = await startSession()
    await post(`/api/assessments/${id}/answers`, { item_id: 'q-py-1', option_id: 'b' })
    const fin = (await post(`/api/assessments/${id}/finish`, {})) as {
      status: number
      body: ProblemBody
    }
    expect(fin.status).toBe(409)
    expect(fin.body.code).toBe('not_enough_answers')

    // Abandoned attempts do NOT trigger the graded cooldown; new start allowed.
    const el = (await req('/api/assessments/eligibility?specialization=frontend')) as {
      body: EligibilityBody
    }
    expect(el.body.can_start).toBe(true)
  })

  it('5) integrity rides along with the answer and is never echoed back', async () => {
    const id = await startSession()
    const r = await post(`/api/assessments/${id}/answers`, {
      item_id: 'q-py-1',
      option_id: 'b',
      integrity: { focus_loss: 3, paste: 1 },
    })
    expect(r.status).toBe(200)
    expect(JSON.stringify(r.body)).not.toContain('focus_loss')
    expect(JSON.stringify(r.body)).not.toContain('paste')
  })

  it('6) stale item answer → 409 item_not_current (multi-tab guard)', async () => {
    const id = await startSession()
    const stale = (await post(`/api/assessments/${id}/answers`, {
      item_id: 'q-py-2', // current is q-py-1
      option_id: 'b',
    })) as { status: number; body: ProblemBody }
    expect(stale.status).toBe(409)
    expect(stale.body.code).toBe('item_not_current')
  })

  it('7) unknown session → 404 not_found (runner shows the dead-session state)', async () => {
    const missing = (await req('/api/assessments/nope-42')) as { status: number; body: ProblemBody }
    expect(missing.status).toBe(404)
    expect(missing.body.code).toBe('not_found')
    const fin = (await post('/api/assessments/nope-42/finish', {})) as { status: number }
    expect(fin.status).toBe(404)
  })
})
