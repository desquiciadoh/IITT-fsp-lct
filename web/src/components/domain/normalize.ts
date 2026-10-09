/**
 * The backend emits score components both as a dict (pool items today) and as
 * a list (contract target) — see BE gap G8. Everything renders through this
 * normalizer so both shapes behave identically.
 */
import type { ScoreComponent, ScoreComponentsDict } from '@/api/types'

/** Max points per segment for the dict shape (sums to 100). */
const DICT_MAXES: Record<string, number> = {
  skill: 35,
  grade: 25,
  strength: 15,
  fsp: 15,
  salary: 10,
}

const DICT_TOTAL = Object.values(DICT_MAXES).reduce((a, b) => a + b, 0)

export function normalizeComponents(
  input: ScoreComponent[] | ScoreComponentsDict | undefined | null,
): ScoreComponent[] {
  if (!input) return []

  if (Array.isArray(input)) {
    const total = input.reduce((sum, c) => sum + Math.max(0, c.contribution), 0)
    return input.map((c) => ({
      ...c,
      weight: c.weight ?? (total > 0 ? Math.max(0, c.contribution) / total : 0),
    }))
  }

  return Object.entries(input)
    .filter(([, contribution]) => typeof contribution === 'number')
    .map(([key, contribution]) => ({
      key: key as ScoreComponent['key'],
      contribution: contribution as number,
      weight: (DICT_MAXES[key] ?? 10) / DICT_TOTAL,
    }))
}
