import { describe, expect, it } from 'vitest'
import {
  fieldErrorsFromError,
  parsePositionForm,
  toPositionInput,
  type PositionFormValues,
} from './position-schema'

const BASE: PositionFormValues = {
  title: 'Python-разработчик',
  specialization: 'backend',
  grades: ['middle'],
  must_skills: ['python'],
  nice_skills: ['redis'],
  work_formats: ['remote'],
  location: 'Москва',
  salary_min: 220000,
  salary_max: 320000,
  salary_type: 'gross',
  team_context: '',
  description: '',
  allow_adjacent: false,
  is_public: true,
}

const form = (patch: Partial<PositionFormValues>) => parsePositionForm({ ...BASE, ...patch })

describe('FE-09 stage 2 — positionSchema (B15 client-side gates)', () => {
  it('accepts a fully valid wizard payload', () => {
    const r = form({})
    expect(r.success).toBe(true)
  })

  it('rejects salary_min = 0 with a Russian message (BE.md B15: backend 500s on this)', () => {
    const r = form({ salary_min: 0 })
    expect(r.success).toBe(false)
    if (!r.success) {
      expect(fieldErrorsFromError(r.error).salary_min).toMatch(/больше нуля/)
    }
  })

  it('rejects an empty salary_min before submit', () => {
    const r = form({ salary_min: '' as unknown as number })
    expect(r.success).toBe(false)
    if (!r.success) expect(fieldErrorsFromError(r.error).salary_min).toBeDefined()
  })

  it('rejects salary_max < salary_min', () => {
    const r = form({ salary_min: 300000, salary_max: 250000 })
    expect(r.success).toBe(false)
    if (!r.success) {
      expect(fieldErrorsFromError(r.error).salary_max).toMatch(/меньше/)
    }
  })

  it('requires an explicit gross/net choice — no default (TK transparency)', () => {
    const r = form({ salary_type: undefined as unknown as PositionFormValues['salary_type'] })
    expect(r.success).toBe(false)
    if (!r.success) {
      expect(fieldErrorsFromError(r.error).salary_type).toMatch(/выберите/i)
    }
  })

  it('rejects fractional salaries (RUB/month integers)', () => {
    const r = form({ salary_min: 220000.5 })
    expect(r.success).toBe(false)
  })

  it('requires at least one grade', () => {
    const r = form({ grades: [] })
    expect(r.success).toBe(false)
    if (!r.success) expect(fieldErrorsFromError(r.error).grades).toMatch(/грейд/)
  })

  it('forbids the same skill in must and nice lists', () => {
    const r = form({ must_skills: ['python'], nice_skills: ['python'] })
    expect(r.success).toBe(false)
    if (!r.success) expect(fieldErrorsFromError(r.error).nice_skills).toMatch(/одновременно/)
  })

  it('rejects an empty title', () => {
    const r = form({ title: '   ' })
    expect(r.success).toBe(false)
  })

  it('toPositionInput trims, drops empties and keeps salary fields', () => {
    const r = form({ title: '  Go-разработчик ', location: '', team_context: '  ' })
    if (!r.success) throw new Error('expected valid')
    const body = toPositionInput(r.data)
    expect(body.title).toBe('Go-разработчик')
    expect(body.location).toBeUndefined()
    expect(body.team_context).toBeUndefined()
    expect(body.salary_min).toBe(220000)
    expect(body.salary_max).toBe(320000)
    expect(body.salary_type).toBe('gross')
    // skills are lowercased by the editor; input pass-through keeps them clean
    expect(body.must_skills).toEqual(['python'])
  })
})
