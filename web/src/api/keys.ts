/** Every TanStack Query key in one place (FE1.md §1). */

export const keys = {
  me: ['me'] as const,
  taxonomy: ['taxonomy'] as const,
  profile: ['profile'] as const,
  consents: ['consents'] as const,
  eligibility: (spec: string) => ['eligibility', spec] as const,
  assessments: ['assessments'] as const,
  assessment: (id: string) => ['assessment', id] as const,
  session: (id: string) => ['session', id] as const,
  result: (id: string) => ['result', id] as const,
  offers: (status?: string) => ['offers', status ?? 'all'] as const,
  offer: (id: string) => ['offer', id] as const,
  company: ['company'] as const,
  positions: ['positions'] as const,
  position: (id: string) => ['position', id] as const,
  pool: (positionId: string) => ['pool', positionId] as const,
  /** FE-10 — per-filter pool query; base prefix ['pool', id] for invalidation. */
  poolQuery: (positionId: string, query: string) => ['pool', positionId, 'query', query] as const,
  shortlist: (positionId: string) => ['pool', positionId, 'shortlist'] as const,
  leagues: (spec?: string) => ['leagues', spec ?? 'all'] as const,
  talentSearch: ['talent', 'search'] as const,
  talent: (publicId: string) => ['talent', publicId] as const,
  companies: (query?: string) => ['companies', query ?? ''] as const,
  labReport: ['lab', 'report'] as const,
  labTwins: (query: string) => ['lab', 'twins', query] as const,
  vacancies: (query: string) => ['vacancies', query] as const,
  vacancy: (id: string) => ['vacancy', id] as const,
  myApplications: ['applications', 'me'] as const,
  positionApplications: (positionId: string) =>
    ['applications', 'position', positionId] as const,
  /** BE-18 · micro-tasks */
  microTasks: ['micro-tasks'] as const,
  microTask: (id: string) => ['micro-tasks', id] as const,
  microTaskSubmissions: (id: string) => ['micro-tasks', id, 'submissions'] as const,
  myMicroTasks: ['micro-tasks', 'me'] as const,
  /** BE-20 · Need Health for a position (FE-17). */
  positionHealth: (id: string) => ['positions', id, 'health'] as const,
}
