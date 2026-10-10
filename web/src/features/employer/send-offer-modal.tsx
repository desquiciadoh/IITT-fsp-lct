import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm, useWatch, type Control, type UseFormRegister, type FieldErrors } from 'react-hook-form'
import { toast } from 'sonner'
import { Send } from 'lucide-react'
import { ApiError } from '@/api/client'
import { useSendOffer, type SendOfferInput } from '@/api/offers'
import type { Offer, Position, TalentShort } from '@/api/types'
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
import {
  CONTACT_CHANNELS,
  offerFormSchema,
  toSendOfferInput,
  type OfferFormInput,
  type OfferFormValues,
} from '@/features/employer/schemas'
import { errorMessage } from '@/i18n/errors'
import { CONTACT_CHANNEL_LABEL, SALARY_TYPE_LABEL } from '@/lib/labels'

/**
 * FE-11 · Send Offer modal (opened from a pool row or the talent drawer via
 * `?offer=<public_id>`).
 *
 * Contract rules baked in here:
 * - salary is prefilled from the position (FE2.md §FE-11);
 * - `salary_type` is ALWAYS sent explicitly — the backend silently defaults
 *   to gross today (BE.md B15), so the field has no default and is required;
 * - `why_you` is NEVER part of this form — the server computes it (BE fix B9);
 * - errors are shown by code: 422 `salary_invalid`, 403
 *   `candidate_not_reachable`, 404 (`not_found`).
 */

const FIELD_TO_CODE: Record<string, string> = {
  salary_min: 'salary_invalid',
  salary_max: 'salary_invalid',
  salary_type: 'salary_invalid',
}

export function sendOfferDefaults(position?: Position): Partial<OfferFormInput> {
  return {
    // Prefill from the position; empty when the position has no salary yet.
    title: position?.title ?? '',
    description: position?.description ?? '',
    salary_min: position?.salary_min != null ? String(position.salary_min) : '',
    salary_max: position?.salary_max != null ? String(position.salary_max) : '',
    // B15: deliberately NO default for salary_type.
    contact_channel: 'platform',
    contact_value: '',
  }
}

export function SendOfferModal({
  positionId,
  position,
  candidate,
  open,
  onClose,
  onSent,
}: {
  positionId: string
  position?: Position
  /** G10: identity may be missing on the employer payload; the drawer passes it. */
  candidate?: TalentShort | null
  open: boolean
  onClose: () => void
  onSent?: (offer: Offer) => void
}) {
  const [serverCode, setServerCode] = useState<string | null>(null)
  const send = useSendOffer()

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
    // Explicit generics: with z.coerce the inferred input/output types differ;
    // the form stores raw strings and zodResolver coerces them on submit.
  } = useForm<OfferFormInput, unknown, OfferFormValues>({
    // Cast: @hookform/resolvers infers `unknown` for z.coerce.number() inputs.
    resolver: zodResolver(offerFormSchema) as never,
    defaultValues: sendOfferDefaults(position),
  })

  // Fresh prefill every time the dialog opens (position may have changed).
  useEffect(() => {
    if (open) {
      reset(sendOfferDefaults(position))
      setServerCode(null)
    }
  }, [open, position, reset])

  // zodResolver hands the coerced output to onSubmit; the form itself keeps raw strings.
  const onSubmit = handleSubmit((raw: OfferFormValues) => {
    setServerCode(null)
    const input: SendOfferInput = {
      ...toSendOfferInput(raw),
      candidate_public_id: candidate?.public_id ?? '',
      position_id: positionId,
    }
    send.mutate(input, {
      onSuccess: (offer) => {
        toast.success('Оффер отправлен')
        onSent?.(offer)
        onClose()
      },
      onError: (err) => {
        // Show the error by its contract code (FE2.md §FE-11).
        const code = err instanceof ApiError ? err.code : 'api_error'
        setServerCode(code)
      },
    })
  })

  const serverMessage =
    serverCode === 'salary_invalid'
      ? errorMessage('salary_invalid')
      : serverCode === 'candidate_not_reachable'
        ? errorMessage('candidate_not_reachable')
        : serverCode === 'not_found'
          ? errorMessage('not_found')
          : serverCode
            ? errorMessage(serverCode)
            : null

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !send.isPending) onClose()
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Отправить оффер</DialogTitle>
          <DialogDescription>
            {candidate
              ? `Кандидат: ${candidate.display_name ?? candidate.public_id}`
              : 'Кандидат получит предложение и сможет ответить прямо на платформе.'}
          </DialogDescription>
        </DialogHeader>

        <form className="flex flex-col gap-4" onSubmit={(e) => void onSubmit(e)} noValidate>
          {/* title */}
          <label className="flex flex-col gap-1 text-sm font-medium">
            Название вакансии *
            <input
              id="offer-title"
              className="rounded-md border border-border bg-background px-3 py-2 text-sm font-normal"
              {...register('title')}
            />
            <span className="text-xs font-normal text-destructive">{errors.title?.message as string | undefined}</span>
          </label>

          {/* description */}
          <label className="flex flex-col gap-1 text-sm font-medium">
            Описание *
            <textarea
              id="offer-description"
              rows={4}
              maxLength={5000}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm font-normal"
              {...register('description')}
            />
            <span className="text-xs font-normal text-destructive">
              {errors.description?.message as string | undefined}
            </span>
          </label>

          {/* salary (prefilled from the position; type has no default — B15) */}
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">Зарплата *</legend>
            <div className="flex gap-2">
              <label className="flex flex-1 flex-col gap-1 text-xs text-muted-foreground">
                Минимум
                <Input type="number" min={1} {...register('salary_min')} aria-label="salary_min" />
              </label>
              <label className="flex flex-1 flex-col gap-1 text-xs text-muted-foreground">
                Максимум
                <Input type="number" min={1} {...register('salary_max')} aria-label="salary_max" />
              </label>
            </div>
            <Controller
              control={control}
              name="salary_type"
              render={({ field }) => (
                <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Тип зарплаты">
                  {(['gross', 'net'] as const).map((t) => (
                    <label key={t} className="flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm">
                      <input
                        type="radio"
                        name="salary_type"
                        value={t}
                        checked={field.value === t}
                        onChange={() => field.onChange(t)}
                      />
                      {SALARY_TYPE_LABEL[t]} ({t})
                    </label>
                  ))}
                </div>
              )}
            />
            <span className="text-xs text-destructive">
              {(errors.salary_min?.message ?? errors.salary_max?.message ?? errors.salary_type?.message) as
                | string
                | undefined}
            </span>
            {serverCode === 'salary_invalid' && (
              <p className="text-xs text-destructive" role="alert">
                {errorMessage('salary_invalid')}
              </p>
            )}
          </fieldset>

          {/* contact channel */}
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">Как связаться *</legend>
            <Controller
              control={control}
              name="contact_channel"
              render={({ field }) => (
                <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Канал связи">
                  {CONTACT_CHANNELS.map((c) => (
                    <label key={c} className="flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm">
                      <input
                        type="radio"
                        name="contact_channel"
                        value={c}
                        checked={field.value === c}
                        onChange={() => field.onChange(c)}
                      />
                      {CONTACT_CHANNEL_LABEL[c]}
                    </label>
                  ))}
                </div>
              )}
            />
            <ChannelValueField control={control} register={register} errors={errors} />
          </fieldset>

          {/* expiry (optional, BE default 14 days) */}
          <label className="flex flex-col gap-1 text-sm font-medium">
            Срок ответа в днях (необязательно, по умолчанию 14)
            <Input type="number" min={1} max={90} {...register('expires_in_days')} aria-label="expires_in_days" />
            <span className="text-xs font-normal text-destructive">
              {errors.expires_in_days?.message as string | undefined}
            </span>
          </label>

          {serverMessage && serverCode !== 'salary_invalid' && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {serverMessage}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={send.isPending}>
              Отмена
            </Button>
            <Button type="submit" disabled={send.isPending || !candidate?.public_id}>
              <Send className="mr-1 h-4 w-4" />
              {send.isPending ? 'Отправляем…' : 'Отправить оффер'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** contact_value is not needed for the in-platform chat — render it only for external channels. */
function ChannelValueField({
  control,
  register,
  errors,
}: {
  /** Control typed with the same three generics as the parent useForm call. */
  control: Control<OfferFormInput, unknown, OfferFormValues>
  register: UseFormRegister<OfferFormInput>
  errors: FieldErrors<OfferFormInput>
}) {
  const channel = useWatch({ control, name: 'contact_channel' })
  if (channel === 'platform') return null
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      Контакт для связи *
      <Input {...register('contact_value')} aria-label="contact_value" placeholder={placeholderFor(channel)} />
      <span className="text-destructive">{errors.contact_value?.message}</span>
    </label>
  )
}

function placeholderFor(channel?: string): string {
  if (channel === 'email') return 'hr@company.ru'
  if (channel === 'phone') return '+7 900 000-00-00'
  if (channel === 'telegram') return '@username'
  return ''
}

// Re-export mapping used by tests / callers that assert which field failed.
export { FIELD_TO_CODE }
