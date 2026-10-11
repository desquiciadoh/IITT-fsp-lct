import { http, HttpResponse } from 'msw'
import type { ValidationReport, LabFamiliesResponse, LabTwinsResponse } from '@/api/types'

const json = (data: unknown) =>
  HttpResponse.json(data as Record<string, unknown>, {
    headers: { 'X-Stub': 'true' },
  })

export const mockValidationReport: ValidationReport = {
  generated_at: '2026-10-10T14:30:00+03:00',
  git_sha: '992c2a04',
  synthetic_fixture: false,
  assessment: {
    simulees: 10000,
    exact_acc: 0.63,
    adjacent_acc: 0.991,
    qwk: 0.7638,
    retest_same_grade: 0.545,
    retest_r: 0.765,
    median_len: 20.0,
    max_family_exposure: 1.0,
    collision_rate: 0.0003,
    generator_errors: 0,
    confusion: [
      [793, 738, 33, 0],
      [391, 2084, 948, 10],
      [11, 704, 2270, 452],
      [0, 22, 431, 1113],
    ],
    tif: {
      theta: [-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
      info: [1.4, 2.8, 5.2, 8.4, 11.2, 13.8, 14.5, 13.9, 11.6, 8.7, 5.5, 3.1, 1.6],
    },
    leak_attack: [
      { leak_share: 0.1, static_dtheta: 0.14, parametric_dtheta: 0.0 },
      { leak_share: 0.3, static_dtheta: 0.6, parametric_dtheta: 0.1 },
      { leak_share: 0.5, static_dtheta: 0.94, parametric_dtheta: 0.15 },
    ],
  },
  matching: {
    candidates: 1397,
    needs: 60,
    non_fsp_parity: 0.846,
    pool_p95_ms: 53.0,
    systems: [
      { name: 'keyword', ndcg10: 0.684, p10: 0.73, r50: 0.71, mrr: 0.78 },
      { name: 'bm25', ndcg10: 0.49, p10: 0.53, r50: 0.59, mrr: 0.59 },
      { name: 'embeddings_only', ndcg10: 0.433, p10: 0.47, r50: 0.51, mrr: 0.52 },
      { name: 'ours_no_verified', ndcg10: 0.598, p10: 0.65, r50: 0.67, mrr: 0.69 },
      { name: 'ours', ndcg10: 0.536, p10: 0.642, r50: 0.65, mrr: 0.67 },
    ],
  },
}

export const mockFamiliesResponse: LabFamiliesResponse = {
  total: 5,
  families: [
    {
      id: 'sh.ds.lru_evicted.v1',
      version: 1,
      topic: 'algorithms.data_structures',
      specs: ['backend', 'frontend'],
      skills: ['algorithms', 'data_structures'],
      format: 'code_output',
      a: 1.2,
      b: 0.8,
      c: 0.0,
      time_limit_s: 240,
      exposures: 240,
      exposure_rate: 0.24,
      correct_rate: 0.31,
      expected_p_theta0: 0.2769,
      drift_flag: false,
    },
    {
      id: 'sh.algo.complexity.v2',
      version: 2,
      topic: 'algorithms.complexity',
      specs: ['backend', 'frontend', 'ml_data'],
      skills: ['algorithms'],
      format: 'complexity',
      a: 0.9,
      b: 0.0,
      c: 0.167,
      time_limit_s: 90,
      exposures: 520,
      exposure_rate: 0.52,
      correct_rate: 0.61,
      expected_p_theta0: 0.5833,
      drift_flag: false,
    },
    {
      id: 'sh.ds.bst_depth.v1',
      version: 1,
      topic: 'algorithms.data_structures',
      specs: ['backend'],
      skills: ['algorithms'],
      format: 'code_output',
      a: 1.1,
      b: 0.5,
      c: 0.0,
      time_limit_s: 240,
      exposures: 190,
      exposure_rate: 0.19,
      correct_rate: 0.38,
      expected_p_theta0: 0.3659,
      drift_flag: false,
    },
    {
      id: 'ml.models.knn.v1',
      version: 1,
      topic: 'ml.models',
      specs: ['ml_data'],
      skills: ['machine_learning', 'scikit_learn'],
      format: 'numeric_scenario',
      a: 1.1,
      b: -0.3,
      c: 0.0,
      time_limit_s: 150,
      exposures: 85,
      exposure_rate: 0.085,
      correct_rate: 0.59,
      expected_p_theta0: 0.5818,
      drift_flag: false,
    },
    {
      id: 'sh.code.find_bug.v1',
      version: 1,
      topic: 'algorithms.code_reading',
      specs: ['backend', 'frontend'],
      skills: ['python', 'debugging'],
      format: 'find_bug',
      a: 1.1,
      b: -0.5,
      c: 0.2,
      time_limit_s: 120,
      exposures: 310,
      exposure_rate: 0.31,
      correct_rate: 0.15,
      expected_p_theta0: 0.7073,
      drift_flag: true,
    },
  ],
}

export const mockTwinsResponse: LabTwinsResponse = {
  specialization: 'backend',
  grade: 'middle',
  twins: [
    {
      family_id: 'sh.ds.lru_evicted.v1',
      topic: 'algorithms.data_structures',
      level: 'middle',
      b: 0.8,
      time_limit_s: 240,
      instance_a: {
        stem_md: 'Что напечатает программа?\n\nОтвет — целое число.',
        input: 'number',
        code: {
          lang: 'python',
          text: `from collections import OrderedDict

cache = OrderedDict()
evicted = 0
for k in [2, 4, 2, 7, 3, 7, 3, 6, 9, 2, 4, 5, 4, 9]:
    if k in cache:
        cache.move_to_end(k)
        continue
    if len(cache) == 2:
        old, _ = cache.popitem(last=False)
        evicted += old
    cache[k] = True
print(evicted)`,
        },
        options: null,
      },
      instance_b: {
        stem_md: 'Что напечатает программа?\n\nОтвет — целое число.',
        input: 'number',
        code: {
          lang: 'python',
          text: `from collections import OrderedDict

cache = OrderedDict()
evicted = 0
for k in [9, 2, 4, 5, 3, 9, 5, 3, 7, 9]:
    if k in cache:
        cache.move_to_end(k)
        continue
    if len(cache) == 3:
        old, _ = cache.popitem(last=False)
        evicted += old
    cache[k] = True
print(evicted)`,
        },
        options: null,
      },
    },
    {
      family_id: 'sh.ds.op_cost.v1',
      topic: 'algorithms.data_structures',
      level: 'junior',
      b: -0.3,
      time_limit_s: 60,
      instance_a: {
        stem_md: '`store` — список из n = 8 540 000 товаров. Какова средняя (амортизированная) сложность одной операции?',
        input: 'choice',
        code: {
          lang: 'python',
          text: 'min(store)',
        },
        options: [
          { id: 'o1', text_md: 'Θ(n)' },
          { id: 'o2', text_md: 'Θ(n log n)' },
          { id: 'o3', text_md: 'Θ(log n)' },
          { id: 'o4', text_md: 'Θ(1)' },
        ],
      },
      instance_b: {
        stem_md: '`rows` — deque из n = 6 611 000 задач. Какова средняя (амортизированная) сложность одной операции?',
        input: 'choice',
        code: {
          lang: 'python',
          text: 'rows.appendleft(x)',
        },
        options: [
          { id: 'o1', text_md: 'Θ(1)' },
          { id: 'o2', text_md: 'Θ(n)' },
          { id: 'o3', text_md: 'Θ(log n)' },
          { id: 'o4', text_md: 'Θ(n log n)' },
        ],
      },
    },
  ],
}

export const labHandlers = [
  http.get('*/api/lab/report', () => json(mockValidationReport)),
  http.get('*/api/lab/families', () => json(mockFamiliesResponse)),
  http.get('*/api/lab/twins', ({ request }) => {
    const url = new URL(request.url)
    const spec = url.searchParams.get('specialization') ?? 'backend'
    const grade = url.searchParams.get('grade') ?? 'middle'
    return json({
      ...mockTwinsResponse,
      specialization: spec,
      grade,
    })
  }),
]
