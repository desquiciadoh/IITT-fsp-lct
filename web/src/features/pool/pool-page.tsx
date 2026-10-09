import { useState } from 'react'
import { usePositionPool } from '@/api/pool'
import { EmptyState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'
import { rankedPool } from '@/features/pool/rank'
import { WeightPanel } from '@/features/pool/components/weight-panel'
import { RelaxationsPanel } from '@/features/pool/components/relaxations-panel'
import { HealthPanel } from '@/features/pool/components/health-panel'
import { PoolRow } from '@/features/pool/components/pool-row'
import type { PoolWeights } from '@/api/types'

/** FE-17 preview: the scouting payload slot for FE2's position page (FE-10). */
export function PoolPage() {
  const { data: pool, isLoading, isError } = usePositionPool('pos-1')
  const [weights, setWeights] = useState<PoolWeights | null>(null)

  if (isLoading) return <RowSkeleton count={4} />
  if (isError || !pool) return <EmptyState title="Пул не загружен" description="Попробуйте позже." />

  const activeWeights = weights ?? pool.weights
  const ranked = rankedPool(pool.candidates, activeWeights)

  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Работодатель · скутинг
        </span>
        <h1 className="text-2xl font-bold">Senior Backend Engineer</h1>
        <p className="text-sm text-muted-foreground">
          Пул позиции пос-1 · слот для страницы вакансии (FE2, FE-10). Слайдеры пере-ранжируют пул
          без запроса.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <aside className="flex flex-col gap-4">
          <WeightPanel
            weights={activeWeights}
            onChange={(next) => setWeights(next)}
          />
          <RelaxationsPanel relaxations={pool.relaxations} />
          <HealthPanel health={pool.health} />
        </aside>

        <ul aria-label="Ранжированный пул" className="flex flex-col gap-3">
          {ranked.map((item) => (
            <PoolRow key={item.candidate.public_id} item={item} />
          ))}
        </ul>
      </div>
    </section>
  )
}