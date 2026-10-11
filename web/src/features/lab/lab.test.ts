import { describe, expect, it } from 'vitest'
import {
  mockValidationReport,
  mockFamiliesResponse,
  mockTwinsResponse,
} from '@/mocks/handlers/lab'

describe('ValidationReport data integrity (ML.md / commit 992c2a04)', () => {
  it('contains the real measured metrics with 10 misses out of 15', () => {
    expect(mockValidationReport.git_sha).toBe('992c2a04')
    expect(mockValidationReport.generated_at).toBeTruthy()
    expect(mockValidationReport.synthetic_fixture).toBe(false)

    const { assessment, matching } = mockValidationReport

    // Real measured values matching ML.md §4 (ML-8)
    expect(assessment.exact_acc).toBe(0.63) // MISS (target >= 0.80)
    expect(assessment.adjacent_acc).toBe(0.991) // PASS (target >= 0.98)
    expect(assessment.qwk).toBe(0.7638) // MISS (target >= 0.80)
    expect(assessment.retest_same_grade).toBe(0.545) // MISS (target >= 0.80)
    expect(assessment.retest_r).toBe(0.765) // MISS (target >= 0.85)
    expect(assessment.median_len).toBe(20.0) // MISS (target <= 14)
    expect(assessment.max_family_exposure).toBe(1.0) // MISS (target <= 0.5)
    expect(assessment.collision_rate).toBe(0.0003) // PASS (target <= 0.001)
    expect(assessment.generator_errors).toBe(0) // PASS (target == 0)

    expect(matching.non_fsp_parity).toBe(0.846) // PASS (target >= 0.80)
    expect(matching.pool_p95_ms).toBe(53.0) // PASS (target < 300 ms)
  })

  it('confusion matrix is 4x4 non-negative counts matching ML-8 golden run', () => {
    const { confusion } = mockValidationReport.assessment
    expect(confusion.length).toBe(4)
    expect(confusion[0]).toEqual([793, 738, 33, 0])
    expect(confusion[1]).toEqual([391, 2084, 948, 10])
    expect(confusion[2]).toEqual([11, 704, 2270, 452])
    expect(confusion[3]).toEqual([0, 22, 431, 1113])
  })

  it('TIF theta and info arrays match in length', () => {
    const { tif } = mockValidationReport.assessment
    expect(tif.theta.length).toBeGreaterThan(0)
    expect(tif.theta.length).toBe(tif.info.length)
  })

  it('leak attack demonstrates parametric stability over static collapse', () => {
    const { leak_attack } = mockValidationReport.assessment
    expect(leak_attack).toEqual([
      { leak_share: 0.1, static_dtheta: 0.14, parametric_dtheta: 0.0 },
      { leak_share: 0.3, static_dtheta: 0.6, parametric_dtheta: 0.1 },
      { leak_share: 0.5, static_dtheta: 0.94, parametric_dtheta: 0.15 },
    ])
    // At 50% leak: static +0.94 vs parametric +0.15
    expect(leak_attack[2].static_dtheta).toBe(0.94)
    expect(leak_attack[2].parametric_dtheta).toBe(0.15)
  })

  it('matching systems: keyword baseline (0.684) beats our multi-objective scorer (0.536)', () => {
    const { systems } = mockValidationReport.matching
    const ours = systems.find((s) => s.name === 'ours')
    const keyword = systems.find((s) => s.name === 'keyword')
    const ablated = systems.find((s) => s.name === 'ours_no_verified')

    expect(ours).toBeDefined()
    expect(keyword).toBeDefined()
    expect(ablated).toBeDefined()

    expect(keyword!.ndcg10).toBe(0.684)
    expect(ours!.ndcg10).toBe(0.536)
    expect(ablated!.ndcg10).toBe(0.598)

    // Honest reporting: keyword beats ours in this synthetic world
    expect(keyword!.ndcg10).toBeGreaterThan(ours!.ndcg10)
    expect(ablated!.ndcg10).toBeGreaterThan(ours!.ndcg10)
  })
})

describe('Test Twins integrity (FE-14)', () => {
  it('never leaks answer key or oracle in any twin instance', () => {
    for (const twin of mockTwinsResponse.twins) {
      expect(twin.instance_a).not.toHaveProperty('key')
      expect(twin.instance_b).not.toHaveProperty('key')
      expect(twin.instance_a).not.toHaveProperty('oracle')
      expect(twin.instance_b).not.toHaveProperty('oracle')
      expect(twin.instance_a).not.toHaveProperty('fingerprint')
      expect(twin.instance_b).not.toHaveProperty('fingerprint')
    }
  })

  it('twin instances have matched difficulty parameter b', () => {
    for (const twin of mockTwinsResponse.twins) {
      expect(typeof twin.b).toBe('number')
      expect(typeof twin.time_limit_s).toBe('number')
      expect(twin.instance_a.stem_md).toBeTruthy()
      expect(twin.instance_b.stem_md).toBeTruthy()
    }
  })
})

describe('Parametric Families catalog (BE-22)', () => {
  it('contains expected item family metadata and flags drift', () => {
    expect(mockFamiliesResponse.families.length).toBeGreaterThan(0)
    const driftFamily = mockFamiliesResponse.families.find((f) => f.drift_flag)
    expect(driftFamily).toBeDefined()
    expect(driftFamily?.drift_flag).toBe(true)

    const normalFamily = mockFamiliesResponse.families.find((f) => !f.drift_flag)
    expect(normalFamily).toBeDefined()
    expect(normalFamily?.drift_flag).toBe(false)
  })
})
