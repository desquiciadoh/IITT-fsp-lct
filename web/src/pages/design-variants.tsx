import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

type Variant = {
  id: string
  name: string
  desc: string
  cssClass: string
}

const VARIANTS: Variant[] = [
  {
    id: 'brand',
    name: 'Brand book (light)',
    desc: 'Утверждённая тема по брендбуку: Montserrat, белый фон, CTA #FF0053, заголовки #310F53, градиенты фиолетовой палитры.',
    cssClass: 'dv-brand',
  },
  {
    id: 'arena',
    name: 'Arena (dark)',
    desc: 'Тёмная «спортивная» тема: неон-акцент, крупные цифры рейтинга, ощущение турнирной таблицы.',
    cssClass: 'dv-arena',
  },
  {
    id: 'fsp-red',
    name: 'FSP Red (light)',
    desc: 'Светлая тема с красным акцентом ФСП: энергия, бренд, «официальный» тон федерации.',
    cssClass: 'dv-fsp-red',
  },
  {
    id: 'corporate',
    name: 'Corporate (light)',
    desc: 'Сдержанная деловая тема: синий, плотные данные, «hr-продукт для компании».',
    cssClass: 'dv-corporate',
  },
]

function Chip({ children }: { children: ReactNode }) {
  return (
    <span
      className="rounded-full border px-2 py-0.5 text-xs"
      style={{ borderColor: 'var(--v-line)', color: 'var(--v-muted)' }}
    >
      {children}
    </span>
  )
}

function OfferCard() {
  return (
    <div
      className="w-full max-w-sm rounded-xl border p-4"
      style={{ background: 'var(--v-panel)', borderColor: 'var(--v-line)' }}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase" style={{ color: 'var(--v-muted)' }}>
          Черновик оффера
        </span>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-semibold"
          style={{ background: 'var(--v-accent)', color: 'var(--v-accent-fg)' }}
        >
          отправлен
        </span>
      </div>
      <div className="mt-2 text-lg font-bold">Middle Python Backend</div>
      <div className="mt-1 text-2xl font-extrabold tabular-nums" style={{ color: 'var(--v-accent)' }}>
        180 000 – 260 000 ₽ <span className="text-sm font-medium">до вычета</span>
      </div>
      <div className="mt-2 text-sm" style={{ color: 'var(--v-muted)' }}>
        Yandex Tech · удалённо · Core Services
      </div>
      <div className="mt-3 flex gap-1.5">
        <Chip>тест подтверждён</Chip>
        <Chip>ФСП подтверждён</Chip>
      </div>
      <div className="mt-4 flex gap-2">
        <Button style={{ background: 'var(--v-accent)', color: 'var(--v-accent-fg)' }}>
          Принять
        </Button>
        <Button
          variant="outline"
          style={{ borderColor: 'var(--v-line)', color: 'var(--v-fg)' }}
        >
          Отклонить
        </Button>
      </div>
    </div>
  )
}

function LeagueCard() {
  return (
    <div
      className="w-full max-w-sm rounded-xl border p-4"
      style={{ background: 'var(--v-panel)', borderColor: 'var(--v-line)' }}
    >
      <div className="text-xs uppercase" style={{ color: 'var(--v-muted)' }}>
        бэкенд · мидл
      </div>
      <div className="mt-1 flex items-end gap-3">
        <span className="text-4xl font-extrabold tabular-nums">1240</span>
        <span className="mb-1 text-sm" style={{ color: 'var(--v-muted)' }}>
          ± 85 · 78-й перцентиль
        </span>
      </div>
      <div
        className="mt-3 h-2 w-full overflow-hidden rounded-full"
        style={{ background: 'var(--v-line)' }}
      >
        <div className="h-full w-[78%]" style={{ background: 'var(--v-accent)' }} />
      </div>
      <div className="mt-3 flex gap-1.5">
        <Chip>подтверждён</Chip>
        <Chip>2 приза ФСП</Chip>
      </div>
    </div>
  )
}

function VariantBlock({ variant }: { variant: Variant }) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-lg font-bold">{variant.name}</h2>
        <p className="text-sm text-muted-foreground">{variant.desc}</p>
      </div>
      <div
        className={cn('rounded-2xl border p-5', variant.cssClass)}
        style={{
          background: 'var(--v-bg)',
          color: 'var(--v-fg)',
          borderColor: 'var(--v-line)',
        }}
      >
        <header
          className="mb-4 flex items-center justify-between border-b pb-3"
          style={{ borderColor: 'var(--v-line)' }}
        >
          <span className="text-sm font-bold">FSP DRAFT</span>
          <nav className="flex gap-4 text-sm" style={{ color: 'var(--v-muted)' }}>
            <span>Кандидат</span>
            <span>Работодателю</span>
            <span>Лиги</span>
            <span
              className="rounded-lg px-2 py-1 font-semibold"
              style={{ background: 'var(--v-accent)', color: 'var(--v-accent-fg)' }}
            >
              Войти
            </span>
          </nav>
        </header>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <div className="text-2xl font-extrabold leading-tight">
              Тест подтверждает грейд.
              <br />
              Работодатель приходит первым.
            </div>
            <p className="mt-2 text-sm" style={{ color: 'var(--v-muted)' }}>
              Зарплата видна до первого сообщения. Контакты открываются только
              после принятия оффера.
            </p>
            <div className="mt-3 flex gap-2">
              <Button style={{ background: 'var(--v-accent)', color: 'var(--v-accent-fg)' }}>
                Начать тест
              </Button>
              <Button
                variant="outline"
                style={{ borderColor: 'var(--v-line)', color: 'var(--v-fg)' }}
              >
                Смотреть пул
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-3">
            <LeagueCard />
            <OfferCard />
          </div>
        </div>
      </div>
    </section>
  )
}

export function DesignVariantsPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-8 p-8">
      <div>
        <h1 className="text-2xl font-bold">Дизайн-направления</h1>
        <p className="text-muted-foreground">
          Три варианта визуальной темы на одном макете (шапка, герой, лига,
          оффер). Голосуй за вариант — дальше раскатываем его в токены.
        </p>
      </div>
      {VARIANTS.map((v) => (
        <VariantBlock key={v.id} variant={v} />
      ))}
    </main>
  )
}
