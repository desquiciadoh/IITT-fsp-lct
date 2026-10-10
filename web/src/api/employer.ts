import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { Company, CompanyInput, JdParseResult, Position, PositionInput } from '@/api/types'

/**
 * FE-09 · Company & position wizard — API layer.
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
