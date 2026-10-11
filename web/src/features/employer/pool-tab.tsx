import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { Position, Spec } from '@/api/types'
import { usePool, useShortlistTray, useToggleShortlist } from '@/api/scouting'
import {
  applyClientFilters,
  deriveGaps,
  deriveRelaxations,
  needsClientFiltering,
  POOL_PAGE_SIZE,
  useAbsorbShortlist,
  useScoutingFilters,
} from '@/features/scouting/filters'
import { LeagueShelves } from '@/features/scouting/league-shelves'
import { FilterPanel } from '@/features/scouting/filter-panel'
import { ShortlistTray } from '@/features/scouting/shortlist-tray'
import { TalentDrawer } from '@/features/scouting/talent-drawer'
import { SendOfferModal } from '@/features/employer/send-offer-modal'
import { TalentRow } from '@/components/domain/talent-row'
import { ScoreBar } from '@/components/domain/score-bar'
import { AcceptanceBadge } from '@/components/domain/acceptance-badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { ApiError } from '@/api/client'
import { WeightControls } from '@/features/scouting/pool-power/weight-controls'
import { NeedHealthPanel } from '@/features/scouting/pool-power/need-health-panel'
import {
  PRESETS,
  isBalanced,
  rerank,
  type WeightProfile,
} from '@/features/scouting/pool-power/ranking'

/**
 * FE-10 · Scouting pool tab of `/employer/positions/:id`.
 *
 * Layout: league shelves (G7) → filter panel (URL-synced) → ranked rows
 * (TalentRow + ScoreBar + ReasonChips, gaps derived per G8) → pagination →
 * relaxation hints. The shortlist tray (G16) lives in the sidebar and
 * survives filter changes; the candidate drawer opens via `?c=<public_id>`,
 * so a reload restores filters + drawer from the URL alone.
 *
 * FE-11 · "Send offer" opens SendOfferModal through `?offer=<public_id>` —
 * URL-synced like the drawer, so a reload reopens the modal for the same
 * candidate.
 */
export function PoolTab({ positionId, specialization, position }: { positionId: string; specialization?: Spec; position?: Position }) {
  const [filters, setFilters] = useScoutingFilters()
  const [searchParams, setSearchParams] = useSearchParams()

  // FE-17 · live weight-based re-ranking (client-side, no request).
  const [weights, setWeights] = useState<WeightProfile>({ ...PRESETS[0].weights })
  const activeRanking = !isBalanced(weights)

  const pool = usePool(positionId, filters)
  const toggle = useToggleShortlist(positionId)
  const { tray, absorb, reconcile, remove } = useShortlistTray(positionId)

  // Server ignores filters today (G8): detect by absent `facets` and fall
  // back to client-side filtering with the same semantics + pagination.
  const fallback = needsClientFiltering(pool.data?.facets, filters)
  const view = fallback ? applyClientFilters(pool.data, filters) : null
  const items = view ? view.items : (pool.data?.items ?? [])
  const total = view ? view.total : (pool.data?.total ?? 0)
  const page = view ? view.page : (pool.data?.page ?? filters.page)
  const pages = view ? view.pages : (pool.data?.pages ?? Math.max(1, Math.ceil(total / POOL_PAGE_SIZE)))

  // Keep the tray cache in sync with every rendered batch (G16).
  useAbsorbShortlist(pool.data?.items, absorb, reconcile)

  const openCandidate = (publicId: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('c', publicId)
    setSearchParams(next, { replace: true })
  }

  // FE-11 · offer modal state lives in `?offer=<public_id>` (URL-synced).
  const offerPublicId = searchParams.get('offer')
  const setOfferParam = (publicId: string | null) => {
    const next = new URLSearchParams(window.location.search)
    if (publicId) next.set('offer', publicId)
    else next.delete('offer')
    setSearchParams(next, { replace: true })
  }
  const poolCandidate = pool.data?.items.find((i) => i.talent.public_id === offerPublicId)?.talent
  const trayCandidate = tray.data?.find((t) => t.public_id === offerPublicId)
  // G10: identity may be unknown (e.g. deep link after reload) — the modal
  // still works with just the public id.
  const offerCandidate = poolCandidate ?? trayCandidate ?? (offerPublicId ? { public_id: offerPublicId } : null)
  const onToggle = (publicId: string) => {
    const entry = items.find((i) => i.talent.public_id === publicId)
    const inShortlist = tray.data?.some((t) => t.public_id === publicId) ?? entry?.shortlisted ?? false
    toggle.mutate({ publicId, add: !inShortlist, talent: entry?.talent })
  }
  const relaxations = pool.data?.relaxations ?? deriveRelaxations(items)
  const ranked = rerank(items, weights)

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <LeagueShelves specialization={specialization} />
        <FilterPanel filters={filters} onChange={setFilters} facets={pool.data?.facets} />
        <WeightControls weights={weights} onChange={setWeights} />

        {pool.isLoading ? (
          <div className="flex flex-col gap-2" aria-busy="true">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))}
          </div>
        ) : pool.isError ? (
          <ErrorState
            code={pool.error instanceof ApiError ? pool.error.code : undefined}
            description="Не удалось загрузить пул кандидатов."
            onRetry={() => void pool.refetch()}
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
              {activeRanking && ' · пересортировано по весам (без запроса)'}
              {fallback && ' · фильтры применены на клиенте (бэкенд ещё не поддерживает G8)'}
            </p>
            <ul className="flex flex-col gap-3">
              {ranked.map(({ entry, score, components }) => {
                const gaps = deriveGaps(entry)
                const isShortlisted = tray.data?.some((t) => t.public_id === entry.talent.public_id) ?? entry.shortlisted
                return (
                  <li key={entry.talent.public_id}>
                    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-1 transition-colors hover:border-primary/40">
                      <div
                        role="button"
                        tabIndex={0}
                        className="cursor-pointer text-left"
                        onClick={() => openCandidate(entry.talent.public_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            openCandidate(entry.talent.public_id)
                          }
                        }}
                        aria-label={`Открыть карточку ${entry.talent.display_name ?? entry.talent.public_id}`}
                      >
                        <TalentRow
                          talent={entry.talent}
                          score={score}
                          reasons={entry.reasons}
                          shortlisted={isShortlisted}
                          onToggleShortlist={onToggle}
                          className="border-0 hover:bg-transparent"
                        />
                      </div>
                      <div className="flex flex-col gap-1 px-3 pb-2">
                        <div className="flex items-center justify-between gap-2">
                          <ScoreBar score={score} components={components} className="flex-1" />
                          <AcceptanceBadge value={entry.acceptance_likelihood} />
                        </div>
                        {gaps.length > 0 && (
                          <p className="mt-1.5 text-xs text-muted-foreground">
                            Пробелы: {gaps.join('; ')}
                          </p>
                        )}
                      </div>
                    </div>
                  </li>
                )
              })}
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

            {relaxations.length > 0 && (
              <section aria-label="Как расширить пул" className="rounded-xl border border-dashed border-border p-3">
                <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                  Как расширить пул
                </h3>
                <ul className="list-disc pl-4 text-sm text-muted-foreground">
                  {relaxations.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>

      <div className="w-full shrink-0 lg:w-80 lg:sticky lg:top-4">
        <ShortlistTray
          talents={tray.data ?? []}
          onSelect={(publicId) => {
            const next = new URLSearchParams(window.location.search)
            next.set('c', publicId)
            setSearchParams(next, { replace: true })
          }}
          onRemove={(publicId) => {
            toggle.mutate({ publicId, add: false })
            remove(publicId)
          }}
        />
        <NeedHealthPanel positionId={positionId} className="mt-4" />
      </div>

      <TalentDrawer positionId={positionId} onOpenOffer={(publicId) => setOfferParam(publicId)} />

      {/* FE-11 · Send Offer modal (?offer=<public_id>) */}
      <SendOfferModal
        positionId={positionId}
        position={position}
        candidate={offerCandidate}
        open={Boolean(offerPublicId)}
        onClose={() => setOfferParam(null)}
      />
    </div>
  )
}
