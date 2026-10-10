import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { useCompany, useCreateCompany, useSaveCompany } from '@/api/employer'
import { ApiError } from '@/api/client'
import type { CompanyInput } from '@/api/types'
import { companySchema, type CompanyFormValues } from '@/features/employer/schemas'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'
import { TrustBadge } from '@/components/domain/trust-badge'

/**
 * FE-09 · Company (`/employer/company`).
 * GET/PUT /api/companies/me; `trust_level` is read-only and shown as TrustBadge.
 * After the BE fix for B1, employers without a company get 403
 * `company_required` — then this screen becomes a create form (gap G17,
 * POST /api/companies). Both branches share one form component.
 */

const FIELDS: { name: keyof CompanyFormValues; label: string; hint?: string; textarea?: boolean }[] = [
  { name: 'name', label: 'Название компании' },
  { name: 'inn', label: 'ИНН', hint: '10 или 12 цифр, необязательно' },
  { name: 'website', label: 'Сайт', hint: 'https://…, необязательно' },
  { name: 'email_domain', label: 'Email-домен', hint: 'например company.ru — подтверждает доверие' },
  { name: 'business_domain', label: 'Сфера деятельности', hint: 'необязательно' },
  { name: 'contact_email', label: 'Контактный email', hint: 'для связи платформы с компанией' },
  { name: 'description', label: 'Описание', hint: 'необязательно', textarea: true },
]

function CompanyForm({
  initialValues,
  submitting,
  submitLabel,
  onSubmit,
}: {
  initialValues: CompanyFormValues
  submitting: boolean
  submitLabel: string
  onSubmit: (values: CompanyFormValues) => void
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: initialValues,
  })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      {FIELDS.map((f) => (
        <div key={f.name} className="flex flex-col gap-1">
          <label htmlFor={f.name} className="text-sm font-medium">
            {f.label}
          </label>
          {f.textarea ? (
            <textarea
              id={f.name}
              rows={4}
              className="w-full rounded-md border border-input bg-background p-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              {...register(f.name)}
            />
          ) : (
            <Input id={f.name} {...register(f.name)} />
          )}
          {f.hint && !errors[f.name] && (
            <p className="text-xs text-muted-foreground">{f.hint}</p>
          )}
          {errors[f.name]?.message && (
            <p role="alert" className="text-xs text-destructive">
              {errors[f.name]?.message}
            </p>
          )}
        </div>
      ))}
      <div>
        <Button type="submit" disabled={submitting}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}

const EMPTY_VALUES: CompanyFormValues = {
  name: '',
  inn: '',
  website: '',
  email_domain: '',
  business_domain: '',
  description: '',
  contact_email: '',
}

function toInput(values: CompanyFormValues): CompanyInput {
  return {
    name: values.name.trim(),
    inn: values.inn.trim() || undefined,
    website: values.website.trim() || undefined,
    email_domain: values.email_domain.trim() || undefined,
    business_domain: values.business_domain?.trim() || undefined,
    description: values.description?.trim() || undefined,
    contact_email: values.contact_email.trim() || undefined,
  }
}

export function CompanyPage() {
  const { data: company, isLoading, isError, error, refetch } = useCompany()
  const save = useSaveCompany()
  const create = useCreateCompany()

  const missing = error instanceof ApiError && error.code === 'company_required'

  useEffect(() => {
    if (save.isSuccess) toast.success('Профиль компании сохранён')
  }, [save.isSuccess])

  useEffect(() => {
    if (create.isSuccess) toast.success('Компания создана')
  }, [create.isSuccess])

  if (isLoading) return <Skeleton className="h-64 rounded-xl" />

  // Gap G17: after BE fixes B1 the endpoint answers 403 company_required.
  if (isError && !missing) {
    return <ErrorState code={error instanceof ApiError ? error.code : undefined} onRetry={() => void refetch()} />
  }

  if (missing || (!isError && !company)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Создать компанию</CardTitle>
        </CardHeader>
        <CardContent>
          <CompanyForm
            initialValues={EMPTY_VALUES}
            submitting={create.isPending}
            submitLabel="Создать компанию"
            onSubmit={(values) => create.mutate(toInput(values))}
          />
        </CardContent>
      </Card>
    )
  }

  const initialValues: CompanyFormValues = {
    name: company?.name ?? '',
    inn: company?.inn ?? '',
    website: company?.website ?? '',
    email_domain: company?.email_domain ?? '',
    business_domain: company?.business_domain ?? '',
    description: company?.description ?? '',
    contact_email: company?.contact_email ?? '',
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">Профиль компании</h1>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          Доверие: <TrustBadge level={company?.trust_level ?? 'none'} showLabel />
        </span>
      </div>
      <Card>
        <CardContent className="pt-6">
          <CompanyForm
            initialValues={initialValues}
            submitting={save.isPending}
            submitLabel="Сохранить"
            onSubmit={(values) => save.mutate(toInput(values))}
          />
        </CardContent>
      </Card>
      {save.isError && (
        <p role="alert" className="text-sm text-destructive">
          {save.error instanceof ApiError ? save.error.message : 'Не удалось сохранить'}
        </p>
      )}
    </div>
  )
}
