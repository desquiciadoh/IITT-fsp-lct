import { useQuery } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { LabTwinsResponse, ValidationReport } from '@/api/types'

/** FE-13 · Validation Lab — GET /api/lab/report (gap G11). */
export function useLabReport() {
  return useQuery({
    queryKey: keys.labReport,
    queryFn: () => customFetch<ValidationReport>('/api/lab/report'),
    staleTime: 60_000,
  })
}

export type TestTwinsParams = {
  positionId?: string | null
  specialization?: string
  grade?: string
  enabled?: boolean
}

/** FE-14 · Test Twins — GET /api/lab/twins (gap BE-22). */
export function useTestTwins({
  positionId,
  specialization,
  grade,
  enabled = true,
}: TestTwinsParams) {
  const params = new URLSearchParams()
  if (positionId) params.set('position_id', positionId)
  if (specialization) params.set('specialization', specialization)
  if (grade) params.set('grade', grade)
  const query = params.toString()
  return useQuery({
    queryKey: keys.labTwins(query),
    queryFn: () =>
      customFetch<LabTwinsResponse>(`/api/lab/twins${query ? `?${query}` : ''}`),
    enabled: enabled && Boolean(positionId || specialization),
    staleTime: 60_000,
  })
}
