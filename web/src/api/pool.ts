import { useQuery } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { PositionPool } from '@/api/types'

/** `GET /api/positions/{id}/pool` (G20 / FE-17, FE2 scouting page). */
export function usePositionPool(positionId: string) {
  return useQuery({
    queryKey: keys.pool(positionId),
    queryFn: () => customFetch<PositionPool>(`/api/positions/${positionId}/pool`),
    enabled: Boolean(positionId),
  })
}