export function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-4 p-8">
      <h1 className="text-3xl font-bold">FSP Draft</h1>
      <p className="text-muted-foreground">
        React-SPA в разработке. Роуты появятся по мере готовности фич.
      </p>
      <nav className="flex flex-col gap-2">
        <a className="underline" href="/dev/design">
          /dev/design — дизайн-направления
        </a>
        <a className="underline" href="/dev/ui">
          /dev/ui — UI-кит
        </a>
        <a className="underline" href="/api/docs/">
          /api/docs/ — Swagger бэкенда
        </a>
      </nav>
    </main>
  )
}
