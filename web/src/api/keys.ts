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
  offersBoard: (view: 'candidate' | 'employer', status?: string) =>
    ['offers', view, status ?? 'all'] as const,
  offer: (id: string) => ['offer', id] as const,
  company: ['company'] as const,
  positions: ['positions'] as const,
  position: (id: string) => ['position', id] as const,
  /** FE-09 · one-shot JD parse result — no cache key needed; kept for clarity. */
  positionDraft: ['position-draft'] as const,
  pool: (positionId: string) => ['pool', positionId] as const,
  leagues: (spec?: string) => ['leagues', spec ?? 'all'] as const,
  talentSearch: ['talent', 'search'] as const,
  talent: (publicId: string) => ['talent', publicId] as const,
  labReport: ['lab', 'report'] as const,
}
