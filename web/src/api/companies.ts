import { useQuery } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { CompanyMinimal } from '@/api/generated/models'

/** GET /api/companies?search= — live company lookup for the blocklist (R27, G17 closed). */
export function useCompanySearch(q: string) {
  return useQuery({
    queryKey: keys.companySearch(q),
    queryFn: () => customFetch<CompanyMinimal[]>(`/api/companies?search=${encodeURIComponent(q.trim())}`),
    enabled: q.trim().length >= 2,
  })
}