import { z } from 'zod'

/**
 * FE-09 · Stage 2 — position wizard form schema.
 *
 * Field constraints mirror the OpenAPI `Position` model, but the salary block
 * is intentionally STRICTER than the backend (BE.md B15): Django returns a
 * generic 422 `salary_invalid` (and historically 500 for salary_min = 0), so
 * every salary problem must be caught client-side BEFORE submit:
 *  - salary_min > 0;
 *  - salary_max >= salary_min;
 *  - salary_type has no default — the employer must explicitly pick gross/net
 *    (TK.md: salary transparency is a core product principle).
 */
export const SALARY_TYPES = ['gross', 'net'] as const
export type SalaryType = (typeof SALARY_TYPES)[number]

const MAX_SALARY = 2_147_483_647

export const positionSchema = z
  .object({
    title: z
      .string()
      .trim()
      .min(1, 'Укажите название вакансии')
      .max(255, 'Максимум 255 символов'),
    specialization: z.enum(['backend', 'frontend', 'ml_data'], {
      message: 'Выберите специализацию',
    }),
    grades: z
      .array(z.enum(['intern', 'junior', 'middle', 'senior']))
      .min(1, 'Выберите хотя бы один грейд'),
    must_skills: z.array(z.string().trim()).default([]),
    nice_skills: z.array(z.string().trim()).default([]),
    work_formats: z.array(z.enum(['office', 'hybrid', 'remote'])).default([]),
    location: z.string().trim().max(255, 'Максимум 255 символов').default(''),
    salary_min: z
      .number({ message: 'Укажите минимальную зарплату' })
      .int('Целое число рублей в месяц')
      .positive('Зарплата «от» должна быть больше нуля')
      .max(MAX_SALARY, 'Слишком большое значение'),
    salary_max: z
      .number({ message: 'Укажите максимальную зарплату' })
      .int('Целое число рублей в месяц')
      .max(MAX_SALARY, 'Слишком большое значение'),
    // gap G6: the parse draft never sets salary_type — force an explicit choice.
    salary_type: z.enum(SALARY_TYPES, {
      message: 'Обязательно выберите: до вычета налогов или на руки',
    }),
    team_context: z.string().trim().max(2000, 'Максимум 2000 символов').default(''),
    description: z.string().trim().max(5000, 'Максимум 5000 символов').default(''),
    allow_adjacent: z.boolean().default(false),
    is_public: z.boolean().default(true),
  })
  .superRefine((val, ctx) => {
    if (
      typeof val.salary_min === 'number' &&
      typeof val.salary_max === 'number' &&
      Number.isFinite(val.salary_min) &&
      Number.isFinite(val.salary_max) &&
      val.salary_max < val.salary_min
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['salary_max'],
        message: '«До» не может быть меньше «От»',
      })
    }
    const overlap = val.must_skills.filter((s) => val.nice_skills.includes(s))
    if (overlap.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['nice_skills'],
        message: `Навык «${overlap[0]}» нельзя указать одновременно как обязательный и желательный`,
      })
    }
  })

export type PositionFormValues = z.infer<typeof positionSchema>

/** Numeric form fields arrive as strings from <input>; coerce before parsing. */
export function parsePositionForm(values: PositionFormValues) {
  return positionSchema.safeParse({
    ...values,
    salary_min: Number(values.salary_min),
    salary_max: Number(values.salary_max),
  })
}

/** Map zod issues to `{field: message}` for inline rendering (first issue wins). */
export function fieldErrorsFromError(error: z.ZodError): Partial<Record<string, string>> {
  const out: Partial<Record<string, string>> = {}
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? '')
    if (key && !out[key]) out[key] = issue.message
  }
  return out
}

/**
 * Valid form values → POST /api/positions payload.
 * Empty optional strings are dropped; unknown_terms are NOT silently merged
 * into skills — only what the employer confirmed via chips is sent.
 */
export function toPositionInput(data: z.infer<typeof positionSchema>) {
  const {
    title,
    specialization,
    grades,
    must_skills,
    nice_skills,
    work_formats,
    location,
    salary_min,
    salary_max,
    salary_type,
    team_context,
    description,
    allow_adjacent,
    is_public,
  } = data
  const cleanList = (xs: string[]) => xs.map((s) => s.trim()).filter(Boolean)
  return {
    title: title.trim(),
    specialization,
    grades,
    must_skills: cleanList(must_skills),
    nice_skills: cleanList(nice_skills),
    work_formats,
    location: location || undefined,
    salary_min,
    salary_max,
    salary_type,
    team_context: team_context || undefined,
    description: description || undefined,
    allow_adjacent,
    is_public,
  }
}
