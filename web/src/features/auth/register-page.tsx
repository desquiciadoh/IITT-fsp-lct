import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { customFetch, ApiError } from '@/api/client'
import { keys } from '@/api/keys'
import type { Me } from '@/api/types'
import { errorMessage } from '@/i18n/errors'
import { applyApiErrorToForm } from '@/features/auth/form-errors'
import { registerSchema, type RegisterValues } from '@/features/auth/schemas'
import { AuthShell } from '@/features/auth/auth-shell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type RegisterResponse = {
  user_id: string
  email: string
  role: string
  email_verified: boolean
}

const ROLE_OPTIONS: { value: 'candidate' | 'employer'; title: string; hint: string }[] = [
  { value: 'candidate', title: 'Кандидат', hint: 'Тест, лига, офферы' },
  { value: 'employer', title: 'Работодатель', hint: 'Пул талантов, офферы' },
]

export function RegisterPage() {
  const navigate = useNavigate()
  const client = useQueryClient()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: '', password: '', role: 'candidate' },
  })

  const handleError = (error: unknown) => {
    const hasFieldErrors = applyApiErrorToForm(error, setError)
    if (error instanceof ApiError) {
      if (!hasFieldErrors || error.code !== 'validation_failed') {
        toast.error(errorMessage(error.code, error.detail))
      }
      return
    }
    toast.error('Не удалось создать аккаунт. Проверьте соединение.')
  }

  const registerMut = useMutation({
    mutationFn: (values: RegisterValues) =>
      customFetch<RegisterResponse>('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      }),
    onSuccess: async (result, values) => {
      try {
        const user = await customFetch<Me>('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: values.email, password: values.password }),
        })
        client.clear()
        if (user) client.setQueryData(keys.me, user)
        client.invalidateQueries({ queryKey: keys.me })
        if (result.email_verified) {
          toast.success('Аккаунт создан')
          navigate('/', { replace: true })
        } else {
          toast.success('Аккаунт создан. Подтвердите email.')
          navigate('/verify', { replace: true })
        }
      } catch (error) {
        handleError(error)
      }
    },
    onError: handleError,
  })

  return (
    <AuthShell
      title="Регистрация"
      subtitle="Выберите роль — она не меняется после создания аккаунта"
      footer={
        <>
          Уже есть аккаунт?{' '}
          <Link to="/login" className="text-foreground underline underline-offset-4">
            Войти
          </Link>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={handleSubmit((values) => registerMut.mutate(values))}
        noValidate
      >
        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium">Роль</legend>
          <div className="grid grid-cols-2 gap-2">
            {ROLE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={cn(
                  'cursor-pointer rounded-lg border p-3 transition-colors',
                  'has-[:checked]:border-primary has-[:checked]:bg-primary/10',
                  errors.role && 'border-destructive',
                )}
              >
                <input
                  type="radio"
                  value={option.value}
                  className="sr-only"
                  {...register('role')}
                />
                <div className="text-sm font-semibold">{option.title}</div>
                <div className="text-xs text-muted-foreground">{option.hint}</div>
              </label>
            ))}
          </div>
          {errors.role && (
            <p className="text-xs text-destructive" role="alert">
              {errors.role.message}
            </p>
          )}
        </fieldset>

        <div className="space-y-1.5">
          <label htmlFor="reg-email" className="text-sm font-medium">
            Email
          </label>
          <Input
            id="reg-email"
            type="email"
            placeholder="email@example.com"
            autoComplete="email"
            aria-invalid={!!errors.email}
            {...register('email')}
          />
          {errors.email && (
            <p className="text-xs text-destructive" role="alert">
              {errors.email.message}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reg-password" className="text-sm font-medium">
            Пароль
          </label>
          <Input
            id="reg-password"
            type="password"
            placeholder="Минимум 6 символов"
            autoComplete="new-password"
            aria-invalid={!!errors.password}
            {...register('password')}
          />
          {errors.password && (
            <p className="text-xs text-destructive" role="alert">
              {errors.password.message}
            </p>
          )}
        </div>

        <Button type="submit" className="w-full" disabled={registerMut.isPending}>
          {registerMut.isPending ? 'Создаём…' : 'Создать аккаунт'}
        </Button>
      </form>
    </AuthShell>
  )
}
