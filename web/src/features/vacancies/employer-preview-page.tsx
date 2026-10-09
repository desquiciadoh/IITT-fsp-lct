import { EmployerVacancyPanel } from './components/employer-vacancy-panel'

/**
 * FE-15 dev preview: the employer panel as it will slot into FE2's position
 * page (`/employer/positions/:id`, FE-10). Replace the fixture position id
 * with the real one once FE2's page merges.
 */
export function EmployerPreviewPage() {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 p-4 py-10">
      <header className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          FE-15 · dev preview
        </span>
        <h1 className="text-xl font-bold">Панель вакансии (для страницы позиции FE2)</h1>
        <p className="text-sm text-muted-foreground">
          Демонстрация на позиции <code className="font-mono text-xs">pos-1</code>. Когда FE2 (FE-10)
          сдаст страницу позиции, этот компонент монтируется вместо превью.
        </p>
      </header>
      <EmployerVacancyPanel positionId="pos-1" />
    </main>
  )
}