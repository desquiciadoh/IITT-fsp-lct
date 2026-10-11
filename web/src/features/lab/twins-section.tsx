import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { RefreshCw, Code2, Clock, Split, ShieldCheck } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CardSkeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/domain/states'
import { useLabTwins } from '@/api/lab'
import type { LabTwin, LabTwinInstance } from '@/api/types'

const SPECS = [
  { value: 'backend', label: 'Backend' },
  { value: 'frontend', label: 'Frontend' },
  { value: 'ml_data', label: 'ML & Data' },
]

const GRADES = [
  { value: 'intern', label: 'Intern' },
  { value: 'junior', label: 'Junior' },
  { value: 'middle', label: 'Middle' },
  { value: 'senior', label: 'Senior' },
]

function InstanceCard({
  label,
  instance,
  timeLimit,
}: {
  label: 'Вариант А (Instance A)' | 'Вариант Б (Instance B)'
  instance: LabTwinInstance
  timeLimit: number
}) {
  return (
    <div className="flex-1 rounded-lg border border-border bg-card p-4 flex flex-col justify-between">
      <div className="space-y-3">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <span className="font-semibold text-sm text-heading">{label}</span>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {timeLimit} сек
          </span>
        </div>

        <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed">
          <ReactMarkdown>{instance.stem_md}</ReactMarkdown>
        </div>

        {instance.code && (
          <div className="overflow-hidden rounded-md border border-border bg-muted/40">
            <div className="flex items-center justify-between border-b border-border bg-muted/60 px-2.5 py-1 text-[10px] text-muted-foreground font-mono">
              <span className="flex items-center gap-1">
                <Code2 className="h-3 w-3" />
                {instance.code.lang || 'code'}
              </span>
            </div>
            <pre className="overflow-x-auto p-3 text-[11px] font-mono leading-snug">
              <code>{instance.code.text}</code>
            </pre>
          </div>
        )}

        {instance.options && instance.options.length > 0 && (
          <div className="space-y-1.5 pt-1">
            <div className="text-[11px] font-medium text-muted-foreground">Варианты ответа:</div>
            <div className="grid gap-1.5">
              {instance.options.map((opt) => (
                <div
                  key={opt.id}
                  className="rounded border border-border/80 bg-background/50 px-2.5 py-1.5 text-xs text-foreground"
                >
                  <ReactMarkdown>{opt.text_md || opt.text || ''}</ReactMarkdown>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 pt-2 border-t border-border flex items-center justify-between text-[10px] text-muted-foreground">
        <span>Ввод: {instance.input ?? 'choice'}</span>
        <span className="inline-flex items-center gap-1 text-plus">
          <ShieldCheck className="h-3 w-3" />
          Ответ скрыт сервером
        </span>
      </div>
    </div>
  )
}

function TwinRow({ twin }: { twin: LabTwin }) {
  return (
    <Card className="overflow-hidden border-border">
      <CardHeader className="bg-muted/30 pb-3 border-b border-border">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono text-[10px]">
              {twin.family_id}
            </Badge>
            <span className="text-xs font-medium text-muted-foreground">{twin.topic}</span>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <Badge variant="secondary" className="capitalize text-[10px]">
              Грейд: {twin.level}
            </Badge>
            <span className="text-xs font-semibold tabular-nums text-heading">
              Сложность b: {twin.b.toFixed(2)}
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-4">
        <div className="flex flex-col gap-4 lg:flex-row">
          <InstanceCard
            label="Вариант А (Instance A)"
            instance={twin.instance_a}
            timeLimit={twin.time_limit_s}
          />
          <InstanceCard
            label="Вариант Б (Instance B)"
            instance={twin.instance_b}
            timeLimit={twin.time_limit_s}
          />
        </div>
      </CardContent>
    </Card>
  )
}

export function TwinsSection() {
  const [specialization, setSpecialization] = useState('backend')
  const [grade, setGrade] = useState('middle')

  const { data, isLoading, isError, refetch, isFetching } = useLabTwins({
    specialization,
    grade,
  })

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <CardTitle className="text-base flex items-center gap-1.5">
                <Split className="h-4 w-4 text-primary" />
                Генератор тестов-близнецов (Test Twins & Blueprint Builder)
              </CardTitle>
              <CardDescription>
                Параллельная генерация уникальных вариантов заданий из одного параметрического семейства с одинаковой сложностью b и кривой TIF
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void refetch()}
              disabled={isFetching}
              className="gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              Сгенерировать другие сиды
            </Button>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground font-medium">Специализация:</span>
              <div className="flex gap-1">
                {SPECS.map((s) => (
                  <Button
                    key={s.value}
                    size="xs"
                    variant={specialization === s.value ? 'default' : 'outline'}
                    onClick={() => setSpecialization(s.value)}
                  >
                    {s.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground font-medium">Грейд:</span>
              <div className="flex gap-1">
                {GRADES.map((g) => (
                  <Button
                    key={g.value}
                    size="xs"
                    variant={grade === g.value ? 'default' : 'outline'}
                    onClick={() => setGrade(g.value)}
                  >
                    {g.label}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </CardHeader>
      </Card>

      {isLoading ? (
        <CardSkeleton />
      ) : isError ? (
        <ErrorState
          description="Не удалось загрузить варианты тестов-близнецов."
          onRetry={() => void refetch()}
        />
      ) : !data?.twins || data.twins.length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          Нет доступных семейств для выбранной специализации и грейда.
        </Card>
      ) : (
        <div className="space-y-4">
          {data.twins.map((twin) => (
            <TwinRow key={twin.family_id} twin={twin} />
          ))}
        </div>
      )}
    </div>
  )
}
