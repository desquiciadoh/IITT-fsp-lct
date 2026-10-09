import { useState } from 'react'
import { AlertTriangle, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { useCreateOffer } from '@/api/offers'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { Button } from '@/components/ui/button'
import type { PoolCandidate } from '@/api/types'

/** FE-17: send-offer modal with a below-floor warning (the floor value stays hidden). */
export function SendOfferDialog({
  candidate,
  onClose,
}: {
  candidate: PoolCandidate
  onClose: () => void
}) {
  const send = useCreateOffer()
  const [title, setTitle] = useState(`Оффер · ${candidate.display_name}`)
  const [salaryMin, setSalaryMin] = useState(candidate.declared_salary_min)
  const [salaryMax, setSalaryMax] = useState(Math.round(candidate.declared_salary_min * 1.15))
  const [contactChannel, setContactChannel] = useState<'platform' | 'email' | 'telegram'>('platform')
  const [contactValue, setContactValue] = useState('')

  const belowFloor = salaryMax < candidate.declared_salary_min

  const submit = () =>
    send.mutate(
      {
        candidate_public_id: candidate.public_id,
        title,
        description: 'Приглашение из пула талантов.',
        salary_min: salaryMin,
        salary_max: salaryMax,
        salary_type: 'gross',
        contact_channel: contactChannel,
        contact_value: contactValue,
      },
      {
        onSuccess: () => {
          toast.success('Draft оффер отправлен кандидату')
          onClose()
        },
        onError: (error) =>
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось отправить оффер.',
          ),
      },
    )

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Оффер для ${candidate.display_name}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4"
      onClick={onClose}
    >
      <div
        className="flex w-full max-w-md flex-col gap-4 rounded-xl border border-border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <h2 className="text-base font-semibold">Отправить оффер</h2>
            <span className="font-mono text-xs text-muted-foreground">
              {candidate.display_name} · {candidate.public_id}
            </span>
          </div>
          <button aria-label="Закрыть" onClick={onClose} className="rounded-md p-1 hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </header>

        <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
          Название
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm normal-case text-foreground outline-none focus:border-primary"
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
            Зарплата от
            <input
              type="number"
              value={salaryMin}
              onChange={(e) => setSalaryMin(Number(e.target.value))}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
            Зарплата до
            <input
              type="number"
              value={salaryMax}
              onChange={(e) => setSalaryMax(Number(e.target.value))}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
            />
          </label>
        </div>

        {belowFloor && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-warn"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            Зарплата выше нижней планки кандидата — вероятен отказ без уточнения.
          </p>
        )}

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
            Канал связи
            <select
              value={contactChannel}
              onChange={(e) => setContactChannel(e.target.value as typeof contactChannel)}
              className="rounded-lg border border-border bg-background px-2 py-2 text-sm text-foreground outline-none focus:border-primary"
            >
              <option value="platform">Платформа</option>
              <option value="email">Email</option>
              <option value="telegram">Telegram</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs uppercase tracking-wide text-muted-foreground">
            Контакт
            <input
              value={contactValue}
              onChange={(e) => setContactValue(e.target.value)}
              placeholder="если не «платформа»"
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
            />
          </label>
        </div>

        <Button onClick={submit} disabled={send.isPending} className="self-end">
          <Send className="h-4 w-4" /> Отправить
        </Button>
      </div>
    </div>
  )
}