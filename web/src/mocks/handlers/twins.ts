import { http, HttpResponse } from 'msw'
import type { TestTwins, TwinItem } from '@/api/types'

/**
 * G21 / FE-14 mock: JD → blueprint → two unique instances with the same
 * difficulty profile. Items mirror `ItemView`; no answer keys anywhere.
 */

const json = (data: unknown, status = 200) =>
  HttpResponse.json(data as Record<string, unknown>, { status, headers: { 'X-Stub': 'true' } })

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code, detail },
    { status, headers: { 'Content-Type': 'application/problem+json', 'X-Stub': 'true' } },
  )

const diffs = (skill: number, grade: number, strength: number) => ({ skill, grade, strength })

function instanceItems(stem: (seq: number) => string): TwinItem[] {
  const levels = ['senior', 'senior', 'middle', 'senior', 'middle']
  const formats = ['code', 'choice', 'code', 'text', 'choice']
  const inputTypes = ['editor', 'choice', 'editor', 'text', 'choice']
  const options = ['def parse(x): …', 'O(n) / O(n log n) / O(n²)', 'между выбором и …']
  return [1, 2, 3, 4, 5].map((seq, index) => ({
    seq,
    level: levels[index],
    format: formats[index],
    stem_md: stem(seq),
    input_type: inputTypes[index],
    time_limit_s: index === 2 ? 600 : 300,
    options: inputTypes[index] === 'choice' ? options : undefined,
  }))
}

const FIXTURE: TestTwins = {
  blueprint: {
    id: 'bp-1',
    position_id: 'pos-1',
    derived_from: 'JD · Senior Backend Engineer · Acme Systems',
    requirements: [
      'Микросервисы на Python',
      'PostgreSQL под высокой нагрузкой',
      'Docker / Kubernetes',
      'Баланс нагрузки и очереди',
    ],
    target_grade: 'senior',
    difficulty: diffs(78, 72, 64),
  },
  instances: [
    {
      id: 'twin-a-1',
      status: 'ready',
      item_ids: ['it-1-1', 'it-1-2', 'it-1-3', 'it-1-4', 'it-1-5'],
      items: instanceItems((seq) =>
        [`Упростите вызов в асинхронном потоке: опишите, где возникают гонки и как их исключить.`,
          `Исправьте N+1 в пагинации списка заказов.`, `Дана схема: buses, stops, routes. Напишите индекс для «маршруты по остановке».`,
          `Масштабируйте очередь на 10× нагрузку: на что смотреть в первую очередь?`,
          `Выберите стратегию кэширования для профиля 95% чтений.`][seq - 1],
      ),
      difficulty: diffs(78, 73, 64),
    },
    {
      id: 'twin-b-1',
      status: 'ready',
      item_ids: ['it-2-1', 'it-2-2', 'it-2-3', 'it-2-4', 'it-2-5'],
      items: instanceItems((seq) =>
        [`Опишите, как пробить узкое место в worker'е, нагружающем БД.`,
          `Рефакторинг: извлеките транзакцию, которая держит блокировки при долгом расчёте.`,
          `Спроектируйте поле маршрута: индексы и партиционирование по дате.`,
          `Правильный capacity-планнинг: метрики и предупреждения.`,
          `Выберите механизм ретраев со сбоями и идемпотентностью.`][seq - 1],
      ),
      difficulty: diffs(79, 71, 65),
    },
  ],
  generated_at: new Date(Date.now() - 60_000).toISOString(),
}

export const twinsHandlers = [
  http.get('*/api/lab/twins', ({ request }) => {
    const positionId = new URL(request.url).searchParams.get('position_id')
    if (!positionId) return problem(400, 'validation_failed', 'position_id is required.')
    return json(FIXTURE)
  }),
]