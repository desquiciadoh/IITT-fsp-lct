import { lazy, Suspense, type ComponentType } from 'react'
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom'
import { HomePage } from '@/pages/home'
import { LoginPage } from '@/features/auth/login-page'
import { RegisterPage } from '@/features/auth/register-page'
import { VerifyPage } from '@/features/auth/verify-page'
import { AppLayout } from '@/app/layouts/app-layout'
import { RequireAuth, RequireRole, OnboardingGate } from '@/app/guards'
import { IndexRedirect } from '@/app/index-redirect'
import { Placeholder } from '@/app/placeholder'
import { CardSkeleton } from '@/components/ui/skeleton'

const ph = (title: string, owner: 'FE1' | 'FE2', task: string) => (
  <Placeholder title={title} owner={owner} task={task} />
)

/**
 * R30 · Route-level code splitting. Pages that are not on the landing path
 * load lazily so the main chunk stays small (target < 400 KB). Auth pages
 * and the home page stay eager — they are the entry funnel; dev-only pages
 * (/dev/*) are lazy. The codebase uses named exports only, hence the
 * `.then((m) => ({ default: m.X }))` adapter per route module.
 */
const lazyPage = (load: () => Promise<{ default: ComponentType }>) => lazy(load)

const DevUiPage = lazyPage(() => import('@/pages/dev-ui').then((m) => ({ default: m.DevUiPage })))
const DesignVariantsPage = lazyPage(() =>
  import('@/pages/design-variants').then((m) => ({ default: m.DesignVariantsPage })),
)
const JuryPage = lazyPage(() => import('@/features/jury/jury-page').then((m) => ({ default: m.JuryPage })))
const OnboardingPage = lazyPage(() =>
  import('@/features/onboarding/onboarding-page').then((m) => ({ default: m.OnboardingPage })),
)
const DashboardPage = lazyPage(() =>
  import('@/features/candidate/dashboard-page').then((m) => ({ default: m.DashboardPage })),
)
const StartPage = lazyPage(() =>
  import('@/features/qualification-runner/start-page').then((m) => ({ default: m.StartPage })),
)
const TestRunnerPage = lazyPage(() =>
  import('@/features/qualification-runner/test-runner-page').then((m) => ({
    default: m.TestRunnerPage,
  })),
)
const ResultPage = lazyPage(() =>
  import('@/features/result/result-page').then((m) => ({ default: m.ResultPage })),
)
const OffersListPage = lazyPage(() =>
  import('@/features/offers/offers-list-page').then((m) => ({ default: m.OffersListPage })),
)
const OfferDetailPage = lazyPage(() =>
  import('@/features/offers/offer-detail-page').then((m) => ({ default: m.OfferDetailPage })),
)
const SettingsPage = lazyPage(() =>
  import('@/features/settings/settings-page').then((m) => ({ default: m.SettingsPage })),
)
const EmployerDashboardPage = lazyPage(() =>
  import('@/features/employer/dashboard-page').then((m) => ({ default: m.EmployerDashboardPage })),
)
const CompanyPage = lazyPage(() =>
  import('@/features/employer/company-page').then((m) => ({ default: m.CompanyPage })),
)
const NewPositionPage = lazyPage(() =>
  import('@/features/employer/new-position-page').then((m) => ({ default: m.NewPositionPage })),
)
const PositionDetailPage = lazyPage(() =>
  import('@/features/employer/position-detail-page').then((m) => ({
    default: m.PositionDetailPage,
  })),
)
const OffersBoardPage = lazyPage(() =>
  import('@/features/employer/offers-board-page').then((m) => ({ default: m.OffersBoardPage })),
)
const TalentSearchPage = lazyPage(() =>
  import('@/features/talent/talent-search-page').then((m) => ({ default: m.TalentSearchPage })),
)

// Shared per-route fallback: CardSkeleton matches the loading state the
// pages themselves render while their queries are pending.
const page = (Page: ReturnType<typeof lazyPage>) => (
  <Suspense fallback={<CardSkeleton />}>
    <Page />
  </Suspense>
)

function CandidateProfileRedirect() {
  const location = useLocation()
  return <Navigate to={{ pathname: '/candidate/settings', search: location.search }} replace />
}

export const router = createBrowserRouter([
  { path: '/', element: <IndexRedirect /> },
  { path: '/home', element: <HomePage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/verify', element: <VerifyPage /> },
  { path: '/dev/ui', element: page(DevUiPage) },
  { path: '/dev/design', element: page(DesignVariantsPage) },
  {
    // Public pages inside the shell (no RequireAuth; no SSE for anonymous users)
    element: <AppLayout />,
    children: [
      { path: '/jury', element: page(JuryPage) },
      { path: '/lab', element: ph('Лаборатория', 'FE1', 'FE-13') },
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
                element: page(OnboardingPage),
              },
              {
                element: <OnboardingGate />,
                children: [
                  { path: '/candidate', element: page(DashboardPage) },
                  { path: '/candidate/profile', element: <CandidateProfileRedirect /> },
                  {
                    path: '/candidate/qualification/start',
                    element: page(StartPage),
                  },
                  {
                    path: '/candidate/qualification/:id',
                    element: page(TestRunnerPage),
                  },
                  {
                    path: '/candidate/qualification/:id/result',
                    element: page(ResultPage),
                  },
                  { path: '/candidate/offers', element: page(OffersListPage) },
                  {
                    path: '/candidate/offers/:id',
                    element: page(OfferDetailPage),
                  },
                  { path: '/candidate/settings', element: page(SettingsPage) },
                ],
              },
            ],
          },
          {
            element: <RequireRole role="employer" />,
            children: [
              { path: '/employer', element: page(EmployerDashboardPage) },
              { path: '/employer/company', element: page(CompanyPage) },
              {
                path: '/employer/positions/new',
                element: page(NewPositionPage),
              },
              {
                path: '/employer/positions/:id',
                element: page(PositionDetailPage),
              },
              { path: '/employer/talent', element: page(TalentSearchPage) },
              { path: '/employer/offers', element: page(OffersBoardPage) },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
