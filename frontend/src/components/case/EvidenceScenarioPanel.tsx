import { useState } from 'react'
import { ApiError } from '../../api/client'
import { runEvidenceScenario } from '../../api/scenario'
import type { EvidenceGapResponse, EvidenceScenarioResponse, EvidenceType } from '../../api/types'
import { formatCurrency, formatEvidenceType, formatPercent, formatSignedCurrency } from '../../utils/format'
import { cn } from '../../utils/cn'
import { DecisionBadge } from '../common/DecisionBadge'
import { ErrorState } from '../common/ErrorState'
import { InlineSpinner } from '../common/LoadingStates'
import { Panel } from '../common/Panel'

/**
 * Phase 7A -- evidence scenario analysis.
 *
 * Toggles are offered only for evidence types this case's reason code
 * actually requires (read from the case's own gap analysis), so the UI never
 * invents support for a toggle the backend wouldn't find meaningful. All
 * numbers come from the backend's two evaluations; nothing is computed here.
 */
export function EvidenceScenarioPanel({ caseId, gap }: { caseId: string; gap: EvidenceGapResponse }) {
  const [selected, setSelected] = useState<Set<EvidenceType>>(new Set())
  const [result, setResult] = useState<EvidenceScenarioResponse | null>(null)
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [error, setError] = useState<ApiError | null>(null)

  // Only required types are offered, and each is toggled in the direction
  // that is actually meaningful for its current state.
  const toggleable = gap.items.filter((item) => item.required)

  function toggle(evidenceType: EvidenceType) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(evidenceType)) next.delete(evidenceType)
      else next.add(evidenceType)
      return next
    })
  }

  async function run() {
    const add: EvidenceType[] = []
    const remove: EvidenceType[] = []
    for (const item of toggleable) {
      if (!selected.has(item.evidence_type)) continue
      if (item.status === 'MISSING') add.push(item.evidence_type)
      else remove.push(item.evidence_type)
    }
    if (add.length === 0 && remove.length === 0) return

    setStatus('running')
    setError(null)
    try {
      setResult(await runEvidenceScenario(caseId, { add_evidence: add, remove_evidence: remove }))
      setStatus('done')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError('network', 'Unexpected error', null, caught))
      setStatus('error')
    }
  }

  function reset() {
    setSelected(new Set())
    setResult(null)
    setError(null)
    setStatus('idle')
  }

  return (
    <Panel
      title="Evidence Scenario Analysis"
      subtitle="What would change if this evidence were added or removed?"
      action={
        <span className="rounded border border-review-500/40 bg-review-50/5 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-review-700">
          Scenario
        </span>
      }
    >
      <ul className="flex flex-col gap-1.5">
        {toggleable.map((item) => {
          const checked = selected.has(item.evidence_type)
          const action = item.status === 'MISSING' ? 'Add' : 'Remove'
          return (
            <li key={item.evidence_type}>
              <label className="flex cursor-pointer items-center gap-2.5 py-0.5">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(item.evidence_type)}
                  className="h-3.5 w-3.5 shrink-0 accent-accent-600"
                />
                <span className="text-sm text-ink-200">{formatEvidenceType(item.evidence_type)}</span>
                <span
                  className={cn(
                    'text-[11px] font-medium uppercase',
                    item.status === 'MISSING' ? 'text-avoid-600' : 'text-contest-600',
                  )}
                >
                  {item.status === 'MISSING' ? 'missing' : 'on file'}
                </span>
                {checked && <span className="text-[11px] text-ink-500">→ {action}</span>}
              </label>
            </li>
          )
        })}
      </ul>

      <div className="mt-4 flex items-center gap-2 border-t border-ink-800 pt-4">
        <button
          type="button"
          onClick={run}
          disabled={selected.size === 0 || status === 'running'}
          className="rounded bg-accent-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500"
        >
          Run scenario
        </button>
        {(result || status === 'error') && (
          <button
            type="button"
            onClick={reset}
            className="rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-sm font-medium text-ink-200 transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
          >
            Clear
          </button>
        )}
        {status === 'running' && <InlineSpinner label="Re-scoring…" />}
      </div>

      {status === 'error' && (
        <div className="mt-4">
          <ErrorState error={error} title="Scenario could not be evaluated" onRetry={() => void run()} compact />
        </div>
      )}

      {status === 'done' && result && <ScenarioComparison result={result} />}
    </Panel>
  )
}

function ScenarioComparison({ result }: { result: EvidenceScenarioResponse }) {
  const { current, scenario, delta } = result

  return (
    <div className="mt-5 border-t border-ink-800 pt-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SideColumn
          heading="Current"
          probability={current.score.calibrated_probability}
          decision={current.decision.decision}
          expectedNetValue={current.decision.expected_net_value}
          coverage={current.evidence_gap.coverage_ratio}
        />
        <SideColumn
          heading="Scenario"
          highlight
          probability={scenario.score.calibrated_probability}
          decision={scenario.decision.decision}
          expectedNetValue={scenario.decision.expected_net_value}
          coverage={scenario.evidence_gap.coverage_ratio}
        />
      </div>

      <dl className="mt-4 flex flex-wrap items-center gap-x-8 gap-y-2 border-t border-ink-800 pt-4 text-sm">
        <Delta label="Δ P(win)" value={formatSignedPercent(delta.calibrated_probability)} positive={delta.calibrated_probability >= 0} />
        <Delta
          label="Δ Expected net value"
          value={formatSignedCurrency(delta.expected_net_value)}
          positive={delta.expected_net_value >= 0}
        />
        <div>
          <dt className="text-xs text-ink-500">Decision</dt>
          <dd className="mt-0.5 text-sm font-medium text-ink-100">
            {delta.decision_changed ? (
              <span className="text-ink-50">
                {delta.decision_from.replace(/_/g, ' ')} → {delta.decision_to.replace(/_/g, ' ')}
              </span>
            ) : (
              <span className="text-ink-400">unchanged</span>
            )}
          </dd>
        </div>
      </dl>

      {(delta.critical_gaps_resolved.length > 0 || delta.critical_gaps_introduced.length > 0) && (
        <div className="mt-3 flex flex-col gap-1 text-xs">
          {delta.critical_gaps_resolved.length > 0 && (
            <p className="text-contest-600">
              Critical gaps resolved: {delta.critical_gaps_resolved.map(formatEvidenceType).join(', ')}
            </p>
          )}
          {delta.critical_gaps_introduced.length > 0 && (
            <p className="text-avoid-600">
              Critical gaps introduced: {delta.critical_gaps_introduced.map(formatEvidenceType).join(', ')}
            </p>
          )}
        </div>
      )}

      <p className="mt-4 border-t border-ink-800 pt-3 text-xs text-ink-500">{result.disclaimer}</p>
    </div>
  )
}

function SideColumn({
  heading,
  probability,
  decision,
  expectedNetValue,
  coverage,
  highlight,
}: {
  heading: string
  probability: number
  decision: EvidenceScenarioResponse['current']['decision']['decision']
  expectedNetValue: number
  coverage: number
  highlight?: boolean
}) {
  return (
    <div className={cn('rounded border px-4 py-3', highlight ? 'border-accent-600/40 bg-ink-950/40' : 'border-ink-800')}>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{heading}</p>
      <p className="tabular mt-1.5 text-2xl font-bold text-ink-50">{formatPercent(probability, 1)}</p>
      <div className="mt-2">
        <DecisionBadge decision={decision} />
      </div>
      <dl className="mt-3 flex flex-col gap-1 text-xs">
        <div className="flex justify-between gap-3">
          <dt className="text-ink-500">Expected net value</dt>
          <dd className="tabular text-ink-200">{formatCurrency(expectedNetValue, true)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-ink-500">Evidence coverage</dt>
          <dd className="tabular text-ink-200">{formatPercent(coverage, 0)}</dd>
        </div>
      </dl>
    </div>
  )
}

function Delta({ label, value, positive }: { label: string; value: string; positive: boolean }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className={cn('tabular mt-0.5 text-sm font-semibold', positive ? 'text-contest-600' : 'text-avoid-600')}>
        {value}
      </dd>
    </div>
  )
}

function formatSignedPercent(value: number): string {
  const formatted = formatPercent(Math.abs(value), 2)
  return `${value >= 0 ? '+' : '−'}${formatted}`
}
