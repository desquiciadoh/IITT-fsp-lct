import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  ApplicationCandidate,
  ApplicationEmployer,
  ApplicationStatus,
  Grade,
  Position,
  Spec,
  Vacancy,
  VacancyListResponse,
  WorkFormat,
} from '@/api/types'

/**
 * FE-15 · Vacancies & applications — API layer (BE-17 is live on the backend).
 *
 * Candidate: GET /api/vacancies, POST /api/vacancies/{id}/apply,
 * GET /api/candidates/me/applications, POST .../{id}/withdraw.
 * Employer: GET /api/positions/{id}/applications, PATCH .../{id}/status,
 * publish toggle via PUT /api/positions/{id} {is_public}.
 */

export type VacancyFilters = {
  specialization?: Spec | ''
  grades?: Grade[]
  work_formats?: WorkFormat[]
  search?: string
  page?: number
}

export function vacancyFiltersToParams(f: VacancyFilters): URLSearchParams {
  const p = new URLSearchParams()
  if (f.specialization) p.set('specialization', f.specialization)
  if (f.grades?.length) p.set('grades', f.grades.join(','))
  if (f.work_formats?.length) p.set('work_formats', f.work_formats.join(','))
  if (f.search?.trim()) p.set('search', f.search.trim())
  if (f.page && f.page > 1) p.set('page', String(f.page))
  return p
}

export function useVacancies(filters: VacancyFilters, enabled = true) {
  const query = vacancyFiltersToParams(filters).toString()
  return useQuery({
    queryKey: keys.vacancies(query),
    queryFn: () =>
      customFetch<VacancyListResponse>(`/api/vacancies${query ? `?${query}` : ''}`),
    enabled,
  })
}

export function useVacancy(id: string | null) {
  return useQuery({
    queryKey: keys.vacancy(id ?? ''),
    queryFn: () => customFetch<Vacancy>(`/api/vacancies/${id}`),
    enabled: Boolean(id),
  })
}

export function useMyApplications() {
  return useQuery({
    queryKey: keys.myApplications,
    queryFn: () => customFetch<ApplicationCandidate[]>('/api/candidates/me/applications'),
  })
}

export function useApplyVacancy() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      customFetch<ApplicationCandidate>(`/api/vacancies/${id}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: note ?? '' }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myApplications })
    },
  })
}

export function useWithdrawApplication() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      customFetch<ApplicationCandidate>(`/api/candidates/me/applications/${id}/withdraw`, {
        method: 'POST',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myApplications })
    },
  })
}

export function usePositionApplications(positionId: string, enabled = true) {
  return useQuery({
    queryKey: keys.positionApplications(positionId),
    queryFn: () =>
      customFetch<ApplicationEmployer[]>(`/api/positions/${positionId}/applications`),
    enabled: Boolean(positionId) && enabled,
  })
}

export function useUpdateApplicationStatus(positionId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      customFetch<ApplicationEmployer>(
        `/api/positions/${positionId}/applications/${id}/status`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.positionApplications(positionId) })
    },
  })
}

/** Publish toggle: PUT /api/positions/{id} {is_public} (partial update). */
export function useSetPositionPublic() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, isPublic }: { id: string; isPublic: boolean }) =>
      customFetch<Position>(`/api/positions/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_public: isPublic }),
      }),
    onSuccess: (position) => {
      client.setQueryData(keys.position(position.id), position)
      void client.invalidateQueries({ queryKey: keys.positions })
      void client.invalidateQueries({ queryKey: ['vacancies'] })
    },
  })
}
