/**
 * FE-10 · Candidate drawer.
 *
 * Opens when the URL carries `?c=<public_id>` (single source of truth —
 * reload restores the drawer). Data: GET /api/talent/{public_id} (gap G9):
 *  - `contacts` is null until the company holds a grant → we show a gated
 *    placeholder instead of contact values;
 *  - FSP section renders `fsp_results` (gold/silver/bronze per event);
 *  - skills are split into verified vs self-reported (gap G8 sources);
 *  - topics/assessments/integrity sections render real rows once served.
 */
import { useEffect } from 'react'
import { CheckCircle2, Flag, Lock, ShieldAlert, Trophy, X } from 'lucide-react'

import { useTalent } from '@/api/scouting'
import type { Grade, LeagueStatus, PoolSkill, Source, Spec, TalentShortView } from '@/api/types'
import {
  ASSESSMENT_KIND_LABEL,
  FSP_TIER_LABEL,
  GRADE_LABEL,
  SKILL_SOURCE_GROUP_LABEL,
  SPEC_LABEL,
} from '@/lib/labels'
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
  poolTalent?: TalentShortView
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

  const talent: TalentShortView | undefined = data ?? poolTalent

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

            {/* skills — split by verification source (gap G8) */}
            {(talent.skills?.length ?? 0) > 0 && (
              <SkillsBlock skills={talent.skills!} />
            )}

            {/* FSP results — detailed per-event list (G9/G8 payload) */}
            {data?.fsp_results && data.fsp_results.length > 0 && (
              <Block title="ФСП">
                <ul className="flex flex-col gap-1.5" aria-label="Результаты ФСП">
                  {data.fsp_results.map((r, i) => (
                    <li key={r.event_id ?? i} className="flex items-center gap-2 text-sm">
                      <Trophy className="h-4 w-4 shrink-0 text-warn" aria-hidden />
                      <span className="min-w-0 flex-1 truncate">
                        {r.event_name ?? r.discipline ?? 'Соревнование'}
                        {r.date ? ` · ${new Date(r.date).getFullYear()}` : ''}
                      </span>
                      <span className="shrink-0 font-semibold text-xs uppercase">
                        {FSP_TIER_LABEL[r.tier ?? ''] ?? r.tier ?? '—'}
                        {r.placement != null ? ` · ${r.placement} место` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
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

            {/* G9 sections — rendered with real rows once BE serves them */}
            {Array.isArray(data?.topics) && data.topics.length > 0 && (
              <Block title="Топики">
                <ul className="flex flex-col gap-1 text-sm" aria-label="Результаты по топикам">
                  {data.topics.map((t, i) => (
                    <li key={t.key ?? i} className="flex items-center justify-between gap-2">
                      <span>{t.label ?? t.key}</span>
                      <span className="tabular-nums text-muted-foreground">
                        <CheckCircle2 className="mr-1 inline h-3.5 w-3.5 text-fsp-plus align-[-2px]" aria-hidden />
                        {t.correct}/{t.total}
                      </span>
                    </li>
                  ))}
                </ul>
              </Block>
            )}
            {Array.isArray(data?.assessments) && data.assessments.length > 0 && (
              <Block title="Аттестации">
                <ul className="flex flex-col gap-1 text-sm" aria-label="История аттестаций">
                  {data.assessments.map((a, i) => (
                    <li key={a.id ?? i} className="flex items-center justify-between gap-2">
                      <span>
                        {ASSESSMENT_KIND_LABEL[a.kind] ?? a.kind}
                        {a.taken_at ? ` · ${new Date(a.taken_at).toLocaleDateString('ru-RU')}` : ''}
                      </span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        {GRADE_LABEL[a.result_grade ?? ''] ?? a.result_grade ?? '—'}
                        {a.rating != null ? ` · ${a.rating}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              </Block>
            )}
            {Array.isArray(data?.integrity_flags) && data.integrity_flags.length > 0 && (
              <Block title="Добросовестность">
                <ul className="flex flex-col gap-1 text-sm" aria-label="Флаги добросовестности">
                  {data.integrity_flags.map((f, i) => (
                    <li key={f.session_id ?? i} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5">
                        <ShieldAlert className="h-4 w-4 shrink-0 text-warn" aria-hidden />
                        Сессия {f.session_id ?? `#${i + 1}`}
                        {f.taken_at ? ` · ${new Date(f.taken_at).toLocaleDateString('ru-RU')}` : ''}
                      </span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        потерь фокуса: {f.focus_loss ?? 0} · вставок: {f.paste ?? 0}
                        {f.flagged && (
                          <span className="ml-2 inline-flex items-center gap-1 font-semibold text-warn">
                            <Flag className="h-3 w-3" aria-hidden />
                            флаг
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </Block>
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

/** Skills grouped by verification source: verified vs self-reported (G8). */
function SkillsBlock({ skills }: { skills: PoolSkill[] }) {
  const isVerified = (s: PoolSkill) => s.source !== 'declared' && s.source !== undefined
  const verified = skills.filter(isVerified)
  const selfReported = skills.filter((s) => !isVerified(s))
  return (
    <Block title="Навыки">
      <div className="flex flex-col gap-2.5">
        {verified.length > 0 && (
          <SkillGroup label={SKILL_SOURCE_GROUP_LABEL.verified} skills={verified} />
        )}
        {selfReported.length > 0 && (
          <SkillGroup label={SKILL_SOURCE_GROUP_LABEL.self} skills={selfReported} />
        )}
      </div>
    </Block>
  )
}

function SkillGroup({ label, skills }: { label: string; skills: PoolSkill[] }) {
  return (
    <div className="flex flex-col gap-1" role="group" aria-label={label}>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <SkillChip key={s.name} name={s.name} source={s.source as PoolSkill['source'] extends never ? never : import('@/api/types').Source} />
        ))}
      </div>
    </div>
  )
}
