import { z } from 'zod'

export const consentSchema = z.object({
  processing: z.boolean().refine((v) => v, 'Без согласия нельзя продолжить'),
  publication: z.boolean(),
  fsp_sync: z.boolean(),
})
export type ConsentValues = z.infer<typeof consentSchema>

export const surveySchema = z
  .object({
    specialization: z.enum(['backend', 'frontend', 'ml_data'], {
      message: 'Выберите специализацию',
    }),
    years_experience: z
      .number()
      .min(0, 'Не может быть меньше 0')
      .max(50, 'Слишком много')
      .nullable()
      .optional(),
    roles: z.array(z.string().min(1)).min(1, 'Укажите хотя бы одну роль'),
    work_formats: z
      .array(z.enum(['office', 'hybrid', 'remote']))
      .min(1, 'Выберите хотя бы один формат'),
    salary_min: z
      .number({ message: 'Укажите зарплату' })
      .int('Целое число')
      .min(1, 'Минимум 1 ₽')
      .max(2147483647, 'Слишком много'),
    salary_max: z
      .number({ message: 'Укажите зарплату' })
      .int('Целое число')
      .min(1, 'Минимум 1 ₽')
      .max(2147483647, 'Слишком много'),
    salary_type: z.enum(['gross', 'net'], { message: 'Выберите gross или net' }),
    salary_floor: z.number().int().min(0).nullable().optional(),
    about: z.string().max(2000, 'Максимум 2000 символов').optional(),
  })
  .refine((v) => v.salary_min <= v.salary_max, {
    message: 'Минимум не может быть больше максимума',
    path: ['salary_max'],
  })

export type SurveyValues = z.input<typeof surveySchema>
export type SurveyOutput = z.output<typeof surveySchema>
