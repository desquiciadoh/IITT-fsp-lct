// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { OfferDetailPage } from '@/features/offers/offer-detail-page'

/**
 * R19 — a `sent` offer whose POST /view always conflicts (version_conflict /
 * invalid_transition) while GET keeps returning the very same body must not
 * hang on "Открываем оффер…". After one auto-retry it shows ErrorState with a
 * retry button.
 */
const OFFER = {
  id: 'o1',
  status: 'sent',
  version: 1,
  title: 'Backend-разработчик',
  position: 'Backend',
  salary_min: 200000,
  salary_max: 300000,
  salary_type: 'gross',
  expires_at: new Date('2999-01-01').toISOString(),
  updated_at: new Date('2025-01-01').toISOString(),
}

const conflict = (code: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status: 409, code, detail: 'conflict' },
    { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
  )

const server = setupServer(
  http.get('*/api/auth/csrf', () => HttpResponse.json({ detail: 'ok' })),
  http.get('*/api/offers/:id', () => HttpResponse.json(OFFER)),
  http.post('*/api/offers/:id/view', () => conflict('invalid_transition')),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/candidate/offers/o1']}>
        <Routes>
          <Route path="/candidate/offers/:id" element={<OfferDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('OfferDetailPage auto-view (R19)', () => {
  it('stops after one retry and shows ErrorState instead of hanging', async () => {
    renderPage()

    expect(await screen.findByRole('button', { name: 'Повторить' })).toBeTruthy()
    expect(screen.queryByText('Открываем оффер…')).toBeNull()
  })
})
