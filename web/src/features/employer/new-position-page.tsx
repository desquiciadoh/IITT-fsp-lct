import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, FileSearch, LoaderCircle } from 'lucide-react'
import { useParseJd } from '@/api/employer'
import { ApiError } from '@/api/client'
import type { JdParseResult } from '@/api/types'
import { PositionForm, draftToForm } from '@/features/employer/position-form'
import type { PositionFormState } from '@/features/employer/schemas'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * FE-09 · New position wizard (`/employer/positions/new`).
 *  Step 1: paste a JD → POST /api/positions/parse (gap G6, mocked).
 *  Step 2: editable form prefilled with the draft; `unknown_terms` are
 *          highlighted in the skill chips; blueprint bars from the parse.
 *  Save: POST /api/positions (real endpoint).
 */
export function NewPositionPage() {
  const [parsed, setParsed] = useState<JdParseResult | null>(null)
  const [jdText, setJdText] = useState('')
  const parse = useParseJd()

  const onParse = () => {
    if (jdText.trim().length < 40) {
      toast.error('Вставьте текст вакансии — минимум 40 символов')
      return
    }
    parse.mutate(jdText, {
      onSuccess: (result) => setParsed(result),
      onError: (error) =>
        toast.error(error instanceof ApiError ? error.message : 'Не удалось распознать вакансию'),
    })
  }

  if (parsed) {
    const defaults: PositionFormState = draftToForm(parsed.draft)
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <h1 className="text-lg font-semibold">Новая вакансия · шаг 2 из 2</h1>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/employer/positions/new" onClick={() => setParsed(null)}>
              <ArrowLeft className="mr-1 h-4 w-4" /> Другой текст
            </Link>
          </Button>
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Проверьте черновик и сохраните</CardTitle>
          </CardHeader>
          <CardContent>
            <PositionForm
              mode="create"
              defaultValues={defaults}
              unknownTerms={(parsed.unknown_terms ?? []).map((t) => t.toLowerCase())}
              blueprint={parsed.blueprint ?? []}
              parseSource={parsed.source}
            />
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <h1 className="text-lg font-semibold">Новая вакансия · шаг 1 из 2</h1>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Вставьте описание вакансии</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <textarea
            aria-label="Текст вакансии"
            rows={10}
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="Мы ищем backend-разработчика… стек, требования, условия"
            className="w-full rounded-md border border-input bg-background p-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={onParse} disabled={parse.isPending}>
              {parse.isPending ? (
                <>
                  <LoaderCircle className="mr-1 h-4 w-4 animate-spin" /> Распознаём…
                </>
              ) : (
                <>
                  <FileSearch className="mr-1 h-4 w-4" /> Распознать
                </>
              )}
            </Button>
            <Button
              variant="outline"
              type="button"
              onClick={() =>
                setParsed({
                  draft: {},
                  unknown_terms: [],
                  blueprint: [],
                  source: 'manual',
                })
              }
            >
              Заполнить вручную
            </Button>
            <span className="text-xs text-muted-foreground">
              Парсер заполнит форму, все поля можно будет отредактировать.
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
