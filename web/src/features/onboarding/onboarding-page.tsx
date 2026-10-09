import { Navigate, useParams } from 'react-router-dom'
import type { ComponentType } from 'react'
import { cn } from '@/lib/utils'
import { ConsentStep } from '@/features/onboarding/steps/consent-step'
import { ProfileStep } from '@/features/onboarding/steps/profile-step'
import { SurveyStep } from '@/features/onboarding/steps/survey-step'
import { ClaimStep } from '@/features/onboarding/steps/claim-step'

const STEPS = [
  { id: 'consent', label: 'Согласия' },
  { id: 'profile', label: 'Профиль' },
  { id: 'survey', label: 'Опрос' },
  { id: 'claim', label: 'Грейд' },
] as const

type StepId = (typeof STEPS)[number]['id']

const STEP_COMPONENT: Record<StepId, ComponentType> = {
  consent: ConsentStep,
  profile: ProfileStep,
  survey: SurveyStep,
  claim: ClaimStep,
}

/** Onboarding wizard: consent → profile → survey → claim (FE-04). */
export function OnboardingPage() {
  const { step } = useParams()
  const valid = STEPS.some((s) => s.id === step)
  if (!step || !valid) return <Navigate to="/candidate/onboarding/consent" replace />

  const index = STEPS.findIndex((s) => s.id === step)
  const Step = STEP_COMPONENT[step as StepId]

  return (
    <section className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
      <header className="flex flex-col gap-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Онбординг кандидата
        </span>
        <ol className="flex items-center gap-2">
          {STEPS.map((s, i) => (
            <li key={s.id} className="flex flex-1 flex-col gap-1.5">
              <div
                className={cn(
                  'h-1.5 rounded-full',
                  i <= index ? 'bg-primary' : 'bg-muted',
                )}
              />
              <span
                className={cn(
                  'text-xs',
                  i === index ? 'font-semibold text-foreground' : 'text-muted-foreground',
                )}
              >
                {i + 1}. {s.label}
              </span>
            </li>
          ))}
        </ol>
      </header>
      <Step />
    </section>
  )
}
