import { useState, useMemo } from 'react'
import { AlertTriangle, CheckCircle2, Search, SlidersHorizontal, Layers } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CardSkeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'
import { useLabFamilies } from '@/api/lab'

export function FamiliesSection() {
  const { data, isLoading, isError, refetch } = useLabFamilies()
  const [search, setSearch] = useState('')
  const [selectedSpec, setSelectedSpec] = useState<string>('all')
  const [onlyDrift, setOnlyDrift] = useState(false)

  const families = useMemo(() => data?.families ?? [], [data?.families])

  const filteredFamilies = useMemo(() => {
    return families.filter((f) => {
      if (search) {
        const q = search.toLowerCase()
        const matchesId = f.id.toLowerCase().includes(q)
        const matchesTopic = f.topic.toLowerCase().includes(q)
        if (!matchesId && !matchesTopic) return false
      }
      if (selectedSpec !== 'all' && !f.specs.includes(selectedSpec)) {
        return false
      }
      if (onlyDrift && !f.drift_flag) {
        return false
      }
      return true
    })
  }, [families, search, selectedSpec, onlyDrift])

  const driftCount = families.filter((f) => f.drift_flag).length

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <CardTitle className="text-base flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-primary" />
                Каталог параметрических семейств и мониторинг дрейфа (Item Families)
              </CardTitle>
              <CardDescription>
                Параметры 3PL IRT (дискриминативность a, сложность b, угадывание c) и детекция дрейфа сложности
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={driftCount > 0 ? 'warning' : 'success'} className="gap-1">
                {driftCount > 0 ? (
                  <>
                    <AlertTriangle className="h-3 w-3" /> Дрейф: {driftCount} семейств
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-3 w-3" /> Все семейства стабильны
                  </>
                )}
              </Badge>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-full max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Поиск по ID или теме..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 text-xs h-8"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="flex gap-1">
                {['all', 'backend', 'frontend', 'ml_data'].map((sp) => (
                  <Button
                    key={sp}
                    size="xs"
                    variant={selectedSpec === sp ? 'default' : 'outline'}
                    onClick={() => setSelectedSpec(sp)}
                  >
                    {sp === 'all' ? 'Все стеки' : sp}
                  </Button>
                ))}
              </div>

              <Button
                size="xs"
                variant={onlyDrift ? 'destructive' : 'outline'}
                onClick={() => setOnlyDrift((prev) => !prev)}
                className="gap-1"
              >
                <SlidersHorizontal className="h-3 w-3" />
                Только с дрейфом ({driftCount})
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <CardSkeleton />
          ) : isError ? (
            <ErrorState
              description="Не удалось загрузить каталог параметрических семейств."
              onRetry={() => void refetch()}
            />
          ) : filteredFamilies.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              Семейств по выбранным фильтрам не найдено.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table
                className="w-full border-collapse text-xs"
                aria-label="Таблица параметрических семейств"
              >
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="p-2.5 text-left font-semibold text-muted-foreground">ID семейства</th>
                    <th className="p-2.5 text-left font-semibold text-muted-foreground">Топик / Стек</th>
                    <th className="p-2.5 text-center font-semibold text-muted-foreground">a (дискр.)</th>
                    <th className="p-2.5 text-center font-semibold text-muted-foreground">b (сложн.)</th>
                    <th className="p-2.5 text-center font-semibold text-muted-foreground">c (угад.)</th>
                    <th className="p-2.5 text-center font-semibold text-muted-foreground">Время</th>
                    <th className="p-2.5 text-center font-semibold text-muted-foreground">Показов</th>
                    <th className="p-2.5 text-center font-semibold text-muted-foreground">Факт / Ожид</th>
                    <th className="p-2.5 text-right font-semibold text-muted-foreground">Статус</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredFamilies.map((fam) => (
                    <tr key={fam.id} className="hover:bg-muted/20 transition-colors">
                      <td className="p-2.5 font-mono text-[11px] font-semibold text-foreground">
                        {fam.id}
                      </td>
                      <td className="p-2.5">
                        <div className="font-medium text-foreground">{fam.topic}</div>
                        <div className="flex gap-1 mt-0.5">
                          {fam.specs.map((s) => (
                            <span
                              key={s}
                              className="rounded bg-muted px-1 py-0.2 text-[9px] text-muted-foreground"
                            >
                              {s}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="p-2.5 text-center tabular-nums font-semibold">
                        {fam.a.toFixed(2)}
                      </td>
                      <td className="p-2.5 text-center tabular-nums font-semibold">
                        {fam.b.toFixed(2)}
                      </td>
                      <td className="p-2.5 text-center tabular-nums text-muted-foreground">
                        {fam.c.toFixed(2)}
                      </td>
                      <td className="p-2.5 text-center tabular-nums text-muted-foreground">
                        {fam.time_limit_s} с
                      </td>
                      <td className="p-2.5 text-center tabular-nums">
                        <div className="font-semibold">{fam.exposures}</div>
                        <div className="text-[10px] text-muted-foreground">
                          {(fam.exposure_rate * 100).toFixed(1)}%
                        </div>
                      </td>
                      <td className="p-2.5 text-center tabular-nums">
                        {fam.correct_rate !== null ? (
                          <div className="text-[11px]">
                            <span className="font-semibold">{(fam.correct_rate * 100).toFixed(0)}%</span>
                            <span className="text-muted-foreground"> / {(fam.expected_p_theta0 * 100).toFixed(0)}%</span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-[10px]">нет данных</span>
                        )}
                      </td>
                      <td className="p-2.5 text-right">
                        {fam.drift_flag ? (
                          <Badge variant="danger" className="text-[10px] py-0 px-1.5 gap-0.5">
                            <AlertTriangle className="h-3 w-3" />
                            Дрейф
                          </Badge>
                        ) : (
                          <Badge variant="success" className="text-[10px] py-0 px-1.5 gap-0.5">
                            <CheckCircle2 className="h-3 w-3" />
                            OK
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
