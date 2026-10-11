import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function TifChart({ tif }: { tif: { theta: number[]; info: number[] } }) {
  const chartData = tif.theta.map((th, i) => {
    const infoVal = tif.info[i] ?? 0
    const seVal = infoVal > 0 ? Number((1 / Math.sqrt(infoVal)).toFixed(2)) : 0
    return {
      theta: th,
      info: Number(infoVal.toFixed(2)),
      se: seVal,
    }
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Кривая информации теста (Test Information Function / TIF)</CardTitle>
            <CardDescription>
              Зависимость информативности I(θ) и стандартной ошибки SE(θ) от скрытого уровня способностей кандидата θ
            </CardDescription>
          </div>
          <div className="text-xs text-muted-foreground">
            Минимум ошибки SE достигается при θ ∈ [-1.5, +1.5]
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="h-[280px] w-full" role="img" aria-label="График TIF и стандартной ошибки в зависимости от тета">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e0ee" />
              <XAxis
                dataKey="theta"
                tick={{ fontSize: 11, fill: '#5c5470' }}
                label={{ value: 'Способность кандидата (θ)', position: 'insideBottom', offset: -5, fontSize: 11 }}
              />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 11, fill: '#5c5470' }}
                label={{ value: 'Информация I(θ)', angle: -90, position: 'insideLeft', offset: 15, fontSize: 11 }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 11, fill: '#5c5470' }}
                label={{ value: 'Стандартная ошибка SE', angle: 90, position: 'insideRight', offset: 15, fontSize: 11 }}
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
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="info"
                name="Информация I(θ)"
                stroke="#520978"
                strokeWidth={2.5}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="se"
                name="Стандартная ошибка SE"
                stroke="#ff0053"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <details className="text-xs text-muted-foreground cursor-pointer">
          <summary className="font-medium hover:text-foreground">Показать числовую таблицу TIF (текстовая альтернатива)</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full border-collapse border border-border text-center">
              <thead>
                <tr className="bg-muted/40">
                  <th className="border border-border p-1.5">θ</th>
                  {chartData.map((d) => (
                    <td key={d.theta} className="border border-border p-1.5 tabular-nums font-semibold">
                      {d.theta}
                    </td>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th className="border border-border p-1.5 text-left bg-muted/20">I(θ)</th>
                  {chartData.map((d) => (
                    <td key={d.theta} className="border border-border p-1.5 tabular-nums">
                      {d.info}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th className="border border-border p-1.5 text-left bg-muted/20">SE(θ)</th>
                  {chartData.map((d) => (
                    <td key={d.theta} className="border border-border p-1.5 tabular-nums">
                      {d.se}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </CardContent>
    </Card>
  )
}
