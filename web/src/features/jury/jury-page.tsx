import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FlaskConical, RotateCcw, Timer } from 'lucide-react'
import { customFetch, ApiError } from '@/api/client'
import { keys } from '@/api/keys'
import type { Me } from '@/api/types'
import { errorMessage } from '@/i18n/errors'
import { PERSONAS, type PersonaId } from '@/lib/personas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type TimeTravelResponse = { clock_offset_days: number }

const GUIDE = [
  {
    title: 'Что это',
    body: 'FSP Draft — платформа обратного найма: кандидаты проходят тест и попадают в Лиги, работодатели сами присылают офферы с зарплатой. Судьям — быстрый тур по всем ролям.',
  },
  {
    title: 'Персоны',
    body: 'Одна кнопка — мгновенный вход от роли. Переключайтесь между Анной, Алексом и компанией, чтобы увидеть разные взгляды на одни и те же данные.',
  },
  {
    title: 'Time travel',
    body: 'Сдвигает демо-часы вперёд: кулдауны пересдачи, дедлайны офферов и «свежесть» данных срабатывают мгновенно — без ожидания суток.',
  },
  {
    title: 'Reset',
    body: 'Возвращает демо-данные к исходному состоянию, если эксперименты зашли слишком далеко.',
  },
]

export function JuryPage() {
  const navigate = useNavigate()
  const client = useQueryClient()
  const [days, setDays] = useState('30')
  const [offset, setOffset] = useState<number | null>(null)

  const handleError = (error: unknown) =>
    toast.error(
      error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось выполнить запрос.',
    )

  const loginPersona = useMutation({
    mutationFn: (persona: PersonaId) =>
      customFetch<Me>('/api/demo/persona', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona }),
      }),
    meta: { skipAuthRedirect: true },
    onSuccess: (data) => {
      // Drop the anonymous cache and seed the caretaker user before redirecting,
      // so we never flash the previous role's data.
      client.clear()
      if (data) client.setQueryData(keys.me, data)
      client.invalidateQueries({ queryKey: keys.me })
      navigate('/', { replace: true })
    },
    onError: handleError,
  })

  const timeTravel = useMutation({
    mutationFn: (value: number) =>
      customFetch<TimeTravelResponse>('/api/demo/time-travel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: value }),
      }),
    onSuccess: (data) => {
      setOffset(data.clock_offset_days)
      toast.success(`Смещение часов: +${data.clock_offset_days} дн.`)
    },
    onError: handleError,
  })

  const reset = useMutation({
    mutationFn: () =>
      customFetch<void>('/api/demo/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      }),
    onSuccess: () => {
      void client.invalidateQueries()
      toast.success('Демо-данные сброшены')
    },
    onError: handleError,
  })

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-4 py-10">
      <header className="flex flex-col gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Jury Mode
        </span>
        <h1 className="text-2xl font-bold">Как смотреть FSP Draft за 5 минут</h1>
        <p className="text-muted-foreground">
          Короткий гид для судей хакатона: роли, экраны и демо-инструменты.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2">
        {GUIDE.map((item) => (
          <article key={item.title} className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-bold">{item.title}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{item.body}</p>
          </article>
        ))}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="border-b border-border pb-1 text-sm font-bold uppercase text-muted-foreground">
          Войти персоной
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {PERSONAS.map((persona) => (
            <button
              key={persona.id}
              type="button"
              disabled={loginPersona.isPending}
              onClick={() => loginPersona.mutate(persona.id)}
              className={cn(
                'rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary hover:bg-secondary',
                'disabled:opacity-60',
              )}
            >
              <div className="text-sm font-semibold">{persona.title}</div>
              <div className="mt-1 text-xs text-muted-foreground">{persona.description}</div>
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="border-b border-border pb-1 text-sm font-bold uppercase text-muted-foreground">
          Демо-инструменты
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Timer className="h-4 w-4 text-info" /> Time travel
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Сдвигает демо-часы вперёд на N дней.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <Input
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={(e) => setDays(e.target.value)}
                aria-label="Дней"
                className="w-24"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={timeTravel.isPending}
                onClick={() => timeTravel.mutate(Number(days) || 30)}
              >
                Прыгнуть
              </Button>
            </div>
            {offset !== null && (
              <p className="mt-2 text-xs text-muted-foreground">
                Текущее смещение: <span className="font-mono">+{offset} дн.</span>
              </p>
            )}
          </div>

          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <RotateCcw className="h-4 w-4 text-warn" /> Reset
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Возвращает демо-данные к исходному состоянию.
            </p>
            <Button
              size="sm"
              variant="outline"
              className="mt-3"
              disabled={reset.isPending}
              onClick={() => reset.mutate()}
            >
              Сбросить
            </Button>
          </div>
        </div>
      </section>

      <footer className="flex items-center gap-4 border-t border-border pt-4 text-sm">
        <Link
          to="/lab"
          className="inline-flex items-center gap-1.5 font-medium underline underline-offset-4"
        >
          <FlaskConical className="h-4 w-4" /> Validation Lab
        </Link>
        <span className="text-muted-foreground">
          Нужен сид данных: <code className="font-mono text-xs">manage.py seed --mode=mini</code>
        </span>
      </footer>
    </main>
  )
}
