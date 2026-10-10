/**
 * FE-10 · Scouting screen — /employer/positions/:id.
 *
 * Structure (FE2.md §FE-10):
 *  - position header (usePosition)
 *  - league shelves per grade (useLeagues, gap G7)
 *  - filters bar bound to the URL (useScoutingUrlState — URL is the single
 *    source of truth; reload restores everything incl. drawer `?c=`)
 *  - ranked candidate pool (usePositionPool; client-side fallback when the
 *    BE ignores filters — gap G8)
 *  - shortlist tray, resilient to filter changes (gap G16)
 *  - candidate drawer with gated contacts (gap G9)
 *
 * The offer-send modal is FE-11 and intentionally not wired here.
 */
import { useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'

import { useLeagues, usePosition, usePositionPool, useShortlistToggle } from '@/api/scouting'
import type { Grade, PoolItemView } from '@/api/types'
import { GRADE_LABEL, SALARY_TYPE_LABEL, SPEC_LABEL, WORK_FORMAT_LABEL } from '@/lib/labels'
import { formatSalary } from '@/components/domain/salary-tag'
import { ScoreBar } from '@/components/domain/score-bar'
import { TalentRow } from '@/components/domain/talent-row'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton, Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { CandidateDrawer } from '@/features/scouting/candidate-drawer'
import { FiltersBar } from '@/features/scouting/filters-bar'
import { collectShortlist, ShortlistTray } from '@/features/scouting/shortlist-tray'
import { useScoutingUrlState } from '@/features/scouting/url-state'

const PAGE_SIZE = 5

export function ScoutingPage() {
  const { id: positionId = '' } = useParams<{ id: string }>()
  const { filters, setFilters, setPage, setCandidate, resetFilters } =
    useScoutingUrlState(positionId)

  const { data: position, isLoading: posLoading, isError: posError, refetch: refetchPosition } =
    usePosition(positionId)

  const { data: shelves } = useLeagues(position?.specialization)

  const pool = usePositionPool(positionId, filters)
  const toggle = useShortlistToggle(positionId)
  const qc = useQueryClient()

  // Tray survives filters: rebuilt from every cached pool query on each render.
  const trayItems = collectShortlist(positionId, qc)

  const items = pool.data?.items ?? []
  const total = pool.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const page = Math.min(filters.page, pageCount)
  const pageItems: PoolItemView[] = pool.data
    ? items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
    : []

  const onToggleShortlist = (publicId: string) => {
    const item = items.find((i) => i.talent.public_id === publicId)
    toggle.mutate({ publicId, add: !item?.shortlisted })
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-6">
      {/* --- position header ------------------------------------------------ */}
      {posLoading ? (
        <header className="flex flex-col gap-2">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </header>
      ) : posError ? (
        <ErrorState
          title="Не удалось загрузить вакансию"
          description="Проверьте, что ссылка верна, и попробуйте ещё раз."
          onRetry={() => void refetchPosition()}
        />
      ) : position ? (
        <header className="flex flex-col gap-1.5">
          <h1 className="text-xl font-bold">{position.title}</h1>
          <p className="text-sm text-muted-foreground">
            {position.company} · {SPEC_LABEL[position.specialization] ?? position.specialization}
            {position.location && <> · {position.location}</>}
          </p>
          <p className="text-sm tabular-nums">
            {formatSalary(position.salary_min)} – {formatSalary(position.salary_max)} ₽{' '}
            <span className="text-muted-foreground">
              ({SALARY_TYPE_LABEL[position.salary_type] ?? position.salary_type})
            </span>
          </p>
          {(position.work_formats?.length ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground">
              Формат: {position.work_formats!.map((f) => WORK_FORMAT_LABEL[f] ?? f).join(', ')}
            </p>
          )}
        </header>
      ) : null}

      {/* --- league shelves (G7) -------------------------------------------- */}
      <section aria-label="Лиги" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(['intern', 'junior', 'middle', 'senior'] as Grade[]).map((g) => {
          const shelf = shelves?.find((s) => s.grade === g)
          const active = filters.grades.includes(g)
          return (
            <button
              key={g}
              type="button"
              aria-pressed={active}
              onClick={() =>
                setFilters({
                  grades: active ? filters.grades.filter((x) => x !== g) : [...filters.grades, g],
                  preset: undefined,
                })
              }
              className={`flex flex-col gap-1 rounded-xl border p-3 text-left transition-colors ${
                active
                  ? 'border-[var(--fsp-accent)] bg-[var(--fsp-accent)]/10'
                  : 'border-border bg-card hover:border-foreground/40'
              }`}
            >
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {GRADE_LABEL[g]}
              </span>
              {shelf ? (
                <>
                  <span className="text-lg font-bold tabular-nums">
                    {shelf.confirmed + shelf.unconfirmed}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    подтверждено: {shelf.confirmed} · без подтв.: {shelf.unconfirmed}
                  </span>
                  {typeof shelf.median_expectation === 'number' && (
                    <span className="text-xs tabular-nums text-muted-foreground">
                      медиана: {formatSalary(shelf.median_expectation)} ₽
                    </span>
                  )}
                </>
              ) : (
                <Skeleton className="h-6 w-16" />
              )}
            </button>
          )
        })}
      </section>

      {/* --- filters ---------------------------------------------------------- */}
      <FiltersBar
        filters={filters}
        setFilters={setFilters}
        resetFilters={resetFilters}
        shelves={shelves}
        clientFiltered={pool.data?.clientFiltered}
      />

      {/* --- pool list -------------------------------------------------------- */}
      <main aria-label="Кандидаты" className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Пул кандидатов
            {pool.data && (
              <span className="ml-2 tabular-nums text-foreground">
                {total} {plural(total, ['кандидат', 'кандидата', 'кандидатов'])}
              </span>
            )}
          </h2>
          {pool.isFetching && !pool.isLoading && (
            <span className="text-xs text-muted-foreground">обновляем…</span>
          )}
        </div>

        {pool.isLoading ? (
          <RowSkeleton count={4} />
        ) : pool.isError ? (
          <ErrorState
            title="Список кандидатов не загрузился"
            description="Проблемы с сетью или сервером. Попробуйте ещё раз."
            onRetry={() => void pool.refetch()}
          />
        ) : pageItems.length === 0 ? (
          <EmptyState
            title="Под фильтры никто не подошёл"
            description="Попробуйте ослабить условия: убрать «только подтверждённые», расширить зарплату или снять навыки."
            action={
              <Button variant="outline" onClick={resetFilters}>
                Сбросить фильтры
              </Button>
            }
          />
        ) : (
          pageItems.map((item) => (
            <div key={item.talent.public_id} className="flex flex-col gap-2">
              {/* clicking anywhere on the row opens the drawer (?c=); the
                  star button stops propagation inside TalentRow consumers */}
              <div onClick={() => setCandidate(item.talent.public_id)}>
                <TalentRow
                  talent={item.talent}
                  score={item.score}
                  reasons={item.reasons}
                  gaps={item.gaps}
                  shortlisted={item.shortlisted}
                  onToggleShortlist={onToggleShortlist}
                  className="cursor-pointer"
                />
                <div className="px-4 pb-1">
                  <ScoreBar score={item.score} components={item.components} />
                </div>
              </div>
            </div>
          ))
        )}

        {/* pagination — page lives in the URL (?page=) */}
        {pool.data && pageCount > 1 && (
          <nav aria-label="Пагинация" className="mt-2 flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              Назад
            </Button>
            <span className="text-sm tabular-nums text-muted-foreground">
              {page} / {pageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pageCount}
              onClick={() => setPage(page + 1)}
            >
              Вперёд
            </Button>
          </nav>
        )}
      </main>

      {/* --- shortlist tray --------------------------------------------------- */}
      <ShortlistTray
        items={trayItems}
        onOpenCandidate={(id) => setCandidate(id)}
        onRemove={(id) => toggle.mutate({ publicId: id, add: false })}
      />

      {/* --- candidate drawer (?c=) ------------------------------------------- */}
      {filters.candidate && (
        <CandidateDrawer
          publicId={filters.candidate}
          poolTalent={items.find((i) => i.talent.public_id === filters.candidate)?.talent}
          onClose={() => setCandidate(undefined)}
        />
      )}
    </div>
  )
}

/** Russian plural forms: 1 кандидат / 2-4 кандидата / 5+ кандидатов. */
function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1]
  return forms[2]
}
