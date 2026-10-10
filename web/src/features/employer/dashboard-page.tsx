import { Link } from 'react-router-dom'
import { Briefcase, Mailbox, Plus, Users } from 'lucide-react'
import { isCompanyRequired, useCompany } from '@/api/companies'
import { useOffers } from '@/api/offers'
import { usePositions } from '@/api/positions'
import type { OfferStatus, Position, PositionStatus } from '@/api/types'
import type { SalaryType } from '@/features/employer/position-schema'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { RowSkeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { SalaryTag } from '@/components/domain/salary-tag'
import { TrustBadge } from '@/components/domain/trust-badge'
import { errorMessage } from '@/i18n/errors'
import { countOffersByStatus, sortPositions } from './dashboard-helpers'
import {
  GRADE_LABEL,
  OFFER_STATUS_LABEL,
  POSITION_STATUS_LABEL,
  SPEC_LABEL,
  WORK_FORMAT_LABEL,
} from '@/lib/labels'

/** Statuses shown in the summary tiles (FE2.md §FE-09: sent/viewed/accepted). */
const SUMMARY_STATUSES: OfferStatus[] = ['sent', 'viewed', 'accepted', 'declined']

/**
 * FE-09 · Stage 3 — employer dashboard (/employer).
 * Lists positions (GET /api/positions), shows an offers-by-status summary
 * (GET /api/offers, client-side aggregation until a stats endpoint exists)
 * and the "create position" CTA. B1/G17: without a company profile the
 * wizard stays locked and a banner links to /employer/company.
 */
export function EmployerDashboardPage() {
  const company = useCompany()
  const positions = usePositions()
  const offers = useOffers()

  // B1: GET /api/companies/me → 403 company_required means "no company yet".
  const noCompany = company.isError && isCompanyRequired(company.error)
  const hasCompany = Boolean(company.data)

  const offerCounts = countOffersByStatus(offers.data ?? [])

  const sortedPositions = positions.data ? sortPositions(positions.data) : undefined

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Кабинет работодателя</h1>
          <p className="text-sm text-muted-foreground">
            Вакансии, отклики и офферы в одном месте.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasCompany && company.data ? <TrustBadge level={company.data.trust_level} /> : null}
          <Button asChild disabled={!hasCompany}>
            <Link to="/employer/positions/new">
              <Plus className="h-4 w-4" />
              Создать новую вакансию
            </Link>
          </Button>
        </div>
      </div>

      {/* B1/G17: company profile is a prerequisite for publishing positions. */}
      {(noCompany || (company.isError && !hasCompany)) && (
        <Card className="border-warn/50 bg-warn/10">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-5 w-5 text-warn" />
              Сначала создайте профиль компании
            </CardTitle>
            <CardDescription>
              Без профиля компании нельзя публиковать вакансии и отправлять офферы.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild size="sm">
              <Link to="/employer/company">Создать компанию</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Positions list */}
      <section className="flex flex-col gap-3" aria-labelledby="positions-heading">
        <div className="flex items-center gap-2">
          <Briefcase className="h-5 w-5 text-muted-foreground" />
          <h2 id="positions-heading" className="text-lg font-semibold">
            Вакансии
          </h2>
          {positions.data ? (
            <Badge variant="secondary">{positions.data.length}</Badge>
          ) : null}
        </div>

        {positions.isPending ? (
          <RowSkeleton count={3} />
        ) : positions.isError ? (
          <ErrorState
            title="Не удалось загрузить вакансии"
            description={errorMessage(positions.error instanceof Error ? positions.error.message : undefined)}
            onRetry={() => void positions.refetch()}
          />
        ) : positions.data && positions.data.length === 0 ? (
          <EmptyState
            title="Вакансий пока нет"
            description="Создайте первую вакансию через мастер с парсингом описания."
            action={
              <Button asChild disabled={!hasCompany} size="sm">
                <Link to="/employer/positions/new">Создать вакансию</Link>
              </Button>
            }
          />
        ) : positions.data ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(sortedPositions ?? []).map((p) => (
              <PositionCard key={p.id} position={p} />
            ))}
          </div>
        ) : null}
      </section>

      {/* Offers summary (client-side aggregation; gap: no stats endpoint yet) */}
      <section className="flex flex-col gap-3" aria-labelledby="offers-heading">
        <div className="flex items-center gap-2">
          <Mailbox className="h-5 w-5 text-muted-foreground" />
          <h2 id="offers-heading" className="text-lg font-semibold">
            Офферы по статусам
          </h2>
        </div>

        {offers.isPending ? (
          <RowSkeleton count={2} />
        ) : offers.isError ? (
          <ErrorState
            title="Не удалось загрузить статистику офферов"
            description={errorMessage(offers.error instanceof Error ? offers.error.message : undefined)}
            onRetry={() => void offers.refetch()}
          />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {SUMMARY_STATUSES.map((status) => (
              <Card key={status}>
                <CardContent className="flex flex-col items-center gap-1 py-5">
                  <span className="text-2xl font-bold tabular-nums">
                    {offerCounts[status] ?? 0}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {OFFER_STATUS_LABEL[status]}
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

/** Simple position card for the dashboard grid (edit screen is stage 4). */
function PositionCard({ position }: { position: Position }) {
  const status: PositionStatus = position.status ?? 'open'
  return (
    <Card className="transition hover:border-primary/50">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="line-clamp-2 text-base">
            <Link
              to={`/employer/positions/${position.id}`}
              className="hover:underline underline-offset-4"
            >
              {position.title}
            </Link>
          </CardTitle>
          <Badge variant={status === 'open' ? 'success' : 'outline'}>
            {POSITION_STATUS_LABEL[status]}
          </Badge>
        </div>
        <CardDescription className="text-xs">
          {SPEC_LABEL[position.specialization]}
          {position.grades.length > 0 &&
            ` · ${position.grades.map((g) => GRADE_LABEL[g]).join(', ')}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <SalaryTag
          min={position.salary_min}
          max={position.salary_max}
          type={position.salary_type as SalaryType}
        />
        <div className="flex flex-wrap gap-1">
          {(position.work_formats ?? []).map((wf) => (
            <Badge key={wf} variant="info">
              {WORK_FORMAT_LABEL[wf]}
            </Badge>
          ))}
          {position.location ? <Badge variant="outline">{position.location}</Badge> : null}
        </div>
        <div className="text-xs text-muted-foreground">
          {!position.is_public && 'Приватный подбор · '}
          создана {new Date(position.created_at).toLocaleDateString('ru-RU')}
        </div>
      </CardContent>
    </Card>
  )
}
