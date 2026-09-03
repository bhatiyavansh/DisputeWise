import type { SimulationResponse } from '../../api/types'
import { formatCurrency, formatEvidenceType, formatPercent, formatSignedCurrency } from '../../utils/format'
import { DecisionBadge } from '../common/DecisionBadge'
import { RiskBandBadge } from '../common/RiskBandBadge'
import { Panel } from '../common/Panel'
import { ShapPanel } from '../case/ShapPanel'
import { EvidenceGapPanel } from '../case/EvidenceGapPanel'
import { RetrievedKnowledgePanel } from '../case/RetrievedKnowledgePanel'
import { ClaimVerificationList } from '../case/ClaimVerificationList'
import { DraftStateBanner } from '../case/DraftStateBanner'

/**
 * Scenario results. Every number is rendered exactly as the backend returned
 * it -- this component computes nothing, and in particular never derives a
 * decision from the probability (the backend's decision-v1 policy is the
 * only thing that decides).
 */
export function SimulationResult({ result }: { result: SimulationResponse }) {
  const { score, decision, generation } = result

  return (
    <div className="flex flex-col gap-5">
      <section className="rounded-lg border border-ink-800 bg-ink-900 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="tabular text-4xl font-bold text-ink-50">
              {formatPercent(score.calibrated_probability, 1)}
            </p>
            <p className="mt-1 text-sm text-ink-500">
              P(win) — calibrated{' '}
              <span className="tabular text-ink-400">(raw: {formatPercent(score.raw_probability, 1)})</span>
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <DecisionBadge decision={decision.decision} size="lg" />
            <RiskBandBadge band={score.risk_band} />
          </div>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-ink-800 pt-4 sm:grid-cols-4">
          <Metric label="Disputed" value={formatCurrency(decision.dispute_amount, true)} />
          <Metric label="Expected recovery" value={formatCurrency(decision.expected_recovery, true)} />
          <Metric label="Contest cost" value={formatCurrency(decision.contest_cost, true)} />
          <Metric
            label="Expected net value"
            value={formatSignedCurrency(decision.expected_net_value)}
            tone={decision.expected_net_value >= 0 ? 'positive' : 'negative'}
          />
        </dl>

        <blockquote className="mt-4 border-l-2 border-accent-600 pl-3 text-sm text-ink-200">
          {decision.reason}
        </blockquote>

        {decision.evidence_gap_downgrade && (
          <p className="mt-3 flex items-start gap-2 rounded border border-review-500/30 bg-review-50/5 px-3 py-2 text-xs text-review-700">
            <span aria-hidden="true">⚠</span>
            This scenario would otherwise qualify for CONTEST, but was routed to human review because
            high-relevance evidence for this reason code is missing.
          </p>
        )}
      </section>

      <ShapPanel positive={score.top_positive_factors} negative={score.top_negative_factors} />

      <EvidenceGapPanel gap={result.evidence_gap} />

      {result.retrieved_sources.length > 0 && <RetrievedKnowledgePanel sources={result.retrieved_sources} />}

      {generation && (
        <>
          <DraftStateBanner draft={generation} />
          {generation.response_body && (
            <Panel title="Drafted Response">
              {generation.summary && <p className="mb-3 text-sm font-medium text-ink-200">{generation.summary}</p>}
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-100">{generation.response_body}</p>
            </Panel>
          )}
          {generation.missing_evidence.length > 0 && (
            <Panel title="Missing evidence referenced by this reason code">
              <ul className="flex flex-wrap gap-2">
                {generation.missing_evidence.map((type) => (
                  <li
                    key={type}
                    className="rounded border border-avoid-500/30 bg-avoid-50/5 px-2 py-1 text-xs font-medium text-avoid-700"
                  >
                    {formatEvidenceType(type)}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          {generation.claims.length > 0 && (
            <ClaimVerificationList claims={generation.claims} verifications={generation.claim_verifications} />
          )}
        </>
      )}

      <Panel title="Provenance" subtitle="versions of every component that produced this scenario">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
          <TraceRow label="Simulation ID" value={result.trace.simulation_id} />
          <TraceRow label="Model" value={result.trace.model_version} />
          <TraceRow label="Feature schema" value={result.trace.feature_schema_version} />
          <TraceRow label="Decision policy" value={result.trace.decision_policy_version} />
          <TraceRow label="Evidence schema" value={result.trace.evidence_schema_version} />
          <TraceRow label="Knowledge base" value={result.trace.knowledge_base_version} />
          <TraceRow label="Retrieval config" value={result.trace.retrieval_config_version} />
          <TraceRow label="Prompt" value={result.trace.prompt_version} />
          <TraceRow label="Response schema" value={result.trace.response_schema_version} />
          <TraceRow label="Verifier" value={result.trace.verifier_version} />
          <TraceRow label="Generated at" value={result.trace.generated_at} />
          <TraceRow label="Persisted" value={result.trace.persisted ? 'yes' : 'no — scenario only'} />
        </dl>
        <p className="mt-4 border-t border-ink-800 pt-3 text-xs text-ink-500">{result.disclaimer}</p>
      </Panel>
    </div>
  )
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'positive' | 'negative' }) {
  const toneClass = tone === 'positive' ? 'text-contest-600' : tone === 'negative' ? 'text-avoid-600' : 'text-ink-50'
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className={`tabular mt-1 text-lg font-semibold ${toneClass}`}>{value}</dd>
    </div>
  )
}

function TraceRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-500">{label}</dt>
      {/* A stage that did not run reports no version rather than a plausible-looking one. */}
      <dd className="font-mono text-ink-300">{value ?? <span className="text-ink-600">not run</span>}</dd>
    </div>
  )
}
