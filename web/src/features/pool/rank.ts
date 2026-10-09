/**
 * FE-17 live pool re-ranking: score = Σ component × weight. Contributions are
 * re-weighted the same way, so they always sum to the shown score — the bar
 * just normalizes the proportions via `normalizeComponents()`.
 */
import type {
  PoolWeights,
  ScoreComponent,
  ScoreComponentsDict,
  WeightPreset,
} from '@/api/types'

export const SCORE_KEYS: ScoreComponent['key'][] = [
  'skill',
  'strength',
  'grade',
  'salary',
  'semantic',
  'freshness',
  'fsp',
]

export const PRESETS: Record<WeightPreset, PoolWeights> = {
  balanced: {
    skill: 0.3,
    grade: 0.2,
    strength: 0.15,
    fsp: 0.15,
    salary: 0.1,
    semantic: 0.05,
    freshness: 0.05,
  },
  skills: {
    skill: 0.4,
    grade: 0.25,
    strength: 0.15,
    fsp: 0.1,
    salary: 0.05,
    semantic: 0.03,
    freshness: 0.02,
  },
  budget: {
    salary: 0.45,
    skill: 0.2,
    grade: 0.15,
    strength: 0.1,
    fsp: 0.05,
    semantic: 0.03,
    freshness: 0.02,
  },
}

export const PRESET_ORDER: WeightPreset[] = ['balanced', 'skills', 'budget']

export function weightedComponents(
  components: ScoreComponentsDict,
  weights: PoolWeights,
): ScoreComponentsDict {
  const out: ScoreComponentsDict = {}
  for (const key of SCORE_KEYS) {
    const contribution = components[key]
    const weight = weights[key] ?? 0
    if (typeof contribution === 'number' && contribution > 0 && weight > 0) {
      out[key] = contribution * weight
    }
  }
  return out
}

export function weightedScore(
  components: ScoreComponentsDict,
  weights: PoolWeights,
): number {
  const sum = Object.values(weightedComponents(components, weights)).reduce(
    (acc, value) => acc + (value ?? 0),
    0,
  )
  const clamped = Math.min(100, Math.max(0, sum))
  return Math.round(clamped * 10) / 10
}

/** Renormalise the given weights to sum to 1 (keeps every nonzero key). */
export function normalizeWeights(weights: PoolWeights): PoolWeights {
  const entries = Object.entries(weights).filter(([, value]) => (value ?? 0) > 0)
  const total = entries.reduce((acc, [, value]) => acc + (value ?? 0), 0)
  if (total <= 0) return {}
  const out: PoolWeights = {}
  for (const [key, value] of entries) {
    out[key as ScoreComponent['key']] = Math.round(((value ?? 0) / total) * 1000) / 1000
  }
  return out
}

export type RankedPoolItem = {
  candidate: import('@/api/types').PoolCandidate
  score: number
  components: ScoreComponentsDict
}

/** Re-rank the pool client-side under the given weights (no request). */
export function rankedPool(
  candidates: import('@/api/types').PoolCandidate[],
  weights: PoolWeights,
): RankedPoolItem[] {
  return candidates
    .map((candidate) => {
      const score = weightedScore(candidate.components, weights)
      return {
        candidate,
        score,
        components: weightedComponents(candidate.components, weights),
      }
    })
    .sort((a, b) => b.score - a.score || a.candidate.public_id.localeCompare(b.candidate.public_id))
}