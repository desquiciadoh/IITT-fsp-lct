import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import { useCreateMicroTask } from '@/api/microtasks'
import { errorMessage } from '@/i18n/errors'
import { SPEC_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import type { Grade, MicroTaskFormat, Spec } from '@/api/types'

const SPECS = ['backend', 'frontend', 'ml_data'] as const
const GRADES = ['intern', 'junior', 'middle', 'senior'] as const
const FORMATS: MicroTaskFormat[] = ['auto', 'open']

export function TaskCreatePage() {
  const navigate = useNavigate()
  const create = useCreateMicroTask()
  const [title, setTitle] = useState('')
  const [specialization, setSpecialization] = useState<Spec>('backend')
  const [grades, setGrades] = useState<Grade[]>([])
  const [format, setFormat] = useState<MicroTaskFormat>('auto')
  const [promptMd, setPromptMd] = useState('')
  const [key, setKey] = useState('')
  const [deadline, setDeadline] = useState('')

  const toggleGrade = (g: (typeof GRADES)[number]) =>
    setGrades((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]))

  const submit = () => {
    if (!title.trim() || grades.length === 0 || !promptMd.trim()) {
      toast.error('Заполните название, грейды и условие задачи')
      return
    }
    let parsedKey: unknown
    if (key.trim()) {
      try {
        parsedKey = JSON.parse(key)
      } catch {
        parsedKey = key
      }
    }
    create.mutate(
      {
        title: title.trim(),
        specialization,
        grades,
        format,
        prompt_md: promptMd.trim(),
        ...(parsedKey !== undefined ? { key: parsedKey } : {}),
        ...(deadline ? { deadline: new Date(deadline).toISOString() } : {}),
      },
      {
        onSuccess: () => {
          toast.success('Задача создана')
          navigate('/employer/micro-tasks')
        },
        onError: (error) =>
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Не удалось создать задачу.',
          ),
      },
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Новая микрозадача</h1>
      <Card className="gap-4 py-5">
        <CardContent className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Название
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Например: оценка стоимости жилья" />
          </label>

          <label className="flex flex-col gap-1 text-sm font-medium">
            Специализация
            <select
              value={specialization}
              onChange={(e) => setSpecialization(e.target.value as Spec)}
              className="rounded-md border border-input bg-card px-3 py-1.5 text-sm"
            >
              {SPECS.map((s) => (
                <option key={s} value={s}>
                  {SPEC_LABEL[s] ?? s}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">Грейды</legend>
            <div className="flex flex-wrap gap-2">
              {GRADES.map((g) => (
                <label
                  key={g}
                  className="flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={grades.includes(g)}
                    onChange={() => toggleGrade(g)}
                  />
                  {g}
                </label>
              ))}
            </div>
          </fieldset>

          <label className="flex flex-col gap-1 text-sm font-medium">
            Проверка
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as MicroTaskFormat)}
              className="rounded-md border border-input bg-card px-3 py-1.5 text-sm"
            >
              {FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f === 'auto' ? 'автопроверка по ключу' : 'ручная проверка'}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm font-medium">
            Условие (markdown)
            <textarea
              value={promptMd}
              onChange={(e) => setPromptMd(e.target.value)}
              rows={7}
              placeholder={'Опишите задачу. Например:\nОцените дом: дана таблица, постройте модель…'}
              className="rounded-md border border-input bg-card px-3 py-2 text-sm"
            />
          </label>

          {format === 'auto' && (
            <label className="flex flex-col gap-1 text-sm font-medium">
              Ключ для автопроверки (хранится только на сервере)
              <Input
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder='либ "expected" либ {"answer": 42}'
              />
              <span className="text-xs font-normal text-muted-foreground">
                Ответ кандидата сравнивается с ключом. Ключ не попадает в ответ API.
              </span>
            </label>
          )}

          <label className="flex flex-col gap-1 text-sm font-medium">
            Дедлайн (необязательно)
            <Input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </label>

          <div>
            <Button disabled={create.isPending} onClick={submit}>
              {create.isPending ? 'Создаём…' : 'Создать задачу'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}