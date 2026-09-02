import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EconomicDecisionPanel } from './EconomicDecisionPanel'
import { makeDecision } from '../../tests/fixtures'

describe('EconomicDecisionPanel', () => {
  it('renders a CONTEST decision using the backend-provided numbers verbatim', () => {
    const decision = makeDecision({ decision: 'CONTEST', expected_net_value: 7928, calibrated_probability: 0.968 })
    render(<EconomicDecisionPanel decision={decision} source="real" />)

    expect(screen.getByText('Contest')).toBeInTheDocument()
    // 7928 formatted with no decimals by the currency formatter -> "+₹7,928"
    // (appears twice: the headline field and the sensitivity table's "current" column)
    expect(screen.getAllByText(/\+₹7,928/).length).toBeGreaterThan(0)
  })

  it('renders a HUMAN_REVIEW decision correctly', () => {
    const decision = makeDecision({
      decision: 'HUMAN_REVIEW',
      reason: 'Routed to human review: expected net value is close to the decision boundary.',
      expected_net_value: 12,
    })
    render(<EconomicDecisionPanel decision={decision} source="real" />)
    expect(screen.getByText('Human Review')).toBeInTheDocument()
  })

  it('renders a DO_NOT_CONTEST decision correctly, including a negative expected net value', () => {
    const decision = makeDecision({
      decision: 'DO_NOT_CONTEST',
      expected_net_value: -80,
      expected_recovery: 220,
      contest_cost: 300,
    })
    render(<EconomicDecisionPanel decision={decision} source="real" />)

    expect(screen.getByText("Don't Contest")).toBeInTheDocument()
    expect(screen.getByText(/−₹80/)).toBeInTheDocument()
  })

  it('renders exactly the backend numbers -- never a frontend-recomputed value', () => {
    // Deliberately inconsistent numbers (a frontend recompute would show something
    // different from raw_probability * recoverable_amount - cost); the panel must
    // still show the backend's own expected_net_value untouched.
    const decision = makeDecision({
      calibrated_probability: 0.5,
      recoverable_amount: 1000,
      contest_cost: 300,
      expected_recovery: 999999, // intentionally not 0.5 * 1000
      expected_net_value: 555, // intentionally not 999999 - 300
    })
    render(<EconomicDecisionPanel decision={decision} source="real" />)
    expect(screen.getByText(/\+₹555/)).toBeInTheDocument()
  })

  it('shows the DEV MOCK badge only when the decision came from the mock adapter', () => {
    const decision = makeDecision()
    const { rerender } = render(<EconomicDecisionPanel decision={decision} source="real" />)
    expect(screen.queryByText(/Dev Mock/i)).not.toBeInTheDocument()

    rerender(<EconomicDecisionPanel decision={decision} source="mock" />)
    expect(screen.getByText(/Dev Mock/i)).toBeInTheDocument()
  })

  it('surfaces the evidence-gap downgrade explanation when present', () => {
    const decision = makeDecision({ evidence_gap_downgrade: true, decision: 'HUMAN_REVIEW' })
    render(<EconomicDecisionPanel decision={decision} source="real" />)
    expect(screen.getByText(/routed to human review because/i)).toBeInTheDocument()
  })
})
