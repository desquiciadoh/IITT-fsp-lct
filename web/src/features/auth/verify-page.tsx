import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { CheckCircle2, Loader2, MailQuestion, XCircle } from 'lucide-react'
import { customFetch, ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { useMe } from '@/api/me'
import { AuthShell } from '@/features/auth/auth-shell'
import { Button } from '@/components/ui/button'

/**
 * Email verification.
 * POST /api/auth/verify-email is live on the BE (G2 shipped); the `missing`
 * MSW mode keeps a stub for offline demos. In DEMO_MODE accounts are
 * auto-verified, so without a token we show the "confirmed" state when
 * /api/me says so (FE-02).
 */
export function VerifyPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const { data: me } = useMe()

  const verify = useMutation({
    mutationFn: (value: string) =>
      customFetch<void>('/api/auth/verify-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: value }),
      }),
  })

  const { mutate } = verify
  useEffect(() => {
    if (token) mutate(token)
  }, [token, mutate])

  if (token) {
    if (verify.isPending) {
      return (
        <AuthShell title="Подтверждение email" subtitle="Проверяем ссылку…">
          <div className="flex items-center justify-center gap-2 py-6 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" /> Подтверждаем…
          </div>
        </AuthShell>
      )
    }
    if (verify.isSuccess) {
      return (
        <AuthShell
          title="Email подтверждён"
          subtitle="Аккаунт активен — можно войти."
          footer={
            <Link to="/login">
              <Button>Войти</Button>
            </Link>
          }
        >
          <div className="flex flex-col items-center gap-2 py-4 text-center">
            <CheckCircle2 className="h-10 w-10 text-plus" aria-hidden />
            <p className="text-sm text-muted-foreground">
              Подтверждение прошло успешно.
            </p>
          </div>
        </AuthShell>
      )
    }
    const error = verify.error
    return (
      <AuthShell
        title="Ссылка не сработала"
        subtitle={
          error instanceof ApiError
            ? errorMessage(error.code, error.detail)
            : 'Не удалось подтвердить email.'
        }
        footer={
          <Link to="/register" className="underline underline-offset-4">
            Зарегистрироваться заново
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <XCircle className="h-10 w-10 text-minus" aria-hidden />
        </div>
      </AuthShell>
    )
  }

  if (me?.email_verified) {
    return (
      <AuthShell
        title="Email подтверждён"
        subtitle={me.email}
        footer={
          <Link to="/">
            <Button>В кабинет</Button>
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <CheckCircle2 className="h-10 w-10 text-plus" aria-hidden />
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Проверьте почту"
      subtitle="Мы отправили письмо со ссылкой для подтверждения"
      footer={
        <Link to="/login" className="underline underline-offset-4">
          Войти
        </Link>
      }
    >
      <div className="flex flex-col items-center gap-3 py-4 text-center">
        <MailQuestion className="h-10 w-10 text-info" aria-hidden />
        <p className="text-sm text-muted-foreground">
          В демо-режиме аккаунты подтверждаются автоматически — письмо может не
          прийти. Перейдите по ссылке из письма, чтобы подтвердить email.
        </p>
      </div>
    </AuthShell>
  )
}
