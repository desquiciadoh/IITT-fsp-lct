import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { CheckCircle2, MapPin } from 'lucide-react'
import { ApiError } from '@/api/client'
import { useProfile } from '@/api/profile'
import {
  useApplyVacancy,
  useMyApplications,
  useVacancies,
  type VacancyFilters,
} from '@/api/vacancies'
import type { ApplicationStatus, Vacancy } from '@/api/types'
import { errorMessage } from '@/i18n/errors'
import { GRADE_LABEL, SPEC_LABEL, WORK_FORMAT_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Card, CardContent } from '@/components/ui/card'
import { SalaryTag } from '@/components/domain/salary-tag'
import { ApplicationStatusChip } from '@/components/domain/application-status-chip'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'

const SPECS = ['backend', 'frontend', 'ml_data'] as const

function fitsGrade(vacancy: Vacancy, grade: string | undefined): boolean {
  return Boolean(grade) && vacancy.grades.includes(grade as never)
}

function VacancyCard({
  vacancy,
  appliedStatus,
  onApply,
}: {
  vacancy: Vacancy
  appliedStatus?: ApplicationStatus
  onApply: (vacancy: Vacancy) => void
}) {
  const { data: profile } = useProfile()
  const fit = fitsGrade(vacancy, profile?.league?.grade)

  return (
    <Card className="gap-4 py-5">
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold">{vacancy.title}</h2>
            <span className="text-sm text-muted-foreground">
              {vacancy.company?.name} · {SPEC_LABEL[vacancy.specialization] ?? vacancy.specialization}
            </span>
          </div>
          <SalaryTag
            min={vacancy.salary_min}
            max={vacancy.salary_max}
            type={vacancy.salary_type}
            emphasize
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {vacancy.grades.map((g) => (
            <Badge key={g} variant="outline">
              {GRADE_LABEL[g] ?? g}
            </Badge>
          ))}
          {fit && (
            <Badge variant="success" className="inline-flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" /> подходит по грейду
            </Badge>
          )}
          {vacancy.location && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {vacancy.location}
            </span>
          )}
          {(vacancy.work_formats ?? []).map((f) => (
            <span key={f}>· {WORK_FORMAT_LABEL[f] ?? f}</span>
          ))}
        </div>

        {vacancy.description && (
          <p className="line-clamp-2 text-sm text-muted-foreground">{vacancy.description}</p>
        )}

        <div className="flex items-center justify-between gap-3">
          <Link
            to={`/lab?tab=twins&position_id=${vacancy.id}`}
            className="text-xs text-muted-foreground underline underline-offset-4"
          >
            Как выглядит тест
          </Link>
          {appliedStatus ? (
            <ApplicationStatusChip status={appliedStatus} />
          ) : (
            <Button size="sm" onClick={() => onApply(vacancy)}>
              Откликнуться
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function CandidateVacanciesPage() {
  const [specialization, setSpecialization] = useState('')
  const [search, setSearch] = useState('')
  const [submittedSearch, setSubmittedSearch] = useState('')
  const [applying, setApplying] = useState<Vacancy | null>(null)
  const [note, setNote] = useState('')

  const filters: VacancyFilters = useMemo(
    () => ({ specialization: specialization as never, search: submittedSearch }),
    [specialization, submittedSearch],
  )
  const { data, isLoading, isError, refetch } = useVacancies(filters)
  const { data: applications } = useMyApplications()
  const applyVacancy = useApplyVacancy()

  const appliedByPosition = useMemo(() => {
    const map = new Map<string, ApplicationStatus>()
    for (const app of applications ?? []) map.set(app.position.id, app.status)
    return map
  }, [applications])

  const submit = (vacancy: Vacancy) => {
    applyVacancy.mutate(
      { id: vacancy.id, note },
      {
        onSuccess: () => {
          toast.success('Отклик отправлен')
          setApplying(null)
          setNote('')
        },
        onError: (error) => {
          toast.error(
            error instanceof ApiError
              ? errorMessage(error.code, error.detail)
              : 'Не удалось отправить отклик.',
          )
        },
      },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Вакансии</h1>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setSubmittedSearch(search)
          }}
        >
          <select
            aria-label="Специализация"
            value={specialization}
            onChange={(e) => setSpecialization(e.target.value)}
            className="rounded-md border border-input bg-card px-3 py-1.5 text-sm text-foreground"
          >
            <option value="">Все специализации</option>
            {SPECS.map((s) => (
              <option key={s} value={s}>
                {SPEC_LABEL[s] ?? s}
              </option>
            ))}
          </select>
          <Input
            aria-label="Поиск"
            placeholder="Поиск по названию"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-48"
          />
          <Button type="submit" variant="outline" size="sm">
            Найти
          </Button>
        </form>
      </div>

      {isLoading ? (
        <RowSkeleton count={3} />
      ) : isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="Вакансий не найдено"
          description="Попробуйте изменить фильтры — работодатели публикуют новые вакансии регулярно."
        />
      ) : (
        <div className="grid gap-3">
          {data.items.map((vacancy) => (
            <VacancyCard
              key={vacancy.id}
              vacancy={vacancy}
              appliedStatus={appliedByPosition.get(vacancy.id)}
              onApply={setApplying}
            />
          ))}
        </div>
      )}

      <Dialog open={applying !== null} onOpenChange={(open) => !open && setApplying(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Отклик на «{applying?.title}»</DialogTitle>
            <DialogDescription>
              Работодатель получит доступ к вашим контактам и сможет выйти на связь.
            </DialogDescription>
          </DialogHeader>
          <label className="flex flex-col gap-1 text-sm">
            Сопроводительное письмо (необязательно)
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              className="rounded-md border border-input bg-card px-3 py-2 text-sm"
            />
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApplying(null)}>
              Отмена
            </Button>
            <Button
              disabled={applyVacancy.isPending}
              onClick={() => applying && submit(applying)}
            >
              Отправить отклик
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
