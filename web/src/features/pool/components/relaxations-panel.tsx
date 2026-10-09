import { Unlock } from 'lucide-react'
import type { Relaxation } from '@/api/types'

function plural(n: number) {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'кандидат'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'кандидата'
  return 'кандидатов'
}

/** FE-17 counterfactual hints: «убрать X → +N кандидатов». */
export function RelaxationsPanel({ relaxations }: { relaxations: Relaxation[] }) {
  if (relaxations.length === 0) return null
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <header className="text-sm font-semibold">Что расширить</header>
      {relaxations.map((relaxation) => (
        <p key={relaxation.label} className="flex items-start gap-2 text-sm">
          <Unlock className="mt-0.5 h-4 w-4 shrink-0 text-info" />
          <span>
            Убрать требование «{relaxation.label}» → <b>{relaxation.added_candidates}</b>{' '}
            {plural(relaxation.added_candidates)} в пуле.
          </span>
        </p>
      ))}
    </div>
  )
}