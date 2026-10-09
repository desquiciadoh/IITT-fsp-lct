// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { LabPage } from '@/features/lab/lab-page'
import type { ValidationReport } from '@/api/types'

/** jsdom has no layout engine; keep ResponsiveContainer from crashing (FE-13). */
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const fixture: ValidationReport = {
  generated_at: '2026-10-09T12:00:00Z',
  git_sha: '0000000',
  synthetic_fixture: true,
  assessment: {
    simulees: 2048,
    exact_acc: 0.73,
    adjacent_acc: 0.94,
    qwk: 0.81,
    retest_same_grade: 0.77,
    retest_r: 0.72,
    median_len: 12,
    max_family_exposure: 4,
    collision_rate: 0.03,
    generator_errors: 2,
    confusion: [
      [612, 96, 22, 8],
      [74, 558, 84, 14],
      [31, 88, 419, 32],
      [9, 18, 54, 188],
    ],
    tif: {
      theta: [-3, -2, -1, 0, 1, 2, 3],
      info: [2.1, 5.2, 10.1, 11.9, 9.4, 4.8, 2.0],
    },
    leak_attack: [
      { leak_share: 0.02, static_dtheta: 0.4, parametric_dtheta: 0.9 },
      { leak_share: 0.25, static_dtheta: 3.9, parametric_dtheta: 12.8 },
    ],
  },
  matching: {
    candidates: 320,
    needs: 12,
    non_fsp_parity: 0.96,
    pool_p95_ms: 180,
    systems: [{ name: 'blended', ndcg10: 0.87, p10: 0.5, r50: 0.9, mrr: 0.79 }],
  },
}

const server = setupServer(http.get('*/api/lab/report', () => HttpResponse.json(fixture)))

beforeAll(() => {
  document.cookie = 'csrftoken=test-token'
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
  server.listen({ onUnhandledRequest: 'error' })
})
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LabPage />
    </QueryClientProvider>,
  )
}

describe('LabPage (FE-13)', () => {
  it('renders the fixture report with a red FIXTURE banner', async () => {
    renderPage()

    await waitFor(() => expect(screen.getByText('Качество теста и матчинга')).toBeInTheDocument(), {
      timeout: 3000,
    })

    expect(screen.getByText(/FIXTURE/)).toBeInTheDocument()
    expect(screen.getByText('Точность')).toBeInTheDocument()
    expect(screen.getByText('73%')).toBeInTheDocument()
    expect(screen.getByText('Матрица ошибок')).toBeInTheDocument()
    expect(screen.getByText('Кривая информации (TIF)')).toBeInTheDocument()
    expect(screen.getByText('Атаки на утечки')).toBeInTheDocument()
    expect(screen.getByText('Матчинг')).toBeInTheDocument()
    expect(screen.getByText('0000000')).toBeInTheDocument()
  })

  it('hides the FIXTURE banner when the report is real', async () => {
    server.use(
      http.get('*/api/lab/report', () =>
        HttpResponse.json({ ...fixture, synthetic_fixture: false }),
      ),
    )
    renderPage()

    await waitFor(() => expect(screen.getByText('Качество теста и матчинга')).toBeInTheDocument(), {
      timeout: 3000,
    })
    expect(screen.queryByText(/FIXTURE/)).not.toBeInTheDocument()
  })
})