// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setupServer } from 'msw/node'
import { PoolPage } from '@/features/pool/pool-page'
import { poolHandlers } from '@/mocks/handlers/pool'

const server = setupServer(...poolHandlers)

beforeAll(() => {
  document.cookie = 'csrftoken=test-token'
  server.listen({ onUnhandledRequest: 'error' })
})
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

function renderPool() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PoolPage />
    </QueryClientProvider>,
  )
}

describe('PoolPage (FE-17)', () => {
  it('renders weights, relaxations, health and candidates from the fixture', async () => {
    renderPool()
    expect(await screen.findByText('Веса матчинга')).toBeInTheDocument()
    expect(screen.getByText('Что расширить')).toBeInTheDocument()
    expect(screen.getByText('Здоровье потребности')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Анна Иванова')).toBeInTheDocument())
    expect(screen.getAllByText('Отправить').length).toBeGreaterThan(0)
  })

  it('re-ranks on a preset click without a request', async () => {
    renderPool()
    await waitFor(() => expect(screen.getByText('Анна Иванова')).toBeInTheDocument())
    const list = screen.getByRole('list', { name: 'Ранжированный пул' })
    const before = list.textContent ?? ''
    fireEvent.click(screen.getByText('Бюджет'))
    await waitFor(() => {
      expect(list.textContent).not.toBe(before)
    })
  })
})