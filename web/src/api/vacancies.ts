import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { Application, ApplicationStatus, Vacancy } from '@/api/types'

/** GET /api/vacancies — public position list, salary first (FE-15). */
export function useVacancies() {
  return useQuery({
    queryKey: keys.vacancies,
    queryFn: () => customFetch<Vacancy[]>('/api/vacancies'),
  })
}

/** GET /api/positions/{id} — position detail (shared with FE2's position page). */
export function usePosition(positionId: string) {
  return useQuery({
    queryKey: keys.position(positionId),
    queryFn: () => customFetch<Vacancy>(`/api/positions/${positionId}`),
    enabled: Boolean(positionId),
  })
}

/** GET /api/candidates/me/applications — the candidate's application statuses (FE-15). */
export function useApplications() {
  return useQuery({
    queryKey: keys.applications,
    queryFn: () => customFetch<Application[]>('/api/candidates/me/applications'),
  })
}

/** GET /api/positions/{id}/applications — the employer's applicant pipeline (FE-15). */
export function usePositionApplications(positionId: string) {
  return useQuery({
    queryKey: keys.positionApplications(positionId),
    queryFn: () => customFetch<Application[]>(`/api/positions/${positionId}/applications`),
    enabled: Boolean(positionId),
  })
}

/** POST /api/vacancies/{id}/apply — candidate applies; employer gains a contact grant. */
export function useApply(vacancyId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (note?: string) =>
      customFetch<Application>(`/api/vacancies/${vacancyId}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(note ? { note } : {}),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.vacancies })
      void client.invalidateQueries({ queryKey: keys.applications })
    },
  })
}

/** PUT /api/applications/{id} — employer moves the applicant through the pipeline. */
export function useSetApplicationStatus() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) =>
      customFetch<Application>(`/api/applications/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.applications })
      void client.invalidateQueries({ queryKey: ['applications', 'position'] })
    },
  })
}

/** PUT /api/positions/{id} — publish toggle (only `is_public` is patched today). */
export function useSetPositionPublic(positionId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (is_public: boolean) =>
      customFetch<Vacancy>(`/api/positions/${positionId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_public }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.vacancies })
    },
  })
}