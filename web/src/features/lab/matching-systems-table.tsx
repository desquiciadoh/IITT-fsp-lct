import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Trophy, TrendingDown, Info } from 'lucide-react'

type SystemBenchmark = {
  name: string
  ndcg10: number
  p10: number
  r50: number
  mrr: number
}

const SYSTEM_LABELS: Record<string, { title: string; desc: string }> = {
  keyword: {
    title: 'Keyword Match (Baseline)',
    desc: 'Прямое совпадение по заявленным кандидатом навыкам',
  },
  ours_no_verified: {
    title: 'Ours (No Verified / Declared only)',
    desc: 'Скорер на только заявленных данных (без верификации тестом и ФСП)',
  },
  ours: {
    title: 'FSP Draft (Full Production)',
    desc: 'Полный скорер: грейд IRT + верифицированные навыки + зарплатный фильтр',
  },
  bm25: {
    title: 'BM25 Lexical',
    desc: 'Классический лексический поиск по тексту резюме',
  },
  embeddings_only: {
    title: 'Embedding Baseline (Hashed n-gram)',
    desc: 'Семантический поиск (лексический hash-бэкенд до загрузки USER-bge-m3)',
  },
}

export function MatchingSystemsTable({ systems }: { systems: SystemBenchmark[] }) {
  const keywordSystem = systems.find((s) => s.name === 'keyword')
  const keywordNdcg = keywordSystem ? keywordSystem.ndcg10 : 0.684

  // Sort systems by ndcg10 descending to show actual ranking order
  const sortedSystems = [...systems].sort((a, b) => b.ndcg10 - a.ndcg10)

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-1.5">
              <Trophy className="h-4 w-4 text-primary" />
              Бенчмарк систем матчинга и ранжирования (Matching Benchmark)
            </CardTitle>
            <CardDescription>
              Сравнение систем на одном пуле кандидатов по скрытому оракулу истинной компетенции (truth.jsonl)
            </CardDescription>
          </div>
          <div className="text-xs text-muted-foreground">
            Целевой уровень nDCG@10 ≥ 0.800 (текущий: 0.536 — MISS)
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table
            className="w-full border-collapse text-xs"
            aria-label="Таблица бенчмарка моделей ранжирования"
          >
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="p-3 text-left font-semibold text-muted-foreground">Система</th>
                <th className="p-3 text-left font-semibold text-muted-foreground min-w-[140px]">nDCG@10</th>
                <th className="p-3 text-left font-semibold text-muted-foreground min-w-[140px]">P@10</th>
                <th className="p-3 text-center font-semibold text-muted-foreground">R@50</th>
                <th className="p-3 text-center font-semibold text-muted-foreground">MRR</th>
                <th className="p-3 text-right font-semibold text-muted-foreground">Δ к Keyword</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sortedSystems.map((sys) => {
                const isOurs = sys.name === 'ours'
                const isKeyword = sys.name === 'keyword'
                const info = SYSTEM_LABELS[sys.name] ?? { title: sys.name, desc: '' }
                const lift = sys.ndcg10 - keywordNdcg

                return (
                  <tr
                    key={sys.name}
                    className={`transition-colors ${
                      isOurs
                        ? 'bg-primary/5 font-medium'
                        : isKeyword
                          ? 'bg-muted/30 font-medium'
                          : 'hover:bg-muted/20'
                    }`}
                  >
                    <td className="p-3">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-foreground text-sm">{info.title}</span>
                        {isOurs && (
                          <Badge variant="outline" className="text-[10px] py-0 px-1.5 border-primary text-primary">
                            Наша модель
                          </Badge>
                        )}
                        {isKeyword && (
                          <Badge variant="secondary" className="text-[10px] py-0 px-1.5">
                            Лидер бенчмарка
                          </Badge>
                        )}
                      </div>
                      <div className="text-[11px] text-muted-foreground">{info.desc}</div>
                    </td>

                    <td className="p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold tabular-nums text-sm">
                          {(sys.ndcg10 * 100).toFixed(1)}%
                        </span>
                        <span className="text-[10px] text-muted-foreground tabular-nums">
                          {sys.ndcg10.toFixed(3)}
                        </span>
                      </div>
                      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(sys.ndcg10 * 100, 100)}%`,
                            backgroundColor: isKeyword ? '#520978' : isOurs ? '#ff0053' : '#8a83d1',
                          }}
                        />
                      </div>
                    </td>

                    <td className="p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold tabular-nums text-sm">
                          {(sys.p10 * 100).toFixed(1)}%
                        </span>
                        <span className="text-[10px] text-muted-foreground tabular-nums">
                          {sys.p10.toFixed(3)}
                        </span>
                      </div>
                      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(sys.p10 * 100, 100)}%`,
                            backgroundColor: isKeyword ? '#520978' : isOurs ? '#ff0053' : '#8a83d1',
                          }}
                        />
                      </div>
                    </td>

                    <td className="p-3 text-center tabular-nums text-sm font-semibold">
                      {(sys.r50 * 100).toFixed(1)}%
                    </td>

                    <td className="p-3 text-center tabular-nums text-sm font-semibold">
                      {sys.mrr.toFixed(3)}
                    </td>

                    <td className="p-3 text-right tabular-nums">
                      {isKeyword ? (
                        <span className="text-muted-foreground text-xs font-semibold">baseline (0.684)</span>
                      ) : lift < 0 ? (
                        <span className="inline-flex items-center gap-0.5 text-minus font-semibold text-xs">
                          <TrendingDown className="h-3 w-3" />
                          {(lift * 100).toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-plus font-semibold text-xs">
                          +{(lift * 100).toFixed(1)}%
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-border bg-muted/20 p-3 text-xs text-muted-foreground space-y-1">
          <div className="flex items-center gap-1 font-semibold text-foreground">
            <Info className="h-3.5 w-3.5 text-primary" />
            Почему Keyword (0.684) сейчас обгоняет многофакторный скорер (0.536)?
          </div>
          <p>
            Оракул релевантности в бенчмарке оценивает <em>только чистую компетенцию</em> (скиллы + грейд), где в синтетических резюме скиллы сгенерированы с высокой точностью (recall 85%). Скорер FSP Draft взвешивает зарплатные ожидания, свежесть и доверие к источнику, занижая кандидатов с несоответствующими ожиданиями. Платформа намеренно не оверфиттит веса под синтетический оракул, сохраняя реалистичную бизнес-логику найма.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
