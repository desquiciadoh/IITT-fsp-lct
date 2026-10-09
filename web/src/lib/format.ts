/** Formatting helpers: money and dates (RU locale, UTC-safe). */

export function formatMoney(value: number): string {
  return Math.round(value)
    .toLocaleString('ru-RU')
    .replace(/\u00A0/g, ' ')
}

export function formatSalaryRange(min: number, max: number, currency = '₽'): string {
  return `${formatMoney(min)} – ${formatMoney(max)} ${currency}`
}

export function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** "2 ч 15 мин" / "45 с" style duration from milliseconds. */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h} ч ${m} мин`
  if (m > 0) return `${m} мин ${s} с`
  return `${s} с`
}
