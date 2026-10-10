/**
 * FE-09 · Company API layer (FE2.md §FE-09).
 *
 * Endpoints: GET / PUT /api/companies/me.
 * gap G17: after BE fixes B1 there is no dedicated create endpoint yet, so
 * the "create company" form PUTs to /api/companies/me and the backend must
 * upsert. Until then the backend auto-creates a company for employers; the
 * frontend treats 403 `company_required` as "no company yet" and shows the
 * creation form instead of an error page.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch, ApiError } from '@/api/client'
import { keys } from '@/api/keys'
import type { Company, CompanyInput } from '@/api/types'

/** True when the employer has no company yet (BE.md B1 / gap G17). */
export function isCompanyRequired(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 403 &&
    (error.code === 'company_required' || error.code === 'forbidden')
  )
}

export function useCompany() {
  return useQuery({
    queryKey: keys.company,
    queryFn: () => customFetch<Company>('/api/companies/me'),
    // 403 company_required is a legit empty state, not a failure to retry.
    retry: (count, error) => !isCompanyRequired(error) && count < 2,
    staleTime: 30_000,
  })
}

/** PUT /api/companies/me — update, and (per gap G17) also create. */
export function useUpdateCompany() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: CompanyInput) =>
      customFetch<Company>('/api/companies/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: (company) => {
      client.setQueryData(keys.company, company)
    },
  })
}
