import { useQuery } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { AssessmentResult, Eligibility } from '@/api/types'

export function useResult(id: string) {
  return useQuery({
    queryKey: keys.result(id),
    queryFn: () => customFetch<AssessmentResult>(`/api/assessments/${id}/result`),
    enabled: Boolean(id),
  })
}

/** GET /api/assessments returns an array today; also accept {items} (gap G14). */
export function useHistory() {
  return useQuery({
    queryKey: keys.assessments,
    queryFn: async () => {
      const data = await customFetch<AssessmentResult[] | { items: AssessmentResult[] }>(
        '/api/assessments',
      )
      if (Array.isArray(data)) return data
      return data.items ?? []
    },
  })
}

export function useEligibility(specialization?: string) {
  const spec = specialization || 'backend'
  return useQuery({
    queryKey: keys.eligibility(spec),
    queryFn: () =>
      customFetch<Eligibility>(
        `/api/assessments/eligibility?specialization=${encodeURIComponent(spec)}`,
      ),
    retry: false,
  })
}

/**
 * Player Card download. The server may fall back to an HTML page —
 * detect it by content-type and refuse (FE-06).
 */
export async function downloadPlayerCard(): Promise<void> {
  const res = await fetch('/api/candidates/me/card.pdf', { credentials: 'include' })
  const contentType = res.headers.get('content-type') ?? ''
  if (!res.ok || !contentType.includes('application/pdf')) {
    throw new Error(contentType.includes('text/html') ? 'card_fallback_html' : 'card_failed')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'player-card.pdf'
  a.click()
  URL.revokeObjectURL(url)
}
