import { z } from 'zod'

/**
 * FE-09 · Stage 1 — company profile form schema.
 * Field constraints mirror the OpenAPI `Company` model (max lengths, INN
 * pattern) plus friendly Russian messages. The backend PUT handler is an
 * upsert (gap G17), so the same schema drives both create and edit forms.
 */
export const companySchema = z.object({
  name: z.string().trim().min(1, 'Укажите название компании').max(255, 'Максимум 255 символов'),
  inn: z
    .string()
    .trim()
    .regex(/^(\d{10}|\d{12})$/, 'ИНН — 10 или 12 цифр')
    .optional()
    .or(z.literal('')),
  website: z
    .string()
    .trim()
    .url('Укажите адрес целиком, например https://example.ru')
    .optional()
    .or(z.literal('')),
  email_domain: z
    .string()
    .trim()
    .regex(/^[a-z0-9.-]+\.[a-z]{2,}$/i, 'Домен, например example.ru')
    .optional()
    .or(z.literal('')),
  business_domain: z.string().trim().max(255, 'Максимум 255 символов').optional().or(z.literal('')),
  description: z.string().trim().max(2000, 'Максимум 2000 символов').optional().or(z.literal('')),
  contact_email: z
    .string()
    .trim()
    .email('Укажите корректный email')
    .optional()
    .or(z.literal('')),
})
export type CompanyFormValues = z.infer<typeof companySchema>

/** Form values → PUT /api/companies/me payload (empty strings dropped). */
export function toCompanyInput(values: CompanyFormValues) {
  const clean = <T extends string | undefined>(v: T): T | undefined => (v ? v : undefined)
  return {
    name: values.name.trim(),
    inn: clean(values.inn),
    website: clean(values.website),
    email_domain: clean(values.email_domain),
    business_domain: clean(values.business_domain),
    description: clean(values.description),
    contact_email: clean(values.contact_email),
  }
}
