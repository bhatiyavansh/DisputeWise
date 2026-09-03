import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DraftStateBanner } from './DraftStateBanner'

/**
 * Phase 8, item 12 -- the UI must tell these five situations apart, and must
 * never present one as another. (Backend/network failure is the sixth, and is
 * handled a level up by ErrorState, since no response arrives at all.)
 */
describe('DraftStateBanner', () => {
  it('shows a verified draft as ready', () => {
    render(<DraftStateBanner state="DRAFT_READY" reason="All material claims are supported." />)
    expect(screen.getByText('Draft ready')).toBeInTheDocument()
  })

  it('shows a verifier rejection as blocked BY THE VERIFIER', () => {
    render(
      <DraftStateBanner
        state="DRAFT_BLOCKED"
        reason="Response contains 1 unsupported material claim (C10)."
        errorKind={null}
      />,
    )
    expect(screen.getByText('Draft blocked by verifier')).toBeInTheDocument()
    expect(screen.getByText(/unsupported material claim/)).toBeInTheDocument()
    // must NOT blame the provider
    expect(screen.queryByText(/temporarily unavailable/)).not.toBeInTheDocument()
  })

  it('shows a provider outage as an availability problem, not a verifier rejection', () => {
    render(
      <DraftStateBanner
        state="DRAFT_BLOCKED"
        reason="Generation failed: provider 'openrouter' failed to generate: HTTP 429"
        errorKind="provider_unavailable"
      />,
    )
    expect(screen.getByText('AI generation temporarily unavailable')).toBeInTheDocument()
    // the verifier must not be blamed for a draft that was never written
    expect(screen.queryByText('Draft blocked by verifier')).not.toBeInTheDocument()
    expect(screen.getByText(/nothing was verified/i)).toBeInTheDocument()
  })

  it('shows unusable model output distinctly from an outage', () => {
    render(
      <DraftStateBanner
        state="DRAFT_BLOCKED"
        reason="Generation failed: output failed schema validation"
        errorKind="invalid_output"
      />,
    )
    expect(screen.getByText('AI generation returned unusable output')).toBeInTheDocument()
    expect(screen.queryByText('Draft blocked by verifier')).not.toBeInTheDocument()
  })

  it('shows an unconfigured provider as generation unavailable', () => {
    render(
      <DraftStateBanner
        state="GENERATION_UNAVAILABLE"
        reason="No LLM provider is configured."
        errorKind={null}
      />,
    )
    expect(screen.getByText('AI generation unavailable')).toBeInTheDocument()
  })

  it('never implies a usable draft exists in any failure state', () => {
    for (const [state, kind] of [
      ['DRAFT_BLOCKED', null],
      ['DRAFT_BLOCKED', 'provider_unavailable'],
      ['GENERATION_UNAVAILABLE', null],
    ] as const) {
      const { unmount } = render(<DraftStateBanner state={state} reason="reason" errorKind={kind} />)
      expect(screen.queryByText('Draft ready')).not.toBeInTheDocument()
      unmount()
    }
  })
})
