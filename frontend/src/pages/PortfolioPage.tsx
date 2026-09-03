import { getPortfolioSummary } from '../api/portfolio'
import type { PortfolioGroup } from '../api/types'
import { ErrorState } from '../components/common/ErrorState'
import { SkeletonCard } from '../components/common/LoadingStates'
import { Panel } from '../components/common/Panel'
import { DecisionBadge } from '../components/common/DecisionBadge'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { formatCurrency, formatPercent, formatReasonCode } from '../utils/format'

/**
 * Phase 7C -- portfolio risk view.
 *
 * Every figure is aggregated server-side from the real split and rendered
 * verbatim; the browser never loads per-case rows or computes an economic
 * number. Metrics the dataset cannot support (SLAs, recovery-to-date,
 * throughput) are simply absent rather than estimated.
 */
export function PortfolioPage() {
  const query = useAsyncResource('portfolio:summary', (signal) => getPortfolioSummary(signal))

  if (query.status === 'loading') {
    return (
      <div className="flex flex-col gap-5">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  if (query.status === 'error') {
    return (
      <ErrorState
        error={query.error}
        title={query.error?.kind === 'unavailable' ? 'Portfolio data is not available' : undefined}
        onRetry={query.refetch}
      />
    )
  }

  if (!query.data) return null
  const data = query.data

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight text-ink-50">Portfolio risk</h1>
        <p className="mt-1 text-sm text-ink-400">
          {data.n_cases.toLocaleString()} disputes · {data.split} split · routed by {data.decision_policy_version}
        </p>
      </header>

      {/* Portfolio overview */}
      <section className="grid grid-cols-2 gap-x-8 gap-y-5 rounded-lg border border-ink-800 bg-ink-900 p-5 lg:grid-cols-4">
        <Metric label="Total disputed" value={formatCurrency(data.total_disputed_amount, true)} />
        <Metric label="Expected recovery" value={formatCurrency(data.total_expected_recovery, true)} />
        <Metric
          label="Expected net value (contested)"
          value={formatCurrency(data.contest_only_expected_net_value, true)}
          hint="only contested cases can recover"
        />
        <Metric
          label="Realized net value (contested)"
          value={formatCurrency(data.contest_only_realized_net_value, true)}
          hint="retrospective, known outcomes"
        />
      </section>

      {/* Decision routing */}
      <Panel title="Decision routing" subtitle={`under ${data.decision_policy_version}`}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead>
              <tr className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-ink-500">
                <th className="pb-2 font-medium">Decision</th>
                <th className="pb-2 text-right font-medium">Cases</th>
                <th className="pb-2 text-right font-medium">Share</th>
                <th className="pb-2 text-right font-medium">Amount at risk</th>
                <th className="pb-2 text-right font-medium">Expected recovery</th>
                <th className="pb-2 text-right font-medium">Favorable rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {data.decisions.map((bucket) => (
                <tr key={bucket.decision}>
                  <td className="py-2.5">
                    <DecisionBadge decision={bucket.decision} />
                    {bucket.evidence_gap_downgrades > 0 && (
                      <span className="ml-2 text-xs text-review-700">
                        {bucket.evidence_gap_downgrades.toLocaleString()} evidence-gap downgrades
                      </span>
                    )}
                  </td>
                  <td className="tabular py-2.5 text-right text-ink-100">{bucket.count.toLocaleString()}</td>
                  <td className="tabular py-2.5 text-right text-ink-300">{bucket.percentage.toFixed(1)}%</td>
                  <td className="tabular py-2.5 text-right text-ink-100">{formatCurrency(bucket.total_amount, true)}</td>
                  <td className="tabular py-2.5 text-right text-ink-300">
                    {formatCurrency(bucket.expected_recovery, true)}
                  </td>
                  <td className="tabular py-2.5 text-right text-ink-300">
                    {bucket.actual_favorable_outcome_rate === null
                      ? '—'
                      : formatPercent(bucket.actual_favorable_outcome_rate, 1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-ink-500">
          Favorable rate is retrospective — the share of cases in each bucket that actually resolved in the
          merchant&apos;s favour on this split.
        </p>
      </Panel>

      {/* Breakdowns */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <BreakdownPanel
          title="By reason code"
          groups={data.by_reason_code}
          total={data.n_cases}
          formatKey={formatReasonCode}
        />
        <BreakdownPanel title="By win probability" groups={data.by_probability_band} total={data.n_cases} />
        <BreakdownPanel
          title="By evidence completeness"
          subtitle={`${data.cases_with_missing_high_relevance_evidence.toLocaleString()} cases missing high-relevance evidence`}
          groups={data.by_evidence_completeness}
          total={data.n_cases}
        />
      </div>

      <p className="text-xs text-ink-500">{data.note}</p>
    </div>
  )
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className="tabular mt-1 text-xl font-semibold text-ink-50">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-600">{hint}</p>}
    </div>
  )
}

function BreakdownPanel({
  title,
  subtitle,
  groups,
  total,
  formatKey = (key: string) => key,
}: {
  title: string
  subtitle?: string
  groups: PortfolioGroup[]
  total: number
  formatKey?: (key: string) => string
}) {
  return (
    <Panel title={title} subtitle={subtitle}>
      <ul className="flex flex-col gap-3">
        {groups.map((group) => {
          const share = total > 0 ? group.count / total : 0
          return (
            <li key={group.key}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-ink-200">{formatKey(group.key)}</span>
                <span className="tabular shrink-0 text-ink-400">{group.count.toLocaleString()}</span>
              </div>
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-ink-800">
                <div className="h-full rounded-full bg-accent-600" style={{ width: `${share * 100}%` }} />
              </div>
              <div className="mt-1 flex justify-between text-xs text-ink-500">
                <span>{formatCurrency(group.total_amount, true)}</span>
                <span className="tabular">mean P(win) {formatPercent(group.mean_probability, 0)}</span>
              </div>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
