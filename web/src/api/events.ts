/**
 * Live updates: SSE (`GET /api/events`) → query invalidation, with a shared
 * polling flag as fallback — the backend SSE currently misbehaves (BE.md B14),
 * so on stream error we close it and switch queries to 10 s polling,
 * retrying SSE every 60 s.
 */
import { useEffect, useSyncExternalStore } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { keys } from '@/api/keys'

const POLLING_RETRY_MS = 60_000
export const POLLING_INTERVAL_MS = 10_000

let polling = false
const listeners = new Set<() => void>()

function setPolling(value: boolean) {
  if (polling === value) return
  polling = value
  for (const l of listeners) l()
}

/** True while SSE is down and queries should refetch on an interval. */
export function usePollingFallback(): boolean {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => polling,
    () => false,
  )
}

/** refetchInterval helper: 10 s while polling, disabled while SSE is live. */
export function usePollingInterval(): number | false {
  return usePollingFallback() ? POLLING_INTERVAL_MS : false
}

function handleEvent(client: QueryClient, event: string, raw: string) {
  let data: Record<string, unknown> = {}
  try {
    data = JSON.parse(raw) as Record<string, unknown>
  } catch {
    /* keep empty */
  }
  if (event.startsWith('offer.')) {
    void client.invalidateQueries({ queryKey: ['offers'] })
    const id = typeof data.offer_id === 'string' ? data.offer_id : undefined
    if (id) void client.invalidateQueries({ queryKey: keys.offer(id) })
  } else if (event === 'league.updated') {
    void client.invalidateQueries({ queryKey: ['pool'] })
    void client.invalidateQueries({ queryKey: ['leagues'] })
  } else if (event === 'fsp.synced') {
    void client.invalidateQueries({ queryKey: keys.profile })
  }
}

/** Mount once inside authenticated layouts. No-op while `enabled` is false (anonymous users). */
export function useLiveEvents(enabled = true): void {
  const client = useQueryClient()

  useEffect(() => {
    if (!enabled) return
    let source: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      source = new EventSource('/api/events', { withCredentials: true })
      source.onopen = () => setPolling(false)
      source.onmessage = (e) => handleEvent(client, 'message', e.data)
      // named events (offer.created, league.updated, fsp.synced)
      for (const type of ['offer.created', 'offer.updated', 'league.updated', 'fsp.synced']) {
        source.addEventListener(type, (e) => {
          handleEvent(client, type, (e as MessageEvent).data)
        })
      }
      source.onerror = () => {
        source?.close()
        source = null
        setPolling(true)
        retry = setTimeout(connect, POLLING_RETRY_MS)
      }
    }

    connect()
    return () => {
      source?.close()
      if (retry) clearTimeout(retry)
    }
  }, [client, enabled])
}
