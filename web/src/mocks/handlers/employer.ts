/**
 * FE-09 · Stateful mock for companies / positions / JD parsing.
 *
 * Registered in browser.ts (`all` mode) BEFORE coreHandlers so the wildcard
 * routes cannot be swallowed; also exported as `employerGapHandlers` for
 * `missing` mode (G6/G17 are real gaps, taxonomy stays in gapHandlers).
 *
 * Simulated backend behaviors (kept faithful on purpose):
 *  - BE.md B1 / gap G17: GET /api/companies/me → 403 company_required until
 *    the employer PUTs a company (PUT acts as upsert — that is what the
 *    wizard relies on);
 *  - gap G6: POST /api/positions/parse returns {draft, unknown_terms,
 *    blueprint, source} from a deterministic keyword parser;
 *  - BE.md B15: salary validation mirrors the buggy backend — every error is
 *    labelled `salary_invalid`; the client must never send such payloads
 *    (zod validates first), but the mock still guards against them.
 */
import { http, HttpResponse } from 'msw'
import type { Company, JdParseResult, Position, PositionInput } from '@/api/types'

const stub = (init: ResponseInit = {}) =>
  new Headers({ 'X-Stub': 'true', ...(init.headers ?? {}) })

const json = (data: unknown, init: ResponseInit = {}) =>
  HttpResponse.json(data as Record<string, unknown>, { ...init, headers: stub(init) })

const problem = (status: number, code: string, detail: string, errors?: unknown) => {
  // Normalize [{field, msg}] into DRF-style {field: [msg]} so both the wire
  // contract and client-side field mapping stay predictable.
  const normalizedErrors = Array.isArray(errors)
    ? Object.fromEntries(
        errors.map((e) => [String((e as { field?: unknown }).field), [(e as { msg?: unknown }).msg]])
      )
    : errors
  return HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail, errors: normalizedErrors },
    {
      status,
      headers: stub({ headers: { 'Content-Type': 'application/problem+json' } }),
    },
  )
}

// --- stores -----------------------------------------------------------------

let company: Company | null = null
let positionSeq = 1
const positions = new Map<string, Position>()

const seedPosition: Position = {
  id: 'pos-seed-1',
  company: '/api/companies/comp-seed',
  title: 'Python-разработчик (демо-вакансия)',
  specialization: 'backend',
  grades: ['middle', 'senior'],
  must_skills: ['python', 'django', 'postgresql'],
  nice_skills: ['fastapi', 'redis'],
  work_formats: ['hybrid', 'remote'],
  location: 'Москва',
  salary_min: 220000,
  salary_max: 320000,
  salary_type: 'gross',
  team_context: 'Команда из 5 человек, продукт — аналитика.',
  description: 'Демо-позиция для проверки списка вакансий на дашборде.',
  allow_adjacent: false,
  is_public: true,
  status: 'open',
  created_at: '2026-10-01T09:00:00Z',
}
positions.set(seedPosition.id, structuredClone(seedPosition))

export function resetEmployerMock(): void {
  company = null
  positionSeq = 1
  positions.clear()
  positions.set(seedPosition.id, structuredClone(seedPosition))
}

// --- taxonomy used by the JD parser ------------------------------------------
// gap G3 — same vocabulary as the /api/taxonomy fixture in gaps.ts.

const KNOWN_SKILLS = [
  'python', 'django', 'fastapi', 'postgresql', 'redis', 'kafka',
  'typescript', 'react', 'node.js', 'pytorch', 'pandas',
]

const SKILL_SYNONYMS: Record<string, string> = {
  py: 'python',
  'postgres': 'postgresql',
  'reactjs': 'react',
  'react.js': 'react',
  'ts': 'typescript',
  'node': 'node.js',
}

const SPEC_KEYWORDS: [string, RegExp][] = [
  ['backend', /\b(backend|бэкенд|серверн|api)\b/i],
  ['frontend', /\b(frontend|фронтенд|ui|react|vue)\b/i],
  ['ml_data', /\b(ml|machine learning|data science|mlops|pandas|pytorch)\b/i],
]

const GRADE_KEYWORDS: [string, RegExp][] = [
  ['intern', /\b(intern|стажёр|стажер)\b/i],
  ['junior', /\b(junior|джуниор)\b/i],
  ['middle', /\b(middle|мидл|mid)\b/i],
  ['senior', /\b(senior|сеньор|lead|тимлид)\b/i],
]

const BLUEPRINT_TOPICS: [RegExp, string][] = [
  [/algorithm|алгоритм|структур данных|leetcode/i, 'algorithms'],
  [/sql|postgresql|база|database|индекс/i, 'databases'],
  [/django|flask|fastapi|web framework|rest|api\b/i, 'web_frameworks'],
  [/test|pytest|tdd|покрыт/i, 'testing'],
  [/docker|kubernetes|ci\/cd|devops|деплой/i, 'deployment'],
  [/system design|архитектур|масштаб/i, 'system_design'],
  [/async|concurren|многопоточ|celery|kafka/i, 'concurrency'],
  [/ml|machine learning|model|pytorch|pandas/i, 'machine_learning'],
]

function parseJD(text: string): JdParseResult {
  const lower = text.toLowerCase()

  // Skills: known tokens + synonyms; everything capitalized-looking that is
  // not in the taxonomy becomes an unknown term (chips highlighted in UI).
  const foundSkills = new Set<string>()
  const unknownTerms = new Set<string>()
  // Rank hits by position in the text so `must_skills` keeps a stable,
  // JD-ordered slice instead of the KNOWN_SKILLS declaration order.
  // Deduplicate by skill name keeping the earliest occurrence (Map).
  const hitBySkill = new Map<string, number>()
  const addHit = (skill: string, at: number) => {
    const prev = hitBySkill.get(skill)
    if (prev === undefined || at < prev) hitBySkill.set(skill, at)
  }
  for (const skill of KNOWN_SKILLS) {
    const m = lower.match(new RegExp(`\\b${skill.replace('.', '\\.')}\\b`, 'i'))
    if (m && m.index !== undefined) addHit(skill, m.index)
  }
  for (const [syn, canonical] of Object.entries(SKILL_SYNONYMS)) {
    const m = lower.match(new RegExp(`\\b${syn}\\b`, 'i'))
    const at = m?.index
    if (
      at !== undefined &&
      // A synonym only counts when it is not just a substring of an already
      // matched canonical skill (e.g. "postgres" inside "postgresql").
      !hitBySkill.has(canonical) &&
      ![...hitBySkill.entries()].some(
        ([skill, hitAt]) => skill === canonical || (hitAt <= at && at < hitAt + skill.length),
      )
    ) {
      addHit(canonical, at)
    }
  }
  const skillHits = [...hitBySkill.entries()]
    .map(([skill, at]) => ({ skill, at }))
    .sort((a, b) => a.at - b.at)
  for (const { skill } of skillHits) foundSkills.add(skill)
  // Candidate unknown terms: latin words with tech-ish shape (C#/.NET-style,
  // camelCase, dots/hashes) or quoted tokens, excluding stopwords.
  const STOP = new Set(['the', 'and', 'or', 'for', 'with', 'from', 'this', 'that', 'your', 'our', 'we', 'you', 'are', 'will', 'have', 'has', 'not', 'but'])
  for (const match of text.matchAll(/\b([A-Za-z][A-Za-z0-9+#.]{1,20})\b/g)) {
    const token = match[1]
    const lc = token.toLowerCase()
    if (STOP.has(lc)) continue
    if (KNOWN_SKILLS.includes(lc) || SKILL_SYNONYMS[lc]) continue
    const techy = /[A-Z].*[a-z]|[#.]|[A-Z]{2,}/.test(token) && !/^(http|https|www)$/i.test(token)
    if (techy) unknownTerms.add(token)
  }

  const skills = [...foundSkills]
  // Canonical taxonomy hits rank above synonym-normalized ones so the first
  // slice of `must_skills` is stable regardless of incidental word order.
  const canonicalSet = new Set(KNOWN_SKILLS)
  const ranked = [
    ...skills.filter((s) => canonicalSet.has(s)),
    ...skills.filter((s) => !canonicalSet.has(s)),
  ]
  const mustCount = Math.max(3, skills.filter((s) => canonicalSet.has(s)).length)
  const must = ranked.slice(0, Math.min(mustCount, ranked.length))
  const nice = ranked.slice(must.length)

  let specialization = 'backend'
  for (const [spec, re] of SPEC_KEYWORDS) {
    if (re.test(lower)) {
      specialization = spec
      break
    }
  }

  const grades: string[] = []
  for (const [grade, re] of GRADE_KEYWORDS) {
    if (re.test(lower)) grades.push(grade)
  }

  const salaryMatch = text.match(/(\d{2,3}[\s_-]?\d{3})(?:\s*[-—–]\s*(\d{2,3}[\s_-]?\d{3}))?/)
  const salaryMin = salaryMatch ? Number(salaryMatch[1].replace(/[\s_-]/g, '')) : undefined
  const salaryMax = salaryMatch?.[2] ? Number(salaryMatch[2].replace(/[\s_-]/g, '')) : undefined

  const topics = BLUEPRINT_TOPICS.filter(([re]) => re.test(text)).map(([, topic]) => topic)
  const weights = topics.map((topic, i) => ({
    topic,
    weight: Math.round(((topics.length - i) / (topics.length || 1)) * 100) / 100,
  }))

  const draft: Partial<PositionInput> = {
    title: text.split(/\r?\n/).find((l) => l.trim())?.trim().slice(0, 120) ?? '',
    specialization: specialization as PositionInput['specialization'],
    grades: grades.length ? (grades as PositionInput['grades']) : ['middle'],
    must_skills: must,
    nice_skills: nice,
    description: text.slice(0, 2000),
  }
  if (salaryMin !== undefined) draft.salary_min = salaryMin
  if (salaryMax !== undefined && salaryMin !== undefined && salaryMax >= salaryMin) {
    draft.salary_max = salaryMax
  } else if (salaryMin !== undefined) {
    draft.salary_max = Math.round(salaryMin * 1.3)
  }

  return {
    draft,
    unknown_terms: [...unknownTerms],
    blueprint: weights,
    source: 'mock',
  }
}

function validateSalary(body: Partial<PositionInput>): string | null {
  // Mirrors BE.md B15 semantics: single generic `salary_invalid` code.
  const min = body.salary_min
  const max = body.salary_max
  if (typeof min !== 'number' || min <= 0) return 'salary_invalid'
  if (typeof max === 'number' && max < min) return 'salary_invalid'
  if (!body.salary_type) return 'salary_invalid'
  return null
}

// --- handlers ----------------------------------------------------------------

export const employerHandlers = [
  // B1/G17: no auto-created company; 403 company_required until PUT creates it.
  http.get('*/api/companies/me', () => {
    if (!company) {
      return problem(403, 'company_required', 'Company profile is required for this action.')
    }
    return json(company)
  }),

  // Gap G17: PUT doubles as create (upsert) until a dedicated endpoint ships.
  http.put('*/api/companies/me', async ({ request }) => {
    const raw = (await request.json().catch(() => null)) as Record<string, unknown> | null
    const body: Record<string, unknown> = raw ?? {}
    const errors: { field: string; msg: string }[] = []
    if (typeof body.name !== 'string' || !body.name.trim()) {
      errors.push({ field: 'name', msg: 'This field is required.' })
    }
    const inn = typeof body.inn === 'string' ? body.inn : ''
    if (inn && !/^\d{10}(\d{2})?$/.test(inn)) {
      errors.push({ field: 'inn', msg: 'Enter a valid Russian INN.' })
    }
    if (errors.length) {
      return problem(422, 'validation_failed', 'Company fields are invalid.', errors)
    }
    company = {
      id: company?.id ?? 'comp-1',
      name: String(body.name),
      inn: body.inn as string | undefined,
      website: body.website as Company['website'],
      email_domain: body.email_domain as string | undefined,
      business_domain: body.business_domain as string | undefined,
      description: body.description as string | undefined,
      contact_email: body.contact_email as Company['contact_email'],
      trust_level: company?.trust_level ?? 'none',
      created_at: company?.created_at ?? new Date().toISOString(),
    }
    return json(company)
  }),

  // G6: JD parse — deterministic keyword parser, always stubbed.
  http.post('*/api/positions/parse', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { text?: string }
    if (!body.text || body.text.trim().length < 20) {
      return problem(422, 'validation_failed', 'JD text is too short to parse.', [
        { field: 'text', msg: 'Provide at least 20 characters.' },
      ])
    }
    return json(parseJD(body.text))
  }),

  http.get('*/api/positions', () => json([...positions.values()])),

  http.post('*/api/positions', async ({ request }) => {
    if (!company) {
      // B1: positions require a company.
      return problem(403, 'company_required', 'Create the company profile first.')
    }
    const body = (await request.json().catch(() => null)) as Partial<PositionInput> | null
    if (!body) return problem(400, 'api_error', 'Malformed request body.')
    const salaryError = validateSalary(body)
    if (salaryError) {
      // B15: backend labels every salary problem with one code and dict errors.
      return problem(422, salaryError, 'Salary fields are invalid.', {
        salary_min: ['Ensure 1 - 2147483647.'],
        salary_max: ['Ensure this value is greater than or equal to 1.'],
      })
    }
    const position: Position = {
      id: `pos-${positionSeq++}`,
      company: `/api/companies/${company.id}`,
      title: body.title ?? '',
      specialization: body.specialization ?? 'backend',
      grades: body.grades ?? [],
      must_skills: body.must_skills ?? [],
      nice_skills: body.nice_skills ?? [],
      work_formats: body.work_formats ?? [],
      location: body.location ?? '',
      salary_min: body.salary_min ?? 0,
      salary_max: body.salary_max ?? 0,
      salary_type: body.salary_type ?? 'gross',
      team_context: body.team_context ?? '',
      description: body.description ?? '',
      allow_adjacent: body.allow_adjacent ?? false,
      is_public: body.is_public ?? true,
      status: body.status ?? 'open',
      created_at: new Date().toISOString(),
    }
    positions.set(position.id, position)
    return json(position, { status: 201 })
  }),

  http.get('*/api/positions/:id', ({ params }) => {
    const position = positions.get(String(params.id))
    if (!position) return problem(404, 'not_found', 'Position not found.')
    return json(position)
  }),

  http.put('*/api/positions/:id', async ({ params, request }) => {
    const existing = positions.get(String(params.id))
    if (!existing) return problem(404, 'not_found', 'Position not found.')
    const body = (await request.json().catch(() => null)) as Partial<PositionInput> | null
    if (!body) return problem(400, 'api_error', 'Malformed request body.')
    const salaryError = validateSalary({ ...existing, ...body })
    if (salaryError) {
      return problem(422, salaryError, 'Salary fields are invalid.', {
        salary_min: ['Ensure 1 - 2147483647.'],
      })
    }
    const next: Position = { ...existing, ...body, id: existing.id, created_at: existing.created_at }
    positions.set(next.id, next)
    return json(next)
  }),
]

/**
 * Subset safe for `missing` mode: only endpoints the backend does not serve
 * correctly today (G6 parse, G17 company upsert). Positions CRUD and the
 * taxonomy fixture stay delegated to the real backend / gapHandlers.
 */
export const employerGapHandlers = employerHandlers.filter((handler) => {
  const info = (handler as { info?: { path?: string } }).info
  const path = info?.path ?? ''
  return path.includes('companies') || path.includes('parse')
})
