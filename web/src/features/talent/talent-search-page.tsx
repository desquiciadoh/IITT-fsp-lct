import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { TalentShort } from '@/api/types'
import { keys } from '@/api/keys'
import { usePositions } from '@/api/employer'
import { useShortlistTray, useTalentSearch, useToggleShortlist } from '@/api/scouting'
import { useScoutingFilters, needsClientFiltering, POOL_PAGE_SIZE } from '@/features/scouting/filters'
import { applyClientSearch, resolveFacets } from '@/features/talent/search'
import { FilterPanel } from '@/features/scouting/filter-panel'
import { ShortlistTray } from '@/features/scouting/shortlist-tray'
import { TalentDrawer } from '@/features/scouting/talent-drawer'
import { SendOfferModal } from '@/features/employer/send-offer-modal'
import { TalentRow } from '@/components/domain/talent-row'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { ApiError } from '@/api/client'

/**
 * FE-12 · Talent search (`/employer/talent`) — plain pool search without a
 * position context (no scoring / ScoreBar / reasons).
 *
 * Reuses the whole FE-10 stack: URL-synced filters (useScoutingFilters is a
 * pure hook over search params), FilterPanel, TalentRow, TalentDrawer and the
 * shortlist machinery. The target contract is
 * GET /api/talent/search → {items, total, page} (+ pages/facets, gaps G8/G14):
 * capability detection everywhere — server facets win when present; otherwise
 * filtering and facet counts happen on the client (features/talent/search.ts).
 *
 * Shortlist & offers need a position id (the API is position-scoped). We take
 * it from `?p=<id>` (deep-linkable) or default to the first open position;
 * when there are no positions at all, shortlisting stays hidden rather than
 * broken. Drawer opens via `?c=<public_id>`, offer modal via `?offer=<id>` —
 * same URL-sync pattern as the pool tab, so reload restores the whole view.
 */
export function TalentSearchPage() {
  const [filters, setFilters] = useScoutingFilters()
  const [searchParams, setSearchParams] = useSearchParams()

  const positions = usePositions()
  const position =
    positions.data?.find((p) => String(p.id) === searchParams.get('p')) ??
    positions.data?.[0] ??
    null
  const positionId = position ? String(position.id) : ''

  const client = useQueryClient()
  const search = useTalentSearch(filters)
  const toggle = useToggleShortlist(positionId)
  const { tray, remove } = useShortlistTray(positionId)

  // Capability detection (G8/G14): facets in the response ⇒ server did it.
  const fallback = needsClientFiltering(search.data?.facets, filters)
  const view = fallback ? applyClientSearch(search.data, filters) : null
  const items = view ? view.items : (search.data?.items ?? [])
  const total = view ? view.total : (search.data?.total ?? 0)
  const page = view ? view.page : (search.data?.page ?? filters.page)
  const pages =
    view ? view.pages : (search.data?.pages ?? Math.max(1, Math.ceil(total / POOL_PAGE_SIZE)))
  const facets = resolveFacets(search.data, items)

  // Mirror any candidates explicitly flagged as shortlisted into the tray cache
  // without dropping existing candidates (talent search has no position context).
  const shortlistedIds = items.filter((t) => t.shortlisted).map((t) => t.public_id).join('|')
  useEffect(() => {
    if (!positionId || !search.data) return
    const explicitlyShortlisted = items.filter((t) => t.shortlisted === true)
    if (explicitlyShortlisted.length === 0) return
    client.setQueryData(keys.shortlist(positionId), (prev: TalentShort[] = []) => {
      const known = new Set(prev.map((t) => t.public_id))
      const toAdd = explicitlyShortlisted.filter((t) => !known.has(t.public_id))
      return toAdd.length > 0 ? [...prev, ...toAdd] : prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionId, shortlistedIds, search.data])

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(window.location.search)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next, { replace: true })
  }

  const offerPublicId = searchParams.get('offer')
  const offerCandidate =
    items.find((t) => t.public_id === offerPublicId) ??
    tray.data?.find((t) => t.public_id === offerPublicId) ??
    (offerPublicId ? { public_id: offerPublicId } : null)

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold">Поиск талантов</h1>
        <p className="text-sm text-muted-foreground">
          Поиск по всему пулу кандидатов: грейд лиги, подтверждённые скиллы, достижения ФСП.
        </p>
      </header>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <FilterPanel filters={filters} onChange={setFilters} facets={facets} />

          {search.isLoading ? (
            <div className="flex flex-col gap-2" aria-busy="true">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 rounded-xl" />
              ))}
            </div>
          ) : search.isError ? (
            <ErrorState
              code={search.error instanceof ApiError ? search.error.code : undefined}
              description="Не удалось выполнить поиск по кандидатам."
              onRetry={() => void search.refetch()}
            />
          ) : items.length === 0 ? (
            <EmptyState
              title="Под фильтры никто не подошёл"
              description="Попробуйте смягчить требования или сбросить фильтры."
            />
          ) : (
            <>
              <p className="text-xs text-muted-foreground" role="status">
                Найдено кандидатов: {total}
                {fallback &&
                  ' · фильтры применены на клиенте (бэкенд ещё не поддерживает G8)'}
              </p>
              <ul className="flex flex-col gap-3">
                {items.map((talent) => (
                  <li key={talent.public_id}>
                    <div className="flex items-center gap-1">
                      <div
                        role="button"
                        tabIndex={0}
                        className="min-w-0 flex-1 text-left cursor-pointer"
                        onClick={() => setParam('c', talent.public_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            setParam('c', talent.public_id)
                          }
                        }}
                        aria-label={`Открыть карточку ${talent.display_name ?? talent.public_id}`}
                      >
                        <TalentRow
                          talent={talent}
                          shortlisted={tray.data?.some((t) => t.public_id === talent.public_id)}
                          onToggleShortlist={
                            positionId
                              ? (publicId) => {
                                  const listed = tray.data?.some((t) => t.public_id === publicId)
                                  toggle.mutate({ publicId, add: !listed, talent })
                                }
                              : undefined
                          }
                          className="border-0 hover:bg-transparent"
                        />
                      </div>
                      {positionId && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setParam('offer', talent.public_id)}
                        >
                          Оффер
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>

              {pages > 1 && (
                <nav className="flex items-center justify-between" aria-label="Пагинация">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setFilters({ page: page - 1 })}
                  >
                    <ChevronLeft className="mr-1 h-4 w-4" /> Назад
                  </Button>
                  <span className="text-sm tabular-nums text-muted-foreground">
                    {page} / {pages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= pages}
                    onClick={() => setFilters({ page: page + 1 })}
                  >
                    Вперёд <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                </nav>
              )}
            </>
          )}
        </div>

        {positionId && (
          <div className="w-full shrink-0 lg:w-80 lg:sticky lg:top-4">
            <ShortlistTray
              talents={tray.data ?? []}
              onSelect={(publicId) => setParam('c', publicId)}
              onRemove={(publicId) => {
                toggle.mutate({ publicId, add: false })
                remove(publicId)
              }}
            />
          </div>
        )}
      </div>

      {positionId && (
        <>
          <TalentDrawer
            positionId={positionId}
            onOpenOffer={(publicId) => setParam('offer', publicId)}
          />
          {/* FE-11 reuse: send an offer straight from search results. */}
          <SendOfferModal
            positionId={positionId}
            position={position ?? undefined}
            candidate={offerCandidate}
            open={Boolean(offerPublicId)}
            onClose={() => setParam('offer', null)}
          />
        </>
      )}
    </div>
  )
}
