import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import { usePollingInterval } from '@/api/events'
import type { ContactChannel, Offer, SalaryType } from '@/api/types'

/** Board view: candidate inbox by default; `employer` asks for the employer board. */
export type OffersView = 'candidate' | 'employer'

/** GET /api/offers?status= returns an array today; also accept {items} (gap G14). */
export function useOffers(status?: string, view: OffersView = 'candidate') {
  const interval = usePollingInterval()
  const query = status && status !== 'all' ? `?status=${status}` : ''
  return useQuery({
    queryKey: keys.offersBoard(view, status && status !== 'all' ? status : undefined),
    queryFn: async () => {
      const data = await customFetch<Offer[] | { items: Offer[] }>(`/api/offers${query}`, {
        headers: view === 'employer' ? { 'X-FSP-View': 'employer' } : undefined,
      })
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

/** FE-11: employer → candidate offer payload. `salary_type` must always be sent explicitly (B15). */
export type CreateOfferPayload = {
  candidate_public_id: string
  position_id?: string
  title: string
  description: string
  salary_min: number
  salary_max: number
  salary_type: SalaryType
  currency?: string
  contact_channel: ContactChannel
  contact_value?: string
  expires_in_days?: number
}

/**
 * POST /api/offers — send an offer (FE-11).
 * Never sends `why_you`: the backend computes it (BE fix B9); we also strip it
 * defensively so a future form refactor cannot reintroduce the field.
 */
export function useCreateOffer() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateOfferPayload) => {
      const body: Record<string, unknown> = { ...payload }
      delete body.why_you // B9 guard — server-computed, never client-supplied
      return customFetch<Offer>('/api/offers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-FSP-View': 'employer' },
        body: JSON.stringify(body),
      })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['offers'] })
      void client.invalidateQueries({ queryKey: ['pool'] })
    },
  })
}

/**
 * POST /api/offers/{id}/withdraw {version} — allowed only in `sent`/`viewed`.
 * On 409 (`version_conflict` / `invalid_transition`) the caller refetches (FE-11).
 */
export function useWithdrawOffer() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) =>
      customFetch<Offer>(`/api/offers/${id}/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-FSP-View': 'employer' },
        body: JSON.stringify({ version }),
      }),
    onSuccess: (offer) => {
      client.setQueryData(keys.offer(offer.id), offer)
      void client.invalidateQueries({ queryKey: ['offers'] })
    },
  })
}
