import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMe } from '@/api/me'
import { useLiveEvents } from '@/api/events'
import { customFetch } from '@/api/client'
import { RU } from '@/i18n/ru'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'rounded-md px-3 py-1.5 text-sm transition-colors',
    isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
  ].join(' ')

export function AppLayout() {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const client = useQueryClient()
  useLiveEvents()

  const logout = useMutation({
    mutationFn: () => customFetch<void>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['me'] })
      navigate('/login', { replace: true })
    },
  })

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-4 px-4 py-3">
          <NavLink to="/" className="font-semibold tracking-tight">
            ФСП<span className="text-primary">·</span>Практикум
          </NavLink>
          <nav className="flex flex-1 items-center gap-1">
            {me?.role === 'candidate' && (
              <>
                <NavLink to="/candidate" className={linkClass} end>
                  {RU.nav.dashboard}
                </NavLink>
                <NavLink to="/candidate/offers" className={linkClass}>
                  {RU.nav.offers}
                </NavLink>
                <NavLink to="/candidate/settings" className={linkClass}>
                  {RU.nav.settings}
                </NavLink>
              </>
            )}
            {me?.role === 'employer' && (
              <>
                <NavLink to="/employer" className={linkClass} end>
                  {RU.nav.dashboard}
                </NavLink>
                <NavLink to="/employer/talent" className={linkClass}>
                  {RU.nav.talent}
                </NavLink>
                <NavLink to="/employer/offers" className={linkClass}>
                  {RU.nav.offers}
                </NavLink>
                <NavLink to="/lab" className={linkClass}>
                  Лаб
                </NavLink>
              </>
            )}
            <NavLink to="/jury" className={linkClass}>
              {RU.nav.jury}
            </NavLink>
          </nav>
          {me && (
            <div className="flex items-center gap-2">
              <Badge variant="outline">{me.role}</Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
              >
                {RU.nav.logout}
              </Button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
