/**
 * FE-11 pure logic for the Send Offer modal: zod validation + Russian error
 * mapping. Kept UI-free so it runs in the node test environment.
 */
import { z } from 'zod'
import { ApiError } from '@/api/client'
import type { CreateOfferPayload } from '@/api/offers'
import type { ContactChannel, SalaryType } from '@/api/types'

export const CONTACT_CHANNEL_LABEL: Record<ContactChannel, string> = {
  email: 'Email',
  phone: 'Телефон',
  telegram: 'Telegram',
  platform: 'Через платформу',
}

export const sendOfferSchema = z
  .object({
    title: z.string().trim().min(3, 'Укажите название вакансии (мин. 3 символа)'),
    description: z.string().trim().min(10, 'Добавьте описание (мин. 10 символов)'),
    salaryMin: z
      .number({ message: 'Укажите минимальную зарплату числом' })
      .int()
      .positive('Минимум должен быть больше 0'),
    salaryMax: z
      .number({ message: 'Укажите максимальную зарплату числом' })
      .int()
      .positive('Максимум должен быть больше 0'),
    // B15: gross/net must be chosen explicitly — never rely on the backend default.
    salaryType: z.enum(['gross', 'net'], {
      message: 'Выберите тип зарплаты: до вычета или на руки',
    }),
    contactChannel: z.enum(['email', 'phone', 'telegram', 'platform']),
    contactValue: z.string().trim(),
    expiresInDays: z
      .number()
      .int()
      .min(1, 'Срок действия — от 1 дня')
      .max(90, 'Срок действия — до 90 дней'),
  })
  .superRefine((values, ctx) => {
    if (values.salaryMin > values.salaryMax) {
      ctx.addIssue({
        code: 'custom',
        path: ['salaryMin'],
        message: 'Минимум не может быть больше максимума',
      })
    }
    if (values.contactChannel !== 'platform' && values.contactValue.length === 0) {
      ctx.addIssue({
        code: 'custom',
        path: ['contactValue'],
        message: 'Укажите контакт для связи',
      })
    }
  })

export type SendOfferForm = z.infer<typeof sendOfferSchema>

export type SendOfferDefaults = Partial<
  Pick<SendOfferForm, 'title' | 'description' | 'salaryMin' | 'salaryMax' | 'salaryType'>
>

/** Prefill the modal from the position when available (FE2.md FE-11). */
export function prefillFromPosition(position?: {
  title?: string
  description?: string
  salary_min?: number
  salary_max?: number
  salary_type?: SalaryType | '' | null
}): SendOfferDefaults {
  if (!position) return {}
  return {
    title: position.title,
    description: position.description,
    salaryMin: position.salary_min,
    salaryMax: position.salary_max,
    salaryType: position.salary_type || undefined,
  }
}

export type FieldErrors = Partial<Record<keyof SendOfferForm, string>>

export function buildInitialForm(defaults: SendOfferDefaults): SendOfferForm {
  return {
    title: defaults.title ?? '',
    description: defaults.description ?? '',
    salaryMin: defaults.salaryMin ?? 0,
    salaryMax: defaults.salaryMax ?? 0,
    salaryType: defaults.salaryType ?? ('' as SalaryType),
    contactChannel: 'email',
    contactValue: '',
    expiresInDays: 14,
  }
}

/** Zod output → API payload. `why_you` is never sent (server computes it, B9). */
export function toCreateOfferPayload(
  form: SendOfferForm,
  candidatePublicId: string,
  positionId?: string,
): CreateOfferPayload {
  return {
    candidate_public_id: candidatePublicId,
    ...(positionId ? { position_id: positionId } : {}),
    title: form.title,
    description: form.description,
    salary_min: form.salaryMin,
    salary_max: form.salaryMax,
    salary_type: form.salaryType,
    currency: 'RUB',
    contact_channel: form.contactChannel,
    contact_value: form.contactChannel === 'platform' ? 'platform' : form.contactValue,
    expires_in_days: form.expiresInDays,
  }
}

/** FE-11 error contract: map backend codes to human-readable Russian messages. */
export const OFFER_ERROR_MESSAGES: Record<string, string> = {
  salary_invalid:
    'Зарплата не прошла проверку на сервере: минимум должен быть больше 0 и не превышать максимум.',
  candidate_not_reachable:
    'Кандидат недоступен для оффера: он ещё не открыл контакты или ограничил согласия.',
  not_found: 'Кандидат или вакансия не найдены. Обновите пул и попробуйте снова.',
  validation_failed: 'Проверьте данные формы — некоторые поля заполнены неверно.',
  unauthorized: 'Сессия истекла, войдите заново.',
  forbidden: 'Недостаточно прав для отправки оффера.',
}

export type SendOfferUiError = { message: string; fieldErrors: FieldErrors }

const FIELD_KEY_MAP: Record<string, keyof SendOfferForm> = {
  salary_min: 'salaryMin',
  salary_max: 'salaryMax',
  salary_type: 'salaryType',
  title: 'title',
  description: 'description',
  contact_channel: 'contactChannel',
  contact_value: 'contactValue',
  candidate_public_id: 'title',
  expires_in_days: 'expiresInDays',
}

export function mapSendOfferError(error: unknown): SendOfferUiError {
  if (!(error instanceof ApiError)) {
    return { message: 'Не удалось отправить оффер. Попробуйте ещё раз.', fieldErrors: {} }
  }
  const fieldErrors: FieldErrors = {}
  for (const [field, msgs] of Object.entries(error.fieldErrors)) {
    const key = FIELD_KEY_MAP[field]
    if (key && msgs[0]) fieldErrors[key] = msgs[0]
  }
  const message =
    OFFER_ERROR_MESSAGES[error.code] ??
    (error.status === 404
      ? OFFER_ERROR_MESSAGES.not_found
      : (error.detail ?? 'Ошибка сервера.'))
  return { message, fieldErrors }
}
