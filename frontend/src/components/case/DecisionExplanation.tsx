import type { DecisionResponse } from '../../api/types'
import { Panel } from '../common/Panel'

/**
 * The backend's own deterministic `reason` string is the primary content
 * here -- verbatim, never rewritten. The checklist below it restates the
 * SAME numbers already shown in the Economic Decision panel as simple
 * true/false facts (expected recovery vs. contest cost, probability vs.
 * break-even, evidence coverage); nothing here is invented reasoning beyond
 * what those numbers already say.
 */
export function DecisionExplanation({ decision }: { decision: DecisionResponse }) {
  const recoveryExceedsCost = decision.expected_recovery > decision.contest_cost
  const aboveBreakEven =
    decision.break_even_probability !== null && decision.calibrated_probability > decision.break_even_probability
  const evidenceStrong = decision.evidence_summary.total > 0 && decision.evidence_summary.available / decision.evidence_summary.total >= 0.75
  const evidenceGap = decision.evidence_gap_downgrade

  return (
    <Panel title="Why this decision?" subtitle="Economic reasoning -- separate from the model's own reasoning above">
      <blockquote className="border-l-2 border-accent-600 pl-3 text-sm text-ink-200">{decision.reason}</blockquote>

      <ul className="mt-4 flex flex-col gap-1.5 text-sm">
        <ChecklistItem ok={recoveryExceedsCost} label="Expected recovery exceeds contest cost" />
        <ChecklistItem ok={aboveBreakEven} label="Win probability is above the economic break-even point" />
        <ChecklistItem ok={evidenceStrong} label="Evidence coverage is strong (≥75% available)" />
        {evidenceGap && (
          <ChecklistItem
            ok={false}
            label="High-relevance evidence for this reason code is missing -- CONTEST was downgraded to review"
          />
        )}
      </ul>
    </Panel>
  )
}

function ChecklistItem({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-start gap-2">
      <span className={ok ? 'text-contest-500' : 'text-avoid-500'} aria-hidden="true">
        {ok ? '✓' : '✕'}
      </span>
      <span className="text-ink-300">{label}</span>
    </li>
  )
}
