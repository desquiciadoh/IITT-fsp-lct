import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import { usePollingInterval } from '@/api/events'
import type { ContactChannel, Offer } from '@/api/types'

/** GET /api/offers?status= returns an array today; also accept {items} (gap G14). */
export function useOffers(status?: string) {
  const interval = usePollingInterval()
  const query = status && status !== 'all' ? `?status=${status}` : ''
  return useQuery({
    queryKey: keys.offers(status && status !== 'all' ? status : undefined),
    queryFn: async () => {
      const data = await customFetch<Offer[] | { items: Offer[] }>(`/api/offers${query}`)
      if (Array.isArray(data)) return data
      return data.items ?? []
    },
    refetchInterval: interval,
  })
}

export function useOffer(id: string) {
  const interval = usePollingInterval()
  return useQuery({
    queryKey: keys.offer(id),
    queryFn: () => customFetch<Offer>(`/api/offers/${id}`),
    enabled: Boolean(id),
    refetchInterval: interval,
  })
}

type OfferAction = 'view' | 'accept' | 'decline'

/** POST /api/offers/{id}/{view|accept|decline} with optimistic-lock {version}. */
export function useOfferAction(action: OfferAction) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      customFetch<Offer>(`/api/offers/${id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (offer) => {
      client.setQueryData(keys.offer(offer.id), offer)
      void client.invalidateQueries({ queryKey: ['offers'] })
    },
  })
}

/** 409 contract codes: optimistic lock and state machine (FE-07). */
export function isOfferConflict(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as { code?: string }).code !== undefined &&
    ['version_conflict', 'invalid_transition'].includes((error as { code: string }).code)
  )
}

// --- FE-11 · employer side -----------------------------------------------------

/**
 * POST /api/offers body. Rules from FE2.md §FE-11:
 * - `salary_type` is ALWAYS sent explicitly — the backend silently defaults
 *   to gross today (BE.md B15), so an omitted value would corrupt the offer;
 * - `why_you` is NEVER sent — the server computes it (BE fix B9);
 * - `expires_in_days` is optional (backend default: 14 days).
 */
export type SendOfferInput = {
  candidate_public_id: string
  position_id: string
  title: string
  description: string
  salary_min: number
  salary_max: number
  salary_type: 'gross' | 'net'
  contact_channel: ContactChannel
  /** required for email/phone/telegram; empty for `platform` (in-platform chat) */
  contact_value: string
  expires_in_days?: number
}

/** POST /api/offers → 201. Errors by code: 422 salary_invalid, 403 candidate_not_reachable, 404. */
export function useSendOffer() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: SendOfferInput) =>
      customFetch<Offer>('/api/offers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Belt-and-braces: strip any non-contract keys (e.g. why_you) before send.
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['offers'] })
    },
  })
}

/**
 * POST /api/offers/{id}/withdraw {version} — allowed while `sent`/`viewed`.
 * On 409 (`version_conflict` / `invalid_transition`) the caller refetches
 * the board: our local copy of `version`/`status` is stale.
 */
export function useWithdrawOffer() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) =>
      customFetch<Offer>(`/api/offers/${id}/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['offers'] })
    },
  })
}
