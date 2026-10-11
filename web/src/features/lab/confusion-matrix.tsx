import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const GRADES = ['Intern', 'Junior', 'Middle', 'Senior'] as const

export function ConfusionMatrix({ matrix }: { matrix: number[][] }) {
  const rowTotals = matrix.map((row) => row.reduce((sum, val) => sum + val, 0))
  const colTotals = [0, 1, 2, 3].map((colIdx) =>
    matrix.reduce((sum, row) => sum + (row[colIdx] ?? 0), 0),
  )
  const grandTotal = rowTotals.reduce((sum, val) => sum + val, 0) || 1

  const maxVal = Math.max(...matrix.flatMap((r) => r), 1)

  // Calculate diagonal exact accuracy and adjacent accuracy
  const diagonalSum = matrix.reduce((sum, row, i) => sum + (row[i] ?? 0), 0)
  const adjacentSum = matrix.reduce(
    (sum, row, i) =>
      sum +
      (row[i] ?? 0) +
      (i > 0 ? (row[i - 1] ?? 0) : 0) +
      (i < 3 ? (row[i + 1] ?? 0) : 0),
    0,
  )

  const exactPct = ((diagonalSum / grandTotal) * 100).toFixed(1)
  const adjacentPct = ((adjacentSum / grandTotal) * 100).toFixed(1)

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Матрица ошибок грейдов (Confusion Matrix)</CardTitle>
            <CardDescription>
              Распределение предсказанных грейдов относительно истинного уровня кандидата (N = {grandTotal.toLocaleString()})
            </CardDescription>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className="text-muted-foreground">
              Точное совпадение: <strong className="text-foreground">{exactPct}%</strong>
            </span>
            <span className="text-muted-foreground">
              В пределах ±1 грейда: <strong className="text-foreground">{adjacentPct}%</strong>
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table
            className="w-full border-collapse text-center text-xs"
            aria-label="Матрица ошибок грейдов: строки — истинный грейд, столбцы — предсказанный грейд"
          >
            <thead>
              <tr>
                <th
                  rowSpan={2}
                  className="border border-border bg-muted/40 p-2 text-left font-medium text-muted-foreground"
                >
                  Истинный грейд
                </th>
                <th
                  colSpan={4}
                  className="border border-border bg-muted/60 p-2 font-semibold text-heading uppercase tracking-wider text-[11px]"
                >
                  Присвоенный моделью грейд
                </th>
                <th
                  rowSpan={2}
                  className="border border-border bg-muted/40 p-2 font-medium text-muted-foreground"
                >
                  Всего
                </th>
              </tr>
              <tr>
                {GRADES.map((g) => (
                  <th key={g} className="border border-border bg-muted/30 p-2 font-semibold text-foreground">
                    {g}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {GRADES.map((trueGrade, rowIdx) => {
                const row = matrix[rowIdx] ?? [0, 0, 0, 0]
                const rowTotal = rowTotals[rowIdx] || 1

                return (
                  <tr key={trueGrade}>
                    <th
                      scope="row"
                      className="border border-border bg-muted/30 p-2 text-left font-semibold text-foreground"
                    >
                      {trueGrade}
                    </th>
                    {GRADES.map((_, colIdx) => {
                      const count = row[colIdx] ?? 0
                      const isDiagonal = rowIdx === colIdx
                      const isAdjacent = Math.abs(rowIdx - colIdx) === 1
                      const intensity = Math.min(count / maxVal, 1)
                      const pctOfRow = ((count / rowTotal) * 100).toFixed(1)

                      // Color intensity based on diagonal and token brand/accent
                      let cellBg = 'transparent'
                      let textColor = 'text-foreground'

                      if (isDiagonal) {
                        cellBg = `rgba(82, 9, 120, ${0.12 + intensity * 0.75})` // --fsp-brand
                        if (intensity > 0.45) textColor = 'text-white font-bold'
                      } else if (isAdjacent && count > 0) {
                        cellBg = `rgba(138, 131, 209, ${0.1 + intensity * 0.4})` // --fsp-secondary
                      } else if (count > 0) {
                        cellBg = `rgba(220, 38, 38, ${0.1 + intensity * 0.3})` // error red
                      }

                      return (
                        <td
                          key={colIdx}
                          style={{ backgroundColor: cellBg }}
                          className={`border border-border p-3 transition-colors ${textColor}`}
                          title={`Истинный: ${trueGrade}, Модель: ${GRADES[colIdx]}: ${count} (${pctOfRow}%)`}
                        >
                          <div className="font-semibold tabular-nums text-sm">{count.toLocaleString()}</div>
                          <div className="text-[10px] opacity-80 tabular-nums">{pctOfRow}%</div>
                        </td>
                      )
                    })}
                    <td className="border border-border bg-muted/20 p-2 font-semibold tabular-nums text-muted-foreground">
                      {rowTotals[rowIdx].toLocaleString()}
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-border font-medium bg-muted/40">
                <th scope="row" className="border border-border p-2 text-left text-muted-foreground">
                  Всего предсказано
                </th>
                {colTotals.map((colTotal, i) => (
                  <td key={i} className="border border-border p-2 font-semibold tabular-nums text-foreground">
                    {colTotal.toLocaleString()}
                  </td>
                ))}
                <td className="border border-border p-2 font-bold tabular-nums text-heading">
                  {grandTotal.toLocaleString()}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
