import { useEffect, useState } from 'react'
import { DECLINE_REASON_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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

  // Reset the form every time the dialog reopens.
  useEffect(() => {
    if (open) {
      setReason('')
      setComment('')
    }
  }, [open])

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !pending) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Отклонить оффер</DialogTitle>
          <DialogDescription>
            Причина обязательна — работодатель увидит её и сможет прислать более подходящее
            предложение.
          </DialogDescription>
        </DialogHeader>

        <fieldset>
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

        <label className="block text-sm">
          Комментарий (необязательно)
          <textarea
            rows={3}
            maxLength={1000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Что повлияло на решение?"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </label>

        <DialogFooter>
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
