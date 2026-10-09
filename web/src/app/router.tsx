import { lazy } from 'react'
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom'
import { AppLayout } from '@/app/layouts/app-layout'
import { RequireAuth, RequireRole, OnboardingGate } from '@/app/guards'
import { IndexRedirect } from '@/app/index-redirect'
import { Placeholder } from '@/app/placeholder'

// R30: pages are code-split; each route chunk loads lazily so the main
// bundle stays under (was 899 KB before the split).
const HomePage = lazy(() => import('@/pages/home').then((m) => ({ default: m.HomePage })))
const DevUiPage = lazy(() => import('@/pages/dev-ui').then((m) => ({ default: m.DevUiPage })))
const DesignVariantsPage = lazy(() =>
  import('@/pages/design-variants').then((m) => ({ default: m.DesignVariantsPage })),
)
const LoginPage = lazy(() =>
  import('@/features/auth/login-page').then((m) => ({ default: m.LoginPage })),
)
const RegisterPage = lazy(() =>
  import('@/features/auth/register-page').then((m) => ({ default: m.RegisterPage })),
)
const VerifyPage = lazy(() =>
  import('@/features/auth/verify-page').then((m) => ({ default: m.VerifyPage })),
)
const JuryPage = lazy(() =>
  import('@/features/jury/jury-page').then((m) => ({ default: m.JuryPage })),
)
const OnboardingPage = lazy(() =>
  import('@/features/onboarding/onboarding-page').then((m) => ({ default: m.OnboardingPage })),
)
const ResultPage = lazy(() =>
  import('@/features/result/result-page').then((m) => ({ default: m.ResultPage })),
)
const DashboardPage = lazy(() =>
  import('@/features/candidate/dashboard-page').then((m) => ({ default: m.DashboardPage })),
)
const OffersListPage = lazy(() =>
  import('@/features/offers/offers-list-page').then((m) => ({ default: m.OffersListPage })),
)
const OfferDetailPage = lazy(() =>
  import('@/features/offers/offer-detail-page').then((m) => ({ default: m.OfferDetailPage })),
)
const SettingsPage = lazy(() =>
  import('@/features/settings/settings-page').then((m) => ({ default: m.SettingsPage })),
)

const ph = (title: string, owner: 'FE1' | 'FE2', task: string) => (
  <Placeholder title={title} owner={owner} task={task} />
)

/**
 * The FSP ID OIDC callback (R26) returns the user to `/candidate/profile?fsp_linked=true`;
 * the FSP section lives on settings, so forward there and keep the query.
 */
function ProfileToSettings() {
  const { search } = useLocation()
  return <Navigate to={`/candidate/settings${search}`} replace />
}

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
                element: <OnboardingPage />,
              },
              {
                element: <OnboardingGate />,
                children: [
                  { path: '/candidate', element: <DashboardPage /> },
                  {
                    path: '/candidate/qualification/start',
                    element: ph('Вход в тест', 'FE2', 'FE-05'),
                  },
                  {
                    path: '/candidate/qualification/:id',
                    element: ph('Тест-раннер', 'FE2', 'FE-05'),
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
                  { path: '/candidate/profile', element: <ProfileToSettings /> },
                ],
              },
            ],
          },
          {
            element: <RequireRole role="employer" />,
            children: [
              { path: '/employer', element: ph('Кабинет работодателя', 'FE2', 'FE-09') },
              { path: '/employer/company', element: ph('Профиль компании', 'FE2', 'FE-09') },
              {
                path: '/employer/positions/new',
                element: ph('Новая вакансия', 'FE2', 'FE-09'),
              },
              {
                path: '/employer/positions/:id',
                element: ph('Вакансия (детально)', 'FE2', 'FE-10'),
              },
              { path: '/employer/talent', element: ph('Пул талантов', 'FE2', 'FE-12') },
              { path: '/employer/offers', element: ph('Офферы работодателя', 'FE2', 'FE-11') },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
