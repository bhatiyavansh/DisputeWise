import type { DecisionResponse } from '../../api/types'
import { formatCurrency, formatPercent, formatSignedCurrency } from '../../utils/format'
import { BreakEvenVisualization } from './BreakEvenVisualization'
import { SensitivityTable } from './SensitivityTable'
import { DecisionBadge } from '../common/DecisionBadge'
import { DecisionSourceBadge } from '../common/DecisionSourceBadge'
import { Panel } from '../common/Panel'

/**
 * All numbers here come straight from the /decision response -- the
 * frontend never recomputes expected value, break-even probability, or the
 * decision itself. The backend is the source of truth (spec §9).
 */
export function EconomicDecisionPanel({ decision, source }: { decision: DecisionResponse; source: 'real' | 'mock' }) {
  return (
    <Panel
      title="Economic Decision"
      subtitle={`decision policy ${decision.decision_policy_version}`}
      action={<DecisionSourceBadge source={source} />}
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="grid flex-1 grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
          <Field label="Win probability" value={formatPercent(decision.calibrated_probability)} />
          <Field label="Recoverable amount" value={formatCurrency(decision.recoverable_amount, true)} />
          <Field label="Recovery rate" value={formatPercent(decision.recovery_rate, 0)} />
          <Field label="Expected recovery" value={formatCurrency(decision.expected_recovery, true)} />
          <Field label="Contest cost" value={formatCurrency(decision.contest_cost, true)} />
          <Field
            label="Expected net value"
            value={formatSignedCurrency(decision.expected_net_value)}
            tone={decision.expected_net_value >= 0 ? 'positive' : 'negative'}
            emphasize
          />
        </div>

        <div className="flex shrink-0 flex-col items-start gap-2 lg:items-end">
          <span className="text-xs font-medium uppercase tracking-wide text-ink-500">Decision</span>
          <DecisionBadge decision={decision.decision} size="lg" />
        </div>
      </div>

      <div className="mt-6 border-t border-ink-800 pt-5">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Break-even analysis</h3>
        <BreakEvenVisualization
          currentProbability={decision.calibrated_probability}
          breakEvenProbability={decision.break_even_probability}
        />
        <p className="mt-2 text-xs text-ink-500">{decision.break_even_explanation}</p>
      </div>

      <div className="mt-6 border-t border-ink-800 pt-5">
        <SensitivityTable points={decision.sensitivity} currentProbability={decision.calibrated_probability} />
      </div>

      {decision.evidence_gap_downgrade && (
        <p className="mt-4 flex items-start gap-2 rounded border border-review-500/30 bg-review-50/5 px-3 py-2 text-xs text-review-700">
          <span aria-hidden="true">⚠</span>
          This case would otherwise qualify for CONTEST, but was routed to human review because
          high-relevance evidence for this reason code is missing on file.
        </p>
      )}
    </Panel>
  )
}

function Field({
  label,
  value,
  tone,
  emphasize,
}: {
  label: string
  value: string
  tone?: 'positive' | 'negative'
  emphasize?: boolean
}) {
  const toneClass = tone === 'positive' ? 'text-contest-600' : tone === 'negative' ? 'text-avoid-600' : 'text-ink-100'
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className={`tabular mt-0.5 ${emphasize ? 'text-lg font-semibold' : 'text-sm font-medium'} ${toneClass}`}>{value}</dd>
    </div>
  )
}
