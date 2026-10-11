import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ShieldCheck } from 'lucide-react'

type LeakAttackPoint = {
  leak_share: number
  static_dtheta: number
  parametric_dtheta: number
}

export function LeakAttackChart({ data }: { data: LeakAttackPoint[] }) {
  const chartData = data.map((d) => ({
    name: `${Math.round(d.leak_share * 100)}% утечки`,
    static_dtheta: Number(d.static_dtheta.toFixed(2)),
    parametric_dtheta: Number(d.parametric_dtheta.toFixed(2)),
  }))

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-plus" />
              Устойчивость к утечкам вопросов (Leak Attack Resilience)
            </CardTitle>
            <CardDescription>
              Сравнение инфляции скора Δθ при утечке 10%, 30% и 50% пула вопросов в сеть
            </CardDescription>
          </div>
          <div className="text-xs text-muted-foreground">
            Статический тест уязвим к заучиванию ответов, параметрические семейства — устойчивы
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="h-[260px] w-full" role="img" aria-label="Сравнение инфляции оценки тета при утечке банка заданий">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e0ee" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#5c5470' }} />
              <YAxis
                tick={{ fontSize: 11, fill: '#5c5470' }}
                label={{ value: 'Инфляция оценки (Δθ)', angle: -90, position: 'insideLeft', offset: 15, fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#ffffff',
                  borderColor: '#e5e0ee',
                  borderRadius: '0.5rem',
                  fontSize: '12px',
                }}
              />
              <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '8px' }} />
              <Bar
                dataKey="static_dtheta"
                name="Статический тест (инфляция скора)"
                fill="#dc2626"
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey="parametric_dtheta"
                name="Параметрические семейства (наша система)"
                fill="#520978"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <details className="text-xs text-muted-foreground cursor-pointer">
          <summary className="font-medium hover:text-foreground">Показать числовую таблицу устойчивости к утечкам</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full border-collapse border border-border text-center">
              <thead>
                <tr className="bg-muted/40">
                  <th className="border border-border p-1.5 text-left">Доля утекших заданий</th>
                  <th className="border border-border p-1.5">Статический тест (Δθ)</th>
                  <th className="border border-border p-1.5">Параметрический FSP (Δθ)</th>
                  <th className="border border-border p-1.5 text-right">Защита от читерства</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row) => (
                  <tr key={row.leak_share}>
                    <td className="border border-border p-1.5 text-left font-semibold">
                      {Math.round(row.leak_share * 100)}%
                    </td>
                    <td className="border border-border p-1.5 text-minus font-bold tabular-nums">
                      +{row.static_dtheta.toFixed(2)}
                    </td>
                    <td className="border border-border p-1.5 text-plus font-bold tabular-nums">
                      +{row.parametric_dtheta.toFixed(2)}
                    </td>
                    <td className="border border-border p-1.5 text-right text-plus font-medium">
                      {row.static_dtheta > 0
                        ? `Снижение инфляции на ${Math.round(((row.static_dtheta - row.parametric_dtheta) / row.static_dtheta) * 100)}%`
                        : 'OK'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </CardContent>
    </Card>
  )
}
