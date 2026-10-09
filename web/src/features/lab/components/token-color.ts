const CACHE = new Map<string, string>()

/**
 * FE-13: chart colours must come from `tokens.css`. Recharts needs concrete
 * colour strings (CSS variables don't resolve inside SVG attributes), so the
 * token value is read once and memoized.
 */
export function tokenColor(name: string, fallback: string): string {
  const cached = CACHE.get(name)
  if (cached) return cached
  const value =
    typeof window === 'undefined'
      ? ''
      : getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const resolved = value || fallback
  CACHE.set(name, resolved)
  return resolved
}