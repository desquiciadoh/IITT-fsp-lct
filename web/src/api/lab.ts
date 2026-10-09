import { useQuery } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { ValidationReport } from '@/api/types'

/** GET /api/lab/report — Validation Lab metrics (G11 closed). */
export function useLabReport() {
  return useQuery({
    queryKey: keys.labReport,
    queryFn: () => customFetch<ValidationReport>('/api/lab/report'),
    staleTime: 60_000,
  })
}