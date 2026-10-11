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
  TaxonomyGrade,
  TaxonomySpecialization,
  WorkFormat,
} from '@/api/types'

export function useProfile() {
  return useQuery({
    queryKey: keys.profile,
    queryFn: () => customFetch<CandidateProfile>('/api/candidates/me'),
    staleTime: 10_000,
  })
}

export function normalizeTaxonomy(data: unknown): Taxonomy {
  const d = (data ?? {}) as Record<string, unknown>
  const rawGrades = (d.grades ?? []) as Array<string | { id: string }>
  const grades = (Array.isArray(rawGrades) ? rawGrades : [])
    .map((g) => (typeof g === 'string' ? g : g?.id))
    .filter(Boolean) as Grade[]

  const rawSpecsList: Array<string | { id?: string }> =
    (d.specs as Array<string | { id?: string }>) ??
    (d.specializations as Array<string | { id?: string }>) ??
    []
  const specs = (Array.isArray(rawSpecsList) ? rawSpecsList : [])
    .map((s) => (typeof s === 'string' ? s : s?.id))
    .filter(Boolean) as Spec[]

  const rawSkills = (d.skills ?? []) as Array<string | { name?: string; id?: string }>
  const skills = (Array.isArray(rawSkills) ? rawSkills : [])
    .map((s) =>
      typeof s === 'string'
        ? s
        : s?.name ?? s?.id,
    )
    .filter(Boolean) as string[]

  const rawFormats = (d.work_formats ?? []) as Array<string | { id?: string }>
  const work_formats = (
    Array.isArray(rawFormats) && rawFormats.length > 0
      ? rawFormats.map((f) => (typeof f === 'string' ? f : f?.id)).filter(Boolean)
      : ['office', 'hybrid', 'remote']
  ) as WorkFormat[]

  const rawTopics =
    (d.strength_topics as Array<string | { id?: string }>) ??
    (d.topics as Array<string | { id?: string }>) ??
    []
  const strength_topics = (Array.isArray(rawTopics) ? rawTopics : [])
    .map((t) => (typeof t === 'string' ? t : t?.id))
    .filter(Boolean) as string[]

  return {
    ...(d as unknown as Taxonomy),
    specs: specs.length > 0 ? specs : (['backend', 'frontend', 'ml_data'] as Spec[]),
    grades: grades.length > 0 ? grades : (['intern', 'junior', 'middle', 'senior'] as Grade[]),
    work_formats,
    skills,
    strength_topics,
    grade_details:
      Array.isArray(rawGrades) && rawGrades.length > 0 && typeof rawGrades[0] === 'object'
        ? (rawGrades as unknown as TaxonomyGrade[])
        : undefined,
    specialization_details:
      Array.isArray(d.specializations)
        ? (d.specializations as TaxonomySpecialization[])
        : undefined,
  }
}

export function useTaxonomy() {
  return useQuery({
    queryKey: keys.taxonomy,
    queryFn: () => customFetch<Taxonomy>('/api/taxonomy'),
    staleTime: 5 * 60_000,
    retry: false,
    // The backend TaxonomySerializer returns skills, grades, and specializations
    // as objects (e.g. {id, name, name_ru, descriptor, descriptor_ru, theta_cut, rating_cut}).
    // The frontend Taxonomy type (and form consumers) expect plain string arrays for specs, grades, and skills.
    // Normalise here so PositionForm, ClaimStep, FilterPanel, and other consumers never receive raw objects.
    select: normalizeTaxonomy,
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
