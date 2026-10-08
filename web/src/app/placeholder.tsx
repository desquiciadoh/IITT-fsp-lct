/** Route placeholder: shows owner (FE1/FE2) and task reference. */
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function Placeholder({
  title,
  owner,
  task,
}: {
  title: string
  owner: 'FE1' | 'FE2'
  task: string
}) {
  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-10">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>{title}</CardTitle>
            <Badge variant={owner === 'FE1' ? 'default' : 'secondary'}>{owner}</Badge>
          </div>
          <CardDescription>Задача {task} — экран появится в её рамках.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Скелет готов: роут, гарды, данные и стейл моки подключены.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
