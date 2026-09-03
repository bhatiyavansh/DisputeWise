import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SimulationPage } from './SimulationPage'
import { clearResourceCache } from '../hooks/useAsyncResource'
import { installFetchMock, jsonRoute } from '../tests/mockFetch'
import { makeSimulation } from '../tests/fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
  clearResourceCache()
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/simulation']}>
      <SimulationPage />
    </MemoryRouter>,
  )
}

describe('SimulationPage', () => {
  it('is labelled as a scenario so it cannot be mistaken for a real dispute', () => {
    installFetchMock([])
    renderPage()
    expect(screen.getByText('Scenario')).toBeInTheDocument()
    expect(screen.getByText(/Nothing is saved/)).toBeInTheDocument()
  })

  it('does not call the API until the user runs the simulation', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/simulate$/, 200, makeSimulation())])
    renderPage()

    expect(fetchMock).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Run simulation' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })

  it('POSTs to /simulate and never includes an outcome/target field', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/simulate$/, 200, makeSimulation())])
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Run simulation' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/simulate')
    expect(init?.method).toBe('POST')

    const sent = JSON.parse(init?.body as string)
    for (const forbidden of ['favorable_outcome', 'recovery_amount', 'outcome_at', 'outcome_source']) {
      expect(sent).not.toHaveProperty(forbidden)
    }
  })

  it('renders the backend decision verbatim, without deriving it from the probability', async () => {
    installFetchMock([
      jsonRoute(
        'POST',
        /\/simulate$/,
        200,
        // A deliberately "inconsistent" pairing: a very high win probability
        // that the backend nonetheless routed to HUMAN_REVIEW. The UI must
        // render what it was given, not re-derive a decision client-side.
        makeSimulation({
          score: { ...makeSimulation().score, calibrated_probability: 0.978 },
          decision: { ...makeSimulation().decision, decision: 'HUMAN_REVIEW', evidence_gap_downgrade: true },
        }),
      ),
    ])
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Run simulation' }))

    await waitFor(() => expect(screen.getByText('97.8%')).toBeInTheDocument())
    expect(screen.getByText('Human Review')).toBeInTheDocument()
    expect(screen.queryByText('Contest')).not.toBeInTheDocument()
  })

  it('marks stages that did not run as not-run rather than complete', async () => {
    installFetchMock([jsonRoute('POST', /\/simulate$/, 200, makeSimulation())])
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Run simulation' }))

    // the default fixture has generation disabled
    await waitFor(() => expect(screen.getByText('SCORING')).toBeInTheDocument())
    expect(screen.getAllByText('(not run)').length).toBeGreaterThan(0)
    // prompt / response-schema / verifier versions are all absent when
    // generation didn't run -- each reported as "not run", never invented
    expect(screen.getAllByText('not run')).toHaveLength(3)
  })

  it('surfaces a rejected scenario as a validation error, not a generic failure', async () => {
    installFetchMock([
      jsonRoute('POST', /\/simulate$/, 422, {
        detail: "outcome/target fields are never accepted by simulation: ['favorable_outcome']",
      }),
    ])
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Run simulation' }))

    await waitFor(() => expect(screen.getByText('This scenario was rejected')).toBeInTheDocument())
  })
})
