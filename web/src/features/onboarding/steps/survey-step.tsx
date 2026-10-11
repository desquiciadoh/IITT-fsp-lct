import { useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { useProfile, useSaveProfile } from '@/api/profile'
import type { CandidateProfile } from '@/api/types'
import { applyApiErrorToForm } from '@/features/auth/form-errors'
import { surveySchema, type SurveyValues } from '@/features/onboarding/schemas'
import { SPEC_LABEL, WORK_FORMAT_LABEL, SALARY_TYPE_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import { CardSkeleton } from '@/components/ui/skeleton'
import type { FieldPath } from 'react-hook-form'

const SPECS = Object.keys(SPEC_LABEL) as [string, ...string[]]
const FORMATS = Object.keys(WORK_FORMAT_LABEL) as [string, ...string[]]

function parseRoles(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function profileDefaults(
  profile: CandidateProfile,
  stateSpec: string | undefined,
): Partial<SurveyValues> {
  const rawSpec = stateSpec || profile.specialization || ''
  const specialization = (SPECS as string[]).includes(rawSpec)
    ? (rawSpec as SurveyValues['specialization'])
    : undefined
  return {
    specialization,
    years_experience: profile.years_experience ? Number(profile.years_experience) : null,
    roles: profile.roles ?? [],
    work_formats: profile.work_formats ?? [],
    salary_min: profile.salary_min ?? undefined,
    salary_max: profile.salary_max ?? undefined,
    salary_type: profile.salary_type || undefined,
    salary_floor: profile.salary_floor ?? null,
    about: profile.about ?? '',
  }
}

/** Onboarding step 3: skills/salary survey. */
export function SurveyStep() {
  const navigate = useNavigate()
  const location = useLocation()
  const { data: profile, isLoading } = useProfile()
  const save = useSaveProfile()

  const state = (location.state ?? {}) as { specialization?: string }

  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<SurveyValues>({
    resolver: zodResolver(surveySchema),
  })

  // Wait for the profile, then hydrate the form once. Prevents a lost prefill
  // on refresh (defaults were computed before the query resolved).
  const hydrated = useRef(false)
  useEffect(() => {
    if (isLoading || !profile || hydrated.current) return
    reset(profileDefaults(profile, state.specialization))
    hydrated.current = true
  }, [isLoading, profile, state.specialization, reset])

  if (isLoading) {
    return (
      <section className="rounded-xl border border-border bg-card p-6">
        <CardSkeleton />
      </section>
    )
  }

  const onSubmit = (values: SurveyValues) => {
    const payload = {
      specialization: values.specialization,
      years_experience: values.years_experience ?? null,
      roles: values.roles,
      work_formats: values.work_formats,
      salary_min: values.salary_min,
      salary_max: values.salary_max,
      salary_type: values.salary_type,
      salary_floor: values.salary_floor ?? null,
      ...(values.about ? { about: values.about } : {}),
    }
    save.mutate(payload, {
      onSuccess: () =>
        navigate('/candidate/onboarding/claim', {
          replace: true,
          state: { specialization: values.specialization },
        }),
      onError: (error) => {
        if (!applyApiErrorToForm(error, setError)) {
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Сбой сохранения',
          )
        }
      },
    })
  }

  const fieldError = (name: FieldPath<SurveyValues>) => {
    const entry = (errors as Record<string, { message?: string } | undefined>)[name]
    return entry?.message ? (
      <p className="text-xs text-destructive" role="alert">
        {entry.message}
      </p>
    ) : null
  }

  return (
    <section className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6">
      <div>
        <h1 className="text-lg font-semibold">Опрос</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Несколько полей — по ним работодатели фильтруют пул.
        </p>
      </div>

      <form onSubmit={handleSubmit((values) => onSubmit(values))} className="flex flex-col gap-5">
        <fieldset>
          <legend className="text-sm font-medium">Специализация *</legend>
          <div className="mt-2 flex gap-2">
            {SPECS.map((spec) => (
              <label
                key={spec}
                className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
              >
                <input type="radio" value={spec} {...register('specialization')} />
                {SPEC_LABEL[spec]}
              </label>
            ))}
          </div>
          {fieldError('specialization')}
        </fieldset>

        <label className="text-sm">
          Опыт, лет
          <input
            type="number"
            step="0.5"
            min="0"
            max="50"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            {...register('years_experience', {
              setValueAs: (v: unknown) => (v === '' || v == null ? null : Number(v)),
            })}
          />
          {fieldError('years_experience')}
        </label>

        <label className="text-sm">
          Роли через запятую *
          <input
            type="text"
            placeholder="разработчик, тимлид"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            {...register('roles', {
              setValueAs: (v: unknown) => (typeof v === 'string' ? parseRoles(v) : v),
            })}
          />
          {fieldError('roles')}
        </label>

        <fieldset>
          <legend className="text-sm font-medium">Формат работы *</legend>
          <div className="mt-2 flex gap-2">
            {FORMATS.map((f) => (
              <label
                key={f}
                className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
              >
                <input type="checkbox" value={f} {...register('work_formats')} />
                {WORK_FORMAT_LABEL[f]}
              </label>
            ))}
          </div>
          {fieldError('work_formats')}
        </fieldset>

        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">
            Зарплата от, ₽ *
            <input
              type="number"
              min="1"
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              {...register('salary_min', { valueAsNumber: true })}
            />
            {fieldError('salary_min')}
          </label>
          <label className="text-sm">
            Зарплата до, ₽ *
            <input
              type="number"
              min="1"
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              {...register('salary_max', { valueAsNumber: true })}
            />
            {fieldError('salary_max')}
          </label>
        </div>

        <fieldset>
          <legend className="text-sm font-medium">Способ указания *</legend>
          <div className="mt-2 flex gap-4">
            {(['gross', 'net'] as const).map((t) => (
              <label key={t} className="flex cursor-pointer items-center gap-2 text-sm">
                <input type="radio" value={t} {...register('salary_type')} />
                {SALARY_TYPE_LABEL[t]}
              </label>
            ))}
          </div>
          {fieldError('salary_type')}
        </fieldset>

        <label className="text-sm">
          Минимальный порог (приватно)
          <input
            type="number"
            min="0"
            placeholder="Не показывается работодателям"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            {...register('salary_floor', {
              setValueAs: (v: unknown) => (v === '' || v == null ? null : Number(v)),
            })}
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Виден только вам — фильтр «ниже порога не предлагать».
          </span>
          {fieldError('salary_floor')}
        </label>

        <label className="text-sm">
          О себе
          <textarea
            rows={3}
            maxLength={2000}
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            {...register('about')}
          />
          {fieldError('about')}
        </label>

        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? 'Сохраняем…' : 'Продолжить'}
        </Button>
      </form>
    </section>
  )
}
