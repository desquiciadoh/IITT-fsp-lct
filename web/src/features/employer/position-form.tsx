import { useEffect } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { useCreatePosition, useUpdatePosition } from '@/api/employer'
import type { JdParseResult, Position, PositionInput } from '@/api/types'
import { useTaxonomy } from '@/api/profile'
import {
  positionFormSchema,
  toPositionInput,
  uniqueSkills,
  type PositionFormState,
  type PositionFormValues,
} from '@/features/employer/schemas'
import { applyApiErrorToForm } from '@/features/auth/form-errors'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ChipInput } from '@/components/domain/chip-input'
import { BlueprintBars } from '@/features/employer/blueprint-bars'
import { GRADE_LABEL, SALARY_TYPE_LABEL, SPEC_LABEL, WORK_FORMAT_LABEL } from '@/lib/labels'

/**
 * FE-09 · Editable position form (wizard step 2 / edit tab).
 * Salary rules are validated client-side before submit (zod): salary_min > 0,
 * salary_max ≥ salary_min, salary_type is an explicit radio with NO default —
 * invalid salaries never reach the server (BE.md B15: salary_min = 0 → 500).
 */

const GRADES = ['intern', 'junior', 'middle', 'senior'] as const
const FORMATS = ['office', 'hybrid', 'remote'] as const
const SPECS = ['backend', 'frontend', 'ml_data'] as const

export const EMPTY_POSITION_FORM: PositionFormState = {
  title: '',
  specialization: 'backend',
  grades: [],
  must_skills: [],
  nice_skills: [],
  work_formats: [],
  location: '',
  salary_min: '',
  salary_max: '',
  salary_type: undefined as unknown as 'gross' | 'net', // no default (FE2.md §FE-09)
  team_context: '',
  description: '',
  allow_adjacent: false,
  is_public: true,
}

/** Map a JD parse draft onto editable form defaults (FE2.md §FE-09). */
export function draftToForm(draft: JdParseResult['draft']): PositionFormState {
  return {
    ...EMPTY_POSITION_FORM,
    title: draft.title ?? '',
    specialization: draft.specialization ?? 'backend',
    grades: draft.grades ?? [],
    must_skills: uniqueSkills(draft.must_skills ?? []),
    nice_skills: uniqueSkills(draft.must_skills ?? []).length
      ? uniqueSkills(draft.nice_skills ?? []).filter(
          (s) => !(draft.must_skills ?? []).map((m) => m.toLowerCase()).includes(s),
        )
      : uniqueSkills(draft.nice_skills ?? []),
    work_formats: draft.work_formats ?? [],
    location: draft.location ?? '',
    salary_min: draft.salary_min != null ? String(draft.salary_min) : '',
    salary_max: draft.salary_max != null ? String(draft.salary_max) : '',
    salary_type: draft.salary_type ? (draft.salary_type as 'gross' | 'net') : (undefined as unknown as 'gross' | 'net'),
    team_context: draft.team_context ?? '',
    description: draft.description ?? '',
  }
}

export function positionToForm(p: Position): PositionFormState {
  return {
    ...EMPTY_POSITION_FORM,
    title: p.title,
    specialization: p.specialization,
    grades: p.grades,
    must_skills: p.must_skills ?? [],
    nice_skills: p.nice_skills ?? [],
    work_formats: p.work_formats ?? [],
    location: p.location ?? '',
    salary_min: String(p.salary_min),
    salary_max: String(p.salary_max),
    salary_type: p.salary_type,
    team_context: p.team_context ?? '',
    description: p.description ?? '',
    allow_adjacent: p.allow_adjacent ?? false,
    is_public: p.is_public ?? true,
  }
}

/** Map validated form values onto the API payload (PositionInput). */
export function toApiPayload(values: PositionFormValues): PositionInput {
  return {
    title: values.title.trim(),
    specialization: values.specialization,
    grades: values.grades,
    must_skills: values.must_skills,
    nice_skills: values.nice_skills.filter((s) => !values.must_skills.includes(s)),
    work_formats: values.work_formats,
    location: values.location.trim() || undefined,
    salary_min: values.salary_min,
    salary_max: values.salary_max,
    salary_type: values.salary_type,
    team_context: values.team_context.trim() || undefined,
    description: values.description.trim() || undefined,
    allow_adjacent: values.allow_adjacent,
    is_public: values.is_public,
  }
}

export function PositionForm({
  defaultValues,
  unknownTerms = [],
  blueprint = [],
  parseSource,
  mode,
  positionId,
}: {
  defaultValues: PositionFormState
  unknownTerms?: string[]
  blueprint?: JdParseResult['blueprint']
  parseSource?: string
  mode: 'create' | 'edit'
  positionId?: string
}) {
  const navigate = useNavigate()
  const { data: taxonomy } = useTaxonomy()
  const create = useCreatePosition()
  const update = useUpdatePosition(positionId ?? '')

  const {
    register,
    handleSubmit,
    setValue,
    setError,
    watch,
    control,
    formState: { errors },
  } = useForm<PositionFormState>({
    // Raw form state is looser than the schema input (string salary, taxonomy
    // strings) — zod coerces and narrows on submit.
    resolver: zodResolver(positionFormSchema) as never,
    defaultValues,
  })

  const mustSkills = useWatch({ control, name: 'must_skills' }) ?? []
  const niceSkills = useWatch({ control, name: 'nice_skills' }) ?? []
  const grades = useWatch({ control, name: 'grades' }) ?? []
  const formats = useWatch({ control, name: 'work_formats' }) ?? []
  const salaryType = useWatch({ control, name: 'salary_type' })

  // Re-run the cross-field rule live so the hint appears while typing.
  useEffect(() => {
    const sub = watch((values, { name }) => {
      if (name === 'salary_min' || name === 'salary_max') {
        const min = Number(values.salary_min)
        const max = Number(values.salary_max)
        if (!Number.isNaN(min) && !Number.isNaN(max) && values.salary_min !== '' && values.salary_max !== '' && max < min) {
          setError('salary_max', { type: 'custom', message: 'Максимум не может быть меньше минимума' })
        }
      }
    })
    return () => sub.unsubscribe()
  }, [watch, setError])

  const mutation = mode === 'create' ? create : update

  const onSubmit = (values: PositionFormState) => {
    mutation.mutate(toApiPayload(toPositionInput(values)))
  }

  useEffect(() => {
    if (mutation.isSuccess) {
      toast.success(mode === 'create' ? 'Вакансия создана' : 'Изменения сохранены')
      navigate(`/employer/positions/${mutation.data.id}`)
    }
  }, [mutation.isSuccess, mutation.data, mode, navigate])

  useEffect(() => {
    if (mutation.isError) {
      const error = mutation.error
      if (error instanceof ApiError && error.code === 'company_required') {
        toast.error('Сначала создайте профиль компании')
        navigate('/employer/company')
        return
      }
      // BE labels every serializer error `salary_invalid` with a dict of
      // field messages (FE2.md §FE-09) — map them back onto the fields.
      if (!applyApiErrorToForm(error, setError)) {
        toast.error(error instanceof ApiError ? error.message : 'Не удалось сохранить вакансию')
      }
    }
  }, [mutation.isError, mutation.error, setError, navigate])

  const skillSuggestions = taxonomy?.skills ?? []

  // Prefer the live taxonomy lists when the mock/BE returns them; fall
  // back to the static constants so the form keeps working without taxonomy.
  const specs: readonly string[] =
    taxonomy?.specs && taxonomy.specs.length > 0 ? taxonomy.specs : SPECS
  const gradeOptions: readonly string[] =
    taxonomy?.grades && taxonomy.grades.length > 0 ? taxonomy.grades : GRADES
  const formatOptions: readonly string[] =
    taxonomy?.work_formats && taxonomy.work_formats.length > 0
      ? taxonomy.work_formats
      : FORMATS

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      {parseSource && (
        <p className="text-xs text-muted-foreground">
          Черновик заполнен автоматически (источник: {parseSource}). Проверьте поля перед сохранением.
        </p>
      )}
      {blueprint.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Профиль компетенций</CardTitle>
          </CardHeader>
          <CardContent>
            <BlueprintBars items={blueprint} />
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="title" className="text-sm font-medium">
          Название вакансии
        </label>
        <Input id="title" {...register('title')} />
        {errors.title?.message && <p role="alert" className="text-xs text-destructive">{errors.title.message}</p>}
      </div>

      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">Специализация</legend>
        <div className="flex flex-wrap gap-3">
          {specs.map((s) => (
            <label key={s} className="flex items-center gap-1.5 text-sm capitalize">
              <input type="radio" value={s} {...register('specialization')} className="accent-[color:var(--fsp-accent)]" />
              {SPEC_LABEL[s] ?? s}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">Грейды</legend>
        <div className="flex flex-wrap gap-3">
          {gradeOptions.map((g) => (
            <label key={g} className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={grades.includes(g)}
                onChange={(e) =>
                  setValue(
                    'grades',
                    e.target.checked ? [...grades, g] : grades.filter((x) => x !== g),
                    { shouldDirty: true },
                  )
                }
                className="accent-[color:var(--fsp-accent)]"
              />
              {GRADE_LABEL[g] ?? g}
            </label>
          ))}
        </div>
        {errors.grades?.message && <p role="alert" className="text-xs text-destructive">{errors.grades.message}</p>}
      </fieldset>

      <ChipInput
        id="must_skills"
        label="Обязательные навыки (must)"
        placeholder="python, django… Enter — добавить"
        value={mustSkills}
        suggestions={skillSuggestions}
        highlight={unknownTerms}
        onChange={(next) => setValue('must_skills', next, { shouldDirty: true, shouldValidate: true })}
      />
      <ChipInput
        id="nice_skills"
        label="Желаемые навыки (nice to have)"
        placeholder="redis, kafka…"
        value={niceSkills}
        suggestions={skillSuggestions}
        highlight={unknownTerms}
        onChange={(next) => setValue('nice_skills', next, { shouldDirty: true, shouldValidate: true })}
      />
      {unknownTerms.length > 0 && (
        <p className="text-xs text-warn">
          Не распознано парсером: {unknownTerms.join(', ')} — проверьте написание.
        </p>
      )}

      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">Формат работы</legend>
        <div className="flex flex-wrap gap-3">
          {formatOptions.map((f) => (
            <label key={f} className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={formats.includes(f)}
                onChange={(e) =>
                  setValue(
                    'work_formats',
                    e.target.checked ? [...formats, f] : formats.filter((x) => x !== f),
                    { shouldDirty: true },
                  )
                }
                className="accent-[color:var(--fsp-accent)]"
              />
              {WORK_FORMAT_LABEL[f] ?? f}
            </label>
          ))}
        </div>
        {errors.work_formats?.message && (
          <p role="alert" className="text-xs text-destructive">{errors.work_formats.message}</p>
        )}
      </fieldset>

      <div className="flex flex-col gap-1">
        <label htmlFor="location" className="text-sm font-medium">
          Локация
        </label>
        <Input id="location" placeholder="Москва / не важно" {...register('location')} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="salary_min" className="text-sm font-medium">
            Зарплата от, ₽/мес
          </label>
          <Input id="salary_min" type="number" min={1} inputMode="numeric" {...register('salary_min')} />
          {errors.salary_min?.message && (
            <p role="alert" className="text-xs text-destructive">{errors.salary_min.message}</p>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="salary_max" className="text-sm font-medium">
            Зарплата до, ₽/мес
          </label>
          <Input id="salary_max" type="number" min={1} inputMode="numeric" {...register('salary_max')} />
          {errors.salary_max?.message && (
            <p role="alert" className="text-xs text-destructive">{errors.salary_max.message}</p>
          )}
        </div>
      </div>

      {/* Explicit radio, no default (FE2.md §FE-09 salary transparency). */}
      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">Тип зарплаты</legend>
        <div className="flex flex-wrap gap-3">
          {(['gross', 'net'] as const).map((t) => (
            <label key={t} className="flex items-center gap-1.5 text-sm">
              <input
                type="radio"
                value={t}
                checked={salaryType === t}
                onChange={() => setValue('salary_type', t, { shouldDirty: true, shouldValidate: true })}
                className="accent-[color:var(--fsp-accent)]"
              />
              {SALARY_TYPE_LABEL[t]} ({t})
            </label>
          ))}
        </div>
        {!salaryType && <p className="text-xs text-muted-foreground">Выберите явно — по умолчанию нет.</p>}
        {errors.salary_type?.message && (
          <p role="alert" className="text-xs text-destructive">{errors.salary_type.message}</p>
        )}
      </fieldset>

      <div className="flex flex-col gap-1">
        <label htmlFor="team_context" className="text-sm font-medium">
          Контекст команды
        </label>
        <textarea
          id="team_context"
          rows={2}
          className="w-full rounded-md border border-input bg-background p-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          {...register('team_context')}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="description" className="text-sm font-medium">
          Описание вакансии
        </label>
        <textarea
          id="description"
          rows={4}
          className="w-full rounded-md border border-input bg-background p-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          {...register('description')}
        />
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" {...register('allow_adjacent')} className="accent-[color:var(--fsp-accent)]" />
          Показывать смежным грейдам
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" {...register('is_public')} className="accent-[color:var(--fsp-accent)]" />
          Публичная вакансия
        </label>
      </div>

      <div>
        <Button type="submit" disabled={mutation.isPending}>
          {mode === 'create' ? 'Создать вакансию' : 'Сохранить изменения'}
        </Button>
      </div>
    </form>
  )
}
