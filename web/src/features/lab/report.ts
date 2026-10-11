import type { ValidationLeakPoint, ValidationSystem, ValidationTif } from '@/api/types'

export type ConfusionCell = { row: number; col: number; value: number }

export function maxCell(matrix: number[][] | undefined): number {
  let max = 0
  for (const row of matrix ?? []) {
    for (const value of row ?? []) {
      if (Number.isFinite(value) && value > max) max = value
    }
  }
  return max
}

export function confusionCells(matrix: number[][] | undefined): ConfusionCell[] {
  const cells: ConfusionCell[] = []
  const rows = matrix ?? []
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r] ?? []
    for (let c = 0; c < row.length; c++) cells.push({ row: r, col: c, value: row[c] })
  }
  return cells
}

export function heatIntensity(value: number, max: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0
  if (!Number.isFinite(max) || max <= 0) return 0
  return Math.min(1, value / max)
}

export function tifPoints(tif: ValidationTif | undefined): { theta: number; info: number }[] {
  const theta = tif?.theta ?? []
  const info = tif?.info ?? []
  const n = Math.min(theta.length, info.length)
  const points: { theta: number; info: number }[] = []
  for (let i = 0; i < n; i++) points.push({ theta: theta[i], info: info[i] })
  return points
}

export function leakRows(leak: ValidationLeakPoint[] | undefined): ValidationLeakPoint[] {
  return [...(leak ?? [])].sort((a, b) => a.leak_share - b.leak_share)
}

export function sortSystems(systems: ValidationSystem[] | undefined): ValidationSystem[] {
  return [...(systems ?? [])].sort((a, b) => {
    if (b.ndcg10 !== a.ndcg10) return b.ndcg10 - a.ndcg10
    if (b.p10 !== a.p10) return b.p10 - a.p10
    return a.name.localeCompare(b.name)
  })
}

export function formatPercent(value: number | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

export function formatMillis(value: number | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${Math.round(value)} мс`
}

export function formatDateTime(iso: string | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('ru-RU')
}
