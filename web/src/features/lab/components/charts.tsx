import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { tokenColor } from './token-color'

const GRID = tokenColor('--fsp-line', '#1f2836')
const MUTED = tokenColor('--fsp-muted', '#8b98a8')
const PLUS = tokenColor('--fsp-plus', '#b8ff3c')
const INFO = tokenColor('--fsp-info', '#58c7ff')
const MINUS = tokenColor('--fsp-minus', '#ff6b6b')

const tooltipStyle = {
  background: tokenColor('--fsp-panel', '#121821'),
  border: `1px solid ${tokenColor('--fsp-line', '#1f2836')}`,
  fontSize: 12,
}

function DataTable({ rows }: { rows: { [key: string]: string | number }[] }) {
  const headers = rows.length > 0 ? Object.keys(rows[0]!) : []
  return (
    <details className="mt-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer">Таблица значений</summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse font-mono tabular-nums">
          <thead className="bg-secondary">
            <tr>
              {headers.map((h) => (
                <th key={h} scope="col" className="px-2 py-1 text-left">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-border">
                {headers.map((h) => (
                  <td key={h} className="px-2 py-0.5">
                    {row[h]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

/** TIF: test information function over theta (FE-13). */
export function TifChart({ theta, info }: { theta: number[]; info: number[] }) {
  const data = theta.map((th, i) => ({ theta: th, info: info[i] ?? 0 }))
  return (
    <div>
      <div role="img" aria-label="Кривая информации теста: количество информации по латентной способности theta">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
            <XAxis dataKey="theta" stroke={MUTED} tick={{ fill: MUTED, fontSize: 11 }} />
            <YAxis stroke={MUTED} tick={{ fill: MUTED, fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line type="monotone" dataKey="info" name="Информация" stroke={PLUS} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTable rows={data.map((d) => ({ theta: d.theta, info: d.info.toFixed(2) }))} />
    </div>
  )
}

/** Leak attacks: recall shift under a leaked-item share (FE-13). */
export function LeakChart({
  rows,
}: {
  rows: { leak_share: number; static_dtheta: number; parametric_dtheta: number }[]
}) {
  return (
    <div>
      <div role="img" aria-label="Сдвиг результата атак при утечке заданий: статический и параметрический пул">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
            <XAxis
              dataKey="leak_share"
              tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              stroke={MUTED}
              tick={{ fill: MUTED, fontSize: 11 }}
            />
            <YAxis stroke={MUTED} tick={{ fill: MUTED, fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} formatter={(value) => Number(value).toFixed(2)} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="static_dtheta" name="Статический пул" fill={INFO} />
            <Bar dataKey="parametric_dtheta" name="Параметрический пул" fill={MINUS} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <DataTable
        rows={rows.map((r) => ({
          leak_share: `${Math.round(r.leak_share * 100)}%`,
          static_dtheta: r.static_dtheta.toFixed(2),
          parametric_dtheta: r.parametric_dtheta.toFixed(2),
        }))}
      />
    </div>
  )
}