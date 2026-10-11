import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Mail, Phone, User, AtSign, RefreshCw } from 'lucide-react'
import type { Offer, OfferStatus } from '@/api/types'
import { isOfferConflict, useOffers, useWithdrawOffer } from '@/api/offers'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { RowSkeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { SalaryTag } from '@/components/domain/salary-tag'
import { OFFER_STATUS_LABEL } from '@/lib/labels'

/**
 * FE-11 · Employer offers board (`/employer/offers`).
 *
 * - One column per offer status — all 9 values of OfferStatusEnum (the board
 *   stays honest even when a column is empty);
 * - live updates via the 10 s polling already built into `useOffers` (B14);
 * - Withdraw only while `sent` / `viewed`; on 409 (`version_conflict` /
 *   `invalid_transition`) we refetch the board — our copy is stale;
 * - contacts panel appears for `accepted` offers (offer.candidate_contacts,
 *   B16) — this is the payoff of "send → accept → contacts";
 * - G10 caveat: employer-side payloads carry no candidate identity beyond
 *   `candidate_public_id`, so cards show that id and a link into scouting.
 */

// All nine statuses from OfferStatusEnum, in funnel order.
const BOARD_COLUMNS: readonly OfferStatus[] = [
  'sent',
  'viewed',
  'accepted',
  'declined',
  'withdrawn',
  'expired',
  'interview',
  'hired',
  'closed',
] as const

const WITHDRAWABLE: readonly OfferStatus[] = ['sent', 'viewed'] as const

const fmtDate = (iso?: string | null): string => {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ru-RU')
}

function OfferCard({ offer }: { offer: Offer }) {
  const client = useQueryClient()
  const withdraw = useWithdrawOffer()
  const [conflict, setConflict] = useState(false)
  const canWithdraw = WITHDRAWABLE.includes(offer.status)

  const onWithdraw = () => {
    withdraw.mutate(
      { id: offer.id, version: offer.version },
      {
        onSuccess: () => setConflict(false),
        onError: (err) => {
          if (isOfferConflict(err)) {
            // Our local version/status is stale — refetch the whole board.
            setConflict(true)
            void client.invalidateQueries({ queryKey: ['offers'] })
          }
        },
      },
    )
  }

  return (
    <li>
      <Card className="gap-2 p-3">
        <CardContent className="p-0">
          <div className="flex items-start justify-between gap-2">
            <p className="min-w-0 truncate text-sm font-medium" title={offer.title}>
              {offer.title}
            </p>
            <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
              {OFFER_STATUS_LABEL[offer.status] ?? offer.status}
            </span>
          </div>

          <SalaryTag min={offer.salary_min} max={offer.salary_max} type={offer.salary_type} />

          {/* G10: no name/avatar in employer payloads — only the public id. */}
          <p className="mt-1 text-xs text-muted-foreground">
            Кандидат:{' '}
            <code className="rounded bg-muted px-1 py-0.5">{offer.candidate_public_id ?? 'не указан'}</code>
          </p>

          <dl className="mt-1 flex gap-3 text-[11px] text-muted-foreground tabular-nums">
            <div>
              <dt className="inline">Отправлен: </dt>
              <dd className="inline">{fmtDate(offer.created_at)}</dd>
            </div>
            <div>
              <dt className="inline">Истекает: </dt>
              <dd className="inline">{fmtDate(offer.expires_at)}</dd>
            </div>
          </dl>

          {/* B16 · contacts unlock after the candidate accepts the offer. */}
          {offer.status === 'accepted' && offer.candidate_contacts && (
            <ul className="mt-2 flex flex-col gap-1 rounded-lg border border-border bg-muted/40 p-2 text-xs">
              {offer.candidate_contacts.full_name && (
                <li className="flex items-center gap-1.5 font-medium">
                  <User className="h-3.5 w-3.5 text-muted-foreground" />
                  {offer.candidate_contacts.full_name}
                </li>
              )}
              {offer.candidate_contacts.email && (
                <li className="flex items-center gap-1.5">
                  <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                  <a className="underline underline-offset-2" href={`mailto:${offer.candidate_contacts.email}`}>
                    {offer.candidate_contacts.email}
                  </a>
                </li>
              )}
              {offer.candidate_contacts.phone && (
                <li className="flex items-center gap-1.5">
                  <Phone className="h-3.5 w-3.5 text-muted-foreground" />
                  <a className="underline underline-offset-2" href={`tel:${offer.candidate_contacts.phone}`}>
                    {offer.candidate_contacts.phone}
                  </a>
                </li>
              )}
              {offer.candidate_contacts.telegram && (
                <li className="flex items-center gap-1.5">
                  <AtSign className="h-3.5 w-3.5 text-muted-foreground" />
                  {offer.candidate_contacts.telegram}
                </li>
              )}
            </ul>
          )}

          {canWithdraw && (
            <div className="mt-2 flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={onWithdraw} disabled={withdraw.isPending}>
                Отозвать
              </Button>
              {conflict && (
                <span className="flex items-center gap-1 text-[11px] text-destructive" role="status">
                  <RefreshCw className="h-3 w-3" /> Оффер изменился — список обновлён
                </span>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </li>
  )
}

export function OffersBoardPage() {
  const [statusFilter, setStatusFilter] = useState<'all' | OfferStatus>('all')
  const offers = useOffers(statusFilter === 'all' ? undefined : statusFilter)

  // Bucket by status locally so columns always render (unknown statuses go
  // to `closed`-adjacent tail bucket defensively).
  const buckets = useMemo(() => {
    const map = new Map<OfferStatus, Offer[]>(BOARD_COLUMNS.map((s) => [s, []]))
    for (const o of offers.data ?? []) {
      const list = map.get(o.status)
      if (list) list.push(o)
      else map.set(o.status, [o])
    }
    return map
  }, [offers.data])

  const total = offers.data?.length ?? 0

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/employer">
              <ArrowLeft className="mr-1 h-4 w-4" /> Кабинет
            </Link>
          </Button>
          <h1 className="text-lg font-semibold">Офферы</h1>
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Статус
          <select
            className="rounded-md border border-border bg-background px-2 py-1 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'all' | OfferStatus)}
          >
            <option value="all">Все ({total})</option>
            {BOARD_COLUMNS.map((s) => (
              <option key={s} value={s}>
                {OFFER_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="text-xs text-muted-foreground" role="status" aria-live="polite">
        Обновляется автоматически каждые 10 секунд (B14).
      </p>

      {offers.isLoading ? (
        <RowSkeleton count={4} />
      ) : offers.isError ? (
        <ErrorState
          code={offers.error instanceof ApiError ? offers.error.code : undefined}
          description="Не удалось загрузить офферы."
          onRetry={() => void offers.refetch()}
        />
      ) : total === 0 ? (
        <EmptyState
          title="Пока нет офферов"
          description="Откройте пул кандидатов вакансии и отправьте первый оффер."
          action={
            <Button asChild>
              <Link to="/employer">К вакансиям</Link>
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {BOARD_COLUMNS.map((status) => {
            const items = buckets.get(status) ?? []
            return (
              <section key={status} aria-label={`Колонка: ${OFFER_STATUS_LABEL[status]}`}>
                <Card className="h-full">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center justify-between text-sm font-semibold">
                      {OFFER_STATUS_LABEL[status]}
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
                        {items.length}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    {items.length === 0 ? (
                      <p className="px-3 pb-3 text-xs text-muted-foreground">Пусто</p>
                    ) : (
                      <ul className="flex flex-col gap-2 px-3 pb-3">
                        {items.map((o) => (
                          <OfferCard key={o.id} offer={o} />
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
