import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  AnswerInput,
  AnswerOutcome,
  AssessmentResult,
  AssessmentSession,
  Eligibility,
  StartAssessmentInput,
} from '@/api/types'

export function useResult(id: string) {
  return useQuery({
    queryKey: keys.result(id),
    queryFn: () => customFetch<AssessmentResult>(`/api/assessments/${id}/result`),
    enabled: Boolean(id),
  })
}

/** GET /api/assessments returns an array today; also accept {items} (gap G14). */
export function useHistory() {
  return useQuery({
    queryKey: keys.assessments,
    queryFn: async () => {
      const data = await customFetch<AssessmentResult[] | { items: AssessmentResult[] }>(
        '/api/assessments',
      )
      if (Array.isArray(data)) return data
      return data.items ?? []
    },
  })
}

export function useEligibility(specialization?: string) {
  return useQuery({
    queryKey: keys.eligibility(specialization ?? ''),
    queryFn: () =>
      customFetch<Eligibility>(
        `/api/assessments/eligibility?specialization=${encodeURIComponent(specialization ?? '')}`,
      ),
    retry: false,
    enabled: Boolean(specialization),
  })
}

// --- FE-05 · Test runner ----------------------------------------------------

/**
 * POST /api/assessments {specialization, claimed_grade, mode} → 201 session.
 * Errors: 429 `cooldown_active`, 409 `assessment_in_progress` (FE2.md).
 */
export function createAssessment(input: StartAssessmentInput): Promise<AssessmentSession> {
  return customFetch<AssessmentSession>('/api/assessments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function useCreateAssessment() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: createAssessment,
    onSuccess: (session) => {
      // Prime the runner cache so GET does not refetch right after start.
      client.setQueryData(keys.session(session.id), session)
      void client.invalidateQueries({ queryKey: keys.assessments })
    },
  })
}

/**
 * GET /api/assessments/{id} → session with the served `current` item.
 * A refresh mid-test resumes through this query; during a run the cache is
 * kept fresh by `usePostAnswer`, so polling stays off unless SSE is down.
 */
export function useSession(id: string, enabled = true) {
  return useQuery({
    queryKey: keys.session(id),
    queryFn: () => customFetch<AssessmentSession>(`/api/assessments/${id}`),
    enabled: Boolean(id) && enabled,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })
}

/**
 * POST /api/assessments/{id}/answers {item_id, option_id?, value?, integrity}.
 * `{done:false,next}` updates the session cache in place; `{done:true,result}`
 * primes the result cache and invalidates history/eligibility.
 * Errors: 409 `item_not_current` (caller refetches the session),
 * `assessment_expired` (caller shows the expired state).
 */
export function postAnswer(id: string, input: AnswerInput): Promise<AnswerOutcome> {
  return customFetch<AnswerOutcome>(`/api/assessments/${id}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function usePostAnswer(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: AnswerInput) => postAnswer(id, input),
    onSuccess: (outcome) => {
      if (outcome.done && outcome.result) {
        client.setQueryData(keys.result(outcome.result.id), outcome.result)
        void client.invalidateQueries({ queryKey: keys.assessments })
        void client.invalidateQueries({ queryKey: ['eligibility'] })
        void client.removeQueries({ queryKey: keys.session(id) })
      } else if (outcome.next) {
        client.setQueryData<AssessmentSession>(keys.session(id), (prev) =>
          prev ? { ...prev, current: outcome.next! } : prev,
        )
      }
    },
  })
}

/**
 * FE-05 · Early finish. `POST /api/assessments/{id}/finish` → AssessmentResult
 * (gap G5 — mocked in qualification.ts; the real backend returns 503 until BE
 * ships it). Errors: 409 `not_enough_answers` (<50% answered → abandoned,
 * BE.md R9), 409 `invalid_transition` (already finished), 404 `not_found`.
 */
export function finishAssessment(id: string): Promise<AssessmentResult> {
  return customFetch<AssessmentResult>(`/api/assessments/${id}/finish`, {
    method: 'POST',
  })
}

export function useFinishAssessment(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => finishAssessment(id),
    onSuccess: (result) => {
      // Prime the result cache so FE-06 renders without an extra GET,
      // drop the session cache, refresh history/eligibility (cooldown starts).
      client.setQueryData(keys.result(result.id), result)
      void client.removeQueries({ queryKey: keys.session(id) })
      void client.invalidateQueries({ queryKey: keys.assessments })
      void client.invalidateQueries({ queryKey: ['eligibility'] })
    },
  })
}

/**
 * Player Card download. The server may fall back to an HTML page —
 * detect it by content-type and refuse (FE-06).
 */
export async function downloadPlayerCard(): Promise<void> {
  const res = await fetch('/api/candidates/me/card.pdf', { credentials: 'include' })
  const contentType = res.headers.get('content-type') ?? ''
  if (!res.ok || !contentType.includes('application/pdf')) {
    throw new Error(contentType.includes('text/html') ? 'card_fallback_html' : 'card_failed')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'player-card.pdf'
  a.click()
  URL.revokeObjectURL(url)
}
