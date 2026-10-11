import type { MicroTaskDropCandidate } from '@/api/types'

export type DropStage = 'pending' | 'review' | 'rated'

export function dropStage(drop: MicroTaskDropCandidate): DropStage {
  if (!drop.submitted_at) return 'pending'
  if (drop.employer_rating != null) return 'rated'
  return 'review'
}

export const DROP_STAGE_LABEL: Record<DropStage, string> = {
  pending: 'не решено',
  review: 'на проверке',
  rated: 'оценено',
}

/** Auto-graded tasks return 0/1; open ones have no score until review. */
export function scoreText(score: number | null | undefined): string {
  if (score == null) return '—'
  if (score >= 1) return 'верно'
  if (score > 0) return 'частично'
  return 'неверно'
}

export function deadlinePassed(deadline: string | null | undefined): boolean {
  if (!deadline) return false
  return new Date(deadline).getTime() <= Date.now()
}

/** Prefill-friendly single answer field; both raw JSON and plain text survive. */
export function answerPreview(answer: unknown): string {
  if (answer == null || answer === '') return 'без ответа'
  const text = typeof answer === 'string' ? answer : JSON.stringify(answer)
  return text.length > 120 ? `${text.slice(0, 120)}…` : text
}