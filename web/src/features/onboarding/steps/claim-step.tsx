import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useProfile, useSaveProfile, useTaxonomy } from '@/api/profile'
import { cn } from '@/lib/utils'
import { GRADE_DESCRIPTOR, GRADE_LABEL } from '@/lib/labels'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { Button } from '@/components/ui/button'
import { CardSkeleton } from '@/components/ui/skeleton'

const FALLBACK_GRADES = ['intern', 'junior', 'middle', 'senior'] as const

/** Onboarding step 4: claim a grade, then hand off to the qualification lab. */
export function ClaimStep() {
  const navigate = useNavigate()
  const location = useLocation()
  const { data: profile, isLoading } = useProfile()
  const { data: taxonomy } = useTaxonomy()
  const save = useSaveProfile()
  const [selected, setSelected] = useState<string>('')

  const state = (location.state ?? {}) as { specialization?: string }
  const specialization = state.specialization || profile?.specialization || ''
  const grades: readonly string[] = taxonomy?.grades?.length ? taxonomy.grades : FALLBACK_GRADES

  // Restore a previously claimed grade once the profile arrives.
  const hydrated = useRef(false)
  useEffect(() => {
    if (isLoading || !profile || hydrated.current) return
    if (profile.claimed_grade) setSelected(profile.claimed_grade)
    hydrated.current = true
  }, [isLoading, profile])

  if (isLoading) {
    return (
      <section className="rounded-xl border border-border bg-card p-6">
        <CardSkeleton />
      </section>
    )
  }

  const claim = () => {
    if (!selected) return
    if (!specialization) {
      toast.error('Специализация не выбрана — вернитесь к опросу')
      return
    }
    save.mutate(
      { claimed_grade: selected },
      {
        onSuccess: () =>
          navigate(
            `/candidate/qualification/start?specialization=${encodeURIComponent(specialization)}&claimed_grade=${encodeURIComponent(selected)}`,
          ),
        onError: (error) =>
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Сбой сохранения',
          ),
      },
    )
  }

  return (
    <section className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6">
      <div>
        <h1 className="text-lg font-semibold">Заявите грейд</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Грейд можно подтвердить на квалификации — итоговый результат от него не зависит.
        </p>
      </div>

      <div role="radiogroup" aria-label="Заявленный грейд" className="flex flex-col gap-3">
        {grades.map((grade) => {
          const gradeId = typeof grade === 'string' ? grade : (grade as { id: string }).id
          const gradeLabel =
            typeof grade === 'object' && (grade as { name_ru?: string }).name_ru
              ? (grade as { name_ru: string }).name_ru
              : GRADE_LABEL[gradeId] ?? gradeId
          const gradeDescriptor =
            typeof grade === 'object' && (grade as { descriptor_ru?: string }).descriptor_ru
              ? (grade as { descriptor_ru: string }).descriptor_ru
              : GRADE_DESCRIPTOR[gradeId] ?? ''
          return (
            <button
              key={gradeId}
              type="button"
              role="radio"
              aria-checked={selected === gradeId}
              onClick={() => setSelected(gradeId)}
              className={cn(
                'flex flex-col gap-1 rounded-xl border p-4 text-left transition-colors',
                selected === gradeId
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50',
              )}
            >
              <span className="text-sm font-semibold">{gradeLabel}</span>
              <span className="text-xs leading-relaxed text-muted-foreground">
                {gradeDescriptor}
              </span>
            </button>
          )
        })}
      </div>

      <Button
        type="button"
        className="w-full"
        disabled={!selected || save.isPending}
        onClick={claim}
      >
        {save.isPending ? 'Сохраняем…' : 'Перейти к квалификации'}
      </Button>
      <p className="text-center text-xs text-muted-foreground">
        Шаг 4 из 4. Дальше — тест в олимпийском формате: {GRADE_LABEL[grades[0]]} →{' '}
        {GRADE_LABEL[grades[grades.length - 1]]}.
      </p>
    </section>
  )
}
