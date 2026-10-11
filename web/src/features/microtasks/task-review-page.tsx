import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, Star } from 'lucide-react'
import { ApiError } from '@/api/client'
import {
  useMicroTask,
  useMicroTaskSubmissions,
  usePrefillOffer,
  useRateSubmission,
} from '@/api/microtasks'
import { errorMessage } from '@/i18n/errors'
import { MICROTASK_FORMAT_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'
import { SendOfferModal } from '@/features/employer/send-offer-modal'
import type { OfferFormInput } from '@/features/employer/schemas'
import { answerPreview, scoreText } from '@/features/microtasks/format'
import type { MicroTaskPrefill, MicroTaskSubmission } from '@/api/types'

function RatingStars({ value, onPick }: { value: number; onPick: (n: number) => void }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          aria-label={`Оценка ${n}`}
          onClick={() => onPick(n)}
          className="p-0.5"
        >
          <Star
            className={`h-4 w-4 ${n <= value ? 'fill-current text-amber-500' : 'text-muted-foreground'}`}
          />
        </button>
      ))}
    </div>
  )
}

function SubmissionCard({
  submission,
  rating,
  onRate,
  onInvite,
  inviting,
}: {
  submission: MicroTaskSubmission
  rating: number | null | undefined
  onRate: (n: number) => void
  onInvite: () => void
  inviting: boolean
}) {
  const name = submission.candidate?.display_name ?? submission.candidate?.public_id ?? 'Кандидат'
  return (
    <Card className="gap-4 py-5">
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-col">
            <span className="font-semibold">{name}</span>
            {submission.candidate?.public_id && (
              <span className="font-mono text-xs text-muted-foreground">
                {submission.candidate.public_id}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-sm">
            {submission.score != null && (
              <Badge variant={submission.score >= 1 ? 'success' : 'outline'}>
                авто: {scoreText(submission.score)}
              </Badge>
            )}
            {submission.submitted_at && (
              <span className="text-xs text-muted-foreground">
                {new Date(submission.submitted_at).toLocaleString('ru-RU')}
              </span>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-background p-3 text-sm">
          {answerPreview(submission.answer)}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Оценка работодателя</span>
            <RatingStars value={rating ?? 0} onPick={onRate} />
          </div>
          <Button size="sm" variant="outline" disabled={inviting} onClick={onInvite}>
            {inviting ? 'Готовим оффер…' : 'Пригласить (оффер)'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export function TaskReviewPage() {
  const { id } = useParams<{ id: string }>()
  const { data: task, isLoading: taskLoading, isError: taskError, refetch: refetchTask } = useMicroTask(id ?? '')
  const { data: submissions, isLoading, isError, refetch } = useMicroTaskSubmissions(id ?? '')
  const rate = useRateSubmission()
  const prefill = usePrefillOffer()

  const [invite, setInvite] = useState<{
    defaults: Partial<OfferFormInput>
    candidate: { public_id: string; display_name?: string }
  } | null>(null)

  const openInvite = (submission: MicroTaskSubmission) => {
    prefill.mutate(submission.id, {
      onSuccess: (prefill_: MicroTaskPrefill) => {
        const defaults: Partial<OfferFormInput> = {
          title: prefill_.title,
          description: prefill_.description,
          salary_min: String(prefill_.salary_min),
          salary_max: String(prefill_.salary_max),
          ...(prefill_.salary_type === 'gross' || prefill_.salary_type === 'net'
            ? { salary_type: prefill_.salary_type }
            : {}),
        }
        setInvite({
          defaults,
          candidate: {
            public_id: prefill_.candidate_public_id,
            display_name: prefill_.candidate_name,
          },
        })
      },
      onError: (error) =>
        toast.error(
          error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось создать оффер.',
        ),
    })
  }

  const pickRating = (submission: MicroTaskSubmission, n: number) => {
    if (n === submission.employer_rating) return
    rate.mutate(
      { dropId: submission.id, employer_rating: n },
      {
        onSuccess: () => toast.success(`Оценка ${n}/5 сохранена`),
        onError: (error) =>
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось сохранить оценку.',
          ),
      },
    )
  }

  if (taskLoading || isLoading) return <RowSkeleton count={3} />
  if (taskError || isError) {
    return (
      <ErrorState
        onRetry={() => {
          void refetchTask()
          void refetch()
        }}
      />
    )
  }
  if (!task) return <ErrorState onRetry={() => void refetchTask()} />

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/employer/micro-tasks"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground"
      >
        <ArrowLeft className="h-3 w-3" /> Все задачи
      </Link>

      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold">{task.title}</h1>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline">{MICROTASK_FORMAT_LABEL[task.format] ?? task.format}</Badge>
          {task.grades.map((g) => (
            <Badge key={g} variant="outline">
              {g}
            </Badge>
          ))}
        </div>
      </div>

      {!submissions || submissions.length === 0 ? (
        <EmptyState
          title="Решений пока нет"
          description="Как только кандидат пришлёт ответ, он появится здесь."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {submissions.map((submission) => (
            <SubmissionCard
              key={submission.id}
              submission={submission}
              rating={submission.employer_rating}
              onRate={(n) => pickRating(submission, n)}
              onInvite={() => openInvite(submission)}
              inviting={prefill.isPending}
            />
          ))}
        </div>
      )}

      <SendOfferModal
        candidate={invite?.candidate}
        defaults={invite?.defaults}
        positionId={undefined}
        open={invite !== null}
        onClose={() => setInvite(null)}
        onSent={() => toast.success('Оффер отправлен')}
      />
    </div>
  )
}