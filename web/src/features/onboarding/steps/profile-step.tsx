import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { FileText, Sparkles, Upload } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { useProfile, useSaveProfile, useUploadResume } from '@/api/profile'
import type { ResumeParseResult } from '@/api/types'
import { Button } from '@/components/ui/button'

const MAX_SIZE = 5 * 1024 * 1024

const SOURCE_LABEL: Record<string, string> = {
  llm: 'распознано ИИ',
  rules: 'правила парсера',
}

/** Onboarding step 2: resume upload + prefill review, or manual entry. */
export function ProfileStep() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [parsed, setParsed] = useState<ResumeParseResult | null>(null)
  const [about, setAbout] = useState('')
  const [skills, setSkills] = useState<string[]>([])
  const [specialization, setSpecialization] = useState<string>('')
  const [claimedGrade, setClaimedGrade] = useState<string>('')

  const { data: profile } = useProfile()
  const upload = useUploadResume()
  const save = useSaveProfile()

  const handleFile = (file: File | undefined) => {
    if (!file) return
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('Нужен PDF-файл')
      return
    }
    if (file.size > MAX_SIZE) {
      toast.error('PDF больше 5 МБ')
      return
    }
    upload.mutate(file, {
      onSuccess: (result) => {
        setParsed(result)
        setAbout(result.prefill.about ?? '')
        setSkills(result.prefill.skills ?? [])
        setSpecialization(result.prefill.specialization ?? '')
        setClaimedGrade(result.prefill.claimed_grade ?? '')
        toast.success('Резюме распознано — проверьте предзаполнение')
      },
      onError: (error) => {
        if (error instanceof ApiError && error.code === 'unreadable_pdf') {
          toast.error('Не удалось прочитать PDF — заполните форму вручную')
        } else {
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Сбой загрузки',
          )
        }
      },
    })
  }

  const goToSurvey = (persist: boolean) => {
    const finish = () =>
      navigate('/candidate/onboarding/survey', {
        replace: true,
        state: { specialization, claimedGrade },
      })

    if (!persist || (!parsed && !about && skills.length === 0)) {
      finish()
      return
    }
    save.mutate(
      {
        ...(about ? { about } : {}),
        ...(skills.length > 0 ? { skills } : {}),
        ...(specialization ? { specialization } : {}),
        ...(claimedGrade ? { claimed_grade: claimedGrade } : {}),
      },
      {
        onSuccess: finish,
        onError: (error) =>
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Сбой сохранения',
          ),
      },
    )
  }

  return (
    <section className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6">
      <div>
        <h1 className="text-lg font-semibold">Профиль</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Загрузите резюме (PDF до 5 МБ) — предзаполним анкету. Или заполните вручную.
        </p>
      </div>

      {!parsed && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Загрузить резюме PDF"
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            handleFile(e.dataTransfer.files[0])
          }}
          className={cn(
            'flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors',
            dragOver ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50',
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          {upload.isPending ? (
            <span className="text-sm text-muted-foreground">Распознаём резюме…</span>
          ) : (
            <>
              <Upload className="h-6 w-6 text-muted-foreground" />
              <span className="text-sm font-medium">Перетащите PDF или нажмите</span>
              <span className="text-xs text-muted-foreground">Максимум 5 МБ</span>
            </>
          )}
        </div>
      )}

      {parsed && (
        <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 text-xs font-semibold">
              <FileText className="h-3.5 w-3.5" /> Резюме распознано
            </span>
            <span className="rounded-full border border-info/40 bg-info/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-info">
              {SOURCE_LABEL[parsed.source] ?? parsed.source}
            </span>
            <button
              type="button"
              className="ml-auto text-xs underline underline-offset-4 text-muted-foreground"
              onClick={() => setParsed(null)}
            >
              Сбросить
            </button>
          </div>

          {parsed.unknown_terms.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Не распознано:</span>
              {parsed.unknown_terms.map((term) => (
                <span
                  key={term}
                  className="rounded bg-warn/15 px-1.5 py-0.5 text-xs font-medium text-warn"
                  title="Термин не найден в словаре — проверьте вручную"
                >
                  {term}
                </span>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-1.5">
            {skills.map((s) => (
              <span key={s} className="rounded-md bg-secondary px-2 py-0.5 text-xs">
                {s}
              </span>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">
              Специализация
              <select
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
                value={specialization}
                onChange={(e) => setSpecialization(e.target.value)}
              >
                <option value="">—</option>
                <option value="backend">бэкенд</option>
                <option value="frontend">фронтенд</option>
                <option value="ml_data">ml/data</option>
              </select>
            </label>
            <label className="text-sm">
              Заявленный грейд
              <select
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
                value={claimedGrade}
                onChange={(e) => setClaimedGrade(e.target.value)}
              >
                <option value="">—</option>
                <option value="intern">стажёр</option>
                <option value="junior">джун</option>
                <option value="middle">мидл</option>
                <option value="senior">синьор</option>
              </select>
            </label>
          </div>
        </div>
      )}

      <label className="text-sm">
        О себе
        <textarea
          value={about}
          onChange={(e) => setAbout(e.target.value)}
          rows={4}
          maxLength={2000}
          placeholder="Пара строк о том, чем занимаетесь и что ищете"
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
        />
      </label>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5" />
        Умные подсказки появятся, когда профиль заполнен — сейчас это обычная форма.
      </div>

      <div className="flex gap-2">
        <Button
          type="button"
          variant="ghost"
          onClick={() => goToSurvey(false)}
          disabled={save.isPending}
        >
          Заполнить вручную
        </Button>
        <Button
          type="button"
          className="flex-1"
          onClick={() => goToSurvey(true)}
          disabled={save.isPending}
        >
          {save.isPending ? 'Сохраняем…' : 'Продолжить'}
        </Button>
      </div>
      {profile?.public_id && (
        <p className="text-center text-xs text-muted-foreground">
          ID профиля: <span className="font-mono">{profile.public_id}</span>
        </p>
      )}
    </section>
  )
}
