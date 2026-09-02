import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EvidenceCoverageBar } from './EvidenceCoverageBar'
import { SCORE_RESPONSE } from '../../tests/fixtures'

describe('EvidenceCoverageBar', () => {
  it('computes and displays the coverage percentage from real summary fields', () => {
    render(<EvidenceCoverageBar summary={SCORE_RESPONSE.evidence_summary} />)
    // 14/16 = 87.5% -> rounds to 88%
    expect(screen.getByRole('progressbar', { name: 'Evidence coverage' })).toHaveAttribute('aria-valuenow', '88')
    expect(screen.getByText(/14 \/ 16 available/)).toBeInTheDocument()
  })

  it('visibly surfaces missing high-relevance evidence types', () => {
    render(<EvidenceCoverageBar summary={SCORE_RESPONSE.evidence_summary} />)
    expect(screen.getByText('Missing high-relevance evidence')).toBeInTheDocument()
    expect(screen.getByText('Proof of Delivery')).toBeInTheDocument()
  })

  it('shows no missing-evidence warning when nothing is missing', () => {
    render(
      <EvidenceCoverageBar
        summary={{ ...SCORE_RESPONSE.evidence_summary, missing_key_types: [] }}
      />,
    )
    expect(screen.queryByText('Missing high-relevance evidence')).not.toBeInTheDocument()
  })
})
