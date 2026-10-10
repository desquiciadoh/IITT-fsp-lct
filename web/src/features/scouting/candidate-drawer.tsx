/**
 * FE-10 · Candidate drawer.
 *
 * Opens when the URL carries `?c=<public_id>` (single source of truth —
 * reload restores the drawer). Data: GET /api/talent/{public_id} (gap G9):
 *  - `contacts` is null until the company holds a grant → we show a gated
 *    placeholder instead of contact values;
 *  - future sections (topics/assessments/integrity) are hidden while absent.
 */
import { useEffect } from 'react'
import { Lock, X } from 'lucide-react'

import { useTalent } from '@/api/scouting'
import type { Grade, LeagueStatus, Spec, TalentShort } from '@/api/types'
import { GRADE_LABEL, SPEC_LABEL } from '@/lib/labels'
import { LeagueBadge } from '@/components/domain/league-badge'
import { SalaryTag } from '@/components/domain/salary-tag'
import { SkillChip } from '@/components/domain/skill-chip'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { Skeleton } from '@/components/ui/skeleton'

export function CandidateDrawer({
  publicId,
  poolTalent,
  onClose,
}: {
  publicId: string
  /** row data already in the list — shown while the detail request settles */
  poolTalent?: TalentShort
  onClose: () => void
}) {
  const { data, isLoading, isError, refetch } = useTalent(publicId)

  // Esc closes the drawer (and clears ?c= through the caller).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const talent: TalentShort | undefined = data ?? poolTalent

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Карточка кандидата">
      {/* backdrop */}
      <button
        type="button"
        aria-label="Закрыть карточку"
        onClick={onClose}
        className="absolute inset-0 bg-black/40"
      />
      <section className="relative flex h-full w-full max-w-md flex-col gap-4 overflow-y-auto border-l border-border bg-card p-5 shadow-xl">
        <header className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-bold">{talent?.display_name ?? publicId}</h2>
            <p className="font-mono text-xs text-muted-foreground">{publicId}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {isError ? (
          <ErrorState
            title="Не удалось загрузить карточку"
            description="Проверьте соединение и попробуйте ещё раз."
            onRetry={() => void refetch()}
          />
        ) : isLoading && !talent ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : talent ? (
          <>
            {/* league + salary */}
            <div className="flex flex-wrap items-center gap-2">
              {talent.league && (
                <LeagueBadge
                  status={talent.league.status as LeagueStatus}
                  grade={talent.league.grade as Grade}
                  spec={talent.league.specialization as Spec}
                />
              )}
              {talent.city && <span className="text-sm text-muted-foreground">{talent.city}</span>}
            </div>
            {(talent.salary_min || talent.salary_max) && (
              <SalaryTag
                min={talent.salary_min ?? 0}
                max={talent.salary_max ?? 0}
                type={(talent.salary_type || 'gross') as 'gross' | 'net'}
                emphasize
              />
            )}

            {/* rating line */}
            {talent.league?.rating !== undefined && (
              <p className="text-sm text-muted-foreground">
                Рейтинг: <span className="font-semibold tabular-nums text-foreground">{talent.league.rating}</span>
                {talent.league.percentile !== undefined && (
                  <> · перцентиль <span className="tabular-nums">{talent.league.percentile}%</span></>
                )}
              </p>
            )}

            {/* skills */}
            {(talent.skills?.length ?? 0) > 0 && (
              <Block title="Навыки">
                <div className="flex flex-wrap gap-1.5">
                  {talent.skills!.map((s) => (
                    <SkillChip key={s} name={s} />
                  ))}
                </div>
              </Block>
            )}

            {/* about / experience — gap G9 fields, hidden while absent */}
            {data?.about && (
              <Block title="О себе">
                <p className="text-sm leading-relaxed">{data.about}</p>
              </Block>
            )}
            {data?.experience_text && (
              <Block title="Опыт">
                <p className="whitespace-pre-line text-sm leading-relaxed">{data.experience_text}</p>
              </Block>
            )}

            {/* contacts — gated until the company has a grant (G9) */}
            <Block title="Контакты">
              {data?.contacts ? (
                <ul className="flex flex-col gap-1 text-sm">
                  {data.contacts.email && <li>Email: {data.contacts.email}</li>}
                  {data.contacts.phone && <li>Телефон: {data.contacts.phone}</li>}
                  {data.contacts.telegram && <li>Telegram: {data.contacts.telegram}</li>}
                </ul>
              ) : (
                <div className="flex items-start gap-2 rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">
                  <Lock className="mt-0.5 h-4 w-4 shrink-0" />
                  Контакты откроются после того, как кандидат примет оффер этой компании.
                </div>
              )}
            </Block>

            {/* future G9 sections — rendered only once BE serves them */}
            {Array.isArray(data?.topics) && data.topics.length > 0 && (
              <Block title="Топики"><EmptyState title="данные топиков появятся здесь" /></Block>
            )}
            {Array.isArray(data?.assessments) && data.assessments.length > 0 && (
              <Block title="Аттестации"><EmptyState title="данные аттестаций появятся здесь" /></Block>
            )}

            <p className="mt-auto pt-2 text-xs text-muted-foreground">
              Грейд лиги: {GRADE_LABEL[talent.league?.grade ?? ''] ?? '—'} · Специализация:{' '}
              {SPEC_LABEL[talent.league?.specialization ?? ''] ?? '—'}
            </p>
          </>
        ) : (
          <EmptyState title="Кандидат не найден" description="Возможно, профиль удалён или ссылка устарела." />
        )}
      </section>
    </div>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  )
}
