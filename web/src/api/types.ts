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
  AssessmentResult as GeneratedAssessmentResult,
  AssessmentSession as GeneratedAssessmentSession,
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
export type AssessmentSession = GeneratedAssessmentSession
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

/** GET /api/assessments/eligibility?specialization= */
export type Eligibility = Omit<EligibilityResponse, 'next_attempt_at'> & {
  next_attempt_at?: string | null
}
