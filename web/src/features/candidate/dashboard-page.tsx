import { Link } from 'react-router-dom'
import { Search, Trophy, Zap } from 'lucide-react'
import { useOffers } from '@/api/offers'
import { useApplications } from '@/api/vacancies'
import { useProfile } from '@/api/profile'
import { useEligibility } from '@/api/assessments'
import { useCountdown } from '@/lib/hooks/useCountdown'
import { formatDuration } from '@/lib/format'
import { GRADE_LABEL, SPEC_LABEL } from '@/lib/labels'
import { LeagueBadge } from '@/components/domain/league-badge'
import { OfferCard } from '@/components/domain/offer-card'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { ApplicationStatusChip } from '@/components/domain/application-status-chip'
import { CardSkeleton, RowSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'

function CooldownLine({ deadline }: { deadline: string }) {
  const { remainingMs, expired } = useCountdown(deadline)
  if (expired) return <span className="text-sm text-muted-foreground">Кулдаун закончился — можно пробовать снова.</span>
  return (
    <span className="text-sm text-muted-foreground">
      Следующая попытка через {formatDuration(remainingMs)}
    </span>
  )
}

/** FE-07: candidate dashboard — status card + offers inbox. */
export function DashboardPage() {
  const { data: profile, isLoading: profileLoading } = useProfile()
  const spec = profile?.specialization || 'backend'
  const { data: eligibility } = useEligibility(spec)
  const { data: offers, isLoading, isError, refetch } = useOffers()
  const { data: applications } = useApplications()

  const league = profile?.league
  const cooldown = eligibility && !eligibility.can_start ? eligibility.next_attempt_at : null
  const fresh = (offers ?? []).slice(0, 3)

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-xl border border-border bg-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Ваш статус
            </span>
            {profileLoading ? (
              <CardSkeleton />
            ) : league ? (
              <LeagueBadge
                status={league.status}
                grade={league.grade}
                spec={league.specialization}
              />
            ) : (
              <span className="text-sm text-muted-foreground">
                Лига не открыта — пройдите квалификацию.
              </span>
            )}
            {league?.rating != null && (
              <span className="text-2xl font-extrabold tabular-nums">{league.rating}</span>
            )}
            {league?.percentile != null && (
              <span className="text-xs text-muted-foreground">
                {Math.round(league.percentile)}-й процентиль
              </span>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            {cooldown ? (
              <CooldownLine deadline={cooldown} />
            ) : (
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Zap className="h-4 w-4 text-[var(--fsp-accent)]" />
                Квалификация доступна
              </span>
            )}
            <Button asChild>
              <Link
                to={`/candidate/qualification/start?specialization=${encodeURIComponent(spec)}&claimed_grade=${encodeURIComponent(profile?.claimed_grade || league?.grade || 'middle')}`}
              >
                <Trophy className="h-4 w-4" />
                {league ? 'Пройти ещё раз' : 'Пройти квалификацию'}
              </Link>
            </Button>
          </div>
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          {SPEC_LABEL[spec]}
          {profile?.claimed_grade ? ` · заявлен ${GRADE_LABEL[profile.claimed_grade]}` : ''}
          {league ? ` · подтверждён ${GRADE_LABEL[league.grade]}` : ''}
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Ваши отклики</h2>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/candidate/vacancies">
              <Search className="h-4 w-4" /> Найти вакансии
            </Link>
          </Button>
        </div>
        {applications && applications.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {applications.map((application) => (
              <li
                key={application.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3"
              >
                <div className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium">{application.vacancy.title}</span>
                  <span className="text-xs text-muted-foreground">{application.vacancy.company.name}</span>
                </div>
                <ApplicationStatusChip status={application.status} />
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="Откликов пока нет"
            description="Найдите подходящую вакансию и отправьте отклик — статус будет виден здесь."
          />
        )}
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Входящие офферы</h2>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/candidate/offers">Все офферы</Link>
          </Button>
        </div>
        {isLoading ? (
          <RowSkeleton count={2} />
        ) : isError ? (
          <ErrorState onRetry={() => void refetch()} />
        ) : fresh.length === 0 ? (
          <EmptyState
            title="Офферов пока нет"
            description="Когда работодатель отправит оффер, он появится здесь — с зарплатой и причинами, почему вам подходит."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {fresh.map((offer) => (
              <Link key={offer.id} to={`/candidate/offers/${offer.id}`}>
                <OfferCard offer={offer} viewer="candidate" />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
