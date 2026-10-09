import { tokenColor } from './token-color'

const PLUS = tokenColor('--fsp-plus', '#b8ff3c')
const WARN = tokenColor('--fsp-warn', '#ffc857')

function Bar({ value, color }: { value: number; color: string }) {
  const width = `${Math.round(value * 100)}%`
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-full min-w-24 overflow-hidden rounded-full bg-secondary">
        <div
          className="h-full rounded-full"
          style={{ width, backgroundColor: color, opacity: 0.85 }}
        />
      </div>
      <span className="w-10 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">
        {Math.round(value * 100)}%
      </span>
    </div>
  )
}

/** Systems comparison: nDCG@10 and P@10 as proportional bars, r50/mrr as text (FE-13). */
export function SystemsTable({
  systems,
}: {
  systems: { name: string; ndcg10: number; p10: number; r50: number; mrr: number }[]
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">
          Сравнение систем матчинга по метрикам ранжирования: nDCG@10, P@10, R@50, MRR.
        </caption>
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" className="py-2 pr-4 text-left font-medium">
              Система
            </th>
            <th scope="col" className="py-2 pr-4 text-left font-medium">
              nDCG@10
            </th>
            <th scope="col" className="py-2 pr-4 text-left font-medium">
              P@10
            </th>
            <th scope="col" className="py-2 pr-4 text-left font-medium">
              R@50
            </th>
            <th scope="col" className="py-2 pr-2 text-left font-medium">
              MRR
            </th>
          </tr>
        </thead>
        <tbody>
          {systems.map((row) => (
            <tr key={row.name} className="border-b border-border last:border-0">
              <th scope="row" className="py-2 pr-4 text-left font-mono text-xs">
                {row.name}
              </th>
              <td className="py-2 pr-4">
                <Bar value={row.ndcg10} color={PLUS} />
              </td>
              <td className="py-2 pr-4">
                <Bar value={row.p10} color={WARN} />
              </td>
              <td className="py-2 pr-4 font-mono text-xs tabular-nums text-foreground">
                {row.r50.toFixed(2)}
              </td>
              <td className="py-2 pr-2 font-mono text-xs tabular-nums text-muted-foreground">
                {row.mrr.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}