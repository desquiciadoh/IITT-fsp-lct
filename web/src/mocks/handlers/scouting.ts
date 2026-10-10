/**
 * FE-10 · Scouting mocks (mode `all`).
 *
 * Serves the employer scouting screen end-to-end without a backend:
 *  - GET  /api/positions, /api/positions/{id}          (header + dashboard)
 *  - GET  /api/positions/{id}/pool                     gap G8: response has
 *        NO `facets` (client-side fallback must kick in) and `components`
 *        is the legacy flat dict {skill, grade, strength, fsp, salary}.
 *  - PUT/DELETE /api/positions/{id}/shortlist/{pid}    stateful set → 204,
 *        so tray persistence across filter changes is testable. gap G16.
 *  - GET  /api/talent/{public_id}                      gap G9: contacts are
 *        null (no grant) — drawer must hide them until acceptance.
 */
import { http, HttpResponse } from 'msw'

import type { Grade, PoolItemView, Spec, TalentShort } from '@/api/types'

const json = (data: unknown) =>
  HttpResponse.json(data as Record<string, unknown>, { headers: { 'X-Stub': 'true' } })

// --- seed --------------------------------------------------------------------

type SeedTalent = {
  public_id: string
  display_name: string
  city: string
  spec: Spec
  grade: Grade
  status: 'confirmed' | 'pending' | 'unconfirmed'
  rating?: number
  percentile?: number
  strength?: number | null
  skills: string[]
  formats: ('office' | 'hybrid' | 'remote')[]
  salary_min: number
  salary_max: number
  fsp: { linked: boolean; best_tier?: string; rank?: string; results?: number }
  last_active_at: string
  about?: string
  experience_text?: string
}

const SEED: SeedTalent[] = [
  {
    public_id: 'A1B2C3', display_name: 'Анна К.', city: 'Москва', spec: 'backend',
    grade: 'senior', status: 'confirmed', rating: 2105, percentile: 97, strength: 82,
    skills: ['python', 'django', 'postgresql', 'redis', 'kafka'],
    formats: ['remote', 'hybrid'], salary_min: 320000, salary_max: 400000,
    fsp: { linked: true, best_tier: 'gold', rank: '1', results: 4 },
    last_active_at: '2026-10-08T10:00:00Z',
    about: 'Senior backend-инженер, платёжные системы и highload.',
    experience_text: '5 лет в финтехе: Django, PostgreSQL, Kafka. Призёр FSP 2025.',
  },
  {
    public_id: 'D4E5F6', display_name: 'Дмитрий С.', city: 'Санкт-Петербург', spec: 'backend',
    grade: 'middle', status: 'confirmed', rating: 1842, percentile: 88, strength: 71,
    skills: ['python', 'fastapi', 'postgresql', 'redis'],
    formats: ['remote'], salary_min: 220000, salary_max: 280000,
    fsp: { linked: true, best_tier: 'silver', rank: '2', results: 3 },
    last_active_at: '2026-10-07T09:00:00Z',
    about: 'Backend middle, микросервисы и REST/GraphQL.',
    experience_text: '3 года в e-commerce: FastAPI, PostgreSQL, Redis.',
  },
  {
    public_id: 'G7H8I9', display_name: 'Георгий П.', city: 'Казань', spec: 'backend',
    grade: 'middle', status: 'pending', rating: 1750, percentile: 79, strength: 64,
    skills: ['python', 'django', 'celery'],
    formats: ['hybrid', 'office'], salary_min: 180000, salary_max: 240000,
    fsp: { linked: false },
    last_active_at: '2026-10-05T15:00:00Z',
  },
  {
    public_id: 'J1K2L3', display_name: 'Елена В.', city: 'Новосибирск', spec: 'backend',
    grade: 'junior', status: 'confirmed', rating: 1520, percentile: 61, strength: 55,
    skills: ['python', 'django'],
    formats: ['remote', 'hybrid'], salary_min: 120000, salary_max: 160000,
    fsp: { linked: true, best_tier: 'bronze', rank: '3', results: 2 },
    last_active_at: '2026-10-06T12:00:00Z',
  },
  {
    public_id: 'M4N5O6', display_name: 'Максим Т.', city: 'Екатеринбург', spec: 'backend',
    grade: 'senior', status: 'unconfirmed', rating: 1990, percentile: 93, strength: null,
    skills: ['node.js', 'typescript', 'postgresql'],
    formats: ['remote'], salary_min: 350000, salary_max: 420000,
    fsp: { linked: false },
    last_active_at: '2026-10-01T08:00:00Z',
  },
  {
    public_id: 'P7Q8R9', display_name: 'Полина Р.', city: 'Москва', spec: 'backend',
    grade: 'middle', status: 'confirmed', rating: 1800, percentile: 85, strength: 68,
    skills: ['python', 'fastapi', 'kafka', 'redis'],
    formats: ['office', 'hybrid'], salary_min: 250000, salary_max: 300000,
    fsp: { linked: true, best_tier: 'finalist', rank: '8', results: 5 },
    last_active_at: '2026-10-09T18:00:00Z',
  },
  {
    public_id: 'S1T2U3', display_name: 'Сергей Н.', city: 'Нижний Новгород', spec: 'backend',
    grade: 'intern', status: 'pending', percentile: 40, strength: 30,
    skills: ['python'],
    formats: ['office'], salary_min: 80000, salary_max: 110000,
    fsp: { linked: false },
    last_active_at: '2026-09-28T11:00:00Z',
  },
  {
    public_id: 'V4W5X6', display_name: 'Виктория Л.', city: 'Москва', spec: 'backend',
    grade: 'senior', status: 'confirmed', rating: 2050, percentile: 95, strength: 77,
    skills: ['python', 'django', 'postgresql', 'redis', 'kafka', 'pytorch'],
    formats: ['remote', 'hybrid'], salary_min: 330000, salary_max: 390000,
    fsp: { linked: true, best_tier: 'gold', rank: '1', results: 6 },
    last_active_at: '2026-10-09T20:00:00Z',
  },
]

function toTalentShort(s: SeedTalent): TalentShort {
  return {
    public_id: s.public_id,
    display_name: s.display_name,
    city: s.city,
    work_formats: s.formats,
    salary_min: s.salary_min,
    salary_max: s.salary_max,
    salary_type: 'gross',
    league: {
      specialization: s.spec,
      grade: s.grade,
      status: s.status,
      rating: s.rating,
      percentile: s.percentile,
      strength: s.strength ?? null,
    },
    fsp: s.fsp,
    skills: s.skills,
    last_active_at: s.last_active_at,
  }
}

/** Deterministic pseudo-score so the pool ordering is stable between calls. */
function scoreOf(s: SeedTalent): number {
  const base = s.rating ?? 1200
  const bonus = s.fsp.linked ? 6 : 0
  return Math.min(98, Math.round((base / 24) + bonus + s.skills.length * 2))
}

/** gap G8 — components served as the legacy flat dict (maxes 35/25/15/15/10). */
function componentsOf(s: SeedTalent): Record<string, number> {
  const skill = Math.min(35, s.skills.length * 7)
  const grade = { intern: 8, junior: 15, middle: 21, senior: 25 }[s.grade]
  const strength = Math.min(15, Math.round((s.strength ?? 0) / 7))
  const fsp = s.fsp.linked ? (['gold'].includes(s.fsp.best_tier ?? '') ? 15 : 10) : 0
  const salary = s.salary_min <= 250000 ? 10 : 5
  return { skill, grade, strength, fsp, salary }
}

function reasonsOf(s: SeedTalent) {
  const r: { kind: 'plus' | 'minus' | 'info'; text: string; source?: string }[] = []
  if (s.fsp.linked && s.fsp.best_tier === 'gold') r.push({ kind: 'plus', text: 'Золото FSP', source: 'fsp' })
  if (s.skills.includes('kafka')) r.push({ kind: 'plus', text: 'Опыт с Kafka', source: 'test' })
  if (s.status !== 'confirmed') r.push({ kind: 'minus', text: 'Лига не подтверждена', source: 'declared' })
  if ((s.strength ?? 0) < 50) r.push({ kind: 'minus', text: 'Слабые verified achievements', source: 'microtask' })
  r.push({ kind: 'info', text: `Активен: ${new Date(s.last_active_at).toLocaleDateString('ru-RU')}` })
  return r
}

// --- stateful shortlist (gap G16) ---------------------------------------------

/** positionId → Set of shortlisted public_ids. Survives filter changes. */
const shortlists = new Map<string, Set<string>>()

function listFor(positionId: string): Set<string> {
  let set = shortlists.get(positionId)
  if (!set) {
    set = new Set()
    shortlists.set(positionId, set)
  }
  return set
}

// --- positions -----------------------------------------------------------------

const POSITION_FIXTURE = {
  id: 'pos-1',
  company: 'Yandex',
  title: 'Senior Backend Engineer',
  specialization: 'backend' as Spec,
  grades: ['middle', 'senior'] as Grade[],
  must_skills: ['python', 'postgresql'],
  nice_skills: ['redis', 'kafka'],
  work_formats: ['remote', 'hybrid'],
  location: 'Москва',
  salary_min: 250000,
  salary_max: 400000,
  salary_type: 'gross' as const,
  team_context: 'Платформенная команда, микросервисы.',
  description: 'Разработка высоконагруженных сервисов.',
  allow_adjacent: true,
  is_public: true,
  status: 'active' as const,
  created_at: '2026-09-20T10:00:00Z',
}

export const scoutingHandlers = [
  // GET /api/positions → array (FE2.md §FE-09)
  http.get('*/api/positions', () => json([POSITION_FIXTURE])),

  // GET /api/positions/{id}
  http.get('*/api/positions/:id', ({ params }) =>
    json({ ...POSITION_FIXTURE, id: String(params.id) }),
  ),

  // GET /api/positions/{id}/pool — NO facets (fallback test), dict components (G8)
  http.get('*/api/positions/:id/pool', ({ params }) => {
    const marked = listFor(String(params.id))
    const items: PoolItemView[] = SEED.map((s) => ({
      talent: toTalentShort(s),
      score: scoreOf(s),
      components: componentsOf(s),
      reasons: reasonsOf(s) as PoolItemView['reasons'],
      shortlisted: marked.has(s.public_id),
    })).sort((a, b) => b.score - a.score)

    // Deliberately omit `facets` and `filters_applied`: capability detection
    // must fall back to client-side filtering (gap G8).
    return json({ items, total: items.length, page: 1 })
  }),

  // PUT /api/positions/{id}/shortlist/{public_id} → 204
  http.put('*/api/positions/:id/shortlist/:publicId', ({ params }) => {
    listFor(String(params.id)).add(String(params.publicId))
    return new HttpResponse(null, { status: 204 })
  }),

  // DELETE /api/positions/{id}/shortlist/{public_id} → 204
  http.delete('*/api/positions/:id/shortlist/:publicId', ({ params }) => {
    listFor(String(params.id)).delete(String(params.publicId))
    return new HttpResponse(null, { status: 204 })
  }),

  // GET /api/talent/{public_id} — gap G9: contacts null (no grant yet)
  http.get('*/api/talent/:publicId', ({ params }) => {
    const s = SEED.find((x) => x.public_id === String(params.publicId))
    if (!s) {
      return HttpResponse.json(
        { type: 'about:blank', title: 'not_found', status: 404, code: 'not_found', detail: 'Talent not found.' },
        { status: 404, headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' } },
      )
    }
    return json({
      ...toTalentShort(s),
      about: s.about ?? null,
      experience_text: s.experience_text ?? null,
      contacts: null,
      // gap G9 sections absent → UI hides them
    })
  }),
]
