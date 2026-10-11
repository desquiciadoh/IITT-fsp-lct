import { http, HttpResponse } from 'msw'
import type { Company, JdParseResult, Position } from '@/api/types'

/**
 * FE-09 · Company & position wizard — stateful MSW mock.
 *
 * Endpoints: GET/PUT /api/companies/me, POST /api/companies (gap G17),
 * GET/POST /api/positions, GET/PUT /api/positions/{id},
 * POST /api/positions/parse (gap G6). Every response carries `X-Stub: true`.
 */

const stub = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, {
    status,
    headers: { 'X-Stub': 'true' },
  })

const problem = (status: number, code: string, detail: string, errors?: unknown) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail, errors },
    {
      status,
      headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' },
    },
  )

// --- in-memory state ---------------------------------------------------------

let company: Company | null = null

const positions: Position[] = []

const uid = () => crypto.randomUUID()

function resetStore() {
  company = null
  positions.length = 0
}

// --- JD parse (gap G6) -------------------------------------------------------

const KNOWN_SKILLS = new Set([
  'python', 'django', 'fastapi', 'postgresql', 'redis', 'kafka',
  'typescript', 'react', 'node.js', 'next.js', 'vue', 'angular',
  'sql', 'git', 'docker', 'kubernetes', 'celery', 'pytorch', 'pandas',
  'graphql', 'rest', 'linux', 'clickup', 'jira',
])

// Case-insensitive lookup: the taxonomy is lowercase, JD text may not be.
// Tokenizer note: `[a-z][a-z.+#-]{2,}` keeps trailing punctuation attached to
// the last word of a sentence ("redis." / "celery."), so every lookup must go
// through normSkill() which trims leading/trailing dots and separators.
// Interior dots are preserved on purpose: "node.js" / "next.js" are taxonomy entries.
const normSkill = (word: string) => word.toLowerCase().replace(/^[.+#-]+|[.+#-]+$/g, '')
const skillIn = (word: string) => KNOWN_SKILLS.has(normSkill(word))

/**
 * Remove a section marker from a line without corrupting inflected Russian
 * words: `line.replace(/обязател/i, ' ')` used to cut "Обязательны:" into
 * "ьны:", which then leaked as a fake unknown term. Instead, blank every
 * character the marker matched plus the following label tail up to the first
 * separator (`:` or whitespace), e.g. "Обязательны: python" → "  python".
 */
function stripMarker(line: string, marker: RegExp): string {
  return line.replace(new RegExp(marker.source + '[^\\s:]*[:\\s]?', 'i'), ' ')
}

const SPEC_HINTS: Array<[RegExp, NonNullable<JdParseResult['draft']['specialization']>]> = [
  [/front|react|typescript|vue|angular/i, 'frontend'],
  [/ml|data.?scien|pytorch|pandas|аналитик данных/i, 'ml_data'],
]

function parseJd(text: string): JdParseResult {
  const lower = text.toLowerCase()
  const words = lower.match(/[a-z][a-z.+#-]{2,}/g) ?? []

  const must_skills: string[] = []
  const nice_skills: string[] = []
  const unknown_terms: string[] = []
  // Russian words inflect ("Обязательны:", "Будет плюсом:") — match the stem
  // anywhere inside the line, not only at a word boundary. Stop the must-have
  // section at the nice-to-have marker; without a marker take the rest of the
  // text (the old lazy `(?:...|$)` alternation dropped the final skill).
  // `\s` (not `+`) between the words: "Будет плюсом" contains a real space.
  const NICE_MARKER = /nice\s+to\s+have|(?<!no )plus|будет\s+плюсом|желат/i
  const MUST_MARKER = /required|must\s*have|обязател/i
  let mustSection: string | undefined
  let niceSection: string | undefined
  for (const line of text.split('\n')) {
    if (NICE_MARKER.test(line)) {
      niceSection = (niceSection ?? '') + ' ' + stripMarker(line, NICE_MARKER)
    } else if (MUST_MARKER.test(line)) {
      mustSection = (mustSection ?? '') + ' ' + stripMarker(line, MUST_MARKER)
    } else if (niceSection !== undefined) {
      niceSection += ' ' + line
    } else if (mustSection !== undefined) {
      mustSection += ' ' + line
    }
  }
  const scan = (segment: string | undefined, target: string[], exclude?: string[]) => {
    if (!segment) return
    for (const w of segment.toLowerCase().match(/[a-z][a-z.+#-]{2,}/g) ?? []) {
      const skill = normSkill(w)
      if (skillIn(skill) && !target.includes(skill) && !exclude?.includes(skill)) target.push(skill)
    }
  }
  scan(mustSection, must_skills)
  // Skills already claimed by the must-have section must not leak into nice-to-have.
  scan(niceSection, nice_skills, must_skills)
  // Terms that look like tech but are not in the taxonomy → highlight them.
  for (const w of words) {
    const isTechish = !skillIn(w) && /^(solid|figma|swagger|postman|nginx|rabbitmq|mongodb|mysql|sqlite|terraform|ansible|grafana|prometheus|elastic|elasticsearch|clickhouse|superset|airflow|spark|hadoop|hive|scala|go|rust|c\+\+|java|kotlin|swift|flutter|redux|webpack|vite|tailwind|sass)$/.test(w)
    if (isTechish && !unknown_terms.includes(w)) unknown_terms.push(w)
  }

  let specialization: NonNullable<JdParseResult['draft']['specialization']> = 'backend'
  for (const [re, spec] of SPEC_HINTS) {
    if (re.test(lower)) {
      specialization = spec
      break
    }
  }

  const grades: NonNullable<JdParseResult['draft']['grades']> = []
  if (/senior|старший|\bсеньер/i.test(lower)) grades.push('senior')
  if (/middle|\bmid\b|средн/i.test(lower)) grades.push('middle')
  if (/junior|младш|\bджун/i.test(lower)) grades.push('junior')
  if (/intern|стажёр/i.test(lower)) grades.push('intern')
  if (grades.length === 0) grades.push('middle')

  const work_formats: NonNullable<JdParseResult['draft']['work_formats']> = []
  if (/remote|удален|удалён/i.test(lower)) work_formats.push('remote')
  if (/hybrid|гибрид/i.test(lower)) work_formats.push('hybrid')
  if (/office|офис/i.test(lower)) work_formats.push('office')

  const salaryMatch =
    /(?:от|from)\s*(\d{2,3})[\s.,]*(\d{3})|(?:зарплат\w*|salary)[^\d]{0,30}(\d{2,3})[\s.,]?(\d{3})/i.exec(
      lower,
    )
  let salary_min: number | undefined
  let salary_max: number | undefined
  if (salaryMatch) {
    const a = Number((salaryMatch[1] ?? salaryMatch[3]) + (salaryMatch[2] ?? salaryMatch[4]))
    if (Number.isFinite(a) && a >= 20000) {
      salary_min = a
      salary_max = Math.round(a * 1.4)
    }
  }

  const titleMatch = /(?:vacancy|позиция|разработчик|инженер)[^\n]{0,60}/i.exec(text)

  const blueprint = [
    { topic: 'architecture', weight: 0.3 },
    { topic: 'performance', weight: 0.25 },
    { topic: 'testing', weight: 0.2 },
    { topic: 'product_thinking', weight: 0.15 },
    { topic: 'mentoring', weight: 0.1 },
  ]

  return {
    draft: {
      title: titleMatch ? titleMatch[0].trim().slice(0, 80) : undefined,
      specialization,
      grades,
      must_skills,
      nice_skills,
      work_formats,
      location: /москв/i.test(lower) ? 'Москва' : /санкт-петербург|спб/i.test(lower) ? 'Санкт-Петербург' : undefined,
      salary_min,
      salary_max,
    },
    unknown_terms,
    blueprint,
    source: 'mock_heuristic',
  }
}

// --- handlers ----------------------------------------------------------------

export const employerHandlers = [
  // FE-09 test helper: clear the store between scenarios.
  http.post('*/api/_mock/employer/reset', () => {
    resetStore()
    return stub({ detail: 'ok' })
  }),

  // gap G17 — after BE fix B1, employers without a company get 403 here.
  http.get('*/api/companies/me', () => {
    if (!company) {
      return problem(403, 'company_required', 'Создайте профиль компании, чтобы публиковать вакансии.')
    }
    return stub(company)
  }),

  http.put('*/api/companies/me', async ({ request }) => {
    if (!company) {
      return problem(403, 'company_required', 'Создайте профиль компании, чтобы публиковать вакансии.')
    }
    const body = (await request.json().catch(() => ({}))) as Partial<Company>
    // trust_level / id / created_at are read-only: strip them from the payload.
    const { trust_level: _tl, id: _id, created_at: _ca, ...writable } = body
    company = { ...company, ...writable }
    return stub(company)
  }),

  http.get('*/api/companies', ({ request }) => {
    const url = new URL(request.url)
    const search = (url.searchParams.get('search') ?? '').toLowerCase().trim()
    const all = [
      { id: '00000000-0000-4000-8000-000000000001', name: 'Yandex Tech' },
      { id: '00000000-0000-4000-8000-000000000002', name: 'Ozon' },
      { id: '00000000-0000-4000-8000-000000000003', name: 'Avito' },
      ...(company ? [{ id: company.id, name: company.name }] : []),
    ]
    const filtered = search ? all.filter((c) => c.name.toLowerCase().includes(search)) : all
    return stub({
      items: filtered,
      total: filtered.length,
      page: 1,
      pages: 1,
    })
  }),

  http.post('*/api/companies', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Partial<Company>
    if (!body.name || !body.inn) {
      return problem(400, 'validation_error', 'Поля «Название» и «ИНН» обязательны.', {
        name: ['Обязательное поле.'],
        inn: ['Обязательное поле.'],
      })
    }
    company = {
      id: uid(),
      name: body.name,
      inn: body.inn,
      website: body.website ?? '',
      email_domain: body.email_domain ?? '',
      business_domain: body.business_domain ?? '',
      description: body.description ?? '',
      contact_email: body.contact_email ?? '',
      trust_level: 'none' as Company['trust_level'],
      created_at: new Date().toISOString(),
    }
    return stub(company, 201)
  }),

  http.get('*/api/positions', () => stub(positions)),

  http.post('*/api/positions', async ({ request }) => {
    if (!company) {
      return problem(403, 'company_required', 'Сначала создайте профиль компании.')
    }
    const body = (await request.json().catch(() => ({}))) as Partial<Position>
    const errors: Record<string, string[]> = {}
    if (!body.title) errors.title = ['Обязательное поле.']
    if (!(typeof body.salary_min === 'number' && body.salary_min > 0)) {
      errors.salary_invalid = ['salary_min должен быть больше 0.']
    }
    if (
      typeof body.salary_max === 'number' &&
      typeof body.salary_min === 'number' &&
      body.salary_max < body.salary_min
    ) {
      errors.salary_invalid = ['salary_max должен быть не меньше salary_min.']
    }
    if (!body.salary_type) errors.salary_invalid = ['Укажите gross или net.']
    if (Object.keys(errors).length > 0) {
      // BE today labels every salary error `salary_invalid` (BE.md B15).
      return problem(400, 'validation_error', 'Ошибка валидации.', errors)
    }
    const position: Position = {
      id: uid(),
      company: company.id,
      title: body.title,
      specialization: body.specialization,
      grades: body.grades ?? [],
      must_skills: body.must_skills ?? [],
      nice_skills: body.nice_skills ?? [],
      work_formats: body.work_formats ?? [],
      location: body.location ?? '',
      salary_min: body.salary_min as number,
      salary_max: body.salary_max as number,
      salary_type: body.salary_type,
      team_context: body.team_context ?? '',
      description: body.description ?? '',
      allow_adjacent: body.allow_adjacent ?? false,
      is_public: body.is_public ?? true,
      status: 'open',
      created_at: new Date().toISOString(),
    } as Position
    positions.unshift(position)
    return stub(position, 201)
  }),

  http.get('*/api/positions/parse', () =>
    problem(405, 'method_not_allowed', 'Use POST.'),
  ),

  http.post('*/api/positions/parse', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { text?: string }
    if (!body.text || body.text.trim().length < 20) {
      return problem(400, 'text_too_short', 'Текст вакансии слишком короткий для разбора.')
    }
    return stub(parseJd(body.text))
  }),

  http.get('*/api/positions/:id', ({ params }) => {
    const found = positions.find((p) => p.id === params.id)
    if (!found) return problem(404, 'not_found', 'Вакансия не найдена.')
    return stub(found)
  }),

  http.put('*/api/positions/:id', async ({ request, params }) => {
    const idx = positions.findIndex((p) => p.id === params.id)
    if (idx === -1) return problem(404, 'not_found', 'Вакансия не найдена.')
    const body = (await request.json().catch(() => ({}))) as Partial<Position>
    if (typeof body.salary_min === 'number' && body.salary_min <= 0) {
      return problem(400, 'validation_error', 'Ошибка валидации.', {
        salary_invalid: ['salary_min должен быть больше 0.'],
      })
    }
    positions[idx] = { ...positions[idx], ...body, id: positions[idx].id, created_at: positions[idx].created_at }
    return stub(positions[idx])
  }),
]
