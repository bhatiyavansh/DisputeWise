import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getPolicyDefaults, simulatePolicy } from '../api/portfolio'
import type { Decision, PolicyConfig, PolicySimulationResponse, PolicySummary } from '../api/types'
import { ErrorState } from '../components/common/ErrorState'
import { InlineSpinner, SkeletonCard } from '../components/common/LoadingStates'
import { Panel } from '../components/common/Panel'
import { NumberField } from '../components/simulation/FormControls'
import { cn } from '../utils/cn'
import { formatCurrency } from '../utils/format'

const DECISIONS: Decision[] = ['CONTEST', 'HUMAN_REVIEW', 'DO_NOT_CONTEST']

/**
 * Phase 7B -- decision policy playground.
 *
 * A UI around the EXISTING decision engine: every routing and economic
 * figure below is computed by the backend under a throwaway policy config.
 * No threshold or expected-value math is duplicated here. The production
 * decision-v1 configuration is never modified.
 */
export function PolicyPlaygroundPage() {
  const [config, setConfig] = useState<PolicyConfig | null>(null)
  const [defaults, setDefaults] = useState<PolicyConfig | null>(null)
  const [meta, setMeta] = useState<{ version: string; economics: string; note: string } | null>(null)
  const [result, setResult] = useState<PolicySimulationResponse | null>(null)
  const [status, setStatus] = useState<'loading' | 'idle' | 'running' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)

  useEffect(() => {
    let cancelled = false
    getPolicyDefaults()
      .then((response) => {
        if (cancelled) return
        setConfig(response.defaults)
        setDefaults(response.defaults)
        setMeta({
          version: response.decision_policy_version,
          economics: response.economics_explanation,
          note: response.note,
        })
        setStatus('idle')
      })
      .catch((caught) => {
        if (cancelled) return
        setError(caught instanceof ApiError ? caught : new ApiError('network', 'Unexpected error', null, caught))
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function run() {
    if (!config) return
    setStatus('running')
    setError(null)
    try {
      setResult(await simulatePolicy(config))
      setStatus('idle')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError('network', 'Unexpected error', null, caught))
      setStatus('error')
    }
  }

  function reset() {
    if (defaults) setConfig({ ...defaults })
    setResult(null)
  }

  function set<K extends keyof PolicyConfig>(key: K, value: PolicyConfig[K]) {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  if (status === 'loading') return <SkeletonCard />
  if (!config || !defaults || !meta) {
    return <ErrorState error={error} title="Policy configuration unavailable" />
  }

  const isDefault = (Object.keys(defaults) as (keyof PolicyConfig)[]).every((key) => config[key] === defaults[key])

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-semibold tracking-tight text-ink-50">Decision policy playground</h1>
            <span className="rounded border border-review-500/40 bg-review-50/5 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-review-700">
              Policy simulation
            </span>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-ink-400">
            Change the operating economics and see how the portfolio would be routed. Production{' '}
            <span className="font-mono text-ink-300">{meta.version}</span> is never modified.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={reset}
            disabled={isDefault && !result}
            className="rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-sm font-medium text-ink-200 transition-colors hover:bg-ink-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
          >
            Reset to default
          </button>
          <button
            type="button"
            onClick={run}
            disabled={status === 'running'}
            className="rounded bg-accent-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500"
          >
            {status === 'running' ? 'Routing…' : 'Run policy'}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void run()
          }}
          className="h-fit rounded-lg border border-ink-800 bg-ink-900 px-5 py-4"
        >
          <h2 className="text-sm font-semibold text-ink-100">Operating economics</h2>
          <div className="mt-2 flex flex-col">
            <NumberField
              label="Contest cost"
              hint={`default ₹${defaults.contest_cost}`}
              value={config.contest_cost}
              onChange={(v) => set('contest_cost', v)}
              prefix="₹"
            />
            <NumberField
              label="Recovery rate"
              hint="fraction of the dispute recovered on a win"
              value={config.recovery_rate}
              onChange={(v) => set('recovery_rate', v)}
              step={0.05}
            />
            <NumberField
              label="High-confidence P(win)"
              hint="minimum to be eligible for CONTEST"
              value={config.high_confidence_probability}
              onChange={(v) => set('high_confidence_probability', v)}
              step={0.05}
            />
            <NumberField
              label="Low-confidence P(win)"
              hint="maximum to be eligible for DO_NOT_CONTEST"
              value={config.low_confidence_probability}
              onChange={(v) => set('low_confidence_probability', v)}
              step={0.05}
            />
            <NumberField
              label="Min expected net value"
              value={config.min_expected_net_value}
              onChange={(v) => set('min_expected_net_value', v)}
              prefix="₹"
            />
            <NumberField
              label="Review margin"
              hint="band around the minimum that always goes to review"
              value={config.review_margin}
              onChange={(v) => set('review_margin', v)}
              prefix="₹"
            />
          </div>
          <p className="mt-4 border-t border-ink-800 pt-3 text-xs leading-relaxed text-ink-500">
            {meta.economics}
          </p>
        </form>

        <div className="min-w-0">
          {status === 'error' && (
            <ErrorState
              error={error}
              title={error?.kind === 'invalid' ? 'This policy was rejected' : undefined}
              onRetry={() => void run()}
            />
          )}
          {status === 'running' && (
            <div className="rounded-lg border border-ink-800 bg-ink-900 px-5 py-10 text-center">
              <InlineSpinner label="Re-routing the portfolio…" />
            </div>
          )}
          {status !== 'running' && status !== 'error' && !result && (
            <div className="rounded-lg border border-dashed border-ink-800 px-5 py-10 text-center">
              <p className="text-sm text-ink-400">Adjust the economics, then run the policy.</p>
              <p className="mt-1 text-xs text-ink-600">
                Routing is compared against production {meta.version} and a contest-everything baseline.
              </p>
            </div>
          )}
          {status !== 'running' && result && <PolicyResults result={result} />}
        </div>
      </div>
    </div>
  )
}

function PolicyResults({ result }: { result: PolicySimulationResponse }) {
  const baseline = result.contest_everything_baseline
  const scenario = result.scenario_policy
  const defaultPolicy = result.default_policy

  const baselineBeatsDefault =
    baseline.portfolio.contest_only_realized_net_value > defaultPolicy.portfolio.contest_only_realized_net_value

  return (
    <div className="flex flex-col gap-5">
      <Panel
        title="Routing"
        subtitle={`${result.n_cases.toLocaleString()} cases · ${result.split} split`}
        action={
          result.changed_fields.length > 0 ? (
            <span className="text-xs text-review-700">{result.changed_fields.length} parameter(s) changed</span>
          ) : (
            <span className="text-xs text-ink-500">unchanged from default</span>
          )
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead>
              <tr className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-ink-500">
                <th className="pb-2 font-medium">Decision</th>
                <th className="pb-2 text-right font-medium">Default</th>
                <th className="pb-2 text-right font-medium">Scenario</th>
                <th className="pb-2 text-right font-medium">Change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {DECISIONS.map((decision) => {
                const before = defaultPolicy.buckets[decision]
                const after = scenario.buckets[decision]
                const delta = after.count - before.count
                return (
                  <tr key={decision}>
                    <td className="py-2.5 text-ink-200">{decision.replace(/_/g, ' ')}</td>
                    <td className="tabular py-2.5 text-right text-ink-400">
                      {before.count.toLocaleString()} ({before.percentage.toFixed(1)}%)
                    </td>
                    <td className="tabular py-2.5 text-right text-ink-100">
                      {after.count.toLocaleString()} ({after.percentage.toFixed(1)}%)
                    </td>
                    <td
                      className={cn(
                        'tabular py-2.5 text-right',
                        delta === 0 ? 'text-ink-600' : delta > 0 ? 'text-contest-600' : 'text-avoid-600',
                      )}
                    >
                      {delta === 0 ? '—' : `${delta > 0 ? '+' : ''}${delta.toLocaleString()}`}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Value captured" subtitle="only contested cases can recover, and each incurs the contest cost">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead>
              <tr className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-ink-500">
                <th className="pb-2 font-medium">Policy</th>
                <th className="pb-2 text-right font-medium">Contested</th>
                <th className="pb-2 text-right font-medium">Expected net</th>
                <th className="pb-2 text-right font-medium">Realized net</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              <ValueRow label={`Production ${result.decision_policy_version}`} summary={defaultPolicy} />
              <ValueRow label="Scenario policy" summary={scenario} highlight />
              <ValueRow label="Contest everything (baseline)" summary={baseline} />
            </tbody>
          </table>
        </div>

        {baselineBeatsDefault && (
          <p className="mt-4 rounded border border-review-500/30 bg-review-50/5 px-3 py-2.5 text-xs leading-relaxed text-review-700">
            <span className="font-medium">Policy sensitivity:</span> at a contest cost of ₹
            {result.scenario_config.contest_cost.toLocaleString()}, contesting everything captures more realized
            value than the default routing — the assumed cost is small relative to typical dispute value, so even
            low-probability cases are worth filing. This is a real property of the current cost assumption, not a
            model failure. Raise the contest cost to see routing start to matter.
          </p>
        )}

        <p className="mt-3 text-xs text-ink-500">{result.note}</p>
      </Panel>
    </div>
  )
}

function ValueRow({
  label,
  summary,
  highlight,
}: {
  label: string
  summary: PolicySummary
  highlight?: boolean
}) {
  return (
    <tr className={cn(highlight && 'bg-ink-950/40')}>
      <td className="py-2.5 text-ink-200">{label}</td>
      <td className="tabular py-2.5 text-right text-ink-300">
        {summary.portfolio.contest_volume.toLocaleString()}
      </td>
      <td className="tabular py-2.5 text-right text-ink-300">
        {formatCurrency(summary.portfolio.contest_only_expected_net_value, true)}
      </td>
      <td className="tabular py-2.5 text-right font-medium text-ink-100">
        {formatCurrency(summary.portfolio.contest_only_realized_net_value, true)}
      </td>
    </tr>
  )
}
