import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EvidenceScenarioPanel } from './EvidenceScenarioPanel'
import { EVIDENCE_GAP_RESPONSE, makeScenario } from '../../tests/fixtures'
import { installFetchMock, jsonRoute } from '../../tests/mockFetch'

afterEach(() => vi.unstubAllGlobals())

function renderPanel() {
  return render(<EvidenceScenarioPanel caseId="DSP-031597" gap={EVIDENCE_GAP_RESPONSE} />)
}

describe('EvidenceScenarioPanel', () => {
  it('is labelled as a scenario', () => {
    installFetchMock([])
    renderPanel()
    expect(screen.getByText('Scenario')).toBeInTheDocument()
  })

  it('does not call the API until a scenario is actually run', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/evidence-scenario$/, 200, makeScenario())])
    renderPanel()

    // selecting alone must not fire a request
    await userEvent.click(screen.getByRole('checkbox', { name: /Proof of Delivery/i }))
    expect(fetchMock).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })

  it('sends a missing evidence type as an addition', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/evidence-scenario$/, 200, makeScenario())])
    renderPanel()

    await userEvent.click(screen.getByRole('checkbox', { name: /Proof of Delivery/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1]?.body as string)
    expect(body.add_evidence).toEqual(['proof_of_delivery'])
    expect(body.remove_evidence).toEqual([])
  })

  it('sends an on-file evidence type as a removal', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/evidence-scenario$/, 200, makeScenario())])
    renderPanel()

    // AVS is AVAILABLE in the fixture gap
    await userEvent.click(screen.getByRole('checkbox', { name: /AVS/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1]?.body as string)
    expect(body.remove_evidence).toEqual(['avs'])
    expect(body.add_evidence).toEqual([])
  })

  it('renders both sides and the decision change from the backend', async () => {
    installFetchMock([jsonRoute('POST', /\/evidence-scenario$/, 200, makeScenario())])
    renderPanel()

    await userEvent.click(screen.getByRole('checkbox', { name: /Proof of Delivery/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))

    await waitFor(() => expect(screen.getByText('Current')).toBeInTheDocument())
    // "Scenario" appears twice once results render: the panel's badge and
    // the hypothetical column's heading
    expect(screen.getAllByText('Scenario')).toHaveLength(2)
    expect(screen.getByText('96.8%')).toBeInTheDocument()
    expect(screen.getByText('97.5%')).toBeInTheDocument()
    expect(screen.getByText('HUMAN REVIEW → CONTEST')).toBeInTheDocument()
    expect(screen.getByText(/Critical gaps resolved/)).toBeInTheDocument()
  })

  it('always shows the not-a-causal-estimate disclaimer with results', async () => {
    installFetchMock([jsonRoute('POST', /\/evidence-scenario$/, 200, makeScenario())])
    renderPanel()

    await userEvent.click(screen.getByRole('checkbox', { name: /Proof of Delivery/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))

    await waitFor(() => expect(screen.getByText(/not a causal estimate/)).toBeInTheDocument())
  })

  it('surfaces a rejected scenario instead of showing stale numbers', async () => {
    installFetchMock([jsonRoute('POST', /\/evidence-scenario$/, 422, { detail: 'unknown evidence types' })])
    renderPanel()

    await userEvent.click(screen.getByRole('checkbox', { name: /Proof of Delivery/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))

    await waitFor(() => expect(screen.getByText('Scenario could not be evaluated')).toBeInTheDocument())
    expect(screen.queryByText('Current')).not.toBeInTheDocument()
  })
})
