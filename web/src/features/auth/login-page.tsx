import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { customFetch, ApiError } from '@/api/client'
import { keys } from '@/api/keys'
import type { Me } from '@/api/types'
import { errorMessage } from '@/i18n/errors'
import { applyApiErrorToForm } from '@/features/auth/form-errors'
import { resolveNext } from '@/features/auth/next-route'
import { loginSchema, type LoginValues } from '@/features/auth/schemas'
import { AuthShell } from '@/features/auth/auth-shell'
import { PERSONAS } from '@/lib/personas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const client = useQueryClient()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })

  const finish = (data?: Me) => {
    // Clear first: never let the previous session leak into the next screen.
    client.clear()
    if (data) client.setQueryData(keys.me, data)
    client.invalidateQueries({ queryKey: keys.me })
    // R20: return the user to the page that bounced them, but only inside
    // their own role area (guard against open redirects).
    navigate(resolveNext(searchParams.get('next'), data?.role ?? 'candidate'), { replace: true })
  }

  const handleError = (error: unknown) => {
    if (applyApiErrorToForm(error, setError)) return
    // Only the login form treats a bare 401 as bad credentials.
    const code =
      error instanceof ApiError
        ? error.code === 'unauthorized'
          ? 'bad_credentials'
          : error.code
        : undefined
    toast.error(
      error instanceof ApiError
        ? errorMessage(code, error.detail)
        : 'Не удалось войти. Проверьте соединение.',
    )
  }

  const login = useMutation({
    mutationFn: (values: LoginValues) =>
      customFetch<Me>('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      }),
    meta: { skipAuthRedirect: true },
    onSuccess: finish,
    onError: handleError,
  })

  const persona = useMutation({
    mutationFn: (id: string) =>
      customFetch<Me>('/api/demo/persona', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona: id }),
      }),
    meta: { skipAuthRedirect: true },
    onSuccess: finish,
    onError: handleError,
  })

  return (
    <AuthShell
      title="Вход"
      subtitle="Email и пароль или демо-персона"
      footer={
        <>
          Нет аккаунта?{' '}
          <Link to="/register" className="text-foreground underline underline-offset-4">
            Регистрация
          </Link>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={handleSubmit((values) => login.mutate(values))}
        noValidate
      >
        <div className="space-y-1.5">
          <label htmlFor="login-email" className="text-sm font-medium">
            Email
          </label>
          <Input
            id="login-email"
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
          <label htmlFor="login-password" className="text-sm font-medium">
            Пароль
          </label>
          <Input
            id="login-password"
            type="password"
            placeholder="••••••"
            autoComplete="current-password"
            aria-invalid={!!errors.password}
            {...register('password')}
          />
          {errors.password && (
            <p className="text-xs text-destructive" role="alert">
              {errors.password.message}
            </p>
          )}
        </div>
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? 'Входим…' : 'Войти'}
        </Button>
      </form>

      <div className="mt-5 space-y-2 border-t border-border pt-4">
        <div className="text-xs font-medium text-muted-foreground">Демо-персоны</div>
        <div className="grid grid-cols-2 gap-2">
          {PERSONAS.map((p) => (
            <Button
              key={p.id}
              variant="outline"
              size="sm"
              disabled={persona.isPending}
              onClick={() => persona.mutate(p.id)}
            >
              {p.shortLabel}
            </Button>
          ))}
        </div>
      </div>
    </AuthShell>
  )
}
