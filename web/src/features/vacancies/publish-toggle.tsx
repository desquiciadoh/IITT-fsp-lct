import { toast } from 'sonner'
import { Globe, EyeOff } from 'lucide-react'
import { ApiError } from '@/api/client'
import { useSetPositionPublic } from '@/api/vacancies'
import { errorMessage } from '@/i18n/errors'
import { Button } from '@/components/ui/button'

export function PublishToggle({
  positionId,
  isPublic,
}: {
  positionId: string
  isPublic: boolean
}) {
  const setPublic = useSetPositionPublic()

  const toggle = () => {
    setPublic.mutate(
      { id: positionId, isPublic: !isPublic },
      {
        onSuccess: () =>
          toast.success(isPublic ? 'Вакансия снята с публикации' : 'Вакансия опубликована'),
        onError: (error) =>
          toast.error(
            error instanceof ApiError
              ? errorMessage(error.code, error.detail)
              : 'Не удалось изменить публикацию.',
          ),
      },
    )
  }

  return (
    <Button variant="outline" size="sm" disabled={setPublic.isPending} onClick={toggle}>
      {isPublic ? <EyeOff className="h-4 w-4" /> : <Globe className="h-4 w-4" />}
      {isPublic ? 'Снять с публикации' : 'Опубликовать'}
    </Button>
  )
}
