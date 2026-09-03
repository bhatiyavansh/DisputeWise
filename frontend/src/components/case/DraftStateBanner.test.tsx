import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DraftStateBanner } from './DraftStateBanner'
import { classifyDraftError, classifyDraftResponse } from './draftOutcome'
import { ApiError } from '../../api/client'

/**
 * The AI Response tab must tell six situations apart, and must never present
 * one as another -- in particular, an AI-provider outage is a successful HTTP
 * exchange and must never be reported as an unreachable backend.
 */
describe('draft outcome classification', () => {
  it('A: a transport failure is the only "Backend unreachable" case', () => {
    const outcome = classifyDraftError(new ApiError('network', 'Failed to fetch'))
    expect(outcome.kind).toBe('network')
    expect(outcome.title).toBe('Backend unreachable')
    expect(outcome.message).toMatch(/could not reach the backend/i)
  })

  it('A: an aborted/timed-out request is still a transport failure', () => {
    const outcome = classifyDraftError(new ApiError('network', 'The request timed out or was cancelled.'))
    expect(outcome.title).toBe('Backend unreachable')
  })

  it('B: provider_unavailable is NOT classified as backend unreachable', () => {
    const outcome = classifyDraftResponse({
      response_state: 'DRAFT_BLOCKED', // the backend's Phase 4 representation
      response_state_reason: "Generation failed: provider 'openrouter' reported an upstream error (502)",
      generation_error_kind: 'provider_unavailable',
    })
    expect(outcome.kind).toBe('provider_unavailable')
    expect(outcome.title).toBe('AI generation temporarily unavailable')
    expect(outcome.title).not.toMatch(/unreachable/i)
    expect(outcome.message).toMatch(/risk analysis is available/i)
    expect(outcome.analysisStillAvailable).toBe(true)
  })

  it('C: unusable model output is a generation failure, not a verifier block', () => {
    const outcome = classifyDraftResponse({
      response_state: 'DRAFT_BLOCKED',
      response_state_reason: 'Generation failed: output failed schema validation',
      generation_error_kind: 'invalid_output',
    })
    expect(outcome.kind).toBe('generation_failed')
    expect(outcome.title).toBe('AI generation failed')
  })

  it('D: a verifier rejection is not a backend or provider failure', () => {
    const outcome = classifyDraftResponse({
      response_state: 'DRAFT_BLOCKED',
      response_state_reason: 'Response contains 1 unsupported material claim (C10).',
      generation_error_kind: null,
    })
    expect(outcome.kind).toBe('verifier_blocked')
    expect(outcome.title).toBe('AI response blocked')
    expect(outcome.message).toMatch(/could not be verified against the case evidence/i)
  })

  it('E: no configured provider is reported as generation unavailable', () => {
    const outcome = classifyDraftResponse({
      response_state: 'GENERATION_UNAVAILABLE',
      response_state_reason: 'No LLM provider is configured.',
      generation_error_kind: null,
    })
    expect(outcome.kind).toBe('generation_unavailable')
    expect(outcome.title).toBe('AI generation unavailable')
    expect(outcome.message).toMatch(/not configured/i)
  })

  it('F: a verified draft is ready', () => {
    const outcome = classifyDraftResponse({
      response_state: 'DRAFT_READY',
      response_state_reason: 'All material claims are supported.',
      generation_error_kind: null,
    })
    expect(outcome.kind).toBe('ready')
    expect(outcome.title).toBe('Draft ready')
  })

  it('classifies from the response contract, never from HTTP status', () => {
    // Identical response_state, opposite meanings -- only the additive
    // generation_error_kind field separates them.
    const blocked = classifyDraftResponse({
      response_state: 'DRAFT_BLOCKED',
      response_state_reason: 'x',
      generation_error_kind: null,
    })
    const outage = classifyDraftResponse({
      response_state: 'DRAFT_BLOCKED',
      response_state_reason: 'x',
      generation_error_kind: 'provider_unavailable',
    })
    expect(blocked.kind).toBe('verifier_blocked')
    expect(outage.kind).toBe('provider_unavailable')
  })
})

describe('DraftStateBanner', () => {
  it('renders a provider outage without blaming the verifier or the backend', () => {
    render(
      <DraftStateBanner
        draft={{
          response_state: 'DRAFT_BLOCKED',
          response_state_reason: 'Generation failed: upstream 502 (Service temporarily overloaded)',
          generation_error_kind: 'provider_unavailable',
        }}
      />,
    )
    expect(screen.getByText('AI generation temporarily unavailable')).toBeInTheDocument()
    expect(screen.queryByText('Backend unreachable')).not.toBeInTheDocument()
    expect(screen.queryByText('AI response blocked')).not.toBeInTheDocument()
    // the backend's own machine reason is still shown verbatim
    expect(screen.getByText(/Service temporarily overloaded/)).toBeInTheDocument()
    expect(screen.getByText(/nothing was verified/i)).toBeInTheDocument()
  })

  it('renders a verifier block distinctly', () => {
    render(
      <DraftStateBanner
        draft={{
          response_state: 'DRAFT_BLOCKED',
          response_state_reason: 'Response contains 1 unsupported material claim (C10).',
          generation_error_kind: null,
        }}
      />,
    )
    expect(screen.getByText('AI response blocked')).toBeInTheDocument()
    expect(screen.queryByText(/temporarily unavailable/i)).not.toBeInTheDocument()
  })

  it('never implies a usable draft exists in any failure state', () => {
    for (const draft of [
      { response_state: 'DRAFT_BLOCKED', response_state_reason: 'r', generation_error_kind: null },
      { response_state: 'DRAFT_BLOCKED', response_state_reason: 'r', generation_error_kind: 'provider_unavailable' },
      { response_state: 'GENERATION_UNAVAILABLE', response_state_reason: 'r', generation_error_kind: null },
    ] as const) {
      const { unmount } = render(<DraftStateBanner draft={draft} />)
      expect(screen.queryByText('Draft ready')).not.toBeInTheDocument()
      unmount()
    }
  })
})
