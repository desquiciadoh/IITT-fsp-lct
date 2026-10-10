/**
 * FE-09 · Stage 3 — employer dashboard helpers.
 * The dashboard aggregates offers by status on the client (no stats endpoint
 * yet); these pure helpers keep that logic testable without rendering.
 */
import type { Offer, Position } from '@/api/types'

export type OfferCounts = Record<string, number>

/** Count offers per status; unknown/missing statuses are skipped safely. */
export function countOffersByStatus(offers: readonly Offer[]): OfferCounts {
  const counts: OfferCounts = {}
  for (const offer of offers) {
    if (!offer?.status) continue
    counts[offer.status] = (counts[offer.status] ?? 0) + 1
  }
  return counts
}

/** Sort positions newest-first by `created_at` (dashboard default order). */
export function sortPositions(positions: readonly Position[]): Position[] {
  return [...positions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )
}
