import { Check, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { useApply } from '@/api/vacancies'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { SalaryTag } from '@/components/domain/salary-tag'
import { TrustBadge } from '@/components/domain/trust-badge'
import { Button } from '@/components/ui/button'
import { GRADE_LABEL, SPEC_LABEL, WORK_FORMAT_LABEL } from '@/lib/labels'
import type { Grade, Vacancy } from '@/api/types'

/** FE-15: vacancy in the public list — salary first, then league fit (BE-17 mocked). */
export function VacancyCard({
  vacancy,
  league,
}: {
  vacancy: Vacancy
  league?: { specialization: string; grade: string }
}) {
  const apply = useApply(vacancy.id)

  const fit = Boolean(
    league &&
      vacancy.specialization === league.specialization &&
      vacancy.grades.includes(league.grade as Grade),
  )

  const handleApply = () =>
    apply.mutate(undefined, {
      onSuccess: () => toast.success('Отклик отправлен — компания увидит ваши контакты'),
      onError: (error) =>
        toast.error(
          error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось отправить отклик.',
        ),
    })

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <SalaryTag min={vacancy.salary_min} max={vacancy.salary_max} type={vacancy.salary_type} emphasize />
          <h3 className="text-base font-semibold">{vacancy.title}</h3>
          <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span>{vacancy.company.name}</span>
            <TrustBadge level={vacancy.company.trust_level} />
            {vacancy.location && <span>· {vacancy.location}</span>}
          </div>
        </div>
        {fit ? (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-plus/40 bg-plus/10 px-2 py-0.5 text-xs text-plus">
            <ShieldCheck className="h-3.5 w-3.5" />
            Подходит вашей лиге
          </span>
        ) : (
          <span className="shrink-0 rounded-md border border-border bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
            {SPEC_LABEL[vacancy.specialization]}
          </span>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        {vacancy.grades.map((g) => GRADE_LABEL[g]).join(', ')}
        {' · '}
        {vacancy.work_formats.map((f) => WORK_FORMAT_LABEL[f]).join(', ')}
      </p>

      {vacancy.team_context && <p className="text-sm text-muted-foreground">{vacancy.team_context}</p>}

      <div className="mt-auto">
        <Button
          size="sm"
          disabled={vacancy.is_applied || apply.isPending}
          onClick={handleApply}
        >
          {vacancy.is_applied ? (
            <>
              <Check className="h-4 w-4" /> Отклик отправлен
            </>
          ) : (
            'Откликнуться'
          )}
        </Button>
      </div>
    </article>
  )
}