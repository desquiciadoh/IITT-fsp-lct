import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  CandidateProfile,
  Consents,
  Grade,
  ResumeParseResult,
  Spec,
  Taxonomy,
  TaxonomyWire,
} from '@/api/types'

export function useProfile() {
  return useQuery({
    queryKey: keys.profile,
    queryFn: () => customFetch<CandidateProfile>('/api/candidates/me'),
    staleTime: 10_000,
  })
}

/**
 * GET /api/taxonomy (live on the BE). The wire shape is object-based
 * ({id,name,...} entries); the UI consumes flat string lists, so normalize
 * here and never let raw objects reach the components.
 */
export function useTaxonomy() {
  return useQuery({
    queryKey: keys.taxonomy,
    queryFn: () => customFetch<TaxonomyWire>('/api/taxonomy'),
    staleTime: 5 * 60_000,
    retry: false,
    select: (data): Taxonomy => ({
      specs: (data.specializations ?? []).map((s) => s.id as Spec),
      grades: (data.grades ?? []).map((g) => g.id as Grade),
      skills: (data.skills ?? []).map((s) => s.name),
      decline_reasons: data.decline_reasons ?? [],
    }),
  })
}

/** PUT /api/candidates/me (partial, flat fields). */
export function useSaveProfile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      customFetch<CandidateProfile>('/api/candidates/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      }),
    onSuccess: (profile) => {
      client.setQueryData(keys.profile, profile)
      void client.invalidateQueries({ queryKey: keys.me })
    },
  })
}

/** PUT /api/candidates/me/consents → {processing, publication, fsp_sync} */
export function useSaveConsents() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (patch: Partial<Consents>) =>
      customFetch<Consents>('/api/candidates/me/consents', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...patch, version: '1.0' }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.profile })
      void client.invalidateQueries({ queryKey: keys.me })
    },
  })
}

/** POST /api/candidates/me/resume (multipart, field "file", PDF ≤ 5 MB). */
export function useUploadResume() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return customFetch<ResumeParseResult>('/api/candidates/me/resume', {
        method: 'POST',
        body: form,
      })
    },
  })
}

export interface CompanyMinimal {
  id: string
  name: string
}

export interface CompanyPaginatedResponse {
  items: CompanyMinimal[]
  total: number
  page: number
  pages: number
}

export function useSearchCompanies(search: string) {
  const trimmed = search.trim()
  return useQuery({
    queryKey: keys.companies(trimmed),
    queryFn: () =>
      customFetch<CompanyPaginatedResponse>(
        `/api/companies?search=${encodeURIComponent(trimmed)}`,
      ),
    enabled: trimmed.length >= 2,
    staleTime: 60_000,
  })
}
