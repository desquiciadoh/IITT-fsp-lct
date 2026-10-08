import { useQuery } from '@tanstack/react-query'
import { customFetch, ApiError } from '@/api/client'
import { keys } from '@/api/keys'
import type { Me } from '@/api/types'

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => customFetch<Me>('/api/me'),
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    staleTime: 30_000,
  })
}
