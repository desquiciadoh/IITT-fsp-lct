import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  Company,
  CompanyInput,
  ContactChannel,
  JdParseResult,
  Offer,
  Position,
  PositionInput,
  SalaryType,
} from '@/api/types'

/**
 * FE-09 · Company & position wizard — API layer.
 * FE-11 · Send Offer / offers board — create + withdraw mutations live here
 * (employer side), the shared queries are in `api/offers.ts`.
 *
 * Endpoints: GET/PUT /api/companies/me, POST /api/companies (gap G17),
 * GET/POST /api/positions, GET/PUT /api/positions/{id},
 * POST /api/positions/parse (gap G6). All gaps are mocked in MSW with the
 * target shape (`X-Stub: true`), so nothing changes when BE ships them.
 */

export function useCompany() {
  return useQuery({
    queryKey: keys.company,
    queryFn: () => customFetch<Company>('/api/companies/me'),
    retry: false,
  })
}

/** PUT /api/companies/me → updated company. */
export function useSaveCompany() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CompanyInput) =>
      customFetch<Company>('/api/companies/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    onSuccess: (company) => {
      client.setQueryData(keys.company, company)
    },
  })
}

/**
 * gap G17 — POST /api/companies for employers without a company. Today the
 * backend auto-creates one (security bug B1); after the fix it answers 403
 * `company_required` and this endpoint creates the company explicitly.
 */
export function useCreateCompany() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CompanyInput) =>
      customFetch<Company>('/api/companies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    onSuccess: (company) => {
      client.setQueryData(keys.company, company)
    },
  })
}

/** GET /api/positions returns a plain array today; also accept {items} (G14). */
export function usePositions() {
  return useQuery({
    queryKey: keys.positions,
    queryFn: async () => {
      const data = await customFetch<Position[] | { items: Position[] }>('/api/positions')
      if (Array.isArray(data)) return data
      return data.items ?? []
    },
  })
}

export function usePosition(id: string, enabled = true) {
  return useQuery({
    queryKey: keys.position(id),
    queryFn: () => customFetch<Position>(`/api/positions/${id}`),
    enabled: Boolean(id) && enabled,
  })
}

/** POST /api/positions → 201 created position. */
export function useCreatePosition() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: PositionInput) =>
      customFetch<Position>('/api/positions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    onSuccess: (position) => {
      client.setQueryData(keys.position(position.id), position)
      void client.invalidateQueries({ queryKey: keys.positions })
    },
  })
}

/**
 * FE-11 · Send Offer — POST /api/offers (candidate_public_id, position_id,
 * title, description, salary_min/max, salary_type, contact_channel/value,
 * expires_in_days?). `salary_type` is always sent explicitly (B15) and
 * `why_you` is never sent — the server computes it (B9).
 */
export type CreateOfferInput = {
  candidate_public_id: string
  position_id?: string
  title: string
  description?: string
  salary_min: number
  salary_max: number
  salary_type: SalaryType
  contact_channel: ContactChannel
  contact_value: string
  expires_in_days?: number
}

export function useCreateOffer() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateOfferInput) => {
      const { why_you: _ignored, ...rest } = input as CreateOfferInput & { why_you?: unknown }
      return customFetch<Offer>('/api/offers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rest),
      })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['offers'] })
    },
  })
}

/**
 * FE-11 · Withdraw — POST /api/offers/{id}/withdraw {version}. Allowed in
 * `sent` and `viewed`; on 409 (`version_conflict` / `invalid_transition`)
 * callers should refetch (isOfferConflict).
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
    onSuccess: (offer) => {
      client.setQueryData(keys.offer(offer.id), offer)
      void client.invalidateQueries({ queryKey: ['offers'] })
    },
  })
}

/** PUT /api/positions/{id} → updated position (settings tab, FE-09 edit). */
export function useUpdatePosition(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: Partial<PositionInput>) =>
      customFetch<Position>(`/api/positions/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    onSuccess: (position) => {
      client.setQueryData(keys.position(position.id), position)
      void client.invalidateQueries({ queryKey: keys.positions })
    },
  })
}

/**
 * gap G6 — POST /api/positions/parse {text} → JdParseResult.
 * Not a mutation of server state, but a mutation keeps busy/error UX simple.
 */
export function useParseJd() {
  return useMutation({
    mutationFn: (text: string) =>
      customFetch<JdParseResult>('/api/positions/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }),
  })
}
