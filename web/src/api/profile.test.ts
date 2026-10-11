import { describe, it, expect } from 'vitest'
import { normalizeTaxonomy } from './profile'

describe('normalizeTaxonomy', () => {
  it('normalizes backend objects for grades, specializations, and skills into plain string arrays', () => {
    const backendData = {
      specializations: [
        { id: 'backend', name: 'Backend', name_ru: 'Backend', topics: ['algorithms'] },
        { id: 'frontend', name: 'Frontend', name_ru: 'Frontend', topics: ['react'] },
      ],
      grades: [
        {
          id: 'intern',
          name: 'Стажёр',
          name_ru: 'Стажёр',
          descriptor: 'Базовые навыки',
          descriptor_ru: 'Базовые навыки',
          theta_cut: -2.0,
          rating_cut: 600,
        },
        {
          id: 'junior',
          name: 'Junior',
          name_ru: 'Junior',
          descriptor: 'Типовые задачи',
          descriptor_ru: 'Типовые задачи',
          theta_cut: -1.0,
          rating_cut: 800,
        },
        {
          id: 'middle',
          name: 'Middle',
          name_ru: 'Middle',
          descriptor: 'Ведёт фичу',
          descriptor_ru: 'Ведёт фичу',
          theta_cut: 0.0,
          rating_cut: 1000,
        },
        {
          id: 'senior',
          name: 'Senior',
          name_ru: 'Senior',
          descriptor: 'Архитектура',
          descriptor_ru: 'Архитектура',
          theta_cut: 1.0,
          rating_cut: 1200,
        },
      ],
      skills: [
        { id: 'python', name: 'Python', aliases: [], topic: 'backend' },
        { id: 'django', name: 'Django', aliases: [], topic: 'backend' },
      ],
      topics: [{ id: 'algorithms', name_ru: 'Алгоритмы', specs: ['backend'], skills: ['python'] }],
    }

    const normalized = normalizeTaxonomy(backendData)

    expect(normalized.grades).toEqual(['intern', 'junior', 'middle', 'senior'])
    expect(normalized.specs).toEqual(['backend', 'frontend'])
    expect(normalized.skills).toEqual(['Python', 'Django'])
    expect(normalized.work_formats).toEqual(['office', 'hybrid', 'remote'])
    expect(normalized.grade_details).toHaveLength(4)
    expect(normalized.grade_details?.[0].rating_cut).toBe(600)
  })

  it('handles already-string arrays seamlessly (e.g. from mocks or legacy responses)', () => {
    const mockData = {
      specs: ['backend', 'frontend', 'ml_data'],
      grades: ['intern', 'junior', 'middle', 'senior'],
      work_formats: ['office', 'hybrid', 'remote'],
      skills: ['python', 'typescript'],
      strength_topics: ['architecture'],
    }

    const normalized = normalizeTaxonomy(mockData)

    expect(normalized.grades).toEqual(['intern', 'junior', 'middle', 'senior'])
    expect(normalized.specs).toEqual(['backend', 'frontend', 'ml_data'])
    expect(normalized.skills).toEqual(['python', 'typescript'])
    expect(normalized.work_formats).toEqual(['office', 'hybrid', 'remote'])
    expect(normalized.strength_topics).toEqual(['architecture'])
  })

  it('provides safe fallbacks for empty or null payload', () => {
    const normalized = normalizeTaxonomy(null)

    expect(normalized.grades).toEqual(['intern', 'junior', 'middle', 'senior'])
    expect(normalized.specs).toEqual(['backend', 'frontend', 'ml_data'])
    expect(normalized.work_formats).toEqual(['office', 'hybrid', 'remote'])
    expect(normalized.skills).toEqual([])
  })
})
