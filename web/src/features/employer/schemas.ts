import { z } from 'zod'

/**
 * FE-09 · zod schemas for the company form and the position wizard.
 * Salary rules (FE2.md §FE-09): salary_min > 0, salary_max ≥ salary_min,
 * salary_type required with NO default — validated client-side before
 * submit so invalid salaries never reach the server (the backend answers
 * 500 for salary_min = 0 today, BE.md B15).
 */

const INN_LENGTHS = [10, 12] as const

export const companySchema = z.object({
  name: z.string().trim().min(2, 'Укажите название компании').max(255, 'Максимум 255 символов'),
  inn: z
    .string()
    .trim()
    .regex(/^\d*$/, 'ИНН — только цифры')
    .refine((v) => v === '' || INN_LENGTHS.includes(v.length as (typeof INN_LENGTHS)[number]), {
      message: 'ИНН должен содержать 10 или 12 цифр',
    }),
  website: z
    .string()
    .trim()
    .url('Укажите ссылку, например https://example.ru')
    .or(z.literal('')),
  email_domain: z
    .string()
    .trim()
    .regex(/^[a-z0-9.-]+\.[a-z]{2,}$/i, 'Например: company.ru')
    .or(z.literal('')),
  business_domain: z.string().trim().max(255, 'Максимум 255 символов').optional(),
  description: z.string().trim().max(2000, 'Максимум 2000 символов').optional(),
  contact_email: z.string().trim().email('Укажите корректный email').or(z.literal('')),
})
export type CompanyFormValues = z.input<typeof companySchema>

// --- position wizard --------------------------------------------------------------

export const salaryTypeSchema = z.enum(['gross', 'net'], {
  message: 'Выберите gross или net — значение по умолчанию не задано',
})

export const positionFormSchema = z
  .object({
    title: z.string().trim().min(3, 'Укажите название вакансии').max(255, 'Максимум 255 символов'),
    specialization: z.enum(['backend', 'frontend', 'ml_data']),
    grades: z.array(z.enum(['intern', 'junior', 'middle', 'senior'])).min(1, 'Выберите хотя бы один грейд'),
    must_skills: z.array(z.string()).default([]),
    nice_skills: z.array(z.string()).default([]),
    work_formats: z
      .array(z.enum(['office', 'hybrid', 'remote']))
      .min(1, 'Выберите хотя бы один формат работы'),
    location: z.string().trim().max(255, 'Максимум 255 символов').default(''),
    salary_min: z.coerce
      .number({ message: 'Укажите зарплату' })
      .int('Целое число')
      .min(1, 'Минимум должен быть больше 0'),
    salary_max: z.coerce
      .number({ message: 'Укажите зарплату' })
      .int('Целое число')
      .min(1, 'Минимум должен быть больше 0'),
    salary_type: salaryTypeSchema,
    team_context: z.string().trim().max(2000, 'Максимум 2000 символов').default(''),
    description: z.string().trim().max(5000, 'Максимум 5000 символов').default(''),
    allow_adjacent: z.boolean().default(false),
    is_public: z.boolean().default(true),
  })
  .refine((v) => v.salary_max >= v.salary_min, {
    message: 'Максимум не может быть меньше минимума',
    path: ['salary_max'],
  })

export type PositionFormValues = z.output<typeof positionFormSchema>
/** Raw form input before coercion (react-hook-form generic parameter). */
export type PositionFormInput = Omit<z.input<typeof positionFormSchema>, 'must_skills' | 'nice_skills'> & {
  must_skills?: string[]
  nice_skills?: string[]
}

/**
 * Form values as they live inside react-hook-form BEFORE zod coercion runs:
 * salary arrives from <input type="number"> as string, and taxonomy-driven
 * option lists (grades / work_formats) are plain `string[]` — the
 * renderers index label maps by them, and `toPositionInput` narrows/filters
 * them to the contract enums below.
 */
export type PositionFormState = Omit<PositionFormInput, 'salary_min' | 'salary_max' | 'grades' | 'work_formats'> & {
  salary_min: string
  salary_max: string
  grades: string[]
  work_formats: string[]
}

/** Draft skills arrays may arrive undefined from the parser; normalize once. */
export function uniqueSkills(values: readonly string[]): string[] {
  return [...new Set(values.map((v) => v.trim().toLowerCase()).filter(Boolean))]
}

/** Narrow free-form taxonomy strings to the schema's enum values at runtime. */
const isGrade = (g: string): g is 'intern' | 'junior' | 'middle' | 'senior' =>
  ['intern', 'junior', 'middle', 'senior'].includes(g)
const isFormat = (f: string): f is 'office' | 'hybrid' | 'remote' =>
  ['office', 'hybrid', 'remote'].includes(f)
const isSpec = (s: string): s is 'backend' | 'frontend' | 'ml_data' =>
  ['backend', 'frontend', 'ml_data'].includes(s)

/**
 * Map raw form input (before zod coercion/defaults) onto PositionFormValues.
 * Taxonomy-driven options are plain strings, so unknown values are
 * filtered out here; zod validation still guards the required fields.
 */
export function toPositionInput(values: PositionFormState): PositionFormValues {
  const grades = (values.grades ?? []).filter(isGrade)
  const workFormats = (values.work_formats ?? []).filter(isFormat)
  return {
    title: values.title,
    specialization: isSpec(values.specialization) ? values.specialization : 'backend',
    grades,
    must_skills: uniqueSkills(values.must_skills ?? []),
    nice_skills: uniqueSkills(values.nice_skills ?? []),
    work_formats: workFormats,
    location: values.location ?? '',
    salary_min: Number(values.salary_min),
    salary_max: Number(values.salary_max),
    salary_type: values.salary_type,
    team_context: values.team_context ?? '',
    description: values.description ?? '',
    allow_adjacent: values.allow_adjacent ?? false,
    is_public: values.is_public ?? true,
  }
}

// --- FE-11 · send-offer modal ---------------------------------------------------

export const CONTACT_CHANNELS = ['email', 'phone', 'telegram', 'platform'] as const

/**
 * POST /api/offers form schema (FE2.md §FE-11). Salary rules mirror the
 * position wizard (B15): min > 0, max ≥ min, salary_type has NO default and
 * is always sent explicitly. `why_you` is not part of this form at all —
 * the server computes it (B9).
 */
export const offerFormSchema = z
  .object({
    title: z.string().trim().min(3, 'Укажите название вакансии').max(255, 'Максимум 255 символов'),
    description: z.string().trim().min(10, 'Добавьте описание — от 10 символов').max(5000, 'Максимум 5000 символов'),
    salary_min: z.coerce
      .number({ message: 'Укажите зарплату' })
      .int('Целое число')
      .min(1, 'Минимум должен быть больше 0'),
    salary_max: z.coerce
      .number({ message: 'Укажите зарплату' })
      .int('Целое число')
      .min(1, 'Укажите зарплату'),
    salary_type: salaryTypeSchema,
    contact_channel: z.enum(['email', 'phone', 'telegram', 'platform']),
    // No .default(''): contact_value is a plain controlled input, always present.
    contact_value: z.string().trim().max(255, 'Максимум 255 символов'),
    expires_in_days: z.coerce
      .number({ message: 'Целое число дней' })
      .int('Целое число')
      .min(1, 'Минимум 1 день')
      .max(90, 'Максимум 90 дней')
      .optional(),
  })
  .superRefine((v, ctx) => {
    if (Number(v.salary_max) < Number(v.salary_min)) {
      ctx.addIssue({ code: 'custom', path: ['salary_max'], message: 'Максимум не меньше минимума' })
    }
    // `platform` means in-platform chat — no external contact needed.
    if (v.contact_channel !== 'platform' && v.contact_value === '') {
      ctx.addIssue({ code: 'custom', path: ['contact_value'], message: 'Укажите контакт для связи' })
    }
    if (v.contact_channel === 'email' && v.contact_value !== '' && !z.string().email().safeParse(v.contact_value).success) {
      ctx.addIssue({ code: 'custom', path: ['contact_value'], message: 'Некорректный email' })
    }
  })

/**
 * Form values as they live inside react-hook-form BEFORE zod coercion runs:
 * number fields arrive from <input> as strings, so the form type stays `string`
 * and the schema (`z.coerce.number()`) produces the numeric output.
 */
export type OfferFormInput = {
  title: string
  description: string
  salary_min: string
  salary_max: string
  salary_type: 'gross' | 'net'
  contact_channel: (typeof CONTACT_CHANNELS)[number]
  contact_value: string
  expires_in_days?: string
}

/** Schema output after coercion (numbers) — the third useForm generic. */
export type OfferFormValues = z.output<typeof offerFormSchema>

/** Raw (uncoerced) form state → contract body for useSendOffer (expiry optional). */
export function toSendOfferInput(values: OfferFormInput | OfferFormValues): {
  title: string
  description: string
  salary_min: number
  salary_max: number
  salary_type: 'gross' | 'net'
  contact_channel: (typeof CONTACT_CHANNELS)[number]
  contact_value: string
  expires_in_days?: number
} {
  const days = values.expires_in_days === undefined || values.expires_in_days === '' ? undefined : Number(values.expires_in_days)
  return {
    title: values.title.trim(),
    description: values.description.trim(),
    salary_min: Number(values.salary_min),
    salary_max: Number(values.salary_max),
    salary_type: values.salary_type,
    contact_channel: values.contact_channel,
    contact_value: values.contact_channel === 'platform' ? '' : values.contact_value.trim(),
    ...(days != null && Number.isFinite(days) ? { expires_in_days: days } : {}),
  }
}
