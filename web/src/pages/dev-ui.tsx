import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { LeagueBadge } from '@/components/domain/league-badge'
import { RatingBadge } from '@/components/domain/rating-badge'
import { SalaryTag } from '@/components/domain/salary-tag'
import { StatusChip, type OfferStatus } from '@/components/domain/status-chip'
import { ReasonChips } from '@/components/domain/reason-chips'
import { SkillChip } from '@/components/domain/skill-chip'
import type { Reason } from '@/api/types'
import { ScoreBar } from '@/components/domain/score-bar'
import { OfferCard } from '@/components/domain/offer-card'
import { TalentRow } from '@/components/domain/talent-row'
import { FspBadge } from '@/components/domain/fsp-badge'
import { TrustBadge } from '@/components/domain/trust-badge'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { ApplicationStatusChip } from '@/components/domain/application-status-chip'
import { RowSkeleton, ProfileSkeleton, CardSkeleton } from '@/components/ui/skeleton'
import type { Offer, TalentShort } from '@/api/types'

const ALL_STATUSES: OfferStatus[] = [
  'sent', 'viewed', 'accepted', 'declined', 'withdrawn', 'expired', 'interview', 'hired', 'closed',
]

const REASONS: Reason[] = [
  { kind: 'plus', text: 'SQL и агрегаты подтверждены тестом', source: 'test' },
  { kind: 'plus', text: 'Призёр чемпионата ФСП 2025', source: 'fsp' },
  { kind: 'plus', text: 'Выполнена микрозадача по API', source: 'microtask' },
  { kind: 'minus', text: 'Нет опыта с Kubernetes', source: 'declared' },
  { kind: 'info', text: 'Зарплата в диапазоне вакансии' },
]

const SCORE_LIST = [
  { key: 'skill' as const, contribution: 32 },
  { key: 'strength' as const, contribution: 21 },
  { key: 'grade' as const, contribution: 14 },
  { key: 'salary' as const, contribution: 9 },
  { key: 'semantic' as const, contribution: 7 },
  { key: 'freshness' as const, contribution: 5 },
]

const SCORE_DICT = { skill: 34, grade: 22, strength: 14, fsp: 15, salary: 8 }

const NOW = '2026-01-01T00:00:00.000Z'

const OFFERS: Offer[] = [
  {
    id: 'o-1',
    title: 'Middle Python Backend',
    company: { id: 'c-1', name: 'Yandex Tech', trust_level: 'verified' },
    salary_min: 180000,
    salary_max: 260000,
    salary_type: 'gross',
    status: 'sent',
    why_you: REASONS.slice(0, 3),
    version: 1,
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: 'o-2',
    title: 'Senior Go Engineer',
    company: { id: 'c-2', name: 'Avito', trust_level: 'domain' },
    salary_min: 300000,
    salary_max: 400000,
    salary_type: 'gross',
    status: 'accepted',
    version: 2,
    created_at: NOW,
    updated_at: NOW,
  },
  {
    id: 'o-3',
    title: 'Frontend Lead',
    company: { id: 'c-3', name: 'Tinkoff' },
    salary_min: 250000,
    salary_max: 320000,
    salary_type: 'net',
    status: 'declined',
    version: 1,
    created_at: NOW,
    updated_at: NOW,
  },
]

const TALENTS: TalentShort[] = [
  {
    public_id: 'C-47D2BD',
    display_name: 'anna.dev',
    league: { specialization: 'backend', grade: 'middle', status: 'confirmed' },
    city: 'Москва',
    work_formats: ['remote', 'hybrid'],
    salary_min: 200000,
    salary_max: 280000,
    salary_type: 'gross',
    fsp: { linked: true, best_tier: 'prize_winner', rank: 'kms', results: 4 },
  },
  {
    public_id: 'C-91A3F0',
    display_name: 'ivan.fe',
    league: { specialization: 'frontend', grade: 'senior', status: 'unconfirmed' },
    city: 'Санкт-Петербург',
    work_formats: ['office'],
    salary_min: 300000,
    salary_max: 380000,
    salary_type: 'gross',
    fsp: { linked: false },
  },
  {
    public_id: 'C-12E8C7',
    display_name: 'maria.ml',
    league: { specialization: 'ml_data', grade: 'junior', status: 'pending' },
    work_formats: ['remote'],
    salary_min: 120000,
    salary_max: 160000,
    salary_type: 'net',
    fsp: { linked: true, best_tier: 'participant', rank: 'cat3', results: 2 },
  },
]

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="border-b border-border pb-1 text-sm font-bold uppercase text-muted-foreground">
        {title}
      </h2>
      <div className="flex flex-wrap items-start gap-3">{children}</div>
    </section>
  )
}

export function DevUiPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-8 p-8">
      <div>
        <h1 className="text-2xl font-bold">UI-кит — FE-01</h1>
        <p className="text-muted-foreground">
          Доменные компоненты, все состояния на фикстурах. Тема: Arena (dark),
          токены в <code className="font-mono text-xs">src/styles/tokens.css</code>.
        </p>
      </div>

      <Section title="Кнопки (shadcn)">
        <Button>Основная</Button>
        <Button variant="secondary">Вторичная</Button>
        <Button variant="outline">С-outline</Button>
        <Button variant="ghost">Призрак</Button>
        <Button variant="destructive">Опасная</Button>
      </Section>

      <Section title="Лига (LeagueBadge)">
        <LeagueBadge status="confirmed" grade="middle" spec="backend" />
        <LeagueBadge status="unconfirmed" grade="senior" spec="frontend" />
        <LeagueBadge status="pending" grade="junior" spec="ml_data" />
        <LeagueBadge status="confirmed" grade="intern" />
      </Section>

      <Section title="Рейтинг (RatingBadge)">
        <RatingBadge rating={1240} ci={85} percentile={78} />
        <RatingBadge rating={980} ci={120} />
        <RatingBadge rating={1000} />
      </Section>

      <Section title="Зарплата (SalaryTag)">
        <SalaryTag min={180000} max={260000} type="gross" emphasize />
        <SalaryTag min={150000} max={200000} type="net" />
        <SalaryTag min={80000} max={120000} type="gross" />
      </Section>

      <Section title="Статусы (StatusChip)">
        {ALL_STATUSES.map((s) => (
          <StatusChip key={s} status={s} />
        ))}
      </Section>

      <Section title="Отклики (ApplicationStatusChip)">
        <ApplicationStatusChip status="applied" />
        <ApplicationStatusChip status="reviewing" />
        <ApplicationStatusChip status="interview" />
        <ApplicationStatusChip status="offer" />
        <ApplicationStatusChip status="rejected" />
        <ApplicationStatusChip status="withdrawn" />
      </Section>

      <Section title="Чипы причин (ReasonChips)">
        <ReasonChips reasons={REASONS} />
      </Section>

      <Section title="Скиллы (SkillChip)">
        <SkillChip name="Python" source="test" />
        <SkillChip name="PostgreSQL" source="fsp" />
        <SkillChip name="Kubernetes" source="declared" />
        <SkillChip name="Go" />
      </Section>

      <Section title="Скоринг — список компонентов (ScoreBar)">
        <div className="w-full max-w-md">
          <ScoreBar score={88} components={SCORE_LIST} />
        </div>
      </Section>

      <Section title="Скоринг — словарь бэка (ScoreBar)">
        <div className="w-full max-w-md">
          <ScoreBar score={93} components={SCORE_DICT} />
        </div>
      </Section>

      <Section title="Доверие и ФСП">
        <TrustBadge level="none" />
        <TrustBadge level="domain" />
        <TrustBadge level="verified" showLabel />
        <FspBadge linked={false} />
        <FspBadge linked rank="ms" bestTier="prize_winner" results={4} />
        <FspBadge linked rank="cat2" />
      </Section>

      <Section title="Черновик оффера (OfferCard)">
        {OFFERS.map((offer) => (
          <OfferCard key={offer.id} offer={offer} viewer="candidate" />
        ))}
      </Section>

      <Section title="Строка таланта (TalentRow)">
        <div className="flex w-full flex-col gap-2">
          <TalentRow
            talent={TALENTS[0]}
            score={91}
            reasons={REASONS.slice(0, 2)}
            shortlisted
            onToggleShortlist={() => {}}
          />
          <TalentRow
            talent={TALENTS[1]}
            score={74}
            reasons={[REASONS[3]]}
            onToggleShortlist={() => {}}
          />
          <TalentRow talent={TALENTS[2]} />
        </div>
      </Section>

      <Section title="Скелетоны загрузки">
        <div className="w-full max-w-sm rounded-xl border border-border bg-card p-4">
          <ProfileSkeleton />
        </div>
        <div className="w-full max-w-sm rounded-xl border border-border bg-card p-4">
          <RowSkeleton count={3} />
        </div>
        <div className="w-full max-w-md">
          <CardSkeleton />
        </div>
      </Section>

      <Section title="Пустое и ошибочное состояние">
        <div className="w-full max-w-sm">
          <EmptyState
            title="Офферов пока нет"
            description="Когда работодатель пришлёт оффер, он появится здесь."
          />
        </div>
        <div className="w-full max-w-sm">
          <ErrorState
            description="Бэкенд недоступен. Попробуйте обновить страницу."
            code="api_error"
            onRetry={() => {}}
          />
        </div>
      </Section>
    </main>
  )
}
