/**
 * API DTOs.
 *
 * Types that exist in the generated schema are aliased or derived from
 * `@/api/generated/models` (orval output) so they cannot drift from the
 * backend. Hand-written types are limited to shapes drf-spectacular leaves
 * open (nested serializers flattened to `string`/`unknown`) and to gaps
 * still to be shipped, each tagged with a comment.
 */
import type {
  AnswerResponse as GeneratedAnswerResponse,
  AssessmentResult as GeneratedAssessmentResult,
  AssessmentSession as GeneratedAssessmentSession,
  ItemView as GeneratedItemView,
  CandidateProfile as GeneratedCandidateProfile,
  ConsentsResponse,
  ContactChannelEnum,
  DecisionEnum,
  DeclineReasonEnum,
  EligibilityResponse,
  FSPLinkResponse,
  GradesEnum,
  KindEnum,
  MeResponse,
  ModeEnum,
  Offer as GeneratedOffer,
  OfferStatusEnum,
  ResumeParseResponse,
  SalaryTypeEnum,
  SpecializationEnum,
  Status61dEnum,
  TalentShort as GeneratedTalentShort,
  TrustLevelEnum,
  WorkFormatsEnum,
} from '@/api/generated/models'

// --- enums: single source of truth = the generated schema ---
export type Spec = SpecializationEnum
export type Grade = GradesEnum
export type WorkFormat = WorkFormatsEnum
export type SalaryType = SalaryTypeEnum
export type OfferStatus = OfferStatusEnum
export type AssessmentKind = KindEnum
export type AssessmentMode = ModeEnum
export type AssessmentStatus = Status61dEnum
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

/** The schema has no League model (nested serializers flattened to `string`). */
export type LeagueStatus = 'pending' | 'confirmed' | 'unconfirmed'
export type League = {
  specialization: Spec
  grade: Grade
  status: LeagueStatus
  rating?: number
  percentile?: number
  strength?: number | null
}

/** Reasons carry a source; the schema types `why_you` as `unknown`. */
export type Source = 'test' | 'fsp' | 'microtask' | 'declared'
export type ReasonKind = 'plus' | 'minus' | 'info'
export type Reason = { kind: ReasonKind; text: string; source?: Source }

export type ScoreComponent = {
  key: 'skill' | 'strength' | 'grade' | 'salary' | 'semantic' | 'freshness' | 'fsp'
  contribution: number
  weight?: number
}

/** gap G8 — the backend pool returns a flat components dict today. */
export type ScoreComponentsDict = Partial<
  Record<'skill' | 'grade' | 'strength' | 'fsp' | 'salary' | 'semantic' | 'freshness', number>
>

export type TalentShort = Omit<GeneratedTalentShort, 'public_id' | 'league' | 'fsp' | 'skills'> & {
  public_id: string
  /** present at runtime; the schema does not declare it */
  display_name?: string
  league?: League | null
  fsp?: { linked: boolean; best_tier?: string; rank?: string; results?: number }
  /** the schema flattens this nested list to `string` */
  skills?: string[]
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
}

export type ProfileSkill = {
  id: string
  name: string
  source?: Source | string
  level?: string | null
}

export type Consents = ConsentsResponse

export type CandidateProfile = Omit<
  GeneratedCandidateProfile,
  | 'specialization'
  | 'claimed_grade'
  | 'salary_type'
  | 'about'
  | 'experience_text'
  | 'contacts'
  | 'skills'
  | 'league'
  | 'fsp'
  | 'consents'
> & {
  specialization?: Spec | '' | null
  claimed_grade?: Grade | '' | null
  salary_type?: SalaryType | '' | null
  about?: string | null
  experience_text?: string | null
  contacts?: { email?: string; phone?: string; telegram?: string } | null
  skills?: ProfileSkill[]
  league?: League | null
  fsp?: {
    participant_id?: string
    sports_rank?: string | null
    sync_status?: string
    results?: {
      event_id?: string
      event_name?: string
      discipline?: string
      date?: string
      placement?: number | null
      tier?: string | null
      participants_total?: number | null
    }[]
  } | null
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

/** gap G3 — the taxonomy endpoint is mocked until the backend ships it. */
export type Taxonomy = {
  specs: Spec[]
  grades: Grade[]
  work_formats: WorkFormat[]
  strength_topics: string[]
  skills: string[]
}

export type ResultTopic = { key: string; label: string; correct: number; total: number }
export type EvidencePoint = { seq: number; correct: boolean | null }

/** GET /api/assessments/{id}/result. G5 fields are optional (mocked until BE adds them). */
export type AssessmentResult = Omit<
  GeneratedAssessmentResult,
  'kind' | 'mode' | 'status' | 'theta' | 'se' | 'rating' | 'result_grade' | 'decision' | 'started_at'
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
  // gap G5 — hidden while the backend omits them
  rating_ci?: number | null
  percentile?: number | null
  topics?: ResultTopic[]
  evidence?: EvidencePoint[]
  fallback?: { kind: 'instant' | 'short_test'; reason?: string } | null
  next_attempt_at?: string | null
}

/**
 * GET /api/assessments/eligibility?specialization= (FE-05 start screen).
 * gap G5: `reason` carries the machine code (`cooldown_active`) and
 * `next_attempt_at` the ISO moment when the cooldown ends — the backend
 * returns both today, but the schema marks them optional.
 */
export type Eligibility = Omit<EligibilityResponse, 'next_attempt_at' | 'active_session_id'> & {
  next_attempt_at?: string | null
  active_session_id?: string | null
}

// --- FE-05 · Test runner ----------------------------------------------------

export type ItemInputType = 'choice' | 'number' | 'text'

/**
 * GET /api/assessments/{id} → `current` (FE2.md §FE-05).
 * The schema flattens `code`/`options` to `unknown`; the runtime shapes are:
 * `code: {lang, text} | null`, `options: [{id, text_md}] | null`.
 * gap G5: `level` (difficulty) and `max_items` (progress total) are not on
 * the backend yet — optional here, mocked in qualification.ts.
 */
export type AssessmentItem = Omit<GeneratedItemView, 'code' | 'options' | 'input_type'> & {
  code: { lang: string; text: string } | null
  options: { id: string; text_md: string }[] | null
  input_type: ItemInputType
  level?: number | null
}

export type AssessmentSession = Omit<GeneratedAssessmentSession, 'current'> & {
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

import type { Company as GeneratedCompany, Position as GeneratedPosition } from '@/api/generated/models'

/** GET/PUT /api/companies/me. `trust_level` is read-only (TrustBadge). */
export type Company = GeneratedCompany
/** PUT body: writable subset only (id/trust_level/created_at are readOnly). */
export type CompanyInput = Pick<
  Company,
  'name' | 'inn' | 'website' | 'email_domain' | 'business_domain' | 'description' | 'contact_email'
>

/** gap G17 — company creation endpoint (`company_required` after BE fix B1). */
export type CompanyCreateInput = CompanyInput

/** GET/POST/PUT /api/positions[/{id}]. */
export type Position = GeneratedPosition
/** POST body: writable subset only (id/company/created_at are readOnly). */
export type PositionInput = Omit<Position, 'id' | 'company' | 'created_at'>

/**
 * POST /api/positions/parse → JdParseResult (gap G6; mocked in MSW).
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

import type { PoolItem as GeneratedPoolItem } from '@/api/generated/models/poolItem'
import type { TalentDetailResponse as GeneratedTalentDetail } from '@/api/generated/models/talentDetailResponse'

/**
 * GET /api/positions/{id}/pool item. `components` is a dict today (skill/
 * grade/strength/fsp/salary, max 35/25/15/15/10) and becomes a list (gap G8);
 * everything renders through normalizeComponents(). `gaps` is target shape
 * (G8) — until then derive them from `kind === 'minus'` reasons.
 */
export type PoolEntry = Omit<GeneratedPoolItem, 'talent' | 'components' | 'reasons'> & {
  talent: TalentShort
  components: ScoreComponent[] | ScoreComponentsDict
  /** the generated schema renders reasons as loose dicts — narrowed here */
  reasons: Reason[]
  gaps?: string[]
}

/**
 * The generated schema declares only {items,total,page}. `pages`, `facets`
 * and `relaxations` are BE gap G8 — optional so the UI can detect the
 * capability instead of hardcoding it (client-side filter fallback when
 * `facets` is absent).
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
/** the backend may ignore them today (G8) — see the client-side fallback. */
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
 * gap G7 — GET /api/leagues?specialization= returns a plain array of shelves
 * `{specialization, grade, confirmed, unconfirmed, median_expectation?}`.
 * The static mock in gaps.ts returns {items,...}; the scouting mock serves the
 * target array shape and wins by registration order.
 */
export type LeagueShelf = {
  specialization: Spec
  grade: Grade
  confirmed: number
  unconfirmed: number
  median_expectation?: number | null
}

/**
 * gap G16 — GET /api/positions/{id}/shortlist (list endpoint not shipped).
 * Until then the tray is built from `shortlisted: true` pool items.
 */
export type ShortlistEntry = TalentShort

/**
 * FE-12 · GET /api/talent/search — plain talent search (no position scoring).
 * The generated schema declares only {items,total,page}; `pages` and `facets`
 * are BE gaps G8/G14 — optional so the UI can detect the capability instead of
 * hardcoding it (client-side facet counting + filter fallback when absent).
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
  'league' | 'fsp' | 'skills' | 'contacts' | 'salary_type'
> & {
  display_name?: string
  last_active_at?: string | null
  salary_type?: SalaryType | string
  league?: League | null
  fsp?: { linked: boolean; best_tier?: string; rank?: string; results?: number } | null
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
