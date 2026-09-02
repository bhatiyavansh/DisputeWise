/**
 * DEV-ONLY fixtures. These are REAL case IDs from the existing synthetic
 * dataset (data/generated/train/, seed 42) -- not fabricated -- selected by
 * querying the live backend so manual testing has a known, stable starting
 * point for each decision bucket. See docs/frontend.md for how to find more.
 *
 * Verified against the running backend on 2026-09-02:
 *   POST /cases/{id}/decision for each ID below returns the bucket listed.
 *
 * Not shown anywhere in a production build path other than the dev
 * QuickJump picker (src/components/common/DemoCasePicker.tsx).
 */

export interface DemoCase {
  caseId: string
  label: string
  description: string
}

export const DEMO_CASES: DemoCase[] = [
  {
    caseId: 'DSP-010035',
    label: 'High winnability → CONTEST',
    description: 'unauthorized_transaction, P(win) ≈ 96%, large positive expected net value, complete evidence.',
  },
  {
    caseId: 'DSP-028533',
    label: 'Borderline → HUMAN_REVIEW',
    description: 'duplicate_charge, P(win) ≈ 50%, expected net value near the decision boundary.',
  },
  {
    caseId: 'DSP-018767',
    label: 'Low winnability → DO_NOT_CONTEST',
    description: 'unauthorized_transaction, P(win) ≈ 9%, negative expected net value.',
  },
  {
    caseId: 'DSP-031597',
    label: 'Missing key evidence → CONTEST downgraded',
    description:
      'goods_not_received, P(win) ≈ 97% and strong economics, but proof_of_delivery is missing, so the ' +
      'decision engine routes it to HUMAN_REVIEW instead of CONTEST.',
  },
]
