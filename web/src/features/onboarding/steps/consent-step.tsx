import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Scale } from 'lucide-react'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/i18n/errors'
import { useProfile, useSaveConsents } from '@/api/profile'
import { applyApiErrorToForm } from '@/features/auth/form-errors'
import { consentSchema, type ConsentValues } from '@/features/onboarding/schemas'
import { Button } from '@/components/ui/button'

type ConsentItem = {
  name: 'publication' | 'fsp_sync'
  title: string
  body: string
  required?: boolean
}

const ITEMS: ConsentItem[] = [
  {
    name: 'publication',
    title: 'Публикация профиля работодателям',
    body: 'Разрешить показывать мой профиль компаниям-работодателям: анкета, лига, зарплата и результаты теста. Контакты остаются скрытыми, пока я не приму оффер (152-ФЗ, ст. 10.1).',
    required: true,
  },
  {
    name: 'fsp_sync',
    title: 'Синхронизация с ФСП',
    body: 'Разрешить импорт моих спортивных результатов из Федерации Спортивного Программирования. Результаты влияют на рейтинг, но не на подтверждение грейда.',
  },
]

export function ConsentStep() {
  const navigate = useNavigate()
  const { data: profile } = useProfile()
  const saveConsents = useSaveConsents()
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors },
  } = useForm<ConsentValues>({
    resolver: zodResolver(consentSchema),
    defaultValues: { processing: false, publication: false, fsp_sync: true },
  })

  useEffect(() => {
    const existing = profile?.consents
    if (!existing) return
    setValue('processing', existing.processing)
    setValue('publication', existing.publication)
    setValue('fsp_sync', existing.fsp_sync)
  }, [profile, setValue])

  const onSubmit = (values: ConsentValues) => {
    saveConsents.mutate(values, {
      onSuccess: () => navigate('/candidate/onboarding/profile', { replace: true }),
      onError: (error) => {
        if (!applyApiErrorToForm(error, setError)) {
          toast.error(
            error instanceof ApiError ? errorMessage(error.code, error.detail) : 'Сбой сохранения',
          )
        }
      },
    })
  }

  return (
    <section className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6">
      <div>
        <h1 className="text-lg font-semibold">Согласия</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Три отдельных согласия — их можно отозвать в настройках в любой момент.
        </p>
      </div>

      <label className="flex cursor-pointer gap-3 rounded-lg border border-border p-4">
        <input type="checkbox" className="mt-1 size-4 accent-[var(--fsp-accent)]" {...register('processing')} />
        <span>
          <span className="text-sm font-medium">
            Обработка персональных данных
            <span className="ml-2 rounded-full border border-warn/40 bg-warn/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-warn">
              черновик · требует юр. проверки
            </span>
          </span>
          <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
            Согласие на обработку персональных данных в соответствии с 152-ФЗ «О персональных
            данных»: сбор, анализ результатов теста и хранение профиля кандидата.
          </span>
        </span>
      </label>
      {errors.processing && (
        <p className="-mt-3 text-xs text-destructive" role="alert">
          {errors.processing.message}
        </p>
      )}

      {ITEMS.map((item) => (
        <label
          key={item.name}
          className="flex cursor-pointer gap-3 rounded-lg border border-border p-4"
        >
          <input
            type="checkbox"
            className="mt-1 size-4 accent-[var(--fsp-accent)]"
            {...register(item.name)}
          />
          <span>
            <span className="text-sm font-medium">
              {item.title}
              <span className="ml-2 rounded-full border border-warn/40 bg-warn/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-warn">
                черновик · требует юр. проверки
              </span>
            </span>
            <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
              {item.body}
            </span>
          </span>
        </label>
      ))}

      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <Scale className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Без согласия на обработку профиль не публикуется. Согласие на публикацию обязательно —
        иначе работодатели не увидят вас в пуле.
      </p>

      <Button
        type="button"
        onClick={handleSubmit((values) => onSubmit(values))}
        disabled={saveConsents.isPending}
        className="w-full"
      >
        {saveConsents.isPending ? 'Сохраняем…' : 'Продолжить'}
      </Button>
    </section>
  )
}
