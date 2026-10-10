import { describe, expect, it } from 'vitest'
import type { Offer, Position } from '@/api/types'
import { countOffersByStatus, sortPositions } from './dashboard-helpers'

const offer = (id: string, status: Offer['status']): Offer =>
  ({ id, status }) as unknown as Offer

const position = (id: string, created_at: string): Position =>
  ({ id, created_at }) as unknown as Position

describe('countOffersByStatus', () => {
  it('aggregates sent/viewed/accepted/declined counts', () => {
    const counts = countOffersByStatus([
      offer('o1', 'sent'),
      offer('o2', 'sent'),
      offer('o3', 'viewed'),
      offer('o4', 'accepted'),
      offer('o5', 'declined'),
    ])
    expect(counts.sent).toBe(2)
    expect(counts.viewed).toBe(1)
    expect(counts.accepted).toBe(1)
    expect(counts.declined).toBe(1)
  })

  it('returns an empty map for an empty list', () => {
    expect(countOffersByStatus([])).toEqual({})
  })

  it('skips entries without a status', () => {
    const counts = countOffersByStatus([
      offer('o1', undefined as unknown as Offer['status']),
      offer('o2', 'sent'),
    ])
    expect(Object.keys(counts)).toEqual(['sent'])
  })
})

describe('sortPositions', () => {
  it('orders newest first and does not mutate the input', () => {
    const input = [
      position('old', '2026-01-01T00:00:00Z'),
      position('new', '2026-10-01T00:00:00Z'),
      position('mid', '2026-05-01T00:00:00Z'),
    ]
    const sorted = sortPositions(input)
    expect(sorted.map((p) => p.id)).toEqual(['new', 'mid', 'old'])
    expect(input.map((p) => p.id)).toEqual(['old', 'new', 'mid'])
  })
})
