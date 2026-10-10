/**
 * FE-09 · Positions API layer (FE2.md §FE-09).
 *
 * Endpoints: GET /api/positions, POST /api/positions,
 * GET/PUT /api/positions/{id}, POST /api/positions/parse.
 *
 * gap G6: the JD-parse endpoint is unstable on the backend — always served
 * through the stateful mock in src/mocks/handlers/employer.ts (`X-Stub: true`).
 * BE.md B15: salary validation — the client must validate BEFORE submit
 * (zod in the wizard): `salary_min > 0`, `salary_max >= salary_min`, explicit
 * `salary_type` (the backend silently defaults to gross otherwise and returns
 * 500 for salary_min = 0, labelling every error `salary_invalid`).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { JdParseInput, JdParseResult, Position, PositionInput } from '@/api/types'

/** GET /api/positions — the backend returns a plain array today (no pagination, G14). */
export function usePositions() {
  return useQuery({
    queryKey: keys.positions,
    queryFn: async () => {
      const data = await customFetch<Position[] | { items: Position[] }>('/api/positions')
      return Array.isArray(data) ? data : (data.items ?? [])
    },
    staleTime: 15_000,
  })
}

/** GET /api/positions/{id} — edit screen settings tab. */
export function usePosition(id: string) {
  return useQuery({
    queryKey: keys.position(id),
    queryFn: () => customFetch<Position>(`/api/positions/${id}`),
    enabled: Boolean(id),
  })
}

/** POST /api/positions — save the wizard result. */
export function useCreatePosition() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: PositionInput) =>
      customFetch<Position>('/api/positions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (position) => {
      client.setQueryData(keys.position(position.id), position)
      void client.invalidateQueries({ queryKey: keys.positions })
    },
  })
}

/** PUT /api/positions/{id} — update an existing position (same client-side rules). */
export function useUpdatePosition() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PositionInput }) =>
      customFetch<Position>(`/api/positions/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (position) => {
      client.setQueryData(keys.position(position.id), position)
      void client.invalidateQueries({ queryKey: keys.positions })
    },
  })
}

/**
 * POST /api/positions/parse — one-shot draft generation (gap G6, mocked).
 * Mutation, not a query: the result feeds the wizard's editable draft state
 * and must never be cached across runs (keepPreviousData is irrelevant here).
 */
export function useParseJD() {
  return useMutation({
    mutationFn: (body: JdParseInput) =>
      customFetch<JdParseResult>('/api/positions/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
  })
}
