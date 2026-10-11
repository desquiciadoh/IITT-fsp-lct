import { useQuery } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  ValidationReport,
  LabFamiliesResponse,
  LabTwinsResponse,
} from '@/api/types'

/** FE-13 · Fetch validation & psychometrics report (GET /api/lab/report). */
export function useLabReport() {
  return useQuery<ValidationReport>({
    queryKey: keys.labReport,
    queryFn: () => customFetch<ValidationReport>('/api/lab/report'),
  })
}

/** BE-22 · Fetch parametric item families catalog with drift stats (GET /api/lab/families). */
export function useLabFamilies() {
  return useQuery<LabFamiliesResponse>({
    queryKey: keys.labFamilies,
    queryFn: () => customFetch<LabFamiliesResponse>('/api/lab/families'),
  })
}

export type TwinsFilterParams = {
  specialization?: string
  grade?: string
  positionId?: string
}

/** FE-14 · Fetch side-by-side test twin instances (GET /api/lab/twins). */
export function useLabTwins(params: TwinsFilterParams = {}) {
  const { specialization = 'backend', grade = 'middle', positionId } = params

  return useQuery<LabTwinsResponse>({
    queryKey: keys.labTwins(specialization, grade, positionId),
    queryFn: () => {
      const search = new URLSearchParams()
      if (positionId) {
        search.set('position_id', positionId)
      } else {
        if (specialization) search.set('specialization', specialization)
        if (grade) search.set('grade', grade)
      }
      return customFetch<LabTwinsResponse>(`/api/lab/twins?${search.toString()}`)
    },
  })
}
