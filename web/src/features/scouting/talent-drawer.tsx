import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Link2, Mail, Phone, Send, Star, X } from 'lucide-react'
import { ApiError } from '@/api/client'
import { useQueryClient } from '@tanstack/react-query'
import { useToggleShortlist, useTalent } from '@/api/scouting'
import type { SalaryType, TalentDetail, TalentShort } from '@/api/types'
import { keys } from '@/api/keys'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'
import { LeagueBadge, type Grade, type LeagueStatus, type Spec } from '@/components/domain/league-badge'
import { RatingBadge } from '@/components/domain/rating-badge'
import { FspBadge } from '@/components/domain/fsp-badge'
import { SkillChip } from '@/components/domain/skill-chip'
import { SalaryTag } from '@/components/domain/salary-tag'
import { WORK_FORMAT_LABEL } from '@/lib/labels'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * FE-10 · Candidate drawer (`?c=<public_id>` → GET /api/talent/{public_id}).
 * Sections for topics / assessments / integrity flags come later (gap G9):
 * they are hidden while absent. Contacts are null until the company gets a
 * grant (accepted offer) — then {full_name, email, phone, telegram}.
 */
export function TalentDrawer({ positionId }: { positionId: string }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const publicId = searchParams.get('c')
  const { data, isLoading, isError, error, refetch } = useTalent(publicId)

  if (!publicId) return null

  const close = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('c')
    setSearchParams(next, { replace: true })
  }

  const notFound = error instanceof ApiError && error.code === 'not_found'

  return (
    <>
      {/* Overlay: click closes the drawer; Esc handled by the panel below. */}
      <div
        className="fixed inset-0 z-40 bg-black/50"
        aria-hidden="true"
        onClick={close}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Карточка кандидата"
        tabIndex={-1}
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Escape') close()
        }}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col gap-4 overflow-y-auto border-l border-border bg-background p-4 shadow-xl"
      >
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-lg font-semibold">
            {data?.display_name ?? publicId}
          </h2>
          <Button variant="ghost" size="icon-sm" aria-label="Закрыть карточку" onClick={close}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {isLoading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-6 w-2/3 rounded-md" />
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-16 rounded-xl" />
          </div>
        ) : isError || !data ? (
          notFound ? (
            <p className="text-sm text-muted-foreground">Кандидат не найден или недоступен.</p>
          ) : (
            <ErrorState onRetry={() => void refetch()} />
          )
        ) : (
          <DrawerBody positionId={positionId} talent={data} onOpenOffer={() => navigate(`/employer/positions/${positionId}/offer?c=${encodeURIComponent(publicId)}`)} />
        )}
      </aside>
    </>
  )
}

function DrawerBody({
  positionId,
  talent,
  onOpenOffer,
}: {
  positionId: string
  talent: TalentDetail
  onOpenOffer: () => void
}) {
  const [shortlistBusy, setShortlistBusy] = useState(false)

  const copyContact = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      toast.success('Скопировано')
    } catch {
      /* clipboard unavailable in some browsers — the value stays visible */
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {talent.league && (
          <LeagueBadge
            status={talent.league.status as LeagueStatus}
            grade={talent.league.grade as Grade}
            spec={talent.league.specialization as Spec}
          />
        )}
        {talent.city && <span className="text-sm text-muted-foreground">{talent.city}</span>}
        {(talent.work_formats ?? []).map((f) => (
          <span key={f} className="text-sm text-muted-foreground">
            · {WORK_FORMAT_LABEL[f as string] ?? f}
          </span>
        ))}
      </div>

      {(talent.salary_min != null || talent.salary_max != null) && (
        <SalaryTag
          min={talent.salary_min ?? 0}
          max={talent.salary_max ?? 0}
          type={(talent.salary_type as SalaryType) || 'gross'}
          emphasize
        />
      )}

      {talent.last_active_at && (
        <p className="text-xs text-muted-foreground">
          Активность: {formatDate(talent.last_active_at)}
        </p>
      )}

      {talent.league?.rating != null && (
        <RatingBadge rating={talent.league.rating} percentile={talent.league.percentile} />
      )}

      {talent.fsp && (
        <FspBadge
          linked={talent.fsp.linked}
          rank={talent.fsp.rank as never}
          bestTier={talent.fsp.best_tier as never}
          results={talent.fsp.results}
        />
      )}

      {talent.about && <p className="text-sm">{talent.about}</p>}
      {talent.experience_text && (
        <section className="flex flex-col gap-1">
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">Опыт</h3>
          <p className="text-sm text-muted-foreground">{talent.experience_text}</p>
        </section>
      )}

      {talent.skills && talent.skills.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">Навыки</h3>
          <div className="flex flex-wrap gap-1.5">
            {talent.skills.map((s) => (
              <SkillChip key={s.id} name={s.name} source={s.source as never} />
            ))}
          </div>
        </section>
      )}

      {/* Gap G9 — these sections arrive later; hide them while absent. */}
      {talent.topics && talent.topics.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">Темы теста</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {talent.topics.map((t) => (
              <li key={t.key} className="flex justify-between">
                <span>{t.label}</span>
                <span className="tabular-nums text-muted-foreground">
                  {t.correct}/{t.total}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {talent.assessments && talent.assessments.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">Аттестации</h3>
        </section>
      )}
      {talent.integrity_flags && talent.integrity_flags.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">Integrity</h3>
        </section>
      )}

      <section className="flex flex-col gap-1.5">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">Контакты</h3>
        {talent.contacts ? (
          <div className="flex flex-col gap-1 text-sm">
            {talent.contacts.full_name && <div className="font-medium">{talent.contacts.full_name}</div>}
            {talent.contacts.email && (
              <button type="button" className="flex items-center gap-2 text-left hover:underline" onClick={() => void copyContact(talent.contacts!.email!)}>
                <Mail className="h-4 w-4 text-muted-foreground" /> {talent.contacts.email}
              </button>
            )}
            {talent.contacts.phone && (
              <button type="button" className="flex items-center gap-2 text-left hover:underline" onClick={() => void copyContact(talent.contacts!.phone!)}>
                <Phone className="h-4 w-4 text-muted-foreground" /> {talent.contacts.phone}
              </button>
            )}
            {talent.contacts.telegram && (
              <button type="button" className="flex items-center gap-2 text-left hover:underline" onClick={() => void copyContact(talent.contacts!.telegram!)}>
                <Send className="h-4 w-4 text-muted-foreground" /> {talent.contacts.telegram}
              </button>
            )}
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link2 className="h-4 w-4" />
            Контакты откроются после того, как кандидат примет оффер.
          </p>
        )}
      </section>

      <div className="sticky bottom-0 mt-auto flex flex-col gap-2 border-t border-border bg-background pt-3">
        {/* One primary action per screen: send the offer. Shortlist is secondary. */}
        <Button onClick={onOpenOffer}>
          <Send className="mr-1 h-4 w-4" /> Отправить оффер
        </Button>
        <ShortlistToggle
          positionId={positionId}
          publicId={talent.public_id}
          busy={shortlistBusy}
          setBusy={setShortlistBusy}
        />
      </div>
    </>
  )
}

function ShortlistToggle({
  positionId,
  publicId,
  busy,
  setBusy,
}: {
  positionId: string
  publicId: string
  busy: boolean
  setBusy: (v: boolean) => void
}) {
  // The tray cache tells whether this candidate is already shortlisted.
  const tray = useQueryClient().getQueryData<TalentShort[]>(keys.shortlist(positionId))
  const inTray = Boolean(tray?.some((t) => t.public_id === publicId))
  const toggle = useToggleShortlist(positionId)

  return (
    <Button
      variant="outline"
      disabled={busy}
      aria-pressed={inTray}
      onClick={() => {
        setBusy(true)
        toggle.mutate(
          { publicId, add: !inTray },
          { onSettled: () => setBusy(false) },
        )
      }}
    >
      <Star className={cn('mr-1 h-4 w-4', inTray && 'fill-current text-primary')} />
      {inTray ? 'В шорт-листе — убрать' : 'Добавить в шорт-лист'}
    </Button>
  )
}
