import { http, HttpResponse } from 'msw'

/**
 * `all` mode (no backend): FSP link and sync. The reserved id `taken-123`
 * always answers 409 `fsp_id_already_linked` so the error path is demoable.
 */

const json = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail },
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
    },
  )

export const fspHandlers = [
  http.post('*/api/fsp/link', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { participant_id?: string }
    const id = (body.participant_id ?? '').trim()
    if (!id) {
      return problem(400, 'validation_failed', 'participant_id is required.')
    }
    if (id === 'taken-123') {
      return problem(409, 'fsp_id_already_linked', 'This FSP ID is already linked.')
    }
    return json({ participant_id: id, sports_rank: 'kms', sync_status: 'ok', results_count: 6 })
  }),
  http.post('*/api/fsp/sync', () =>
    json({ status: 'ok', synced_at: new Date().toISOString() }),
  ),
]
