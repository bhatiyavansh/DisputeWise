import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AuditTrailTimeline } from './AuditTrailTimeline'
import { EVIDENCE_GAP_RESPONSE, SCORE_RESPONSE, makeDecision, makeDraft } from '../../tests/fixtures'

function renderTrail(draft: Parameters<typeof AuditTrailTimeline>[0]['draft'] = null) {
  return render(
    <AuditTrailTimeline
      caseId="DSP-031597"
      score={SCORE_RESPONSE}
      decision={makeDecision()}
      gap={EVIDENCE_GAP_RESPONSE}
      draft={draft}
    />,
  )
}

describe('AuditTrailTimeline', () => {
  it('shows the full deterministic chain with real versions', () => {
    renderTrail()
    for (const stage of [
      'Case',
      'Feature construction',
      'Risk model',
      'Decision policy',
      'Evidence gap analysis',
      'Knowledge retrieval',
      'Response generation',
      'Claim verification',
      'Human approval boundary',
    ]) {
      expect(screen.getByText(stage)).toBeInTheDocument()
    }
    expect(screen.getByText('features-v1')).toBeInTheDocument()
    expect(screen.getByText('risk-v1')).toBeInTheDocument()
    expect(screen.getByText('decision-v1')).toBeInTheDocument()
    expect(screen.getByText('evidence-v1')).toBeInTheDocument()
  })

  it('marks generation stages NOT RUN, without inventing versions', () => {
    renderTrail(null)
    expect(screen.getAllByText('NOT RUN').length).toBe(3)
    // no generation-side version may appear when generation never ran
    expect(screen.queryByText('prompt-v1.1')).not.toBeInTheDocument()
    expect(screen.queryByText('verifier-v1.1')).not.toBeInTheDocument()
    expect(screen.queryByText('knowledge-v1')).not.toBeInTheDocument()
  })

  it('renders a completed pipeline with claim IDs and verification states', () => {
    renderTrail(makeDraft())
    expect(screen.getByText('knowledge-v1')).toBeInTheDocument()
    expect(screen.getByText('prompt-v1.1')).toBeInTheDocument()
    expect(screen.getByText('verifier-v1.1')).toBeInTheDocument()
    // claim ids appear both as generation chips and in the verification list
    expect(screen.getAllByText('CLAIM-1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('SUPPORTED').length).toBeGreaterThan(0)
  })

  it('distinguishes generation unavailable from generation failed', () => {
    renderTrail(
      makeDraft({
        response_state: 'GENERATION_UNAVAILABLE',
        response_state_reason: 'No LLM provider is configured.',
        response_body: null,
        claims: [],
        claim_verifications: [],
      }),
    )
    expect(screen.getByText('UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByText(/No LLM provider is configured/)).toBeInTheDocument()
    // retrieval still ran, so its version is real and shown
    expect(screen.getByText('knowledge-v1')).toBeInTheDocument()
  })

  it('shows a provider failure as FAILED with the real reason', () => {
    renderTrail(
      makeDraft({
        response_state: 'DRAFT_BLOCKED',
        response_state_reason:
          "Generation failed: provider 'openrouter' reported an upstream error: Service temporarily overloaded",
        response_body: null,
        claims: [],
        claim_verifications: [],
      }),
    )
    expect(screen.getByText('FAILED')).toBeInTheDocument()
    expect(screen.getByText(/Service temporarily overloaded/)).toBeInTheDocument()
  })

  it('shows a verifier-blocked draft as BLOCKED with the blocking claim', () => {
    renderTrail(
      makeDraft({
        response_state: 'DRAFT_BLOCKED',
        response_state_reason: 'Response contains 1 unsupported material claim (C1).',
        claim_verifications: [
          {
            claim_id: 'C1',
            status: 'UNSUPPORTED',
            evidence_ids: [],
            source_ids: [],
            explanation: 'No evidence on file supports this claim.',
            verifier_version: 'verifier-v1.1',
          },
        ],
        trace: { ...makeDraft().trace, claim_statuses: { UNSUPPORTED: 1 } },
      }),
    )
    expect(screen.getByText('BLOCKED')).toBeInTheDocument()
    // once in the status tally, once on the claim itself
    expect(screen.getAllByText('UNSUPPORTED').length).toBe(2)
    expect(screen.getByText(/No evidence on file supports this claim/)).toBeInTheDocument()
  })

  it('always states the human approval boundary', () => {
    renderTrail(makeDraft())
    expect(screen.getByText('BOUNDARY')).toBeInTheDocument()
    expect(screen.getByText(/does not submit to a card network/)).toBeInTheDocument()
  })

  it('never displays chain-of-thought and says so', () => {
    renderTrail(makeDraft())
    expect(screen.getByText(/Chain-of-thought is never requested/)).toBeInTheDocument()
    for (const term of [/reasoning trace/i, /thought process/i, /internal reasoning:/i]) {
      expect(screen.queryByText(term)).not.toBeInTheDocument()
    }
  })
})
