import { useState } from 'react'
import { Send } from 'lucide-react'
import { ScoreBar } from '@/components/domain/score-bar'
import { Button } from '@/components/ui/button'
import { AcceptLikelihoodBadge } from '@/features/pool/components/accept-likelihood-badge'
import { SendOfferDialog } from '@/features/pool/components/send-offer-dialog'
import type { ScoreComponentsDict } from '@/api/types'
import type { RankedPoolItem } from '@/features/pool/rank'

/** FE-17: pool row re-ranked client-side; contributions sum to the shown score. */
export function PoolRow({ item }: { item: RankedPoolItem }) {
  const [inviting, setInviting] = useState(false)
  const { candidate, score, components } = item

  return (
    <li className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <span className="text-sm font-semibold">{candidate.display_name}</span>
          <span className="font-mono text-xs text-muted-foreground">
            {candidate.public_id}
            {candidate.city ? ` · ${candidate.city}` : ''}
          </span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {candidate.skills.map((skill) => (
              <span key={skill} className="rounded-md border border-border bg-secondary px-2 py-0.5 text-xs">
                {skill}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <AcceptLikelihoodBadge level={candidate.accept_likelihood} />
          <Button size="sm" onClick={() => setInviting(true)}>
            <Send className="h-4 w-4" /> Отправить
          </Button>
        </div>
      </div>

      <ScoreBar score={score} components={components as ScoreComponentsDict} />

      {inviting && (
        <SendOfferDialog candidate={candidate} onClose={() => setInviting(false)} />
      )}
    </li>
  )
}