// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { OfferDetailPage } from '@/features/offers/offer-detail-page'
import type { Offer } from '@/api/types'

const now = new Date().toISOString()

const sentOffer: Offer = {
  id: 'off-1',
  company: { id: 'comp-1', name: 'Acme Systems', trust_level: 'verified' },
  position: 'Backend',
  title: 'Senior Backend Engineer',
  salary_min: 300000,
  salary_max: 420000,
  salary_type: 'gross',
  currency: 'RUB',
  status: 'sent',
  version: 1,
  created_at: now,
  updated_at: now,
}

/** Same-body conflict: GET keeps returning `sent`, POST /view keeps 409ing (R19). */
const versionConflict = () =>
  HttpResponse.json(
    {
      type: 'about:blank',
      title: 'version_conflict',
      status: 409,
      code: 'version_conflict',
      detail: 'The offer has changed, reload and retry.',
    },
    { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
  )

const server = setupServer(
  http.post('*/api/offers/:id/view', versionConflict),
  http.get('*/api/offers/:id', () => HttpResponse.json(sentOffer)),
)

beforeAll(() => {
  document.cookie = 'csrftoken=test-token'
  server.listen({ onUnhandledRequest: 'error' })
})
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/candidate/offers/off-1']}>
        <Routes>
          <Route path="/candidate/offers/:id" element={<OfferDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('OfferDetailPage auto-view (R19)', () => {
  it('shows an ErrorState after two conflicts instead of hanging on "Открываем оффер…"', async () => {
    renderPage()

    await waitFor(
      () => {
        expect(screen.getByText('Не удалось открыть оффер')).toBeInTheDocument()
      },
      { timeout: 3000 },
    )

    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument()
    expect(screen.queryByText('Открываем оффер…')).not.toBeInTheDocument()
  })
})
