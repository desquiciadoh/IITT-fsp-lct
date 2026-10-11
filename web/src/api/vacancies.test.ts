import { describe, expect, it } from 'vitest'
import { vacancyFiltersToParams } from '@/api/vacancies'

describe('vacancyFiltersToParams', () => {
  it('omits empty/default values', () => {
    expect(vacancyFiltersToParams({}).toString()).toBe('')
    expect(vacancyFiltersToParams({ specialization: '', search: '  ', page: 1 }).toString()).toBe('')
  })

  it('serializes lists and trims search', () => {
    const params = vacancyFiltersToParams({
      specialization: 'backend',
      grades: ['middle', 'senior'],
      work_formats: ['remote'],
      search: '  python  ',
      page: 2,
    })
    expect(params.get('specialization')).toBe('backend')
    expect(params.get('grades')).toBe('middle,senior')
    expect(params.get('work_formats')).toBe('remote')
    expect(params.get('search')).toBe('python')
    expect(params.get('page')).toBe('2')
  })
})
