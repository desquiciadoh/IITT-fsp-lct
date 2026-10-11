import { http, HttpResponse } from 'msw'
import type { Grade, LeagueShelf, PoolEntry, Spec, TalentShort, WorkFormat } from '@/api/types'

/**
 * FE-10 · Scouting — stateful MSW mock.
 *
 * Serves the scouting routes in their contract shape (`X-Stub: true`) for
 * backend-less demos (G7/G8/G16 shipped on the BE; deep talent sections G9
 * still come later):
 *   GET /api/leagues?specialization=  → plain array of shelves;
 *   GET /api/positions/{id}/pool      → server-side filters, facets,
 *       pagination, components as a list, gaps + relaxations;
 *   PUT/DELETE /api/positions/{id}/shortlist/{public_id} → 204 (stateful);
 *   GET /api/positions/{id}/shortlist → tray list;
 *   GET /api/talent/{public_id}       → detail with contacts gated by an
 *       offer grant (null otherwise), topics section present in target shape.
 *
 * Registered BEFORE employerHandlers so its "…/api/leagues" wins over the
 * static fixture in gaps.ts and its pool routes win over
 * "…/api/positions/:id" there (MSW is first-match-wins).
 */

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, {
    status,
    headers: { 'X-Stub': 'true' },
  })

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail, errors: undefined },
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
    },
  )

// --- seed ---------------------------------------------------------------------

type SeedTalent = TalentShort & {
  league: NonNullable<TalentShort['league']>
  fsp: { linked: boolean; best_tier?: string; rank?: string; results?: number }
  skillsList: { id: string; name: string; source: string }[]
}

const talentSeed: SeedTalent[] = [
  {
    public_id: 't-001',
    display_name: 'Анна Соколова',
    city: 'Москва',
    work_formats: ['hybrid', 'remote'],
    salary_min: 260000,
    salary_max: 340000,
    salary_type: 'gross',
    last_active_at: '2026-10-08T10:00:00Z',
    league: { specialization: 'backend', grade: 'middle', status: 'confirmed', rating: 1842, percentile: 91, strength: 0.78 },
    fsp: { linked: true, best_tier: 'winner', rank: 'kms', results: 4 },
    skillsList: [
      { id: 's1', name: 'python', source: 'test' },
      { id: 's2', name: 'django', source: 'test' },
      { id: 's3', name: 'postgresql', source: 'declared' },
      { id: 's4', name: 'redis', source: 'declared' },
    ],
    skills: ['python', 'django', 'postgresql', 'redis'] as unknown as string[],
  },
  {
    public_id: 't-002',
    display_name: 'Борис Ли',
    city: 'Санкт-Петербург',
    work_formats: ['remote'],
    salary_min: 300000,
    salary_max: 380000,
    salary_type: 'gross',
    last_active_at: '2026-10-07T18:30:00Z',
    league: { specialization: 'backend', grade: 'senior', status: 'confirmed', rating: 2010, percentile: 96, strength: 0.85 },
    fsp: { linked: true, best_tier: 'prize_winner', rank: 'ms', results: 7 },
    skillsList: [
      { id: 's1', name: 'python', source: 'test' },
      { id: 's2', name: 'fastapi', source: 'test' },
      { id: 's3', name: 'kafka', source: 'fsp' },
      { id: 's4', name: 'postgresql', source: 'test' },
    ],
    skills: ['python', 'fastapi', 'kafka', 'postgresql'] as unknown as string[],
  },
  {
    public_id: 't-003',
    display_name: 'Вера Панина',
    city: 'Казань',
    work_formats: ['office', 'hybrid'],
    salary_min: 180000,
    salary_max: 240000,
    salary_type: 'net',
    last_active_at: '2026-10-09T08:10:00Z',
    league: { specialization: 'backend', grade: 'junior', status: 'unconfirmed', rating: 1420, percentile: 64 },
    fsp: { linked: false },
    skillsList: [
      { id: 's1', name: 'python', source: 'declared' },
      { id: 's2', name: 'django', source: 'declared' },
    ],
    skills: ['python', 'django'] as unknown as string[],
  },
  {
    public_id: 't-004',
    display_name: 'Глеб Устинов',
    city: 'Новосибирск',
    work_formats: ['remote'],
    salary_min: 220000,
    salary_max: 300000,
    salary_type: 'gross',
    last_active_at: '2026-10-05T12:00:00Z',
    league: { specialization: 'backend', grade: 'middle', status: 'confirmed', rating: 1705, percentile: 83, strength: 0.61 },
    fsp: { linked: true, best_tier: 'finalist', results: 2 },
    skillsList: [
      { id: 's1', name: 'python', source: 'test' },
      { id: 's2', name: 'redis', source: 'test' },
      { id: 's3', name: 'celery', source: 'declared' },
    ],
    skills: ['python', 'redis', 'celery'] as unknown as string[],
  },
  {
    public_id: 't-005',
    display_name: 'Дарья Ким',
    city: 'Москва',
    work_formats: ['hybrid'],
    salary_min: 320000,
    salary_max: 420000,
    salary_type: 'gross',
    last_active_at: '2026-10-09T20:45:00Z',
    league: { specialization: 'backend', grade: 'senior', status: 'unconfirmed', rating: 1930, percentile: 94, strength: 0.8 },
    fsp: { linked: true, best_tier: 'winner', rank: 'kms', results: 5 },
    skillsList: [
      { id: 's1', name: 'python', source: 'test' },
      { id: 's2', name: 'fastapi', source: 'test' },
      { id: 's3', name: 'postgresql', source: 'test' },
      { id: 's4', name: 'react', source: 'declared' },
    ],
    skills: ['python', 'fastapi', 'postgresql', 'react'] as unknown as string[],
  },
  {
    public_id: 't-006',
    display_name: 'Егор Романов',
    city: 'Екатеринбург',
    work_formats: ['remote', 'office'],
    salary_min: 150000,
    salary_max: 200000,
    salary_type: 'gross',
    last_active_at: '2026-10-01T09:00:00Z',
    league: { specialization: 'backend', grade: 'intern', status: 'unconfirmed', rating: 1180, percentile: 41 },
    fsp: { linked: false },
    skillsList: [{ id: 's1', name: 'python', source: 'declared' }],
    skills: ['python'] as unknown as string[],
  },
]

/** Candidate ids that granted contact access to any company (accepted offers). */
const grantedContacts = new Set<string>(['t-002'])

/**
 * FE-11 cross-link seam: the employer offer mock calls this when an offer is
 * accepted, so `GET /api/talent/{id}` starts returning contacts right away
 * ("accept → contacts appear on the board" acceptance scenario).
 */
export function grantContacts(publicId: string) {
  grantedContacts.add(publicId)
}

const shortlists = new Map<string, Set<string>>()

/**
 * Test helper (used by filters.test.ts): pre-seed the shortlist of a position
 * so acceptance scenarios ("tray survives 10 filter changes", "contacts only
 * after acceptance") can be exercised without driving the UI.
 */
export function seedShortlist(positionId: string, publicIds: string[]) {
  const key = String(positionId)
  if (!shortlists.has(key)) shortlists.set(key, new Set())
  for (const id of publicIds) shortlists.get(key)!.add(id)
}

const PAGE_SIZE = 20

// --- scoring (target contract: components as a list) -------------------------

const GRADE_POINTS: Record<string, number> = { intern: 8, junior: 15, middle: 20, senior: 25 }

function scoreOne(t: SeedTalent): { score: number; components: Record<string, number>; reasons: PoolEntry['reasons']; gaps: string[] } {
  const must = ['python', 'django', 'postgresql']
  const nice = ['redis', 'fastapi', 'kafka']
  const names = (t.skills ?? []).map(String)
  const hitMust = must.filter((s) => names.includes(s)).length
  const hitNice = nice.filter((s) => names.includes(s)).length
  const skill = Math.round(((hitMust * 2 + hitNice) / (must.length * 2 + nice.length)) * 35)
  const grade = GRADE_POINTS[t.league.grade ?? 'junior'] ?? 10
  const strength = Math.round((t.league.strength ?? 0.4) * 15)
  const fsp = t.fsp.linked ? (['winner', 'prize_winner'].includes(t.fsp.best_tier ?? '') ? 15 : 8) : 0
  const salary = t.salary_min != null && t.salary_min <= 300000 ? 10 : 4
  const score = skill + grade + strength + fsp + salary
  const reasons: PoolEntry['reasons'] = [
    { kind: 'plus', text: `${hitMust}/${must.length} обязательных скиллов`, source: 'test' },
  ]
  if (grade >= 20) reasons.push({ kind: 'plus', text: `грейд ${t.league.grade} подтверждён тестом`, source: 'test' })
  if (fsp === 15) reasons.push({ kind: 'plus', text: 'призёр соревнований ФСП', source: 'fsp' })
  const gaps: string[] = []
  for (const s of must) {
    if (!names.includes(s)) {
      gaps.push(`нет подтверждённого «${s}»`)
      reasons.push({ kind: 'minus', text: `не покрыт must-have «${s}»` })
    }
  }
  if (t.league.status !== 'confirmed') reasons.push({ kind: 'info', text: 'грейд не подтверждён' })
  return { score, components: { skill, grade, strength, fsp, salary }, reasons, gaps }
}

function shelfCounts(spec: Spec | string) {
  const shelves: LeagueShelf[] = []
  for (const grade of ['intern', 'junior', 'middle', 'senior'] as Grade[]) {
    const inGrade = talentSeed.filter((t) => t.league.specialization === spec && t.league.grade === grade)
    const salaries = inGrade.map((t) => (t.salary_min ?? 0 + (t.salary_max ?? 0)) / 2).filter((n) => n > 0)
    shelves.push({
      specialization: spec as Spec,
      grade,
      confirmed: inGrade.filter((t) => t.league.status === 'confirmed').length,
      unconfirmed: inGrade.filter((t) => t.league.status !== 'confirmed').length,
      median_expectation: salaries.length
        ? Math.round(salaries.sort((a, b) => a - b)[Math.floor(salaries.length / 2)])
        : null,
    })
  }
  return shelves
}

// --- handlers -----------------------------------------------------------------

export const scoutingHandlers = [
  // Test helper: clear per-run state.
  http.post('*/api/_mock/scouting/reset', () => {
    shortlists.clear()
    return stub({ detail: 'ok' })
  }),

  // Contract shape: plain array of shelves.
  http.get('*/api/leagues', ({ request }) => {
    const spec = new URL(request.url).searchParams.get('specialization') ?? 'backend'
    return stub(shelfCounts(spec))
  }),

  // Contract shape: pool with server-side filters, facets, pagination, list components.
  http.get('*/api/positions/:id/pool', ({ request, params }) => {
    const positionId = String(params.id)
    const sp = new URL(request.url).searchParams
    const listed = shortlists.get(positionId) ?? new Set<string>()

    const scored = talentSeed.map((t) => ({ talent: t, ...scoreOne(t) }))

    // Filters (comma CSV, same wire format as the real query params).
    const csv = (k: string) => (sp.get(k) ? sp.get(k)!.split(',').filter(Boolean) : [])
    const grades = csv('grades')
    const skills = csv('skills')
    const formats = csv('formats')
    const fsp = sp.get('fsp')
    const salaryMax = Number(sp.get('salary_max'))
    const confirmedOnly = sp.get('confirmed_only') === 'true'
    const preset = sp.get('preset')

    const filtered = scored.filter(({ talent: t }) => {
      if (grades.length && !grades.includes(t.league.grade ?? '')) return false
      if (formats.length && !(t.work_formats ?? []).some((f) => formats.includes(f))) return false
      if (Number.isFinite(salaryMax) && salaryMax > 0 && (t.salary_min ?? Infinity) > salaryMax) return false
      if (confirmedOnly && t.league.status !== 'confirmed') return false
      // AND across chips — matches the BE pool selector semantics.
      if (skills.length && !skills.every((s) => (t.skills ?? []).map(String).includes(s))) return false
      if (fsp === 'linked' && !t.fsp.linked) return false
      if (fsp === 'prize' && !(t.fsp.linked && ['winner', 'prize_winner'].includes(t.fsp.best_tier ?? ''))) return false
      if (preset === 'fsp_stars' && !(t.fsp.linked && ['winner', 'prize_winner'].includes(t.fsp.best_tier ?? ''))) return false
      if (preset === 'confirmed' && t.league.status !== 'confirmed') return false
      return true
    })
    filtered.sort((a, b) => b.score - a.score)

    const page = Math.max(1, Number(sp.get('page')) || 1)
    const total = filtered.length
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
    const items: PoolEntry[] = filtered
      .slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
      .map(({ talent: t, score, components, reasons, gaps }) => ({
        talent: { ...t, skills: t.skillsList.map((s) => s.name) } as TalentShort,
        score,
        // Components arrive as a weighted list (contract shape).
        components: Object.entries(components).map(([key, contribution]) => ({
          key: key as never,
          value: contribution,
          weight: 0,
          contribution,
        })),
        reasons,
        gaps,
        shortlisted: listed.has(t.public_id),
      }))

    return stub({
      items,
      total,
      page,
      pages,
      facets: {
        grades: filtered.reduce<Record<string, number>>((acc, { talent: t }) => {
          const g = t.league.grade ?? 'junior'
          acc[g] = (acc[g] ?? 0) + 1
          return acc
        }, {}),
        fsp: {
          linked: filtered.filter(({ talent: t }) => t.fsp.linked).length,
          prize: filtered.filter(({ talent: t }) => t.fsp.linked && ['winner', 'prize_winner'].includes(t.fsp.best_tier ?? '')).length,
        },
        confirmed_only: filtered.filter(({ talent: t }) => t.league.status === 'confirmed').length,
      },
      relaxations: ['Уберите must-have «kafka» → +2 кандидата'],
    })
  }),

  // FE-12 · plain talent search: same filters/facets/pagination as
  // the pool, minus scoring. Registered BEFORE */api/talent/:publicId (MSW is
  // first-match-wins, otherwise "search" would be swallowed as a public id).
  http.get('*/api/talent/search', ({ request }) => {
    const sp = new URL(request.url).searchParams
    const csv = (k: string) => (sp.get(k) ? sp.get(k)!.split(',').filter(Boolean) : [])
    const grades = csv('grades')
    const skills = csv('skills')
    const formats = csv('formats')
    const fsp = sp.get('fsp')
    const salaryMax = Number(sp.get('salary_max'))
    const confirmedOnly = sp.get('confirmed_only') === 'true'
    const preset = sp.get('preset')

    const filtered = talentSeed.filter((t) => {
      if (grades.length && !grades.includes(t.league.grade ?? '')) return false
      if (formats.length && !(t.work_formats ?? []).some((f) => formats.includes(f))) return false
      if (Number.isFinite(salaryMax) && salaryMax > 0 && (t.salary_min ?? Infinity) > salaryMax) return false
      if (confirmedOnly && t.league.status !== 'confirmed') return false
      if (preset === 'confirmed' && t.league.status !== 'confirmed') return false
      // AND across chips — same semantics as the pool handler and the BE
      // selector (apps/matching/selectors.py filter_candidate_profiles).
      if (skills.length && !skills.every((s) => (t.skills ?? []).map(String).includes(s))) return false
      if (fsp === 'linked' && !t.fsp.linked) return false
      const prize = t.fsp.linked && ['winner', 'prize_winner'].includes(t.fsp.best_tier ?? '')
      if (fsp === 'prize' && !prize) return false
      if (preset === 'fsp_stars' && !prize) return false
      return true
    })

    const page = Math.max(1, Number(sp.get('page')) || 1)
    const total = filtered.length
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
    const items: TalentShort[] = filtered
      .slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
      .map((t) => ({ ...t, skills: t.skillsList.map((s) => s.name) }))

    return stub({
      items,
      total,
      page,
      pages,
      facets: {
        grades: filtered.reduce<Record<string, number>>((acc, t) => {
          const g = t.league.grade ?? 'junior'
          acc[g] = (acc[g] ?? 0) + 1
          return acc
        }, {}),
        formats: filtered.reduce<Record<string, number>>((acc, t) => {
          for (const f of t.work_formats ?? []) acc[f] = (acc[f] ?? 0) + 1
          return acc
        }, {}),
        fsp: {
          linked: filtered.filter((t) => t.fsp.linked).length,
          prize: filtered.filter((t) => t.fsp.linked && ['winner', 'prize_winner'].includes(t.fsp.best_tier ?? '')).length,
        },
        confirmed_only: {
          true: filtered.filter((t) => t.league.status === 'confirmed').length,
        },
      },
    })
  }),

  // Shortlist list (live on the BE; the tray also syncs from pool flags).
  http.get('*/api/positions/:id/shortlist', ({ params }) => {
    const listed = shortlists.get(String(params.id)) ?? new Set<string>()
    const items = talentSeed
      .filter((t) => listed.has(t.public_id))
      .map((t) => ({ ...t, skills: t.skillsList.map((s) => s.name) }))
    return stub(items)
  }),

  http.put('*/api/positions/:id/shortlist/:publicId', ({ params }) => {
    const key = String(params.id)
    if (!shortlists.has(key)) shortlists.set(key, new Set())
    shortlists.get(key)!.add(String(params.publicId))
    return new HttpResponse(null, { status: 204, headers: { 'X-Stub': 'true' } })
  }),

  http.delete('*/api/positions/:id/shortlist/:publicId', ({ params }) => {
    shortlists.get(String(params.id))?.delete(String(params.publicId))
    return new HttpResponse(null, { status: 204, headers: { 'X-Stub': 'true' } })
  }),

  // Talent card for the drawer (G9). Contacts are null unless granted.
  http.get('*/api/talent/:publicId', ({ params }) => {
    const t = talentSeed.find((x) => x.public_id === params.publicId)
    if (!t) return problem(404, 'not_found', 'Кандидат не найден.')
    const granted = grantedContacts.has(t.public_id)
    return stub({
      public_id: t.public_id,
      display_name: t.display_name,
      city: t.city,
      work_formats: t.work_formats,
      salary_min: t.salary_min,
      salary_max: t.salary_max,
      salary_type: t.salary_type,
      last_active_at: t.last_active_at,
      league: t.league,
      fsp: t.fsp,
      skills: t.skillsList,
      about: `${t.display_name}: бэкенд-разработка, участие в соревнованиях ФСП.`,
      experience_text: 'Python/Django, микросервисы, PostgreSQL.',
      contacts: granted
        ? {
            full_name: t.display_name,
            email: `${t.public_id}@example.com`,
            phone: '+7 900 000-00-00',
            telegram: '@fsp_candidate',
          }
        : null,
      // G9 sections — present here so the UI can render them when the real BE omits them.
      topics: [
        { key: 'algorithms', label: 'Алгоритмы', correct: 8, total: 10 },
        { key: 'databases', label: 'Базы данных', correct: 6, total: 8 },
      ],
    })
  }),
]

export const _workFormatGuard: WorkFormat = 'remote'
