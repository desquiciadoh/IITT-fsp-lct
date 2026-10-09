import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** Centered shell for login / register / verify screens. */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm space-y-4">
        <div className="text-center">
          <Link to="/" className="text-xl font-semibold text-foreground">
            ФСП<span className="text-primary">·</span>Практикум
          </Link>
        </div>
        <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h1 className="text-lg font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          <div className="mt-5">{children}</div>
        </div>
        {footer && <div className="text-center text-sm text-muted-foreground">{footer}</div>}
      </div>
    </div>
  )
}
