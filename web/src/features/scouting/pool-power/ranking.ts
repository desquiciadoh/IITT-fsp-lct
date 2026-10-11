import { normalizeComponents } from '@/components/domain/normalize'
import type { PoolEntry, ScoreComponent } from '@/api/types'

/**
 * FE-17 · Pool power — live weight-based re-ranking.
 *
 * Pure helpers only (node-testable): presets, per-axis weights and a single
 * `rerank(items, weights)` that reorders the pool client-side (no request).
 * Re-ranked rows keep the "contributions sum to the shown score" invariant by
 * scaling the weighted segments to the computed display score.
 */

export const RANK_AXES = ['skill', 'grade', 'strength', 'salary', 'fsp'] as const
export type RankAxis = (typeof RANK_AXES)[number]

export type WeightProfile = Record<RankAxis, number>

export const RANK_AXIS_LABEL: Record<RankAxis, string> = {
  skill: 'Скиллы',
  grade: 'Грейд',
  strength: 'Профиль',
  salary: 'Зарплата',
  fsp: 'ФСП',
}

export type PresetKey = 'balanced' | 'skills' | 'budget'

export const PRESETS: { key: PresetKey; label: string; description: string; weights: WeightProfile }[] = [
  {
    key: 'balanced',
    label: 'Баланс',
    description: 'Все факторы равны',
    weights: { skill: 1, grade: 1, strength: 1, salary: 1, fsp: 1 },
  },
  {
    key: 'skills',
    label: 'Скиллы',
    description: 'Приоритет навыкам',
    weights: { skill: 3, grade: 1, strength: 1, salary: 0, fsp: 1 },
  },
  {
    key: 'budget',
    label: 'Бюджет',
    description: 'Приоритет зарплате',
    weights: { skill: 1, grade: 1, strength: 1, salary: 3, fsp: 0 },
  },
]

const AXIS_BY_KEY: Partial<Record<ScoreComponent['key'], RankAxis>> = {
  skill: 'skill',
  grade: 'grade',
  strength: 'strength',
  salary: 'salary',
  fsp: 'fsp',
  semantic: 'skill',
  freshness: 'strength',
}

export function axisFor(key: ScoreComponent['key']): RankAxis {
  return AXIS_BY_KEY[key] ?? 'skill'
}

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n))

export function isBalanced(weights: WeightProfile): boolean {
  const values = RANK_AXES.map((a) => weights[a])
  return values.length > 0 && values.every((v) => v === values[0])
}

export type RankedRow = {
  entry: PoolEntry
  /** display score in 0..100 — what the caller shows instead of entry.score */
  score: number
  /** weighted segments; contributions sum to `score` (render via ScoreBar) */
  components: ScoreComponent[]
}

export function rerank(items: PoolEntry[], weights: WeightProfile): RankedRow[] {
  if (isBalanced(weights)) {
    return items.map((entry) => ({
      entry,
      score: entry.score,
      components: normalizeComponents(entry.components),
    }))
  }

  const ranked = items.map((entry): RankedRow => {
    const norm = normalizeComponents(entry.components).filter((c) => (c.contribution ?? 0) > 0)
    // Preserve the entry when it carries no usable components.
    if (norm.length === 0) {
      return { entry, score: entry.score, components: normalizeComponents(entry.components) }
    }

    const weightOf = (c: ScoreComponent) => Math.max(0.0001, weights[axisFor(c.key)])
    const sumW = norm.reduce((s, c) => s + weightOf(c), 0)
    // Weighted average, rescaled by the number of present axes so balanced
    // weights reproduce the original sum (Σ c_i when all w equal).
    const score = clamp(
      Math.round(norm.reduce((s, c) => s + c.contribution * (weightOf(c) / sumW), 0) * norm.length),
      0,
      100,
    )

    // Re-scale segments so their contributions total exactly the shown score.
    const rawTotal = norm.reduce((s, c) => s + c.contribution * weightOf(c), 0) || 1
    const components = norm.map((c) => ({
      key: c.key,
      contribution: score * ((c.contribution * weightOf(c)) / rawTotal),
      weight: weightOf(c) / sumW,
    }))
    return { entry, score, components }
  })

  return ranked.sort((a, b) => b.score - a.score)
}