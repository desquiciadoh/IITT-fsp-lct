import { useProfile } from '@/api/profile'
import { useVacancies } from '@/api/vacancies'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'
import { VacancyCard } from './components/vacancy-card'

/** FE-15: public vacancies list for candidates — salary first, league fit, apply. */
export function VacanciesPage() {
  const { data: profile } = useProfile()
  const { data: vacancies, isLoading, isError, refetch } = useVacancies()

  const league =
    profile?.league && profile.league.status === 'confirmed'
      ? { specialization: profile.league.specialization, grade: profile.league.grade }
      : undefined

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Открытые вакансии
        </span>
        <h1 className="text-2xl font-bold">Вакансии партнёров</h1>
        <p className="text-sm text-muted-foreground">
          Отклик открывает контакты для работодателя — оффер с зарплатой приходит только после
          согласования.
        </p>
      </header>

      {isLoading ? (
        <RowSkeleton count={4} />
      ) : isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : vacancies && vacancies.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {vacancies.map((vacancy) => (
            <VacancyCard key={vacancy.id} vacancy={vacancy} league={league} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="Вакансий пока нет"
          description="Когда работодатель опубликует позицию, она появится здесь."
        />
      )}
    </section>
  )
}