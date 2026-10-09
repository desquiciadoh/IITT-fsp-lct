import { http, HttpResponse } from 'msw'
import type { PoolCandidate, PositionPool } from '@/api/types'
import { PRESETS, weightedScore } from '@/features/pool/rank'

/**
 * G20 / FE-17 pool mock for the scouting page (FE2 FE-10): candidates with
 * score components, relaxations, acceptance likelihood and Need Health.
 */

const json = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail },
    { status, headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' } },
  )

type Seed = Omit<PoolCandidate, 'score'> & { score?: number }

const seeds: Seed[] = [
  {
    public_id: 'c-47D2BD',
    display_name: 'Анна Иванова',
    city: 'Москва',
    skills: ['Python', 'PostgreSQL', 'Redis', 'Docker'],
    components: { skill: 68, grade: 22, strength: 14, fsp: 12, salary: 9 },
    accept_likelihood: 'high',
    declared_salary_min: 260000,
  },
  {
    public_id: 'c-8F3A1C',
    display_name: 'Игорь Смирнов',
    city: 'Санкт-Петербург',
    skills: ['Go', 'Kubernetes', 'gRPC'],
    components: { skill: 55, grade: 20, strength: 16, fsp: 9, salary: 7 },
    accept_likelihood: 'medium',
    declared_salary_min: 220000,
  },
  {
    public_id: 'c-2B9E44',
    display_name: 'Мария Козлова',
    city: 'Москва',
    skills: ['Java', 'Spring', 'Kubernetes'],
    components: { skill: 40, grade: 18, strength: 10, fsp: 8, salary: 12 },
    accept_likelihood: 'low',
    declared_salary_min: 310000,
  },
  {
    public_id: 'c-6D1F90',
    display_name: 'Дмитрий Волков',
    skills: ['Python', 'FastAPI', 'Kafka'],
    components: { skill: 30, grade: 15, strength: 9, fsp: 6, salary: 16 },
    accept_likelihood: 'high',
    declared_salary_min: 180000,
  },
  {
    public_id: 'c-9C2112',
    display_name: 'Елена Романова',
    city: 'Казань',
    skills: ['SQL', 'PostgreSQL', 'ClickHouse'],
    components: { skill: 25, grade: 14, strength: 8, fsp: 5, salary: 20 },
    accept_likelihood: 'medium',
    declared_salary_min: 160000,
  },
  {
    public_id: 'c-4E5B77',
    display_name: 'Павел Орлов',
    skills: ['Node.js', 'TypeScript', 'AWS'],
    components: { skill: 18, grade: 10, strength: 6, fsp: 4, salary: 28 },
    accept_likelihood: 'low',
    declared_salary_min: 250000,
  },
]

const candidates: PoolCandidate[] = seeds.map(({ score, ...seed }) => ({
  ...seed,
  score: (score ?? weightedScore(seed.components, PRESETS.balanced)) as number,
}))

const POOL: PositionPool = {
  candidates,
  weights: PRESETS.balanced,
  relaxations: [
    { label: 'знание Kubernetes', added_candidates: 23 },
    { label: 'опыт в highload', added_candidates: 9 },
    { label: 'сеньор по грейду', added_candidates: 5 },
  ],
  health: {
    active: 4,
    declined_last_30d: 11,
    acceptance_rate: 0.64,
    by_reason: [
      { reason: 'salary_below_expected', count: 6, share: 0.55 },
      { reason: 'no_offer_detail', count: 2, share: 0.18 },
      { reason: 'timing', count: 2, share: 0.18 },
      { reason: 'other', count: 1, share: 0.09 },
    ],
  },
}

export const poolHandlers = [
  http.get('*/api/positions/:id/pool', ({ params }) => {
    if (String(params.id) !== 'pos-1') {
      return problem(404, 'not_found', 'Pool not found for this position.')
    }
    return json(POOL)
  }),
]