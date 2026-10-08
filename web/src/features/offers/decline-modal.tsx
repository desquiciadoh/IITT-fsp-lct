import { useState } from 'react'
import { DECLINE_REASON_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import type { DeclineReason } from '@/api/types'

const REASONS = Object.keys(DECLINE_REASON_LABEL) as DeclineReason[]

/** FE-07: decline modal with a required reason and an optional comment. */
export function DeclineModal({
  open,
  pending,
  onClose,
  onConfirm,
}: {
  open: boolean
  pending: boolean
  onClose: () => void
  onConfirm: (reason: DeclineReason, comment: string) => void
}) {
  const [reason, setReason] = useState<DeclineReason | ''>('')
  const [comment, setComment] = useState('')

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="decline-title"
        className="w-full max-w-md rounded-xl border border-border bg-card p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="decline-title" className="text-base font-semibold">
          Отклонить оффер
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Причина обязательна — работодатель увидит её в обобщённом виде.
        </p>

        <fieldset className="mt-4">
          <legend className="text-sm font-medium">Причина *</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {REASONS.map((r) => (
              <label
                key={r}
                className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm"
              >
                <input
                  type="radio"
                  name="decline-reason"
                  value={r}
                  checked={reason === r}
                  onChange={() => setReason(r)}
                />
                {DECLINE_REASON_LABEL[r]}
              </label>
            ))}
          </div>
        </fieldset>

        <label className="mt-4 block text-sm">
          Комментарий (необязательно)
          <textarea
            rows={3}
            maxLength={1000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Что можно улучшить в предложении"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </label>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Отмена
          </Button>
          <Button
            variant="destructive"
            disabled={!reason || pending}
            onClick={() => reason && onConfirm(reason, comment)}
          >
            {pending ? 'Отклоняем…' : 'Отклонить'}
          </Button>
        </div>
      </div>
    </div>
  )
}
