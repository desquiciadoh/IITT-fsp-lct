import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, ArrowRight, Check, Plus, Sparkles, Trash2, Wand2, X } from 'lucide-react'
import { ApiError } from '@/api/client'
import { isCompanyRequired } from '@/api/companies'
import { useCreatePosition, useParseJD } from '@/api/positions'
import { useTaxonomy } from '@/api/profile'
import { errorMessage } from '@/i18n/errors'
import type { JdParseResult } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ErrorState } from '@/components/domain/states'
import {
  GRADE_LABEL,
  SALARY_TYPE_LABEL,
  SPEC_LABEL,
  WORK_FORMAT_LABEL,
} from '@/lib/labels'
import { cn } from '@/lib/utils'
import {
  fieldErrorsFromError,
  parsePositionForm,
  toPositionInput,
  type PositionFormValues,
} from './position-schema'

/** gap G6: JD text length gate — mirrors the mock's 422 threshold. */
const MIN_JD_LENGTH = 20
const DRAFT_STORAGE_KEY = 'fe09-position-draft'

const SPECIALIZATIONS = ['backend', 'frontend', 'ml_data'] as const
const GRADES = ['intern', 'junior', 'middle', 'senior'] as const
const WORK_FORMATS = ['office', 'hybrid', 'remote'] as const

const TOPIC_LABEL: Record<string, string> = {
  algorithms: 'Алгоритмы',
  databases: 'Базы данных',
  web_frameworks: 'Веб-фреймворки',
  testing: 'Тестирование',
  deployment: 'Деплой и CI/CD',
  system_design: 'Системный дизайн',
  concurrency: 'Многопоточность',
  machine_learning: 'ML',
}

type Step = 1 | 2 | 3

type WizardDraft = {
  jdText: string
  parse: JdParseResult | null
  form: PositionFormValues
}

const EMPTY_FORM: PositionFormValues = {
  title: '',
  specialization: 'backend',
  grades: ['middle'],
  must_skills: [],
  nice_skills: [],
  work_formats: [],
  location: '',
  salary_min: '' as unknown as number,
  salary_max: '' as unknown as number,
  salary_type: undefined as unknown as PositionFormValues['salary_type'],
  team_context: '',
  description: '',
  allow_adjacent: false,
  is_public: true,
}

function loadDraft(): WizardDraft {
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY)
    if (raw) return JSON.parse(raw) as WizardDraft
  } catch {
    // corrupted draft — start clean
  }
  return { jdText: '', parse: null, form: EMPTY_FORM }
}

// --- small shared pieces ------------------------------------------------------

function Field({
  id,
  label,
  hint,
  error,
  optional,
  children,
}: {
  id: string
  label: string
  hint?: string
  error?: string
  optional?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {optional && <span className="ml-1 text-xs text-muted-foreground">(необязательно)</span>}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

/** Toggle-chip used for grades / work formats (multi-select without a combobox). */
function ToggleChip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors',
        active
          ? 'border-primary bg-primary/15 text-primary'
          : 'border-border bg-transparent text-muted-foreground hover:bg-muted',
      )}
    >
      {active && <Check className="h-3 w-3" />}
      {children}
    </button>
  )
}

/** Blueprint topic bars (step 1 preview + step 3 final view). */
function TopicBars({ topics }: { topics: { topic: string; weight: number }[] }) {
  if (!topics.length) {
    return <p className="text-xs text-muted-foreground">Топики не распознаны.</p>
  }
  const max = Math.max(...topics.map((t) => t.weight), 0.01)
  return (
    <ul className="flex flex-col gap-2">
      {topics.map((t) => (
        <li key={t.topic} className="flex items-center gap-3">
          <span className="w-40 shrink-0 truncate text-xs">{TOPIC_LABEL[t.topic] ?? t.topic}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.round((t.weight / max) * 100)}%` }}
            />
          </div>
          <span className="w-12 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
            {(t.weight * 100).toFixed(0)}%
          </span>
        </li>
      ))}
    </ul>
  )
}

/** Editable skill chips with taxonomy autocomplete (gap G3 fallback: free input). */
function SkillEditor({
  id,
  label,
  skills,
  suggestions,
  error,
  onChange,
}: {
  id: string
  label: string
  skills: string[]
  suggestions: string[]
  error?: string
  onChange: (next: string[]) => void
}) {
  const [input, setInput] = useState('')
  const add = (raw: string) => {
    const value = raw.trim().toLowerCase()
    if (!value) return
    if (skills.includes(value)) {
      setInput('')
      return
    }
    onChange([...skills, value])
    setInput('')
  }
  const matches = input.trim()
    ? suggestions
        .filter(
          (s) => s.toLowerCase().includes(input.trim().toLowerCase()) && !skills.includes(s),
        )
        .slice(0, 6)
    : []
  return (
    <div className="flex flex-col gap-1.5" id={id}>
      <span className="text-sm font-medium">{label}</span>
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-transparent p-1.5">
        {skills.map((skill) => (
          <span
            key={skill}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-muted px-2 py-0.5 text-xs"
          >
            {skill}
            <button
              type="button"
              aria-label={`Удалить ${skill}`}
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onChange(skills.filter((s) => s !== skill))}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          value={input}
          list={`${id}-datalist`}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add(input)
            } else if (e.key === 'Backspace' && !input && skills.length) {
              onChange(skills.slice(0, -1))
            }
          }}
          onBlur={() => add(input)}
          placeholder="добавьте навык…"
          className="min-w-28 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      {/* gap G3 — datalist degrades gracefully when the taxonomy mock is off */}
      <datalist id={`${id}-datalist`}>
        {suggestions.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      {matches.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {matches.map((m) => (
            <button
              key={m}
              type="button"
              className="rounded-md border border-dashed border-border px-2 py-0.5 text-xs text-muted-foreground hover:border-primary hover:text-primary"
              onClick={() => add(m)}
            >
              <Plus className="mr-1 inline h-3 w-3" />
              {m}
            </button>
          ))}
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

/** Localized text for any thrown error (ApiError carries the machine code). */
function errText(err: unknown): string {
  return err instanceof ApiError ? errorMessage(err.code, err.detail) : errorMessage(undefined)
}

// --- wizard -------------------------------------------------------------------

/**
 * FE-09 · Stage 2 — position creation wizard (/employer/positions/new).
 * Step 1: paste JD → POST /api/positions/parse (gap G6, mocked) → draft +
 * unknown_terms + blueprint. Step 2: editable form (B15 strict salary rules,
 * explicit gross/net, G3 skill chips). Step 3: blueprint preview + save via
 * POST /api/positions. The draft survives reloads via localStorage.
 */
export function PositionWizardPage() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState<WizardDraft>(loadDraft)
  const [step, setStep] = useState<Step>(draft.parse ? 2 : 1)
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<string, string>>>({})

  const parse = useParseJD()
  const create = useCreatePosition()
  const taxonomy = useTaxonomy()

  // Persist the draft so a reload does not lose the wizard progress.
  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft))
    } catch {
      // storage full/unavailable — non-fatal
    }
  }, [draft])

  const skillSuggestions = useMemo(() => {
    const known = taxonomy.data?.skills ?? []
    const unknown = draft.parse?.unknown_terms ?? []
    return [...new Set([...known, ...unknown])]
  }, [taxonomy.data, draft.parse])

  const setForm = <K extends keyof PositionFormValues>(key: K, value: PositionFormValues[K]) => {
    setDraft((d) => ({ ...d, form: { ...d.form, [key]: value } }))
    setFieldErrors((prev) => (prev[key as string] ? { ...prev, [key as string]: undefined } : prev))
  }

  const onParse = () => {
    const text = draft.jdText.trim()
    if (text.length < MIN_JD_LENGTH) {
      toast.error(`Вставьте описание вакансии — минимум ${MIN_JD_LENGTH} символов`)
      return
    }
    parse.mutate({ text }, {
      onSuccess: (result) => {
        setDraft((d) => ({
          ...d,
          parse: result,
          form: {
            ...d.form,
            ...result.draft,
            // B15/G6: never trust the parser with money — salary stays empty
            // until the employer fills it in explicitly.
            salary_min: result.draft.salary_min ?? d.form.salary_min,
            salary_max: result.draft.salary_max ?? d.form.salary_max,
            salary_type: d.form.salary_type,
          },
        }))
        setStep(2)
        if (result.source === 'mock') {
          toast.info('Черновик собран из мока парсера (G6) — проверьте поля')
        }
      },
      onError: (err) => toast.error(errText(err)),
    })
  }

  const validateStep2 = (): boolean => {
    const parsed = parsePositionForm(draft.form)
    if (!parsed.success) {
      setFieldErrors(fieldErrorsFromError(parsed.error))
      toast.error('Проверьте поля формы — зарплата и грейд обязательны')
      return false
    }
    setFieldErrors({})
    return true
  }

  const onSave = () => {
    const parsed = parsePositionForm(draft.form)
    if (!parsed.success) {
      setFieldErrors(fieldErrorsFromError(parsed.error))
      setStep(2)
      toast.error('Проверьте поля формы — зарплата и грейд обязательны')
      return
    }
    const body = toPositionInput(parsed.data)
    create.mutate(body, {
      onSuccess: (position) => {
        localStorage.removeItem(DRAFT_STORAGE_KEY)
        toast.success('Вакансия создана')
        navigate(`/employer/positions/${position.id}`)
      },
      onError: (err) => {
        if (isCompanyRequired(err)) {
          toast.error('Сначала создайте профиль компании')
          navigate('/employer/company')
          return
        }
        if (err instanceof ApiError && err.status === 422) {
          // B15: backend lumps everything under `salary_invalid`; surface detail.
          const msgs = Object.values(err.fieldErrors).flat()
          toast.error(msgs.join('; ') || errText(err))
          setStep(2)
          return
        }
        toast.error(errText(err))
      },
    })
  }

  const companyMissing = create.isError && isCompanyRequired(create.error)

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Новая вакансия</h1>
        <ol className="flex items-center gap-2 text-xs text-muted-foreground">
          {(['Парсинг JD', 'Параметры', 'Предпросмотр'] as const).map((label, i) => (
            <li key={label} className="flex items-center gap-2">
              {i > 0 && <span aria-hidden>→</span>}
              <span
                className={cn(
                  'rounded-full px-2 py-0.5',
                  step === i + 1 ? 'bg-primary/15 font-medium text-primary' : '',
                  step > i + 1 ? 'text-plus' : '',
                )}
              >
                {i + 1}. {label}
              </span>
            </li>
          ))}
        </ol>
      </div>

      {/* STEP 1 — JD parsing ------------------------------------------------- */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wand2 className="h-4 w-4" /> Шаг 1. Описание вакансии
            </CardTitle>
            <CardDescription>
              Вставьте текст вакансии — парсер соберёт черновик, распознает навыки и предложит
              топики теста. Точность пока гарантируется только на моках (G6), поэтому черновик
              нужно проверить на следующем шаге.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <textarea
              id="jd-text"
              value={draft.jdText}
              onChange={(e) => setDraft((d) => ({ ...d, jdText: e.target.value }))}
              rows={12}
              placeholder={'Senior Backend Developer…\nСтек: Python, Django, PostgreSQL…'}
              className="w-full resize-y rounded-md border border-input bg-transparent p-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
            />
            {parse.isError && (
              <ErrorState
                description={errText(parse.error)}
                onRetry={() => parse.mutate({ text: draft.jdText.trim() })}
              />
            )}
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {draft.jdText.trim().length} символов (минимум {MIN_JD_LENGTH})
              </span>
              <Button onClick={onParse} disabled={parse.isPending}>
                {parse.isPending ? <RowSkeletonInline /> : <Sparkles className="h-4 w-4" />}
                Распознать вакансию
              </Button>
            </div>

            {draft.parse && (
              <div className="flex flex-col gap-4 rounded-md border border-border bg-muted/30 p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  Черновик от парсера
                  <Badge variant="info">источник: {draft.parse.source}</Badge>
                </div>
                {draft.parse.unknown_terms.length > 0 && (
                  <div className="flex flex-col gap-1.5">
                    <span className="text-xs font-medium">
                      Нераспознанные термины (проверьте вручную):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {draft.parse.unknown_terms.map((t) => (
                        <span
                          key={t}
                          title="Не найден в таксономии (G3)"
                          className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-0.5 text-xs text-destructive"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium">Blueprint будущего теста:</span>
                  <TopicBars topics={draft.parse.blueprint} />
                </div>
                <Button variant="secondary" onClick={() => setStep(2)}>
                  Редактировать черновик <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* STEP 2 — editable form ---------------------------------------------- */}
      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Шаг 2. Параметры вакансии</CardTitle>
            <CardDescription>
              Все поля можно править вручную. Зарплата и тип выплаты обязательны — платформа не
              публикует вакансии без раскрытой вилки.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <Field id="title" label="Название вакансии" error={fieldErrors.title}>
              <Input
                id="title"
                value={draft.form.title}
                onChange={(e) => setForm('title', e.target.value)}
                placeholder="Python-разработчик (backend)"
              />
            </Field>

            <Field id="specialization" label="Специализация" error={fieldErrors.specialization}>
              <select
                id="specialization"
                value={draft.form.specialization}
                onChange={(e) =>
                  setForm('specialization', e.target.value as PositionFormValues['specialization'])
                }
                className="h-9 rounded-md border border-input bg-transparent px-3 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {SPECIALIZATIONS.map((s) => (
                  <option key={s} value={s}>
                    {SPEC_LABEL[s]}
                  </option>
                ))}
              </select>
            </Field>

            <Field id="grades" label="Грейды" error={fieldErrors.grades}>
              <div className="flex flex-wrap gap-1.5">
                {GRADES.map((g) => (
                  <ToggleChip
                    key={g}
                    active={draft.form.grades.includes(g)}
                    onClick={() =>
                      setForm(
                        'grades',
                        draft.form.grades.includes(g)
                          ? draft.form.grades.filter((x) => x !== g)
                          : [...draft.form.grades, g],
                      )
                    }
                  >
                    {GRADE_LABEL[g]}
                  </ToggleChip>
                ))}
              </div>
            </Field>

            <SkillEditor
              id="must_skills"
              label="Обязательные навыки (вес ×2 в матчинге)"
              skills={draft.form.must_skills}
              suggestions={skillSuggestions}
              error={fieldErrors.must_skills}
              onChange={(next) => setForm('must_skills', next)}
            />
            <SkillEditor
              id="nice_skills"
              label="Желательные навыки (вес ×1)"
              skills={draft.form.nice_skills}
              suggestions={skillSuggestions}
              error={fieldErrors.nice_skills}
              onChange={(next) => setForm('nice_skills', next)}
            />

            <Field id="work_formats" label="Формат работы" optional error={fieldErrors.work_formats}>
              <div className="flex flex-wrap gap-1.5">
                {WORK_FORMATS.map((f) => (
                  <ToggleChip
                    key={f}
                    active={draft.form.work_formats.includes(f)}
                    onClick={() =>
                      setForm(
                        'work_formats',
                        draft.form.work_formats.includes(f)
                          ? draft.form.work_formats.filter((x) => x !== f)
                          : [...draft.form.work_formats, f],
                      )
                    }
                  >
                    {WORK_FORMAT_LABEL[f]}
                  </ToggleChip>
                ))}
              </div>
            </Field>

            <Field id="location" label="Локация" optional error={fieldErrors.location}>
              <Input
                id="location"
                value={draft.form.location}
                onChange={(e) => setForm('location', e.target.value)}
                placeholder="Москва / не важно"
              />
            </Field>

            {/* B15 block: numbers validated client-side, type has NO default. */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                id="salary_min"
                label="Зарплата от, ₽/мес"
                error={fieldErrors.salary_min}
                hint="Больше нуля — иначе бэкенд отклонит вакансию"
              >
                <Input
                  id="salary_min"
                  type="number"
                  min={1}
                  step={1000}
                  value={draft.form.salary_min}
                  onChange={(e) =>
                    setForm('salary_min', (e.target.value === '' ? '' : Number(e.target.value)) as unknown as number)
                  }
                  placeholder="220000"
                />
              </Field>
              <Field id="salary_max" label="Зарплата до, ₽/мес" error={fieldErrors.salary_max}>
                <Input
                  id="salary_max"
                  type="number"
                  min={1}
                  step={1000}
                  value={draft.form.salary_max}
                  onChange={(e) =>
                    setForm('salary_max', (e.target.value === '' ? '' : Number(e.target.value)) as unknown as number)
                  }
                  placeholder="320000"
                />
              </Field>
            </div>

            <fieldset className="flex flex-col gap-1.5">
              <legend className="text-sm font-medium">Тип выплаты</legend>
              <div className="flex gap-4">
                {(['gross', 'net'] as const).map((t) => (
                  <label key={t} className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name="salary_type"
                      value={t}
                      checked={draft.form.salary_type === t}
                      onChange={() => setForm('salary_type', t)}
                      className="size-4 accent-[var(--fsp-accent)]"
                    />
                    {SALARY_TYPE_LABEL[t]}{' '}
                    <span className="text-xs text-muted-foreground">
                      ({t === 'gross' ? 'до вычета налогов' : 'на руки'})
                    </span>
                  </label>
                ))}
              </div>
              {fieldErrors.salary_type ? (
                <p className="text-xs text-destructive">{fieldErrors.salary_type}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Выбор обязателен: по умолчанию тип не ставится (требование прозрачности).
                </p>
              )}
            </fieldset>

            <Field id="team_context" label="Контекст команды" optional error={fieldErrors.team_context}>
              <textarea
                id="team_context"
                value={draft.form.team_context}
                onChange={(e) => setForm('team_context', e.target.value)}
                rows={3}
                placeholder="Размер команды, процессы, стек в проде…"
                className="w-full resize-y rounded-md border border-input bg-transparent p-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
              />
            </Field>

            <Field id="description" label="Описание вакансии" optional error={fieldErrors.description}>
              <textarea
                id="description"
                value={draft.form.description}
                onChange={(e) => setForm('description', e.target.value)}
                rows={6}
                className="w-full resize-y rounded-md border border-input bg-transparent p-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
              />
            </Field>

            <div className="flex flex-col gap-2">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.form.allow_adjacent}
                  onChange={(e) => setForm('allow_adjacent', e.target.checked)}
                  className="size-4 accent-[var(--fsp-accent)]"
                />
                Показывать кандидатов со смежным грейдом
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.form.is_public}
                  onChange={(e) => setForm('is_public', e.target.checked)}
                  className="size-4 accent-[var(--fsp-accent)]"
                />
                Публичная вакансия (иначе — приватная потребность в найме)
              </label>
            </div>

            {companyMissing && (
              <ErrorState
                title="Компания не создана"
                description="Сначала создайте профиль компании."
                onRetry={() => navigate('/employer/company')}
              />
            )}

            <div className="flex items-center justify-between border-t border-border pt-4">
              <Button variant="ghost" onClick={() => setStep(1)}>
                <ArrowLeft className="h-4 w-4" /> Назад к JD
              </Button>
              <Button
                onClick={() => {
                  if (validateStep2()) setStep(3)
                }}
              >
                К предпросмотру <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* STEP 3 — preview & save ---------------------------------------------- */}
      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle>Шаг 3. Предпросмотр</CardTitle>
            <CardDescription>
              Проверьте вакансию перед публикацией. Blueprint определяет топики адаптивного теста
              для кандидатов.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <div className="flex flex-col gap-2 rounded-md border border-border p-4">
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-base font-semibold">{draft.form.title}</h2>
                <Badge variant={draft.form.is_public ? 'success' : 'secondary'}>
                  {draft.form.is_public ? 'публичная' : 'приватная'}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                {SPEC_LABEL[draft.form.specialization]} ·{' '}
                {draft.form.grades.map((g) => GRADE_LABEL[g]).join(', ')}
                {draft.form.work_formats.length
                  ? ` · ${draft.form.work_formats.map((f) => WORK_FORMAT_LABEL[f]).join(', ')}`
                  : ''}
                {draft.form.location ? ` · ${draft.form.location}` : ''}
              </p>
              <p className="text-lg font-semibold tabular-nums">
                {Number(draft.form.salary_min).toLocaleString('ru-RU')} –{' '}
                {Number(draft.form.salary_max).toLocaleString('ru-RU')} ₽
                <span className="ml-1 text-sm font-normal text-muted-foreground">
                  {SALARY_TYPE_LABEL[draft.form.salary_type]}
                </span>
              </p>
              {(draft.form.must_skills.length > 0 || draft.form.nice_skills.length > 0) && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {draft.form.must_skills.map((s) => (
                    <Badge key={`m-${s}`} variant="default">
                      {s}
                    </Badge>
                  ))}
                  {draft.form.nice_skills.map((s) => (
                    <Badge key={`n-${s}`} variant="outline">
                      {s}
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Blueprint теста</h3>
              {draft.parse ? (
                <TopicBars topics={draft.parse.blueprint} />
              ) : (
                <p className="text-xs text-muted-foreground">
                  Вакансия создана без парсинга JD — тест будет собран по навыкам.
                </p>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-border pt-4">
              <Button variant="ghost" onClick={() => setStep(2)} disabled={create.isPending}>
                <ArrowLeft className="h-4 w-4" /> Изменить параметры
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  disabled={create.isPending}
                  onClick={() => {
                    localStorage.removeItem(DRAFT_STORAGE_KEY)
                    setDraft({ jdText: '', parse: null, form: EMPTY_FORM })
                    setStep(1)
                    toast.info('Черновик очищен')
                  }}
                >
                  <Trash2 className="h-4 w-4" /> Сбросить
                </Button>
                <Button onClick={onSave} disabled={create.isPending}>
                  {create.isPending ? <RowSkeletonInline /> : <Check className="h-4 w-4" />}
                  Создать вакансию
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/** Tiny inline spinner that reuses the skeleton vocabulary of the design system. */
function RowSkeletonInline() {
  return <span className="inline-block h-4 w-4 animate-pulse rounded-full bg-current opacity-40" />
}
