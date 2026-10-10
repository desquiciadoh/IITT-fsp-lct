import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { isOfferConflict, useOffers, useWithdrawOffer } from '@/api/offers'
import { useLiveEvents, POLLING_INTERVAL_MS } from '@/api/events'
import { OFFER_STATUS_LABEL, SALARY_TYPE_LABEL } from '@/lib/labels'
import { formatDate, formatSalaryRange } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { Offer, OfferStatus } from '@/api/types'
import { SendOfferModal } from './send-offer-modal'

/**
 * FE-11 · Employer offers board (`/employer/offers`).
 * GET /api/offers?status= returns a flat array — we group it into the nine
 * status columns here. Live updates: SSE events when healthy, 10 s polling
 * fallback while SSE is broken (B14).
 */

const BOARD_STATUSES: OfferStatus[] = [
  'sent',
  'viewed',
  'accepted',
  'declined',
  'withdrawn',
  'expired',
  'interview',
  'hired',
  'closed',
]

/** G10: employer payload has no candidate identity yet — read the mocked `talent` or fall back. */
export function candidateNameOf(offer: Offer): string {
  const talent = (offer as Offer & { talent?: { display_name?: string } }).talent
  return talent?.display_name || offer.candidate_contacts?.full_name || 'Кандидат скрыт (G10)'
}

export function canWithdraw(offer: Offer): boolean {
  return offer.status === 'sent' || offer.status === 'viewed'
}

/** B16: contacts are exposed only while accepted; BE will switch this to the grant later. */
export function contactsVisible(offer: Offer): boolean {
  return offer.status === 'accepted' && Boolean(offer.candidate_contacts)
}

export function groupByStatus(offers: Offer[]): Record<OfferStatus, Offer[]> {
  const grouped = Object.fromEntries(BOARD_STATUSES.map((s) => [s, [] as Offer[]])) as Record<
    OfferStatus,
    Offer[]
  >
  for (const offer of offers) {
    const bucket = grouped[offer.status]
    if (bucket) bucket.push(offer)
  }
  return grouped
}

function OfferCard({ offer }: { offer: Offer }) {
  const client = useQueryClient()
  const withdraw = useWithdrawOffer()
  const [conflictNote, setConflictNote] = useState<string | null>(null)

  const onWithdraw = () => {
    setConflictNote(null)
    withdraw.mutate(
      { id: offer.id, version: offer.version },
      {
        onError: (error) => {
          // FE-11: on 409 version_conflict / invalid_transition — refetch the board.
          if (isOfferConflict(error)) {
            setConflictNote('Оффер уже изменился — доска обновлена.')
            void client.invalidateQueries({ queryKey: ['offers'] })
          } else {
            setConflictNote('Не удалось отозвать оффер. Попробуйте ещё раз.')
          }
        },
      },
    )
  }

  return (
    <li className="rounded-md border border-border bg-card p-3 text-sm shadow-sm">
      <p className="font-medium">{offer.title}</p>
      <p className="mt-0.5 text-muted-foreground">{candidateNameOf(offer)}</p>
      <p className="mt-1">
        {formatSalaryRange(offer.salary_min, offer.salary_max)}{' '}
        <span className="text-xs text-muted-foreground">
          ({SALARY_TYPE_LABEL[offer.salary_type]})
        </span>
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Отправлен: {formatDate(offer.created_at)}
        {offer.expires_at ? ` · до ${formatDate(offer.expires_at)}` : ''}
      </p>

      {contactsVisible(offer) && offer.candidate_contacts && (
        <div className="mt-2 rounded-md bg-muted/60 p-2 text-xs">
          <p className="font-medium">Контакты кандидата</p>
          <p>{offer.candidate_contacts.full_name}</p>
          {offer.candidate_contacts.email && <p>Email: {offer.candidate_contacts.email}</p>}
          {offer.candidate_contacts.phone && <p>Телефон: {offer.candidate_contacts.phone}</p>}
          {offer.candidate_contacts.telegram && (
            <p>Telegram: {offer.candidate_contacts.telegram}</p>
          )}
        </div>
      )}

      {canWithdraw(offer) && (
        <Button
          size="sm"
          variant="outline"
          className="mt-2"
          onClick={onWithdraw}
          disabled={withdraw.isPending}
        >
          {withdraw.isPending ? 'Отзываем…' : 'Отозвать'}
        </Button>
      )}
      {conflictNote && <p className="mt-1 text-xs text-destructive">{conflictNote}</p>}
    </li>
  )
}

/** Placeholder until FE-10 pool lands on this branch — swap for the real picker import. */
export function CandidateSelectorStub({
  value,
  onChange,
}: {
  value: { public_id: string; display_name?: string } | null
  onChange: (candidate: { public_id: string; display_name?: string } | null) => void
}) {
  const DEMO = [
    { public_id: 'pub-anna', display_name: 'Анна Петрова' },
    { public_id: 'pub-maria', display_name: 'Мария Иванова' },
    { public_id: 'pub-unreachable', display_name: 'Иван Скрыт (недоступен для оффера)' },
  ]
  return (
    <label className="block text-sm">
      Кандидат из пула (заглушка до интеграции с FE-10)
      <select
        value={value?.public_id ?? ''}
        onChange={(e) => {
          const next = DEMO.find((c) => c.public_id === e.target.value) ?? null
          onChange(next)
        }}
        className="mt-1 w-full max-w-sm rounded-md border border-border bg-background px-3 py-2 text-sm"
      >
        <option value="">— выберите кандидата —</option>
        {DEMO.map((c) => (
          <option key={c.public_id} value={c.public_id}>
            {c.display_name}
          </option>
        ))}
      </select>
    </label>
  )
}

export function OffersBoardPage() {
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [modalOpen, setModalOpen] = useState(false)
  const [candidate, setCandidate] = useState<{ public_id: string; display_name?: string } | null>(
    null,
  )

  useLiveEvents(true)
  const { data: offers = [], isLoading, isError, refetch } = useOffers(
    statusFilter,
    'employer',
  )
  const grouped = groupByStatus(offers)

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Доска офферов</h1>
          <p className="text-sm text-muted-foreground">
            Live-обновления: события SSE, при их недоступности — опрос каждые{' '}
            {POLLING_INTERVAL_MS / 1000} с (B14).
          </p>
        </div>
        <Button onClick={() => setModalOpen(true)}>Отправить оффер</Button>
      </header>

      <div className="flex max-w-lg items-end gap-3">
        <CandidateSelectorStub value={candidate} onChange={setCandidate} />
      </div>

      <div className="flex flex-wrap gap-2 text-sm">
        {['all', ...BOARD_STATUSES].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1 ${
              statusFilter === s
                ? 'border-primary bg-primary/10 font-medium'
                : 'border-border bg-background'
            }`}
          >
            {s === 'all' ? 'Все' : OFFER_STATUS_LABEL[s]}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загружаем доску…</p>}
      {isError && (
        <div className="flex items-center gap-3">
          <p className="text-sm text-destructive">Не удалось загрузить офферы.</p>
          <Button size="sm" variant="outline" onClick={() => void refetch()}>
            Повторить
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-4">
        {BOARD_STATUSES.filter((s) => statusFilter === 'all' || statusFilter === s).map((s) => (
          <section key={s} aria-label={OFFER_STATUS_LABEL[s]} className="rounded-lg bg-muted/40 p-3">
            <h2 className="mb-2 flex items-center gap-2 text-sm font-medium">
              {OFFER_STATUS_LABEL[s]}
              <Badge variant="secondary">{grouped[s].length}</Badge>
            </h2>
            <ul className="space-y-2">
              {grouped[s].map((offer) => (
                <OfferCard key={offer.id} offer={offer} />
              ))}
              {grouped[s].length === 0 && (
                <li className="text-xs text-muted-foreground">Пусто</li>
              )}
            </ul>
          </section>
        ))}
      </div>

      <SendOfferModal
        open={modalOpen}
        candidate={candidate}
        onClose={() => setModalOpen(false)}
      />
    </div>
  )
}
