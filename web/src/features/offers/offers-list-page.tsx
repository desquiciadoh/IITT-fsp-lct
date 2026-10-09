import { Link, useSearchParams } from 'react-router-dom'
import { useOffers } from '@/api/offers'
import { usePollingInterval } from '@/api/events'
import { cn } from '@/lib/utils'
import { OfferCard } from '@/components/domain/offer-card'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'

const FILTERS = [
  { id: 'all', label: 'все' },
  { id: 'sent', label: 'новые' },
  { id: 'viewed', label: 'просмотренные' },
  { id: 'accepted', label: 'принятые' },
  { id: 'declined', label: 'отклонённые' },
] as const

/** FE-07: offers inbox with a status filter (?status=). */
export function OffersListPage() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? 'all'
  const { data, isLoading, isError, refetch } = useOffers(status)
  const polling = usePollingInterval()

  const setStatus = (next: string) => {
    if (next === 'all') setParams({})
    else setParams({ status: next })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Офферы</h1>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Фильтр по статусу">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              role="tab"
              aria-selected={status === f.id}
              onClick={() => setStatus(f.id)}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm capitalize transition-colors',
                status === f.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground" aria-live="polite">
          {polling ? 'обновление каждые 10 с' : 'live'}
        </span>
      </div>

      {isLoading ? (
        <RowSkeleton count={3} />
      ) : isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title={status === 'all' ? 'Офферов пока нет' : 'Ничего не найдено'}
          description={
            status === 'all'
              ? 'Работодатели увидят вас в пуле и пришлют оффер с зарплатой первым делом.'
              : 'Попробуйте другой фильтр.'
          }
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {data.map((offer) => (
            <Link key={offer.id} to={`/candidate/offers/${offer.id}`}>
              <OfferCard offer={offer} viewer="candidate" />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
