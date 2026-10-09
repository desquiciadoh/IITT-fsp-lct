import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Link2, RefreshCw, ShieldAlert, X } from 'lucide-react'
import { ApiError, customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import { errorMessage } from '@/i18n/errors'
import { useMe } from '@/api/me'
import { useProfile, useSaveConsents, useSaveProfile } from '@/api/profile'
import { useCompanySearch } from '@/api/companies'
import { formatDate } from '@/lib/format'
import { PLACEMENT_TIER_LABEL, SPORTS_RANK_LABEL } from '@/lib/labels'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

/**
 * Outside DEMO_MODE the backend rejects a bare participant ID (`fsp_oidc_required`),
 * so ownership must be proven through the FSP ID OIDC flow (G15). The callback
 * returns the user to `/candidate/profile?fsp_linked=true`, which the router
 * forwards to this page (see `router.tsx`).
 */
const FSP_OIDC_LINK = '/api/auth/fsp-id/login?intent=link'
const COMPANY_MIN_QUERY = 2

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string
  description: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 rounded-lg border border-border p-4">
      <span>
        <span className="text-sm font-medium">{label}</span>
        <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
          {description}
        </span>
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 size-4 shrink-0 accent-[var(--fsp-accent)]"
      />
    </label>
  )
}

/** FE-08: candidate settings — privacy, consents, FSP. */
export function SettingsPage() {
  const client = useQueryClient()
  const { data: profile, isLoading } = useProfile()
  const { data: me } = useMe()
  const saveProfile = useSaveProfile()
  const saveConsents = useSaveConsents()
  const [searchParams, setSearchParams] = useSearchParams()
  const isDemo = Boolean(me?.demo)

  const [blindMode, setBlindMode] = useState(false)
  const [openToOffers, setOpenToOffers] = useState(true)
  const [salaryFloor, setSalaryFloor] = useState('')
  const [blocked, setBlocked] = useState<string[]>([])
  const [blockedNames, setBlockedNames] = useState<Record<string, string>>({})
  const [blockQuery, setBlockQuery] = useState('')
  const [blockQ, setBlockQ] = useState('')
  const [consents, setConsents] = useState({ processing: true, publication: true, fsp_sync: true })
  const [fspId, setFspId] = useState('')
  const [fspPending, setFspPending] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setBlockQ(blockQuery), 200)
    return () => clearTimeout(timer)
  }, [blockQuery])

  const { data: companyHits } = useCompanySearch(blockQ)

  useEffect(() => {
    if (!profile) return
    setBlindMode(Boolean(profile.blind_mode))
    setOpenToOffers(profile.open_to_offers !== false)
    setSalaryFloor(profile.salary_floor != null ? String(profile.salary_floor) : '')
    setBlocked(profile.blocked_company_ids ?? [])
    if (profile.consents) setConsents(profile.consents)
  }, [profile])

  // Outcome of the FSP ID OIDC round-trip (R26).
  useEffect(() => {
    const linked = searchParams.get('fsp_linked')
    const error = searchParams.get('fsp_error')
    if (!linked && !error) return
    if (linked === 'true') {
      toast.success('ID ФСП привязан, результаты подтянуты')
      void client.invalidateQueries({ queryKey: keys.profile })
    } else if (error) {
      toast.error(errorMessage(error))
    }
    const next = new URLSearchParams(searchParams)
    next.delete('fsp_linked')
    next.delete('fsp_error')
    setSearchParams(next, { replace: true })
  }, [searchParams, client, setSearchParams])

  const savePrivacy = () => {
    const floor = salaryFloor.trim() === '' ? null : Number(salaryFloor)
    if (floor != null && (!Number.isInteger(floor) || floor < 0)) {
      toast.error('Порог — целое число не меньше 0')
      return
    }
    saveProfile.mutate(
      { blind_mode: blindMode, open_to_offers: openToOffers, salary_floor: floor, blocked_company_ids: blocked },
      {
        onSuccess: () => toast.success('Приватность сохранена'),
        onError: (e) =>
          toast.error(e instanceof ApiError ? errorMessage(e.code, e.detail) : 'Сбой сохранения'),
      },
    )
  }

  const saveConsentSection = () => {
    const hidden = !consents.processing || !consents.publication
    if (hidden && !window.confirm('Профиль будет скрыт от работодателей. Продолжить?')) return
    saveConsents.mutate(consents, {
      onSuccess: () => toast.success('Согласия обновлены'),
      onError: (e) =>
        toast.error(e instanceof ApiError ? errorMessage(e.code, e.detail) : 'Сбой сохранения'),
    })
  }

  const linkFsp = () => {
    if (!isDemo) {
      window.location.assign(FSP_OIDC_LINK)
      return
    }
    if (!fspId.trim()) {
      toast.error('Укажите ID участника ФСП')
      return
    }
    setFspPending(true)
    customFetch<{ participant_id: string; results_count: number }>('/api/fsp/link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participant_id: fspId.trim() }),
    })
      .then(() => {
        toast.success('ID ФСП привязан, результаты подтянуты')
        setFspId('')
        void client.invalidateQueries({ queryKey: keys.profile })
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.code === 'fsp_oidc_required') {
          window.location.assign(FSP_OIDC_LINK)
        } else if (e instanceof ApiError && e.code === 'fsp_id_already_linked') {
          toast.error('Этот ID ФСП уже привязан к другому кандидату')
        } else {
          toast.error(
            e instanceof ApiError ? errorMessage(e.code, e.detail) : 'Не удалось привязать ID',
          )
        }
      })
      .finally(() => setFspPending(false))
  }

  const syncFsp = () => {
    setFspPending(true)
    customFetch<{ status: string }>('/api/fsp/sync', { method: 'POST' })
      .then(() => {
        toast.success('Результаты ФСП синхронизированы')
        void client.invalidateQueries({ queryKey: keys.profile })
      })
      .catch((e: unknown) => {
        toast.error(
          e instanceof ApiError ? errorMessage(e.code, e.detail) : 'Синхронизация не удалась',
        )
      })
      .finally(() => setFspPending(false))
  }

  if (isLoading || !profile) {
    return (
      <div className="mx-auto max-w-2xl animate-pulse space-y-4">
        <div className="h-24 rounded-xl bg-muted" />
        <div className="h-40 rounded-xl bg-muted" />
      </div>
    )
  }

  const fsp = profile.fsp

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <h1 className="text-lg font-semibold">Настройки</h1>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Приватность</h2>
        <ToggleRow
          label="Слепой режим"
          description="Скрыть от работодателей название компаний в вашем опыте до этапа интервью."
          checked={blindMode}
          onChange={setBlindMode}
        />
        <ToggleRow
          label="Открыт к предложениям"
          description="Показывать профиль в пуле талантов и принимать офферы."
          checked={openToOffers}
          onChange={setOpenToOffers}
        />
        <label className="rounded-lg border border-border p-4 text-sm">
          Минимальный порог зарплаты, ₽ (приватно)
          <input
            type="number"
            min="0"
            value={salaryFloor}
            onChange={(e) => setSalaryFloor(e.target.value)}
            placeholder="Не показывается работодателям"
            className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Не показывается работодателям — только фильтр «ниже порога не предлагать».
          </span>
        </label>
        <div className="rounded-lg border border-border p-4 text-sm">
          Заблокированные компании
          <div className="mt-2 flex flex-wrap gap-1.5">
            {blocked.length === 0 && (
              <span className="text-xs text-muted-foreground">Список пуст.</span>
            )}
            {blocked.map((id) => {
              const name = blockedNames[id]
              return (
                <span
                  key={id}
                  className="flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-xs"
                >
                  {name ?? id}
                  <button
                    type="button"
                    aria-label={`Убрать ${name ?? id} из блок-листа`}
                    onClick={() => {
                      setBlocked(blocked.filter((b) => b !== id))
                      setBlockedNames((prev) => {
                        const next = { ...prev }
                        delete next[id]
                        return next
                      })
                    }}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              )
            })}
          </div>
          <div className="mt-3">
            <label className="text-xs text-muted-foreground">
              Найти компанию по названию (реестр, `GET /api/companies`)
              <input
                type="text"
                value={blockQuery}
                onChange={(e) => setBlockQuery(e.target.value)}
                placeholder="от 2 символов, например «Яндекс»"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              />
            </label>
            {blockQuery.trim().length >= COMPANY_MIN_QUERY && (
              <ul className="mt-2 max-h-56 overflow-auto divide-y divide-border rounded-lg border border-border">
                {companyHits && companyHits.length > 0 ? (
                  companyHits.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        disabled={blocked.includes(c.id)}
                        onClick={() => {
                          setBlocked([...blocked, c.id])
                          setBlockedNames((prev) => ({ ...prev, [c.id]: c.name }))
                          setBlockQuery('')
                          setBlockQ('')
                        }}
                        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-secondary/50 disabled:text-muted-foreground"
                      >
                        {c.name}
                        {blocked.includes(c.id) && <span className="text-xs">в списке</span>}
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="px-3 py-2 text-sm text-muted-foreground">
                    {companyHits ? 'Ничего не найдено' : 'Ищем…'}
                  </li>
                )}
              </ul>
            )}
          </div>
        </div>
        <Button onClick={savePrivacy} disabled={saveProfile.isPending}>
          {saveProfile.isPending ? 'Сохраняем…' : 'Сохранить приватность'}
        </Button>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Согласия</h2>
        {(!consents.processing || !consents.publication) && (
          <p className="flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            Профиль будет скрыт от работодателей, пока согласия отозваны.
          </p>
        )}
        <ToggleRow
          label="Обработка персональных данных"
          description="152-ФЗ: сбор, анализ результатов и хранение профиля."
          checked={consents.processing}
          onChange={(v) => setConsents({ ...consents, processing: v })}
        />
        <ToggleRow
          label="Публикация профиля"
          description="Показывать профиль компаниям-работодателям (152-ФЗ, ст. 10.1)."
          checked={consents.publication}
          onChange={(v) => setConsents({ ...consents, publication: v })}
        />
        <ToggleRow
          label="Синхронизация с ФСП"
          description="Импорт спортивных результатов из ФСП."
          checked={consents.fsp_sync}
          onChange={(v) => setConsents({ ...consents, fsp_sync: v })}
        />
        <Button onClick={saveConsentSection} disabled={saveConsents.isPending}>
          {saveConsents.isPending ? 'Сохраняем…' : 'Сохранить согласия'}
        </Button>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Федерация спортивного программирования</h2>
        {fsp ? (
          <>
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-4 text-sm">
              <Link2 className="h-4 w-4" />
              <span className="font-mono">{fsp.participant_id}</span>
              <span className="rounded-md bg-secondary px-2 py-0.5 text-xs">
                {SPORTS_RANK_LABEL[fsp.sports_rank ?? ''] ?? fsp.sports_rank ?? 'ранг не указан'}
              </span>
              <span className="text-xs text-muted-foreground">синхронизация: {fsp.sync_status}</span>
              <Button
                variant="outline"
                size="sm"
                className="ml-auto"
                onClick={syncFsp}
                disabled={fspPending}
              >
                <RefreshCw className={cn('h-4 w-4', fspPending && 'animate-spin')} />
                {fspPending ? 'Синхронизируем…' : 'Синхронизировать'}
              </Button>
            </div>
            {fsp.results && fsp.results.length > 0 && (
              <ul className="divide-y divide-border rounded-lg border border-border">
                {fsp.results.map((r) => (
                  <li key={r.event_id} className="flex items-center gap-3 px-4 py-3 text-sm">
                    <span className="flex-1">{r.event_name}</span>
                    <span className="text-xs text-muted-foreground">{formatDate(r.date)}</span>
                    <span className="w-20 text-right tabular-nums">
                      {r.placement != null ? `${r.placement} место` : '—'}
                    </span>
                    <span className="w-24 text-right text-xs text-muted-foreground">
                      {r.tier ? PLACEMENT_TIER_LABEL[r.tier] ?? r.tier : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <div className="flex flex-col gap-2 rounded-lg border border-border p-4">
            {isDemo ? (
              <>
                <label className="text-sm">
                  ID участника ФСП
                  <input
                    type="text"
                    value={fspId}
                    onChange={(e) => setFspId(e.target.value)}
                    placeholder="например, FSP-000123"
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono"
                  />
                </label>
                <Button onClick={linkFsp} disabled={fspPending}>
                  {fspPending ? 'Привязываем…' : 'Привязать ID ФСП'}
                </Button>
                <span className="text-xs text-muted-foreground">
                  Демо-ID для проверки: FSP-000123 (КМС) или FSP-000456 (1 кат.).
                </span>
              </>
            ) : (
              <>
                <Button onClick={linkFsp} disabled={fspPending}>
                  <Link2 className="h-4 w-4" /> Привязать через FSP ID
                </Button>
                <span className="text-xs text-muted-foreground">
                  Подтверждение владения проходит на стороне FSP ID (OIDC).
                </span>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
