import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { usePositions } from '@/api/employer'
import { ApiError } from '@/api/client'
import type { Position } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { RowSkeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { SalaryTag } from '@/components/domain/salary-tag'
import { StatusChip } from '@/components/domain/status-chip'
import { GRADE_LABEL, SPEC_LABEL } from '@/lib/labels'

/** FE-09 · Employer dashboard (`/employer`): positions list + offers summary. */
export function EmployerDashboardPage() {
  const { data: positions = [], isLoading, isError, error, refetch } = usePositions()

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Кабинет работодателя</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link to="/employer/offers">Офферы</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/employer/company">Компания</Link>
          </Button>
          <Button size="sm" asChild>
            <Link to="/employer/positions/new">
              <Plus className="mr-1 h-4 w-4" /> Новая вакансия
            </Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Вакансии</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <RowSkeleton count={3} />
          ) : isError ? (
            <ErrorState code={error instanceof ApiError ? error.code : undefined} onRetry={() => void refetch()} />
          ) : positions.length === 0 ? (
            <EmptyState
              title="Пока нет вакансий"
              description="Создайте первую — можно вставить текст описания, форма заполнится автоматически."
              action={
                <Button asChild>
                  <Link to="/employer/positions/new">Создать вакансию</Link>
                </Button>
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {positions.map((p) => (
                <PositionRow key={p.id} position={p} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <OffersSummary />
    </div>
  )
}

function PositionRow({ position: p }: { position: Position }) {
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <Link
        to={`/employer/positions/${p.id}`}
        className="flex flex-col gap-1 rounded-md py-1 transition-colors hover:bg-accent/50 sm:flex-row sm:items-center sm:justify-between"
      >
        <span className="flex flex-col">
          <span className="font-medium">{p.title}</span>
          <span className="text-xs text-muted-foreground capitalize">
            {SPEC_LABEL[p.specialization]} · {p.grades.map((g) => GRADE_LABEL[g]).join(', ')}
          </span>
        </span>
        <span className="flex items-center gap-2">
          <StatusChip status={p.status ?? 'open'} />
          <SalaryTag min={p.salary_min} max={p.salary_max} type={p.salary_type} />
        </span>
      </Link>
    </li>
  )
}

/** Offers summary card — the full board is FE-11 (`/employer/offers`). */
function OffersSummary() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Офферы</CardTitle>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>Статусы отправленных офферов и ответы кандидатов — на доске офферов.</span>
        <Button variant="outline" size="sm" asChild>
          <Link to="/employer/offers">К офферам</Link>
        </Button>
      </CardContent>
    </Card>
  )
}
