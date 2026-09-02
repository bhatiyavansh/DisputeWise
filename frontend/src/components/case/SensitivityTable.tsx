import type { SensitivityPoint } from '../../api/types'
import { formatPercent, formatSignedCurrency } from '../../utils/format'

/** Explainability surface only -- the API guarantees this never changes the
 * decision itself; the table is presented as "what if" context. */
export function SensitivityTable({ points, currentProbability }: { points: SensitivityPoint[]; currentProbability: number }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">
        Sensitivity: expected net value at nearby win probabilities
      </h3>
      <div className="overflow-x-auto rounded border border-ink-800">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink-800 bg-ink-850 text-xs text-ink-500">
              <th scope="col" className="px-3 py-1.5 text-left font-medium">
                P(win)
              </th>
              {points.map((p) => (
                <th
                  key={p.probability}
                  scope="col"
                  className={`tabular px-3 py-1.5 text-right font-medium ${Math.abs(p.probability - currentProbability) < 1e-6 ? 'text-ink-100' : ''}`}
                >
                  {formatPercent(p.probability)}
                  {Math.abs(p.probability - currentProbability) < 1e-6 && (
                    <span className="ml-1 rounded bg-accent-600/20 px-1 text-[10px] text-accent-500">current</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="px-3 py-1.5 text-xs text-ink-500">Expected net value</td>
              {points.map((p) => (
                <td
                  key={p.probability}
                  className={`tabular px-3 py-1.5 text-right ${p.expected_net_value >= 0 ? 'text-contest-600' : 'text-avoid-600'}`}
                >
                  {formatSignedCurrency(p.expected_net_value)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
