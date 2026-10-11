// @vitest-environment jsdom
/**
 * R19 · Acceptance test — offer auto-view must never hang on the
 * "Открываем оффер…" state. Two consecutive 409s on POST /view (lazy expiry:
 * GET still says `sent`, the first retry races the same expired state) must
 * land the user on ErrorState instead of an infinite pending screen.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { server } from '@/mocks/server'
import { OfferDetailPage } from '@/features/offers/offer-detail-page'

beforeEach(() => {
  // Deterministic clock for the countdown/expiry helpers inside the page.
  vi.useFakeTimers({ toFake: ['Date'] })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

async function renderOfferDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/candidate/offers/race-offer']}>
        <Routes>
          <Route path="/candidate/offers/:id" element={<OfferDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('OfferDetailPage auto-view (R19)', () => {
  it('double 409 on POST /view → ErrorState, no infinite "Открываем оффер…"', async () => {
    // Pin this offer to `sent`: GET keeps returning the stale status while
    // every POST /view answers 409 invalid_transition (the lazy-expiry race
    // from FE1.md R19). No relative-URL fetch here — jsdom would resolve it
    // against localhost:80; the shared store is untouched by this test.
    server.use(
      http.get('*/api/offers/race-offer', () =>
        HttpResponse.json({
          id: 'race-offer',
          title: 'Backend Developer',
          description: '',
          company: { id: 'comp-1', name: 'Acme', trust_level: 'verified' },
          position: 'Backend',
          salary_min: 200000,
          salary_max: 300000,
          salary_type: 'gross',
          currency: 'RUB',
          contact_channel: 'platform',
          status: 'sent',
          why_you: [],
          version: 1,
          expires_at: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          candidate_contacts: null,
        }),
      ),
      http.post('*/api/offers/race-offer/view', () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'invalid_transition', status: 409, code: 'invalid_transition', detail: 'Cannot view an offer in status sent.' },
          { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    )

    await renderOfferDetail()

    // The hang symptom was a permanently visible placeholder text; after the
    // fix the second 409 must surface the error UI with a retry affordance.
    expect(await screen.findByText('Что-то пошло не так')).toBeInTheDocument()
    expect(screen.getByText('invalid_transition')).toBeInTheDocument()
    expect(screen.queryByText('Открываем оффер…')).not.toBeInTheDocument()
  })
})
