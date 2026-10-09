import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, Check, X } from 'lucide-react'
import { useOffer, useOfferAction, isOfferConflict } from '@/api/offers'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { useCountdown } from '@/lib/hooks/useCountdown'
import { formatDate, formatDateTime, formatDuration } from '@/lib/format'
import { CONTACT_CHANNEL_LABEL, DECLINE_REASON_LABEL, OFFER_STATUS_LABEL } from '@/lib/labels'
import { SalaryTag } from '@/components/domain/salary-tag'
import { StatusChip } from '@/components/domain/status-chip'
import { TrustBadge } from '@/components/domain/trust-badge'
import { ReasonChips } from '@/components/domain/reason-chips'
import { ErrorState } from '@/components/domain/states'
import { CardSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { DeclineModal } from '@/features/offers/decline-modal'
import type { DeclineReason, Offer } from '@/api/types'

function Expiry({ offer }: { offer: Offer }) {
  const { remainingMs, expired } = useCountdown(offer.expires_at)
  if (!offer.expires_at || expired) return null
  return (
    <span className="text-xs text-muted-foreground">
      Оффер действует ещё {formatDuration(remainingMs)}
    </span>
  )
}

/** FE-07: offer detail with view / accept / decline state machine. */
export function OfferDetailPage() {
  const { id = '' } = useParams()
  const { data: offer, isLoading, isError, error, refetch } = useOffer(id)
  const view = useOfferAction('view')
  const accept = useOfferAction('accept')
  const decline = useOfferAction('decline')
  const [declineOpen, setDeclineOpen] = useState(false)
  const [viewError, setViewError] = useState<ApiError | null>(null)
  const autoViewed = useRef<string | null>(null)
  const viewRetries = useRef(0)

  const onError = useCallback((err: unknown) => {
    if (isOfferConflict(err)) {
      toast.error('Оффер изменился — данные обновлены, повторите действие')
      void refetch()
      return
    }
    toast.error(
      err instanceof ApiError ? errorMessage(err.code, err.detail) : 'Не удалось выполнить действие',
    )
  }, [refetch])

  useEffect(() => {
    if (!offer || offer.status !== 'sent' || viewError) return
    if (autoViewed.current === offer.id) return
    autoViewed.current = offer.id
    view.mutate(
      { id: offer.id, body: { version: offer.version } },
      {
        onError: (err) => {
          // A version conflict means the offer moved on: refetch and retry once.
          if (isOfferConflict(err) && viewRetries.current < 1) {
            viewRetries.current += 1
            autoViewed.current = null
            toast.error('Оффер изменился — обновляем данные')
            void refetch()
            return
          }
          setViewError(
            err instanceof ApiError
              ? err
              : new ApiError({ status: 0, code: 'api_error', detail: 'Не удалось открыть оффер' }),
          )
        },
      },
    )
  }, [offer, view, refetch, viewError])

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl">
        <CardSkeleton />
      </div>
    )
  }
  if (isError || !offer) {
    return (
      <ErrorState
        code={error instanceof ApiError ? error.code : undefined}
        onRetry={() => void refetch()}
      />
    )
  }

  const showContacts =
    Boolean(offer.candidate_contacts) && ['accepted', 'interview', 'hired'].includes(offer.status)
  const channels: string[] = []
  if (offer.contact_channel && offer.contact_value) {
    const channel = CONTACT_CHANNEL_LABEL[offer.contact_channel] ?? offer.contact_channel
    channels.push(`${channel}: ${offer.contact_value}`)
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <Link
        to="/candidate/offers"
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> К офферам
      </Link>

      <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6">
        <div className="flex items-center justify-between gap-3">
          <StatusChip status={offer.status} />
          <Expiry offer={offer} />
        </div>
        <div>
          <div className="text-xs uppercase text-muted-foreground">
            {offer.position ? offer.position : 'Оффер'}
          </div>
          <h1 className="mt-1 text-xl font-bold">{offer.title}</h1>
        </div>
        <SalaryTag
          min={offer.salary_min}
          max={offer.salary_max}
          type={offer.salary_type}
          emphasize
        />
        {offer.company && (
          <div className="flex items-center gap-2 text-sm">
            {offer.company.name}
            <TrustBadge level={offer.company.trust_level ?? 'none'} />
          </div>
        )}
        {offer.description && (
          <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
            {offer.description}
          </p>
        )}
        {offer.why_you && offer.why_you.length > 0 && (
          <div>
            <h2 className="mb-2 text-sm font-semibold">Почему вы</h2>
            <ReasonChips reasons={offer.why_you} />
          </div>
        )}
        {offer.decline_reason && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
            <span className="font-medium">
              Отклонён: {DECLINE_REASON_LABEL[offer.decline_reason] ?? offer.decline_reason}
            </span>
            {offer.decline_comment && (
              <p className="mt-1 text-xs text-muted-foreground">{offer.decline_comment}</p>
            )}
          </div>
        )}
        {showContacts && offer.candidate_contacts && (
          <div className="rounded-lg border border-border p-3 text-sm">
            <span className="font-medium">Контакты открыты</span>
            <p className="mt-1 text-xs text-muted-foreground">
              {[
                offer.candidate_contacts.full_name,
                offer.candidate_contacts.email,
                offer.candidate_contacts.phone,
                offer.candidate_contacts.telegram,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
            {channels.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">{channels.join(' · ')}</p>
            )}
          </div>
        )}
        <p className="text-xs text-muted-foreground">Обновлён: {formatDateTime(offer.updated_at)}</p>
      </section>

      <section className="flex flex-wrap items-center gap-3">
        {viewError && (
          <div className="w-full">
            <ErrorState
              title="Не удалось открыть оффер"
              code={viewError.code}
              description={errorMessage(viewError.code, viewError.detail)}
              onRetry={() => {
                viewRetries.current = 0
                autoViewed.current = null
                setViewError(null)
              }}
            />
          </div>
        )}
        {!viewError && offer.status === 'viewed' && (
          <>
            <Button
              onClick={() => accept.mutate({ id: offer.id, body: { version: offer.version } }, { onError })}
              disabled={accept.isPending}
            >
              <Check className="h-4 w-4" />
              {accept.isPending ? 'Принимаем…' : 'Принять'}
            </Button>
            <Button
              variant="destructive"
              onClick={() => setDeclineOpen(true)}
              disabled={decline.isPending}
            >
              <X className="h-4 w-4" /> Отклонить
            </Button>
          </>
        )}
        {!viewError && offer.status === 'sent' && (
          <span className="text-sm text-muted-foreground">Открываем оффер…</span>
        )}
        {['accepted', 'interview', 'hired'].includes(offer.status) && (
          <span className="text-sm text-muted-foreground">
            Оффер принят {formatDate(offer.updated_at)} — работодатель получил ваши контакты.
          </span>
        )}
        {['declined', 'withdrawn', 'expired', 'closed'].includes(offer.status) && (
          <span className="text-sm text-muted-foreground">
            Действий недоступно: статус «{OFFER_STATUS_LABEL[offer.status] ?? offer.status}».
          </span>
        )}
      </section>

      <DeclineModal
        open={declineOpen}
        pending={decline.isPending}
        onClose={() => setDeclineOpen(false)}
        onConfirm={(reason: DeclineReason, comment: string) =>
          decline.mutate(
            { id: offer.id, body: { version: offer.version, reason, comment } },
            {
              onSuccess: () => {
                setDeclineOpen(false)
                toast.success('Оффер отклонён')
              },
              onError,
            },
          )
        }
      />
    </div>
  )
}
