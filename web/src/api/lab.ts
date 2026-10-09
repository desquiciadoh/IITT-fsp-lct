import { useQuery } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { TestTwins, ValidationReport } from '@/api/types'

/** GET /api/lab/report — Validation Lab metrics (G11 closed). */
export function useLabReport() {
  return useQuery({
    queryKey: keys.labReport,
    queryFn: () => customFetch<ValidationReport>('/api/lab/report'),
    staleTime: 60_000,
  })
}

/** GET /api/lab/twins?position_id= — Test Twins (G21 / FE-14, BE-22 mocked). */
export function useLabTwins(positionId = 'pos-1') {
  return useQuery({
    queryKey: keys.labTwins(positionId),
    queryFn: () => customFetch<TestTwins>(`/api/lab/twins?position_id=${positionId}`),
    enabled: Boolean(positionId),
  })
}