import { createBrowserRouter, Navigate } from 'react-router-dom'
import { HomePage } from '@/pages/home'
import { DevUiPage } from '@/pages/dev-ui'
import { DesignVariantsPage } from '@/pages/design-variants'
import { LoginPage } from '@/features/auth/login-page'
import { RegisterPage } from '@/features/auth/register-page'
import { VerifyPage } from '@/features/auth/verify-page'
import { JuryPage } from '@/features/jury/jury-page'
import { ScoutingPage } from '@/features/scouting/scouting-page'
import { OnboardingPage } from '@/features/onboarding/onboarding-page'
import { ResultPage } from '@/features/result/result-page'
import { DashboardPage } from '@/features/candidate/dashboard-page'
import { StartPage } from '@/features/qualification-runner/start-page'
import { TestRunnerPage } from '@/features/qualification-runner/test-runner-page'
import { OffersListPage } from '@/features/offers/offers-list-page'
import { OfferDetailPage } from '@/features/offers/offer-detail-page'
import { OffersBoardPage } from '@/features/employer/offers-board-page'
import { SettingsPage } from '@/features/settings/settings-page'
import { CompanyPage } from '@/features/employer/company-page'
import { EmployerDashboardPage } from '@/features/employer/dashboard-page'
import { PositionWizardPage } from '@/features/employer/position-wizard-page'
import { AppLayout } from '@/app/layouts/app-layout'
import { RequireAuth, RequireRole, OnboardingGate } from '@/app/guards'
import { IndexRedirect } from '@/app/index-redirect'
import { Placeholder } from '@/app/placeholder'

const ph = (title: string, owner: 'FE1' | 'FE2', task: string) => (
  <Placeholder title={title} owner={owner} task={task} />
)

export const router = createBrowserRouter([
  { path: '/', element: <IndexRedirect /> },
  { path: '/home', element: <HomePage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/verify', element: <VerifyPage /> },
  { path: '/dev/ui', element: <DevUiPage /> },
  { path: '/dev/design', element: <DesignVariantsPage /> },
  {
    // Public pages inside the shell (no RequireAuth; no SSE for anonymous users)
    element: <AppLayout />,
    children: [
      { path: '/jury', element: <JuryPage /> },
      { path: '/lab', element: ph('Лаборатория', 'FE2', 'FE-18') },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            element: <RequireRole role="candidate" />,
            children: [
              {
                path: '/candidate/onboarding/:step',
                element: <OnboardingPage />,
              },
              {
                element: <OnboardingGate />,
                children: [
                  { path: '/candidate', element: <DashboardPage /> },
                  {
                    path: '/candidate/qualification/start',
                    element: <StartPage />,
                  },
                  {
                    path: '/candidate/qualification/:id',
                    element: <TestRunnerPage />,
                  },
                  {
                    path: '/candidate/qualification/:id/result',
                    element: <ResultPage />,
                  },
                  { path: '/candidate/offers', element: <OffersListPage /> },
                  {
                    path: '/candidate/offers/:id',
                    element: <OfferDetailPage />,
                  },
                  { path: '/candidate/settings', element: <SettingsPage /> },
                ],
              },
            ],
          },
          {
            element: <RequireRole role="employer" />,
            children: [
              { path: '/employer', element: <EmployerDashboardPage /> },
              { path: '/employer/company', element: <CompanyPage /> },
              {
                path: '/employer/positions/new',
                element: <PositionWizardPage />,
              },
              {
                path: '/employer/positions/:id',
                element: <ScoutingPage />,
              },
              { path: '/employer/talent', element: ph('Пул талантов', 'FE2', 'FE-15') },
              { path: '/employer/offers', element: <OffersBoardPage /> },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
