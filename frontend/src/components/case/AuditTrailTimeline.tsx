import type { DecisionResponse, DraftResponse, EvidenceGapResponse, ScoreResponse } from '../../api/types'

/**
 * A vertical timeline of the real version/provenance strings each pipeline
 * stage returned for this case -- not a literal event log (none of these
 * endpoints return per-stage timestamps except response generation, which
 * does) and not a chain-of-thought transcript. Each entry only renders
 * fields the corresponding response actually included.
 */
export function AuditTrailTimeline({
  score,
  decision,
  gap,
  draft,
}: {
  score: ScoreResponse
  decision: DecisionResponse
  gap: EvidenceGapResponse | null
  draft: DraftResponse | null
}) {
  const stages: { title: string; rows: [string, string][] }[] = [
    {
      title: 'Risk scoring',
      rows: [
        ['Model', score.model_version],
        ['Feature schema', score.feature_schema_version],
        ['Calibration method', score.calibration_method],
      ],
    },
    {
      title: 'Economic decision',
      rows: [
        ['Decision policy', decision.decision_policy_version],
        ['Model', decision.model_version],
        ['Feature schema', decision.feature_schema_version],
      ],
    },
  ]

  if (gap) {
    stages.push({
      title: 'Evidence gap analysis',
      rows: [['Evidence schema', gap.schema_version]],
    })
  }

  if (draft) {
    stages.push({
      title: 'Knowledge retrieval',
      rows: [
        ['Knowledge base', draft.knowledge_base_version],
        ['Sources retrieved', String(draft.trace.retrieved_source_ids.length)],
        ['Chunks retrieved', String(draft.trace.retrieved_chunk_ids.length)],
      ],
    })
    stages.push({
      title: 'Response generation',
      rows: [
        ['Prompt', draft.prompt_version],
        ['Response schema', draft.response_schema_version],
        ['Generated at', draft.trace.generated_at],
        ['State', draft.response_state],
      ],
    })
    stages.push({
      title: 'Claim verification',
      rows: [
        ['Verifier', draft.verifier_version],
        ['Claims checked', String(draft.trace.claim_count)],
        ...Object.entries(draft.trace.claim_statuses).map(([status, count]) => [status, String(count)] as [string, string]),
      ],
    })
  }

  return (
    <ol className="flex flex-col gap-0">
      {stages.map((stage, index) => (
        <li key={stage.title} className="relative flex gap-4 pb-6">
          <div className="flex flex-col items-center">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full border-2 border-accent-500 bg-ink-950" aria-hidden="true" />
            {index < stages.length - 1 && <span className="mt-1 w-px flex-1 bg-ink-800" aria-hidden="true" />}
          </div>
          <div className="min-w-0 flex-1 pb-1">
            <h3 className="text-sm font-semibold text-ink-100">{stage.title}</h3>
            <dl className="mt-1.5 flex flex-col gap-1 text-xs">
              {stage.rows.map(([label, value]) => (
                <div key={label} className="flex gap-2">
                  <dt className="w-36 shrink-0 text-ink-500">{label}</dt>
                  <dd className="font-mono text-ink-300">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </li>
      ))}
    </ol>
  )
}
