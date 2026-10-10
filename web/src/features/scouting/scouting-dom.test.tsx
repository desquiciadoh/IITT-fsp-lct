// @vitest-environment happy-dom
/**
 * FE-10 · Integration tests (DOM) — stage 5.
 *
 * Scenarios required by the task:
 *  - candidate drawer is restored from `?c=` on a fresh mount ("reload"),
 *    closes via X / backdrop / Esc and the URL key disappears;
 *  - contacts stay gated (mock returns contacts=null — gap G9);
 *  - shortlist tray survives filter changes end-to-end through the stateful
 *    MSW handlers (PUT/DELETE → in-memory set, gap G16);
 *  - the "фильтр в браузере" fallback badge appears because the mock pool
 *    response has no `facets` (gap G8).
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { setupServer } from 'msw/node'

import { scoutingHandlers } from '@/mocks/handlers/scouting'
import { ScoutingPage } from '@/features/scouting/scouting-page'

const server = setupServer(...scoutingHandlers)
// listen() once per file — happy-dom keeps the msw network object alive
// between tests, and re-configuring an enabled network throws.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

function LocationProbe() {
  const { search } = useLocation()
  return <div data-testid="location">{search}</div>
}

function renderAt(path: string) {
  // StrictMode double-invokes effects like a real reload — good regression
  // guard for the optimistic shortlist mutation (onMutate must be idempotent).
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <StrictMode>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/employer/positions/:id" element={<ScoutingPage />} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
}

const locationOf = () => screen.getByTestId('location').textContent ?? ''

describe('candidate drawer (?c=) — restore & close', () => {
  it('opens directly from the URL on mount (reload restores state)', async () => {
    renderAt('/employer/positions/pos-1?c=A1B2C3')
    const dialog = await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    // header shows pool-row data instantly, detail fields arrive with G9 payload
    expect(within(dialog).getByText('Анна К.')).toBeTruthy()
    await waitFor(() =>
      expect(within(dialog).getByText(/Senior backend-инженер/)).toBeTruthy(),
    )
    expect(within(dialog).getByText('A1B2C3')).toBeTruthy()
  })

  it('gates contacts until an offer is accepted (G9: contacts=null)', async () => {
    renderAt('/employer/positions/pos-1?c=A1B2C3')
    const dialog = await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    await waitFor(() => {
      expect(
        within(dialog).getByText(/Контакты откроются после того, как кандидат примет оффер/),
      ).toBeTruthy()
    })
    // no contact values anywhere in the drawer
    expect(within(dialog).queryByText(/mailto|@/)).toBeNull()
  })

  it('X button removes ?c= from the URL and unmounts the drawer', async () => {
    renderAt('/employer/positions/pos-1?grades=senior&c=A1B2C3')
    const dialog = await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    fireEvent.click(within(dialog).getByLabelText('Закрыть'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    // other filters survive the close; only the drawer key is dropped
    expect(locationOf()).toBe('?grades=senior')
  })

  it('backdrop click clears ?c=', async () => {
    renderAt('/employer/positions/pos-1?c=D4E5F6')
    const dialog = await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    fireEvent.click(within(dialog).getByLabelText('Закрыть карточку'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(locationOf()).toBe('')
  })

  it('Esc key clears ?c=', async () => {
    renderAt('/employer/positions/pos-1?c=D4E5F6')
    await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(locationOf()).toBe('')
  })

  it('clicking a candidate row opens the drawer and writes ?c= into the URL', async () => {
    renderAt('/employer/positions/pos-1')
    const row = await screen.findByText('Анна К.')
    fireEvent.click(row)
    await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    await waitFor(() => expect(locationOf()).toContain('c=A1B2C3'))
  })

  it('drawer state + filters survive a simulated reload (fresh mount from URL)', async () => {
    const view = renderAt('/employer/positions/pos-1?grades=senior&c=A1B2C3')
    await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    // unmount → remount at the same URL == browser reload
    view.unmount()
    renderAt('/employer/positions/pos-1?grades=senior&c=A1B2C3')
    const dialog = await screen.findByRole('dialog', { name: 'Карточка кандидата' })
    expect(within(dialog).getByText('Анна К.')).toBeTruthy()
    expect(locationOf()).toBe('?grades=senior&c=A1B2C3')
  })
})

describe('shortlist tray — survives filter changes (stateful mock, G16)', () => {
  it('keeps a starred candidate after applying filters that hide them from the list', async () => {
    renderAt('/employer/positions/pos-1')
    await screen.findByText('Анна К.')

    // star Anna (senior, remote+hybrid) — rows are divs, find her row via the
    // unique public_id badge rendered next to the name
    const annaRow = (screen.getByText('A1B2C3').closest('div.flex.flex-col.gap-2') ??
      screen.getByText('Анна К.').parentElement) as HTMLElement
    const starBtn = within(annaRow).getByLabelText('В избранное')
    fireEvent.click(starBtn)

    // tray shows her
    const tray = await screen.findByRole('complementary', { name: 'Лоток избранного' })
    await waitFor(() => expect(within(tray).getByText('Анна К.')).toBeTruthy())

    // apply intern-only filter via the league shelf button (aria-pressed state)
    const shelves = screen.getAllByRole('button', { pressed: false }).filter(
      (b) => b.textContent?.includes('стажёр'),
    )
    fireEvent.click(shelves[0])
    // …but the tray must still contain her (rebuilt from cached queries)
    await waitFor(() => expect(within(tray).getByText('Анна К.')).toBeTruthy())
    // while the main list no longer shows her
    await waitFor(() =>
      expect(
        within(screen.getByRole('main', { name: 'Кандидаты' })).queryByText('Анна К.'),
      ).toBeNull(),
    )

    // removing from the tray issues DELETE and drops her everywhere
    const removeBtn = within(tray).getByLabelText(/Убрать Анна К\. из избранного/)
    fireEvent.click(removeBtn)
    await waitFor(() => expect(within(tray).queryByText('Анна К.')).toBeNull())
  })
})

describe('fallback badge (no facets in the pool response, G8)', () => {
  it('shows «фильтр в браузере» once the pool arrives without facets', async () => {
    renderAt('/employer/positions/pos-1')
    await screen.findByText('Анна К.')
    expect(screen.getByText('фильтр в браузере')).toBeTruthy()
  })

  it('client-side filtering actually narrows the visible list', async () => {
    renderAt('/employer/positions/pos-1')
    await screen.findByText('Анна К.')
    // only Сергей Н. is an intern → pick the shelf button (contains "подтверждено")
    const internShelf = screen
      .getAllByRole('button', { pressed: false })
      .find((b) => b.textContent?.includes('стажёр') && b.textContent?.includes('подтверждено'))
    expect(internShelf).toBeTruthy()
    fireEvent.click(internShelf!)
    // only Сергей Н. is an intern
    await waitFor(() => expect(screen.queryByText('Анна К.')).toBeNull())
    expect(screen.getByText('Сергей Н.')).toBeTruthy()
    expect(locationOf()).toContain('grades=intern')
  })
})
