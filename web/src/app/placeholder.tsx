import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function Placeholder({
  title,
}: {
  title: string
  owner?: 'FE1' | 'FE2'
  task?: string
}) {
  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-10">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>Экран находится в разработке.</CardDescription>
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
