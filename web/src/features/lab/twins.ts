import type { LabTwinItem } from '@/api/types'

/** Difficulty (b) mapped to a 0..1 bar ratio over the IRT range [-3, 3]. */
export function difficultyRatio(b: number): number {
  if (!Number.isFinite(b)) return 0
  return Math.min(1, Math.max(0, (b + 3) / 6))
}

export function meanB(values: number[]): number {
  if (!values.length) return 0
  return values.reduce((sum, v) => sum + v, 0) / values.length
}

export function twinMeanDifficulty(twins: LabTwinItem[] | undefined): number {
  return meanB((twins ?? []).map((t) => t.b))
}

export function twinDuration(twins: LabTwinItem[] | undefined): number {
  return (twins ?? []).reduce((sum, t) => sum + t.time_limit_s, 0)
}

export function twinTopicCounts(
  twins: LabTwinItem[] | undefined,
): { topic: string; count: number }[] {
  const order: string[] = []
  const counts = new Map<string, number>()
  for (const t of twins ?? []) {
    if (!counts.has(t.topic)) order.push(t.topic)
    counts.set(t.topic, (counts.get(t.topic) ?? 0) + 1)
  }
  return order.map((topic) => ({ topic, count: counts.get(topic) ?? 0 }))
}

export function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return '0 с'
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = Math.round(totalSeconds % 60)
  if (minutes === 0) return `${seconds} с`
  if (seconds === 0) return `${minutes} мин`
  return `${minutes} мин ${seconds} с`
}
