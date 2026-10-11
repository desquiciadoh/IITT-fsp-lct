import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom'
import { HomePage } from '@/pages/home'
import { LoginPage } from '@/features/auth/login-page'
import { RegisterPage } from '@/features/auth/register-page'
import { VerifyPage } from '@/features/auth/verify-page'
import { AppLayout } from '@/app/layouts/app-layout'
import { RequireAuth, RequireRole, OnboardingGate } from '@/app/guards'
import { IndexRedirect } from '@/app/index-redirect'
import { CardSkeleton } from '@/components/ui/skeleton'

// R30 · Code-split route pages so the entry chunk stays small (Recharts,
// react-markdown, the settings/talent screens, etc. ride in their own chunks).
function RouteFallback() {
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-10">
      <CardSkeleton />
    </div>
  )
}

function page(factory: () => Promise<{ default: ComponentType }>): ReactNode {
  const Lazy = lazy(factory)
  return (
    <Suspense fallback={<RouteFallback />}>
      <Lazy />
    </Suspense>
  )
}

const JuryPage = () => import('@/features/jury/jury-page').then((m) => ({ default: m.JuryPage }))
const LabPage = () => import('@/features/lab/lab-page').then((m) => ({ default: m.LabPage }))
const DevUiPage = () => import('@/pages/dev-ui').then((m) => ({ default: m.DevUiPage }))
const DesignVariantsPage = () =>
  import('@/pages/design-variants').then((m) => ({ default: m.DesignVariantsPage }))
const OnboardingPage = () =>
  import('@/features/onboarding/onboarding-page').then((m) => ({ default: m.OnboardingPage }))
const ResultPage = () =>
  import('@/features/result/result-page').then((m) => ({ default: m.ResultPage }))
const DashboardPage = () =>
  import('@/features/candidate/dashboard-page').then((m) => ({ default: m.DashboardPage }))
const StartPage = () =>
  import('@/features/qualification-runner/start-page').then((m) => ({ default: m.StartPage }))
const TestRunnerPage = () =>
  import('@/features/qualification-runner/test-runner-page').then((m) => ({
    default: m.TestRunnerPage,
  }))
const OffersListPage = () =>
  import('@/features/offers/offers-list-page').then((m) => ({ default: m.OffersListPage }))
const OfferDetailPage = () =>
  import('@/features/offers/offer-detail-page').then((m) => ({ default: m.OfferDetailPage }))
const EmployerDashboardPage = () =>
  import('@/features/employer/dashboard-page').then((m) => ({ default: m.EmployerDashboardPage }))
const CompanyPage = () =>
  import('@/features/employer/company-page').then((m) => ({ default: m.CompanyPage }))
const NewPositionPage = () =>
  import('@/features/employer/new-position-page').then((m) => ({ default: m.NewPositionPage }))
const PositionDetailPage = () =>
  import('@/features/employer/position-detail-page').then((m) => ({ default: m.PositionDetailPage }))
const OffersBoardPage = () =>
  import('@/features/employer/offers-board-page').then((m) => ({ default: m.OffersBoardPage }))
const TalentSearchPage = () =>
  import('@/features/talent/talent-search-page').then((m) => ({ default: m.TalentSearchPage }))
const CandidateVacanciesPage = () =>
  import('@/features/vacancies/candidate-vacancies-page').then((m) => ({
    default: m.CandidateVacanciesPage,
  }))
const TasksInboxPage = () =>
  import('@/features/microtasks/tasks-inbox-page').then((m) => ({ default: m.TasksInboxPage }))
const TaskSolvePage = () =>
  import('@/features/microtasks/task-solve-page').then((m) => ({ default: m.TaskSolvePage }))
const EmployerTasksPage = () =>
  import('@/features/microtasks/employer-tasks-page').then((m) => ({ default: m.EmployerTasksPage }))
const TaskCreatePage = () =>
  import('@/features/microtasks/task-create-page').then((m) => ({ default: m.TaskCreatePage }))
const TaskReviewPage = () =>
  import('@/features/microtasks/task-review-page').then((m) => ({ default: m.TaskReviewPage }))
const SettingsPage = () =>
  import('@/features/settings/settings-page').then((m) => ({ default: m.SettingsPage }))

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
      { path: '/lab', element: page(LabPage) },
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
              { path: '/candidate/onboarding/:step', element: page(OnboardingPage) },
              {
                element: <OnboardingGate />,
                children: [
                  { path: '/candidate', element: page(DashboardPage) },
                  { path: '/candidate/profile', element: <CandidateProfileRedirect /> },
                  { path: '/candidate/qualification/start', element: page(StartPage) },
                  { path: '/candidate/qualification/:id', element: page(TestRunnerPage) },
                  {
                    path: '/candidate/qualification/:id/result',
                    element: page(ResultPage),
                  },
                  { path: '/candidate/offers', element: page(OffersListPage) },
                  { path: '/candidate/offers/:id', element: page(OfferDetailPage) },
                  { path: '/candidate/vacancies', element: page(CandidateVacanciesPage) },
                  { path: '/candidate/micro-tasks', element: page(TasksInboxPage) },
                  { path: '/candidate/micro-tasks/:dropId', element: page(TaskSolvePage) },
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
              { path: '/employer/positions/new', element: page(NewPositionPage) },
              { path: '/employer/positions/:id', element: page(PositionDetailPage) },
              { path: '/employer/talent', element: page(TalentSearchPage) },
              { path: '/employer/offers', element: page(OffersBoardPage) },
              { path: '/employer/micro-tasks', element: page(EmployerTasksPage) },
              { path: '/employer/micro-tasks/new', element: page(TaskCreatePage) },
              { path: '/employer/micro-tasks/:id', element: page(TaskReviewPage) },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
