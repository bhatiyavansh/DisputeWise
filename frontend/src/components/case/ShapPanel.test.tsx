import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ShapPanel } from './ShapPanel'
import { SCORE_RESPONSE } from '../../tests/fixtures'

describe('ShapPanel', () => {
  it('renders actual SHAP factor descriptions and contributions from the API, separated by direction', () => {
    render(<ShapPanel positive={SCORE_RESPONSE.top_positive_factors} negative={SCORE_RESPONSE.top_negative_factors} />)

    expect(screen.getByText('What looks strong')).toBeInTheDocument()
    expect(screen.getByText('What reduces confidence')).toBeInTheDocument()

    expect(screen.getByText('14 evidence items are strong.')).toBeInTheDocument()
    expect(screen.getByText('+1.472')).toBeInTheDocument()

    expect(screen.getByText('Proof of delivery evidence has a strength of 0.00.')).toBeInTheDocument()
    expect(screen.getByText('-0.034')).toBeInTheDocument()
  })

  it('never displays SHAP values as a percentage/probability', () => {
    render(<ShapPanel positive={SCORE_RESPONSE.top_positive_factors} negative={[]} />)
    expect(screen.queryByText(/147\.2%|1\.472%/)).not.toBeInTheDocument()
  })

  it('shows an empty-state message when a direction has no factors', () => {
    render(<ShapPanel positive={[]} negative={[]} />)
    expect(screen.getByText('No positive drivers returned.')).toBeInTheDocument()
    expect(screen.getByText('No negative drivers returned.')).toBeInTheDocument()
  })
})
