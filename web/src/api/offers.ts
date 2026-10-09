import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import { usePollingInterval } from '@/api/events'
import type { Offer } from '@/api/types'

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
