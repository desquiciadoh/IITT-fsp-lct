/**
 * API DTOs.
 *
 * Types that exist in the generated schema are aliased or derived from
 * `@/api/generated/models` (orval output) so they cannot drift from the
 * backend. Hand-written types are limited to shapes drf-spectacular leaves
 * open (nested serializers flattened to `string`/`unknown`, loose enums
 * narrowed here) and to view-normalizations of generated payloads. Former
 * gap comments (G3/G5/G6/G7/G8/G16/G17) were removed once the backend
 * shipped those fields — only genuinely open gaps stay tagged (e.g. G9).
 */
import type {
  AnswerResponse as GeneratedAnswerResponse,
  AssessmentEvidence as GeneratedAssessmentEvidence,
  AssessmentFallback as GeneratedAssessmentFallback,
  AssessmentModeEnum,
  AssessmentResult as GeneratedAssessmentResult,
  AssessmentSession as GeneratedAssessmentSession,
  AssessmentStatusEnum,
  AssessmentTopic as GeneratedAssessmentTopic,
  CandidateFSP as GeneratedCandidateFSP,
  CandidateLeague as GeneratedCandidateLeague,
  CandidateProfile as GeneratedCandidateProfile,
  CandidateSkill as GeneratedCandidateSkill,
  Company as GeneratedCompany,
  ConsentsResponse,
  ContactChannelEnum,
  DecisionEnum,
  DeclineReasonEnum,
  EligibilityResponse,
  FSPLinkResponse,
  GradeEnum,
  ItemView as GeneratedItemView,
  JdDraft as GeneratedJdDraft,
  JdParseBlueprintItem as GeneratedJdBlueprintItem,
  JdParseResult as GeneratedJdParseResult,
  KindEnum,
  LeagueShelf as GeneratedLeagueShelf,
  MeResponse,
  Offer as GeneratedOffer,
  OfferStatusEnum,
  PoolComponent as GeneratedPoolComponent,
  PoolItem as GeneratedPoolItem,
  Position as GeneratedPosition,
  PositionPoolResponse as GeneratedPositionPoolResponse,
  ResumeParseResponse,
  SalaryTypeEnum,
  SpecializationEnum,
  TalentDetailResponse as GeneratedTalentDetail,
  TalentFSP as GeneratedTalentFSP,
  TalentLeague as GeneratedTalentLeague,
  TalentSearchResponse as GeneratedTalentSearchResponse,
  TalentShort as GeneratedTalentShort,
  Taxonomy as GeneratedTaxonomy,
  TaxonomyDeclineReason as GeneratedTaxonomyDeclineReason,
  TaxonomyGrade as GeneratedTaxonomyGrade,
  TaxonomySkill as GeneratedTaxonomySkill,
  TaxonomySpecialization as GeneratedTaxonomySpecialization,
  TaxonomyTopic as GeneratedTaxonomyTopic,
  TrustLevelEnum,
  WorkFormatsEnum,
} from '@/api/generated/models'

// Re-export the generated building blocks so mocks/tests can type payloads
// without importing from the generated folder directly.
export type {
  GeneratedAssessmentEvidence as AssessmentEvidenceDto,
  GeneratedAssessmentFallback as AssessmentFallbackDto,
  GeneratedAssessmentTopic as AssessmentTopicDto,
  GeneratedCandidateFSP,
  GeneratedCandidateLeague,
  GeneratedCandidateSkill,
  GeneratedJdBlueprintItem,
  GeneratedJdDraft,
  GeneratedJdParseResult,
  GeneratedLeagueShelf,
  GeneratedPoolComponent,
  GeneratedPoolItem,
  GeneratedPositionPoolResponse,
  GeneratedTalentFSP,
  GeneratedTalentLeague,
  GeneratedTalentSearchResponse,
  GeneratedTaxonomy,
  GeneratedTaxonomyDeclineReason,
  GeneratedTaxonomyGrade,
  GeneratedTaxonomySkill,
  GeneratedTaxonomySpecialization,
  GeneratedTaxonomyTopic,
}

// --- enums: single source of truth = the generated schema ---
export type Spec = SpecializationEnum
export type Grade = GradeEnum
export type WorkFormat = WorkFormatsEnum
export type SalaryType = SalaryTypeEnum
export type OfferStatus = OfferStatusEnum
export type AssessmentKind = KindEnum
export type AssessmentMode = AssessmentModeEnum
export type AssessmentStatus = AssessmentStatusEnum
export type DeclineReason = (typeof DeclineReasonEnum)[keyof typeof DeclineReasonEnum]
export type GradeDecision = (typeof DecisionEnum)[keyof typeof DecisionEnum] | ''
export type ContactChannel = (typeof ContactChannelEnum)[keyof typeof ContactChannelEnum]
export type TrustLevel = (typeof TrustLevelEnum)[keyof typeof TrustLevelEnum]
export type { ConsentsResponse, FSPLinkResponse }

/** The schema renders `role` as a loose string. */
export type Role = 'candidate' | 'employer' | 'admin'
/** The schema renders `onboarding_step` as a loose string (BE `core/enums.py`). */
export type OnboardingStep = 'consent' | 'profile' | 'qualification' | 'done'

export type Me = Omit<MeResponse, 'role' | 'onboarding_step'> & {
  role: Role
  onboarding_step?: OnboardingStep
}

/** League payload: the schema renders specialization/grade/status as loose strings. */
export type LeagueStatus = 'pending' | 'confirmed' | 'unconfirmed'
export type League = {
  specialization: Spec
  grade: Grade
  status: LeagueStatus
  rating?: number
  percentile?: number | null
  strength?: number | null
}

/** Reasons carry a source; the schema types `why_you` as `unknown`. */
export type Source = 'test' | 'fsp' | 'microtask' | 'declared'
export type ReasonKind = 'plus' | 'minus' | 'info'
export type Reason = { kind: ReasonKind; text: string; source?: Source }

export type ScoreComponentKey =
  | 'skill'
  | 'strength'
  | 'grade'
  | 'salary'
  | 'semantic'
  | 'freshness'
  | 'fsp'

/** Generated PoolComponent is {key,value,weight,contribution}; key is a loose string. */
export type ScoreComponent = {
  key: ScoreComponentKey
  contribution: number
  weight?: number
  value?: number
}

/** Legacy dict shape (BE shipped the list form — kept so MSW mocks/tests can still emit it). */
export type ScoreComponentsDict = Partial<Record<ScoreComponentKey, number>>

/** FSP block on talent payloads (schema TalentFSP has no best_tier/rank fields). */
export type TalentFspView = {
  linked: boolean
  results?: number
  best_tier?: string
  rank?: string
  sports_rank?: string | null
}

export type TalentShort = Omit<
  GeneratedTalentShort,
  'public_id' | 'league' | 'fsp' | 'skills' | 'display_name' | 'verified_topics' | 'salary_type'
> & {
  public_id: string
  /** present at runtime; the schema marks it readOnly */
  display_name?: string
  salary_type?: SalaryType | ''
  league?: League | null
  fsp?: TalentFspView | null
  skills?: string[]
  verified_topics?: readonly string[]
  /** FE-12 · search payload carries the shortlist flag on the talent itself. */
  shortlisted?: boolean
}

export type Offer = Omit<
  GeneratedOffer,
  | 'company'
  | 'description'
  | 'contact_channel'
  | 'contact_value'
  | 'why_you'
  | 'candidate_contacts'
  | 'decline_reason'
  | 'decline_comment'
  | 'expires_at'
  | 'talent'
  | 'decline'
  | 'below_floor'
  | 'acceptance_likelihood'
> & {
  description?: string
  company?: { id: string; name: string; trust_level?: TrustLevel }
  contact_channel?: ContactChannel
  contact_value?: string
  why_you?: Reason[]
  decline_reason?: DeclineReason | null
  decline_comment?: string | null
  expires_at?: string | null
  candidate_contacts?: {
    full_name?: string
    email?: string
    phone?: string
    telegram?: string
  } | null
  talent?: TalentShort | null
  decline?: { reason?: string; comment?: string } | null
  below_floor?: boolean
  acceptance_likelihood?: 'low' | 'medium' | 'high' | null
}

export type ProfileSkill = {
  id: string
  name: string
  source?: Source | string
  level?: string | null
}

export type Consents = ConsentsResponse

export type CandidateFspView = GeneratedCandidateFSP & {
  /** legacy mock shape carried a flat results list; tolerate it */
  best_tier?: string
  rank?: string
}

export type CandidateProfile = Omit<
  GeneratedCandidateProfile,
  | 'specialization'
  | 'claimed_grade'
  | 'salary_type'
  | 'about'
  | 'experience_text'
  | 'league'
  | 'fsp'
> & {
  specialization?: Spec | '' | null
  claimed_grade?: Grade | '' | null
  salary_type?: SalaryType | '' | null
  about?: string | null
  experience_text?: string | null
  /** the schema marks these readOnly but they arrive as plain objects */
  contacts?: GeneratedCandidateProfile['contacts'] | null
  skills?: ProfileSkill[]
  unknown_skills?: string[]
  league?: League | null
  fsp?: CandidateFspView | null
  consents?: Consents | null
}

export type ResumeParseResult = Omit<ResumeParseResponse, 'prefill'> & {
  prefill: {
    specialization?: Spec
    claimed_grade?: Grade
    skills?: string[]
    about?: string
  }
}

/** The wire Taxonomy is object-based (G3 shipped); this is the flat view type. */
export type TaxonomyWire = GeneratedTaxonomy

/**
 * View model consumed by the UI: plain string lists (specs/grades/skills are
 * `{id,name}` objects on the wire — normalized in useTaxonomy().select).
 * `work_formats`/`strength_topics` are not part of the taxonomy endpoint yet,
 * so they stay optional with static fallbacks in the consumers.
 */
export type Taxonomy = {
  specs: Spec[]
  grades: Grade[]
  work_formats?: WorkFormat[]
  strength_topics?: string[]
  skills: string[]
  decline_reasons?: { id: string; name: string }[]
}

export type ResultTopic = GeneratedAssessmentTopic & {
  /** legacy mock key (label); the schema field is `topic` */
  key?: string
  label?: string
  correct?: number
  total?: number
}

/**
 * MSW-only fallback payload may additionally carry `kind` and `reason`;
 * the OpenAPI schema exposes only `{grade, mode}`.
 */
export type MockAssessmentFallback = GeneratedAssessmentFallback & {
  kind?: string
  reason?: string
}
export type EvidencePoint = GeneratedAssessmentEvidence

/**
 * GET /api/assessments/{id}/result. Enums are optional on the wire and
 * narrowed to required here; `percentile` is not in the schema
 * — it stays only on League, not on the result payload.
 */
export type AssessmentResult = Omit<
  GeneratedAssessmentResult,
  | 'kind'
  | 'mode'
  | 'status'
  | 'theta'
  | 'se'
  | 'rating'
  | 'result_grade'
  | 'decision'
  | 'started_at'
  | 'topics'
  | 'evidence'
  | 'fallback'
> & {
  kind: AssessmentKind
  mode: AssessmentMode
  status: AssessmentStatus
  theta: number | null
  se: number | null
  rating: number | null
  result_grade: Grade | ''
  decision: GradeDecision
  started_at: string | null
  topics?: ResultTopic[]
  evidence?: EvidencePoint[]
  fallback?: GeneratedAssessmentFallback | null
}

/**
 * MSW-only fixtures may still emit fields the schema omits (percentile) or
 * relax readonly optionality (fallback/next_attempt_at/start). Tests cast
 * payloads through this alias instead of `as unknown as`.
 */
export type MockAssessmentResult = AssessmentResult & {
  percentile?: number | null
  fallback?: MockAssessmentFallback | null
  next_attempt_at?: string | null
  started_at?: string | null
}

/**
 * GET /api/assessments/eligibility?specialization= (FE-05 start screen).
 * `reason` carries the machine code (`cooldown_active`) and `next_attempt_at`
 * the ISO moment when the cooldown ends.
 */
export type Eligibility = Omit<EligibilityResponse, 'next_attempt_at' | 'active_session_id'> & {
  next_attempt_at?: string | null
  active_session_id?: string | null
}

// --- FE-05 · Test runner ----------------------------------------------------

export type ItemInputType = 'choice' | 'number' | 'text'

/**
 * GET /api/assessments/{id} → `current` (FE2.md §FE-05).
 * The schema flattens `code`/`options`/`input_type` to loose types; the
 * runtime shapes are `code: {lang, text} | null`,
 * `options: [{id, text_md}] | null`.
 */
export type AssessmentItem = Omit<
  GeneratedItemView,
  'code' | 'options' | 'input_type' | 'level'
> & {
  code: { lang: string; text: string } | null
  options: { id: string; text_md: string }[] | null
  input_type: ItemInputType
  level?: string | number | null
}

export type AssessmentSession = Omit<GeneratedAssessmentSession, 'current' | 'max_items'> & {
  /** Served item for the in-progress session; null once finished/expired. */
  current: AssessmentItem | null
  max_items?: number | null
}

/** POST /api/assessments body (schema leaves the enums loose). */
export type StartAssessmentInput = {
  specialization?: Spec
  claimed_grade?: Grade
  mode?: AssessmentMode
  /** `promotion` when eligibility advertises a promotion attempt (FE-05). */
  kind?: AssessmentKind
}

// --- FE-09 · Company & position wizard ---------------------------------------

/** GET/PUT /api/companies/me. `trust_level` is read-only (TrustBadge). */
export type Company = GeneratedCompany
/** PUT body: writable subset only (id/trust_level/created_at are readOnly). */
export type CompanyInput = Pick<
  Company,
  'name' | 'inn' | 'website' | 'email_domain' | 'business_domain' | 'description' | 'contact_email'
>

/** Company creation payload — same writable subset (G17 shipped on the BE). */
export type CompanyCreateInput = CompanyInput

/** GET/POST/PUT /api/positions[/{id}]. */
export type Position = GeneratedPosition
/** POST body: writable subset only (id/company/created_at are readOnly). */
export type PositionInput = Omit<Position, 'id' | 'company' | 'created_at'>

/**
 * POST /api/positions/parse → JdParseResult.
 * The schema renders the draft enums as loose strings — narrowed here.
 */
export type JdBlueprintItem = { topic: string; weight: number }
export type JdDraft = {
  title?: string
  specialization?: Spec
  grades?: Grade[]
  must_skills?: string[]
  nice_skills?: string[]
  work_formats?: WorkFormat[]
  location?: string | null
  salary_min?: number | null
  salary_max?: number | null
  salary_type?: SalaryType | ''
  team_context?: string | null
  description?: string | null
}
export type JdParseResult = {
  draft: JdDraft
  unknown_terms?: string[]
  blueprint?: JdBlueprintItem[]
  source?: string
}

// --- FE-10 · Scouting --------------------------------------------------------

/**
 * GET /api/positions/{id}/pool item. `components` ships as a list of
 * {key,value,weight,contribution}; the legacy dict shape is tolerated by
 * normalizeComponents() so older mocks keep rendering. `gaps` is required
 * on the wire; `deriveGaps()` stays as a fallback for dict-era payloads.
 */
export type PoolEntry = Omit<GeneratedPoolItem, 'talent' | 'components' | 'reasons'> & {
  talent: TalentShort
  components: ScoreComponent[] | ScoreComponentsDict
  /** the generated schema renders reasons as loose dicts — narrowed here */
  reasons: Reason[]
  gaps: string[]
}

/**
 * Pool page. The generated schema declares pages/facets/relaxations; they
 * stay optional so the UI can detect the capability instead of hardcoding
 * it (client-side filter fallback when `facets` is absent in mocks).
 */
export type PoolResponse = {
  items: PoolEntry[]
  total: number
  page: number
  pages?: number
  facets?: Record<string, Record<string, number>>
  relaxations?: string[]
}

/** Pool filters, synced to the URL query string (FE-10). Sent as query params; */
/** the backend may ignore them today — see the client-side fallback. */
export type PoolFilters = {
  grades: Grade[]
  skills: string[]
  fsp: 'any' | 'linked' | 'prize'
  formats: WorkFormat[]
  salary_max: number | null
  confirmed_only: boolean
  preset: string | null
  page: number
}

/**
 * GET /api/leagues?specialization= returns a plain array of shelves
 * `{specialization, grade, confirmed, unconfirmed, median_expectation?}`
 * (schema LeagueShelf with loose spec/grade strings — narrowed here).
 */
export type LeagueShelf = Omit<GeneratedLeagueShelf, 'specialization' | 'grade'> & {
  specialization: Spec
  grade: Grade
}

/**
 * Shortlist tray entry. GET /api/positions/{id}/shortlist exists on the BE;
 * the tray additionally accumulates `shortlisted: true` pool items client-side.
 */
export type ShortlistEntry = TalentShort

/**
 * FE-12 · GET /api/talent/search — plain talent search (no position scoring).
 * `pages` and `facets` stay optional so the UI can detect the capability
 * instead of hardcoding it (client-side facet counting + filter fallback
 * when absent).
 */
export type TalentSearchResponse = {
  items: TalentShort[]
  total: number
  page: number
  pages?: number
  facets?: Record<string, Record<string, number>>
}

/**
 * GET /api/talent/{public_id} — talent fields plus about/experience_text and
 * contacts (null unless the company has a grant). Sections for topics,
 * assessments and integrity flags come later (gap G9): hide them when absent.
 */
export type TalentContacts = {
  full_name?: string
  email?: string
  phone?: string
  telegram?: string
}
export type TalentDetail = Omit<
  GeneratedTalentDetail,
  | 'league'
  | 'fsp'
  | 'skills'
  | 'contacts'
  | 'salary_type'
  | 'topics'
  | 'assessments'
  | 'integrity_flags'
> & {
  display_name?: string
  last_active_at?: string | null
  salary_type?: SalaryType | string
  league?: League | null
  fsp?: TalentFspView | null
  skills?: ProfileSkill[]
  contacts?: TalentContacts | null
  // gap G9 — hidden while absent
  topics?: ResultTopic[]
  assessments?: unknown[]
  integrity_flags?: unknown[]
}

/** Integrity capture payload sent with every answer (FE-05). */
export type AnswerIntegrity = {
  focus_loss: number
  paste: number
}

export type AnswerInput = {
  item_id: string
  option_id?: string
  value?: string
  integrity?: AnswerIntegrity
}

/**
 * POST /api/assessments/{id}/answers → `{done:false,next}` or `{done:true,result}`.
 * Exactly one branch is present at runtime; the schema renders both optional.
 */
export type AnswerOutcome = Omit<GeneratedAnswerResponse, 'next' | 'result'> & {
  next?: AssessmentItem
  result?: AssessmentResult
}
