import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Building2, Info } from 'lucide-react'
import { ApiError } from '@/api/client'
import { isCompanyRequired, useCompany, useUpdateCompany } from '@/api/companies'
import { errorMessage } from '@/i18n/errors'
import type { Company, CompanyInput } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { RowSkeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'
import { TrustBadge } from '@/components/domain/trust-badge'
import { companySchema, toCompanyInput, type CompanyFormValues } from './company-schema'

const EMPTY: CompanyFormValues = {
  name: '',
  inn: '',
  website: '',
  email_domain: '',
  business_domain: '',
  description: '',
  contact_email: '',
}

function toFormValues(company: Company): CompanyFormValues {
  return {
    name: company.name ?? '',
    inn: company.inn ?? '',
    website: company.website ?? '',
    email_domain: company.email_domain ?? '',
    business_domain: company.business_domain ?? '',
    description: company.description ?? '',
    contact_email: company.contact_email ?? '',
  }
}

type FieldErrors = Partial<Record<keyof CompanyFormValues, string>>

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

/**
 * FE-09 · Stage 1 — employer company profile (/employer/company).
 * B1/G17 flow: GET 403 `company_required` → creation form; PUT acts as upsert.
 * `trust_level` is read-only and rendered via TrustBadge (FE1 component).
 */
export function CompanyPage() {
  const { data: company, isLoading, isError, error, refetch } = useCompany()
  const update = useUpdateCompany()

  // No company yet when the API answered 403 company_required (BE.md B1).
  const missing = isError && isCompanyRequired(error)
  const mode: 'create' | 'edit' = company ? 'edit' : 'create'

  const [values, setValues] = useState<CompanyFormValues>(EMPTY)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  // Prefill the edit form once the company arrives (e.g. after saving).
  useEffect(() => {
    if (company) setValues(toFormValues(company))
  }, [company])

  const setValue = <K extends keyof CompanyFormValues>(key: K, value: CompanyFormValues[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }))
    setFieldErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev))
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const parsed = companySchema.safeParse(values)
    if (!parsed.success) {
      const next: FieldErrors = {}
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof CompanyFormValues
        if (!next[field]) next[field] = issue.message
      }
      setFieldErrors(next)
      toast.error('Проверьте поля формы')
      return
    }
    setFieldErrors({})
    const body = toCompanyInput(parsed.data) as CompanyInput
    update.mutate(body, {
      onSuccess: () =>
        toast.success(mode === 'create' ? 'Компания создана' : 'Изменения сохранены'),
      onError: (err) => {
        if (err instanceof ApiError && err.status === 422) {
          // Map backend field errors onto the form (normalized RFC 7807).
          const next: FieldErrors = {}
          for (const [field, msgs] of Object.entries(err.fieldErrors)) {
            if (msgs[0]) next[field as keyof CompanyFormValues] = msgs[0]
          }
          setFieldErrors(next)
        }
        toast.error(err instanceof ApiError ? errorMessage(err.code, err.detail) : 'Сбой сохранения')
      },
    })
  }

  if (isLoading) return <RowSkeleton count={4} />

  if (isError && !missing) {
    return (
      <ErrorState
        title="Не удалось загрузить профиль компании"
        description={
          error instanceof ApiError ? errorMessage(error.code, error.detail) : undefined
        }
        onRetry={() => void refetch()}
      />
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-lg font-semibold">
          <Building2 className="h-5 w-5 text-primary" />
          Профиль компании
        </h1>
        {company && (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <TrustBadge level={company.trust_level} showLabel />
          </span>
        )}
      </div>

      {missing && (
        <Card className="border-info/40 bg-info/5">
          <CardContent className="flex items-start gap-3 text-sm">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" />
            <p className="text-muted-foreground">
              Чтобы публиковать вакансии, сначала создайте профиль компании. Данные проверит
              модерация — после подтверждения компания получит бейг «подтверждена».
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{mode === 'create' ? 'Новая компания' : 'Данные компании'}</CardTitle>
          <CardDescription>
            {mode === 'create'
              ? 'Заполните основные сведения о работодателе.'
              : 'Эти видят кандидаты в карточке оффера. Обновите и сохраните.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
            <Field id="name" label="Название компании *" error={fieldErrors.name}>
              <Input
                id="name"
                value={values.name}
                onChange={(e) => setValue('name', e.target.value)}
                placeholder="ООО «Ромашка»"
                aria-invalid={Boolean(fieldErrors.name)}
                required
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                id="inn"
                label="ИНН"
                optional
                hint="10 или 12 цифр — используется при модерации"
                error={fieldErrors.inn}
              >
                <Input
                  id="inn"
                  value={values.inn}
                  onChange={(e) => setValue('inn', e.target.value)}
                  inputMode="numeric"
                  placeholder="7701234567"
                  aria-invalid={Boolean(fieldErrors.inn)}
                />
              </Field>
              <Field id="website" label="Сайт" optional error={fieldErrors.website}>
                <Input
                  id="website"
                  type="url"
                  value={values.website}
                  onChange={(e) => setValue('website', e.target.value)}
                  placeholder="https://example.ru"
                  aria-invalid={Boolean(fieldErrors.website)}
                />
              </Field>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                id="email_domain"
                label="Email-домен компании"
                optional
                hint="Например, example.ru — подтверждает доверие к компании"
                error={fieldErrors.email_domain}
              >
                <Input
                  id="email_domain"
                  value={values.email_domain}
                  onChange={(e) => setValue('email_domain', e.target.value)}
                  placeholder="example.ru"
                  aria-invalid={Boolean(fieldErrors.email_domain)}
                />
              </Field>
              <Field
                id="business_domain"
                label="Сфера деятельности"
                optional
                error={fieldErrors.business_domain}
              >
                <Input
                  id="business_domain"
                  value={values.business_domain}
                  onChange={(e) => setValue('business_domain', e.target.value)}
                  placeholder="Финтех, e-commerce…"
                  aria-invalid={Boolean(fieldErrors.business_domain)}
                />
              </Field>
            </div>

            <Field
              id="contact_email"
              label="Контактный email *"
              hint="Корпоративная почта для связи с кандидатами"
              error={fieldErrors.contact_email}
            >
              <Input
                id="contact_email"
                type="email"
                value={values.contact_email}
                onChange={(e) => setValue('contact_email', e.target.value)}
                placeholder="hr@example.ru"
                aria-invalid={Boolean(fieldErrors.contact_email)}
              />
            </Field>

            <Field id="description" label="Описание" optional error={fieldErrors.description}>
              <textarea
                id="description"
                value={values.description}
                onChange={(e) => setValue('description', e.target.value)}
                rows={4}
                maxLength={2000}
                placeholder="Пара слов о компании, продукте и культуре"
                aria-invalid={Boolean(fieldErrors.description)}
                className="border-input focus-visible:border-ring flex w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:ring-[3px]"
              />
            </Field>

            {company && (
              <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                <TrustBadge level={company.trust_level} />
                Уровень доверия присваивает модерация — его нельзя изменить вручную.
              </div>
            )}

            <div className="flex items-center gap-3">
              <Button type="submit" disabled={update.isPending}>
                {update.isPending
                  ? 'Сохранение…'
                  : mode === 'create'
                    ? 'Создать компанию'
                    : 'Сохранить изменения'}
              </Button>
              {mode === 'edit' && (
                <Button asChild variant="outline">
                  <Link to="/employer/positions/new">Создать вакансию</Link>
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
