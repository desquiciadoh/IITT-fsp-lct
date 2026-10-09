/**
 * FE-13: confusion matrix as an accessible heatmap table — the numbers are the
 * text alternative, colour intensity is proportional to the cell count.
 */
export function ConfusionMatrix({ matrix }: { matrix: number[][] }) {
  const max = Math.max(...matrix.flat())
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-center text-xs" aria-label="Матрица ошибок оценки">
        <caption className="sr-only">
          Матрица ошибок: строки — фактический грейд, столбцы — предсказанный. Интенсивность
          пропорциональна числу ответов.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="py-1 pr-2 text-right font-medium text-muted-foreground">
              факт \ прогноз
            </th>
            {matrix.map((_, j) => (
              <th key={j} scope="col" className="px-2 py-1 font-mono font-medium text-muted-foreground">
                {j + 1}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={i}>
              <th scope="row" className="py-1 pr-2 text-right font-mono font-medium text-muted-foreground">
                {i + 1}
              </th>
              {row.map((value, j) => {
                const correct = i === j
                const alpha = Math.max(0, Math.min(1, value / max))
                const tint = correct ? 'var(--fsp-plus)' : 'var(--fsp-minus)'
                const background = `color-mix(in srgb, ${tint} ${Math.round(alpha * 70)}%, transparent)`
                return (
                  <td
                    key={j}
                    style={{ background, color: alpha > 0.45 ? 'var(--fsp-bg)' : undefined }}
                    className={`rounded px-2 py-1 font-mono tabular-nums ${correct ? 'font-semibold' : ''}`}
                  >
                    {value}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}