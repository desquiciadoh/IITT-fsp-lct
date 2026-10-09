import { z } from 'zod'

export const loginSchema = z.object({
  email: z.string().min(1, 'Укажите email').email('Некорректный email'),
  password: z.string().min(1, 'Введите пароль'),
})

export const registerSchema = z.object({
  email: z.string().min(1, 'Укажите email').email('Некорректный email'),
  password: z.string().min(6, 'Минимум 6 символов'),
  role: z.enum(['candidate', 'employer'], {
    message: 'Выберите роль',
  }),
})

export type LoginValues = z.infer<typeof loginSchema>
export type RegisterValues = z.infer<typeof registerSchema>
