/**
 * Interim hand-written DTOs for the shapes the backend emits today plus the
 * target shapes from TASKS Â§1.4. Once `pnpm api:gen` output is wired in,
 * features switch to the generated types and this file shrinks to helpers.
 */

export type Spec = 'backend' | 'frontend' | 'ml_data'
export type Grade = 'intern' | 'junior' | 'middle' | 'senior'
export type LeagueStatus = 'pending' | 'confirmed' | 'unconfirmed'
export type WorkFormat = 'office' | 'hybrid' | 'remote'
export type SalaryType = 'gross' | 'net'
export type Source = 'test' | 'fsp' | 'microtask' | 'declared'
export type OfferStatus =
  | 'sent'
  | 'viewed'
  | 'accepted'
  | 'declined'
  | 'expired'
  | 'withdrawn'
  | 'interview'
  | 'hired'
  | 'closed'
export type DeclineReason =
  | 'salary'
  | 'stack'
  | 'format'
  | 'company'
  | 'timing'
  | 'not_looking'
  | 'other'

export type Me = {
  id: string
  role: 'candidate' | 'employer' | 'admin'
  email: string
  email_verified: boolean
  demo: boolean
  company_id?: string | null
  onboarding_step?: 'consent' | 'profile' | 'survey' | 'qualification' | 'done'
}

export type League = {
  specialization: Spec
  grade: Grade
  status: LeagueStatus
  rating?: number
  percentile?: number
  strength?: number | null
}

export type Reason = { kind: 'plus' | 'minus' | 'info'; text: string; source?: Source }

export type ScoreComponent = {
  key: 'skill' | 'strength' | 'grade' | 'salary' | 'semantic' | 'freshness' | 'fsp'
  contribution: number
  weight?: number
}

/** Backend pool components today (BE gap G8). */
export type ScoreComponentsDict = Partial<
  Record<'skill' | 'grade' | 'strength' | 'fsp' | 'salary' | 'semantic' | 'freshness', number>
>

export type TalentShort = {
  public_id: string
  display_name?: string
  city?: string
  work_formats?: WorkFormat[]
  salary_min?: number
  salary_max?: number
  salary_type?: SalaryType
  league?: League | null
  fsp?: { linked: boolean; best_tier?: string; rank?: string; results?: number }
  last_active_at?: string
}

export type Offer = {
  id: string
  title: string
  description?: string
  company?: { id: string; name: string; trust_level?: 'none' | 'domain' | 'verified' }
  position?: string | null
  salary_min: number
  salary_max: number
  salary_type: SalaryType
  currency?: string
  contact_channel?: 'email' | 'phone' | 'telegram' | 'platform'
  contact_value?: string
  status: OfferStatus
  decline_reason?: DeclineReason | null
  decline_comment?: string | null
  why_you?: Reason[]
  version: number
  expires_at?: string | null
  created_at?: string
  updated_at?: string
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

export type Consents = {
  processing: boolean
  publication: boolean
  fsp_sync: boolean
}

export type CandidateProfile = {
  public_id: string
  full_name?: string | null
  city?: string | null
  timezone?: string | null
  specialization?: Spec | '' | null
  claimed_grade?: Grade | '' | null
  years_experience?: string | null
  roles?: string[]
  work_formats?: WorkFormat[]
  salary_min?: number | null
  salary_max?: number | null
  salary_type?: SalaryType | '' | null
  salary_floor?: number | null
  open_to_offers?: boolean
  blind_mode?: boolean
  blocked_company_ids?: string[]
  about?: string | null
  experience_text?: string | null
  completeness?: number
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

export type ResumeParseResult = {
  prefill: {
    specialization?: Spec
    claimed_grade?: Grade
    skills?: string[]
    about?: string
  }
  unknown_terms: string[]
  source: 'llm' | 'rules' | string
}

export type Taxonomy = {
  specs: Spec[]
  grades: Grade[]
  work_formats: WorkFormat[]
  strength_topics: string[]
  skills: string[]
}

export type AssessmentKind = 'initial' | 'fallback' | 'promotion' | 'screening'
export type AssessmentStatus = 'in_progress' | 'finished' | 'abandoned' | 'expired'
export type AssessmentMode = 'full' | 'express'
export type GradeDecision = 'confirmed' | 'unconfirmed' | ''

export type ResultTopic = { key: string; label: string; correct: number; total: number }
export type EvidencePoint = { seq: number; correct: boolean | null }

/** GET /api/assessments/{id}/result. G5 fields are optional (mocked until BE adds them). */
export type AssessmentResult = {
  id: string
  specialization: Spec
  claimed_grade: Grade
  kind: AssessmentKind
  mode: AssessmentMode
  status: AssessmentStatus
  theta: number | null
  se: number | null
  rating: number | null
  result_grade: Grade | ''
  decision: GradeDecision
  promotion_unlocked: boolean
  counts_as_attempt: boolean
  started_at: string | null
  finished_at: string | null
  // gap G5 — hidden when absent
  rating_ci?: number | null
  percentile?: number | null
  topics?: ResultTopic[]
  evidence?: EvidencePoint[]
  fallback?: { kind: 'instant' | 'short_test'; reason?: string } | null
  next_attempt_at?: string | null
}

/** GET /api/assessments/eligibility?specialization= */
export type Eligibility = {
  can_start: boolean
  next_attempt_at?: string | null
  promotion_available?: boolean
  reason?: string | null
  active_session_id?: string | null
}
