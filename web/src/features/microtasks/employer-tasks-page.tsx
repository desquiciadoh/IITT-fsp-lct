import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import { useDeleteMicroTask, useMicroTasks } from '@/api/microtasks'
import { MICROTASK_FORMAT_LABEL } from '@/lib/labels'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState, ErrorState } from '@/components/domain/states'
import { RowSkeleton } from '@/components/ui/skeleton'

export function EmployerTasksPage() {
  const { data, isLoading, isError, refetch } = useMicroTasks()
  const remove = useDeleteMicroTask()

  if (isLoading) return <RowSkeleton count={3} />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="Микрозадач пока нет"
        description="Создайте задачу — она появится у подходящих кандидатов."
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Микрозадачи</h1>
        <Button asChild size="sm">
          <Link to="/employer/micro-tasks/new">
            <Plus className="h-4 w-4" /> Создать задачу
          </Link>
        </Button>
      </div>
      <div className="grid gap-3">
        {data.map((task) => (
          <Card key={task.id} className="gap-4 py-5">
            <CardContent className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-semibold">{task.title}</h2>
                <Badge variant="outline">
                  {MICROTASK_FORMAT_LABEL[task.format] ?? task.format}
                </Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {task.grades.map((g) => (
                  <Badge key={g} variant="outline">
                    {g}
                  </Badge>
                ))}
                {task.deadline && (
                  <span>до {new Date(task.deadline).toLocaleString('ru-RU')}</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button asChild size="sm" variant="outline">
                  <Link to={`/employer/micro-tasks/${task.id}`}>Отклики и решения</Link>
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate(task.id, {
                      onSuccess: () => toast.success('Задача удалена'),
                      onError: () => toast.error('Не удалось удалить задачу'),
                    })
                  }
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}