import type { DecisionResponse, DraftResponse, EvidenceGapResponse, ScoreResponse } from '../../api/types'
import { cn } from '../../utils/cn'
import { formatEvidenceType, formatPercent } from '../../utils/format'

/**
 * Phase 7D -- provenance trail for one case.
 *
 * A reproducibility record, NOT hidden reasoning. It shows which component
 * version produced each stage's output, what that output referenced (source
 * IDs, evidence IDs, claim IDs) and how it was verified. The model's
 * internal reasoning is never requested, stored or displayed -- the backend
 * strips it, and there is nothing here that would render it.
 *
 * Stages that did not run say so. A stage is never given a plausible-looking
 * version string it did not actually report: generation that never ran shows
 * NOT RUN, and generation that failed shows FAILED with the real reason.
 */

type StageStatus = 'COMPLETE' | 'NOT RUN' | 'UNAVAILABLE' | 'FAILED' | 'BLOCKED' | 'BOUNDARY'

interface Stage {
  title: string
  status: StageStatus
  version?: string | null
  detail?: string
  rows?: [string, string][]
  /** Rendered as monospace chips (source/evidence/claim identifiers). */
  chips?: { label: string; items: string[] }[]
  claims?: { claim_id: string; status: string; explanation: string }[]
}

const STATUS_CLASSES: Record<StageStatus, string> = {
  COMPLETE: 'text-contest-600 border-contest-500/30 bg-contest-50/5',
  'NOT RUN': 'text-ink-500 border-ink-700 bg-ink-800/40',
  UNAVAILABLE: 'text-ink-400 border-ink-700 bg-ink-800/40',
  FAILED: 'text-avoid-600 border-avoid-500/30 bg-avoid-50/5',
  BLOCKED: 'text-avoid-600 border-avoid-500/30 bg-avoid-50/5',
  BOUNDARY: 'text-review-700 border-review-500/30 bg-review-50/5',
}

const DOT_CLASSES: Record<StageStatus, string> = {
  COMPLETE: 'border-accent-500',
  'NOT RUN': 'border-ink-700',
  UNAVAILABLE: 'border-ink-700',
  FAILED: 'border-avoid-500',
  BLOCKED: 'border-avoid-500',
  BOUNDARY: 'border-review-500',
}

const CLAIM_STATUS_CLASSES: Record<string, string> = {
  SUPPORTED: 'text-contest-600',
  PARTIALLY_SUPPORTED: 'text-review-700',
  INCOMPLETE: 'text-review-700',
  UNSUPPORTED: 'text-avoid-600',
  INVALID_REFERENCE: 'text-avoid-600',
}

function generationStages(draft: DraftResponse | null): Stage[] {
  if (!draft) {
    return [
      { title: 'Knowledge retrieval', status: 'NOT RUN', detail: 'Response generation has not been requested for this case.' },
      { title: 'Response generation', status: 'NOT RUN' },
      { title: 'Claim verification', status: 'NOT RUN' },
    ]
  }

  const retrieval: Stage = {
    title: 'Knowledge retrieval',
    status: 'COMPLETE',
    version: draft.knowledge_base_version,
    rows: [
      ['Retrieval config', draft.trace.retrieval_config_version],
      ['Chunks retrieved', String(draft.trace.retrieved_chunk_ids.length)],
    ],
    chips: [
      { label: 'Source IDs', items: draft.trace.retrieved_source_ids },
      { label: 'Chunk IDs', items: draft.trace.retrieved_chunk_ids },
    ],
  }

  // The provider was never reachable/configured: no draft exists at all.
  if (draft.response_state === 'GENERATION_UNAVAILABLE') {
    return [
      retrieval,
      {
        title: 'Response generation',
        status: 'UNAVAILABLE',
        detail: draft.response_state_reason,
      },
      { title: 'Claim verification', status: 'NOT RUN', detail: 'Nothing was generated to verify.' },
    ]
  }

  // Generation was attempted but produced nothing usable.
  if (!draft.response_body && draft.claims.length === 0) {
    return [
      retrieval,
      {
        title: 'Response generation',
        status: 'FAILED',
        version: draft.prompt_version,
        detail: draft.response_state_reason,
      },
      { title: 'Claim verification', status: 'NOT RUN', detail: 'No claims were produced to verify.' },
    ]
  }

  const blocked = draft.response_state === 'DRAFT_BLOCKED'
  return [
    retrieval,
    {
      title: 'Response generation',
      status: 'COMPLETE',
      version: draft.prompt_version,
      rows: [
        ['Response schema', draft.response_schema_version],
        ['Claims generated', String(draft.claims.length)],
        ['Generated at', draft.trace.generated_at],
      ],
      chips: [
        { label: 'Claim IDs', items: draft.claims.map((claim) => claim.claim_id) },
        { label: 'Cited evidence IDs', items: draft.trace.cited_evidence_ids },
      ],
    },
    {
      title: 'Claim verification',
      status: blocked ? 'BLOCKED' : 'COMPLETE',
      version: draft.verifier_version,
      detail: draft.response_state_reason,
      rows: Object.entries(draft.trace.claim_statuses).map(
        ([status, count]) => [status.replace(/_/g, ' '), String(count)] as [string, string],
      ),
      claims: draft.claim_verifications.map((verification) => ({
        claim_id: verification.claim_id,
        status: verification.status,
        explanation: verification.explanation,
      })),
    },
  ]
}

export function AuditTrailTimeline({
  caseId,
  score,
  decision,
  gap,
  draft,
}: {
  caseId: string
  score: ScoreResponse
  decision: DecisionResponse
  gap: EvidenceGapResponse | null
  draft: DraftResponse | null
}) {
  const stages: Stage[] = [
    {
      title: 'Case',
      status: 'COMPLETE',
      detail: `${caseId} — ${decision.reason_code.replace(/_/g, ' ')}`,
    },
    {
      title: 'Feature construction',
      status: 'COMPLETE',
      version: score.feature_schema_version,
      detail: 'Leakage-safe: the outcomes table is not an input to feature construction.',
    },
    {
      title: 'Risk model',
      status: 'COMPLETE',
      version: score.model_version,
      rows: [
        ['Calibration', score.calibration_method],
        ['Raw probability', formatPercent(score.raw_probability, 2)],
        ['Calibrated probability', formatPercent(score.calibrated_probability, 2)],
        ['Risk band', score.risk_band.replace(/_/g, ' ')],
      ],
    },
    {
      title: 'Decision policy',
      status: 'COMPLETE',
      version: decision.decision_policy_version,
      rows: [
        ['Decision', decision.decision.replace(/_/g, ' ')],
        ['Expected net value', decision.expected_net_value.toFixed(2)],
        ['Evidence-gap downgrade', decision.evidence_gap_downgrade ? 'yes' : 'no'],
      ],
      detail: decision.reason,
    },
    gap
      ? {
          title: 'Evidence gap analysis',
          status: 'COMPLETE',
          version: gap.schema_version,
          rows: [
            ['Required', String(gap.coverage.required)],
            ['Available', String(gap.coverage.available)],
            ['Missing', String(gap.coverage.missing)],
          ],
          chips: [
            {
              label: 'Reference source IDs',
              items: Array.from(new Set(gap.items.map((item) => item.source_id))),
            },
            {
              label: 'Missing evidence',
              items: gap.items
                .filter((item) => item.status === 'MISSING' && item.required)
                .map((item) => formatEvidenceType(item.evidence_type)),
            },
          ],
        }
      : { title: 'Evidence gap analysis', status: 'NOT RUN' as StageStatus },
    ...generationStages(draft),
    {
      title: 'Human approval boundary',
      status: 'BOUNDARY',
      detail:
        'DisputeWise prepares and verifies. It does not submit to a card network, contact the customer, or change the ' +
        'dispute status. An analyst reviews and acts.',
    },
  ]

  return (
    <>
      <ol className="flex flex-col gap-0">
        {stages.map((stage, index) => (
          <li key={stage.title} className="relative flex gap-4 pb-6 last:pb-0">
            <div className="flex flex-col items-center">
              <span
                className={cn('h-2.5 w-2.5 shrink-0 rounded-full border-2 bg-ink-950', DOT_CLASSES[stage.status])}
                aria-hidden="true"
              />
              {index < stages.length - 1 && <span className="mt-1 w-px flex-1 bg-ink-800" aria-hidden="true" />}
            </div>

            <div className="min-w-0 flex-1 pb-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-ink-100">{stage.title}</h3>
                <span
                  className={cn(
                    'rounded border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide',
                    STATUS_CLASSES[stage.status],
                  )}
                >
                  {stage.status}
                </span>
                {stage.version && <span className="font-mono text-xs text-ink-400">{stage.version}</span>}
              </div>

              {stage.detail && <p className="mt-1 text-xs leading-relaxed text-ink-400">{stage.detail}</p>}

              {stage.rows && stage.rows.length > 0 && (
                <dl className="mt-1.5 flex flex-col gap-1 text-xs">
                  {stage.rows.map(([label, value]) => (
                    <div key={label} className="flex gap-2">
                      <dt className="w-40 shrink-0 text-ink-500">{label}</dt>
                      <dd className="tabular font-mono text-ink-300">{value}</dd>
                    </div>
                  ))}
                </dl>
              )}

              {stage.chips?.map((chip) =>
                chip.items.length > 0 ? (
                  <div key={chip.label} className="mt-2">
                    <p className="text-[11px] uppercase tracking-wide text-ink-600">{chip.label}</p>
                    <ul className="mt-1 flex flex-wrap gap-1">
                      {chip.items.map((item) => (
                        <li
                          key={item}
                          className="rounded border border-ink-800 bg-ink-950/60 px-1.5 py-0.5 font-mono text-[11px] text-ink-400"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null,
              )}

              {stage.claims && stage.claims.length > 0 && (
                <ul className="mt-2 flex flex-col divide-y divide-ink-800 overflow-hidden rounded border border-ink-800">
                  {stage.claims.map((claim) => (
                    <li key={claim.claim_id} className="px-2.5 py-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[11px] text-ink-300">{claim.claim_id}</span>
                        <span
                          className={cn(
                            'text-[11px] font-medium uppercase',
                            CLAIM_STATUS_CLASSES[claim.status] ?? 'text-ink-400',
                          )}
                        >
                          {claim.status.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-ink-500">{claim.explanation}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        ))}
      </ol>

      <p className="mt-5 border-t border-ink-800 pt-3 text-xs text-ink-500">
        This is a provenance record, not model reasoning. Chain-of-thought is never requested, stored or displayed —
        only the versions, inputs, outputs and verification results above.
      </p>
    </>
  )
}
