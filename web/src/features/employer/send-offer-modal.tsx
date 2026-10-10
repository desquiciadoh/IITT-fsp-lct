import { useEffect, useMemo, useState } from 'react'
import { useCreateOffer } from '@/api/offers'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { SALARY_TYPE_LABEL } from '@/lib/labels'
import type { SalaryType } from '@/api/types'
import {
  CONTACT_CHANNEL_LABEL,
  buildInitialForm,
  mapSendOfferError,
  prefillFromPosition,
  sendOfferSchema,
  toCreateOfferPayload,
  type FieldErrors,
  type SendOfferForm,
} from './send-offer-schema'

/**
 * FE-11 · Send Offer modal.
 * - prefills salary/title from the position when available;
 * - always sends `salary_type` explicitly (backend silently defaults to gross — B15);
 * - never sends `why_you` (server computes it — B9);
 * - maps 422 salary_invalid / serializer errors and 403 candidate_not_reachable to Russian.
 */
export function SendOfferModal({
  open,
  candidate,
  position,
  onClose,
  onSent,
}: {
  open: boolean
  candidate?: { public_id: string; display_name?: string } | null
  position?: {
    id?: string
    title?: string
    description?: string
    salary_min?: number
    salary_max?: number
    salary_type?: SalaryType | '' | null
  } | null
  onClose: () => void
  onSent?: (id: string) => void
}) {
  const defaults = useMemo(() => prefillFromPosition(position ?? undefined), [position])
  const [form, setForm] = useState<SendOfferForm>(() => buildInitialForm(defaults))
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)

  // Reset the form every time the dialog reopens (fresh prefill).
  useEffect(() => {
    if (open) {
      setForm(buildInitialForm(defaults))
      setFieldErrors({})
      setFormError(null)
    }
  }, [open, defaults])

  const createOffer = useCreateOffer()

  const set = <K extends keyof SendOfferForm>(key: K, value: SendOfferForm[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    setFieldErrors((e) => ({ ...e, [key]: undefined }))
  }

  const submit = () => {
    setFormError(null)
    const parsed = sendOfferSchema.safeParse(form)
    if (!parsed.success) {
      const next: FieldErrors = {}
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0] ?? '') as keyof SendOfferForm
        if (!next[key]) next[key] = issue.message
      }
      setFieldErrors(next)
      return
    }
    if (!candidate?.public_id) {
      setFormError('Сначала выберите кандидата.')
      return
    }
    createOffer.mutate(toCreateOfferPayload(parsed.data, candidate.public_id, position?.id), {
      onSuccess: (offer) => {
        onSent?.(offer.id)
        onClose()
      },
      onError: (error) => {
        const mapped = mapSendOfferError(error)
        setFormError(mapped.message)
        setFieldErrors(mapped.fieldErrors)
      },
    })
  }

  const errText = (key: keyof SendOfferForm) =>
    fieldErrors[key] ? <p className="mt-1 text-xs text-destructive">{fieldErrors[key]}</p> : null

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !createOffer.isPending) onClose()
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Отправить оффер</DialogTitle>
          <DialogDescription>
            {candidate?.display_name
              ? `Кандидат: ${candidate.display_name}`
              : 'Кандидат выбран из пула'}
            . Зарплата и тип («до вычета» / «на руки») обязательны — бэкенд не подставляет их молча.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <label className="block text-sm">
            Название вакансии *
            <Input
              value={form.title}
              onChange={(e) => set('title', e.target.value)}
              placeholder="Senior Backend Engineer"
              className="mt-1"
            />
            {errText('title')}
          </label>

          <label className="block text-sm">
            Описание / «почему мы» *
            <textarea
              rows={3}
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              placeholder="Коротко: команда, задачи, стек."
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
            {errText('description')}
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Зарплата от, ₽/мес *
              <Input
                type="number"
                min={0}
                step={1000}
                value={form.salaryMin || ''}
                onChange={(e) => set('salaryMin', Number(e.target.value))}
                className="mt-1"
              />
              {errText('salaryMin')}
            </label>
            <label className="block text-sm">
              Зарплата до, ₽/мес *
              <Input
                type="number"
                min={0}
                step={1000}
                value={form.salaryMax || ''}
                onChange={(e) => set('salaryMax', Number(e.target.value))}
                className="mt-1"
              />
              {errText('salaryMax')}
            </label>
          </div>

          <fieldset>
            <legend className="text-sm font-medium">Тип зарплаты *</legend>
            <div className="mt-2 flex gap-2">
              {(['gross', 'net'] as SalaryType[]).map((t) => (
                <label
                  key={t}
                  className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm"
                >
                  <input
                    type="radio"
                    name="salary-type"
                    value={t}
                    checked={form.salaryType === t}
                    onChange={() => set('salaryType', t)}
                  />
                  {SALARY_TYPE_LABEL[t]}
                </label>
              ))}
            </div>
            {errText('salaryType')}
          </fieldset>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Канал связи
              <select
                value={form.contactChannel}
                onChange={(e) =>
                  set('contactChannel', e.target.value as SendOfferForm['contactChannel'])
                }
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                {(Object.keys(CONTACT_CHANNEL_LABEL) as Array<keyof typeof CONTACT_CHANNEL_LABEL>).map(
                  (c) => (
                    <option key={c} value={c}>
                      {CONTACT_CHANNEL_LABEL[c]}
                    </option>
                  ),
                )}
              </select>
            </label>
            <label className="block text-sm">
              Оффер активен, дней
              <Input
                type="number"
                min={1}
                max={90}
                value={form.expiresInDays}
                onChange={(e) => set('expiresInDays', Number(e.target.value))}
                className="mt-1"
              />
              {errText('expiresInDays')}
            </label>
          </div>

          {form.contactChannel !== 'platform' && (
            <label className="block text-sm">
              Контакт для ответа *
              <Input
                value={form.contactValue}
                onChange={(e) => set('contactValue', e.target.value)}
                placeholder={
                  form.contactChannel === 'email'
                    ? 'hr@company.ru'
                    : form.contactChannel === 'telegram'
                      ? '@hr_nick'
                      : '+7 900 000-00-00'
                }
                className="mt-1"
              />
              {errText('contactValue')}
            </label>
          )}

          {formError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {formError}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={createOffer.isPending}>
            Отмена
          </Button>
          <Button onClick={submit} disabled={createOffer.isPending}>
            {createOffer.isPending ? 'Отправляем…' : 'Отправить оффер'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
