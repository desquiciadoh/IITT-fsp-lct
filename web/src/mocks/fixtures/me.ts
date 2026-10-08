import type { Me } from '@/api/types'

export const me: Record<'candidate' | 'candidatePlain' | 'employer' | 'admin', Me> = {
  candidate: {
    id: 'c-1',
    role: 'candidate',
    email: 'anna.fsp@example.com',
    email_verified: true,
    demo: true,
    onboarding_step: 'done',
  },
  candidatePlain: {
    id: 'c-2',
    role: 'candidate',
    email: 'alex.dev@example.com',
    email_verified: true,
    demo: true,
    onboarding_step: 'done',
  },
  employer: {
    id: 'e-1',
    role: 'employer',
    email: 'hr@example.com',
    email_verified: true,
    demo: true,
    company_id: 'comp-1',
    onboarding_step: 'done',
  },
  admin: {
    id: 'a-1',
    role: 'admin',
    email: 'admin@example.com',
    email_verified: true,
    demo: true,
  },
}
