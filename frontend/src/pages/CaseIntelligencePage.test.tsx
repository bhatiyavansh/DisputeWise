import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CaseIntelligencePage } from './CaseIntelligencePage'
import { clearResourceCache } from '../hooks/useAsyncResource'
import { CASE_DETAIL, EVIDENCE_LIST, SCORE_RESPONSE, makeDecision } from '../tests/fixtures'
import { installFetchMock, jsonRoute } from '../tests/mockFetch'

afterEach(() => {
  vi.unstubAllGlobals()
  clearResourceCache()
})

function renderCasePage(caseId: string) {
  return render(
    <MemoryRouter initialEntries={[`/case/${caseId}`]}>
      <Routes>
        <Route path="/case/:caseId" element={<CaseIntelligencePage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CaseIntelligencePage', () => {
  it('renders the correct case, with the calibrated probability from /score', async () => {
    installFetchMock([
      jsonRoute('GET', /\/cases\/DSP-031597$/, 200, CASE_DETAIL),
      jsonRoute('GET', /\/evidence$/, 200, EVIDENCE_LIST),
      jsonRoute('POST', /\/score$/, 200, SCORE_RESPONSE),
      jsonRoute('POST', /\/decision$/, 200, makeDecision()),
    ])

    renderCasePage('DSP-031597')

    await waitFor(() => expect(screen.getAllByText('DSP-031597').length).toBeGreaterThan(0))
    expect(screen.getAllByText('Goods Not Received').length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getAllByText('96.8%').length).toBeGreaterThan(0))
  })

  it('renders missing evidence visibly', async () => {
    installFetchMock([
      jsonRoute('GET', /\/cases\/DSP-031597$/, 200, CASE_DETAIL),
      jsonRoute('GET', /\/evidence$/, 200, EVIDENCE_LIST),
      jsonRoute('POST', /\/score$/, 200, SCORE_RESPONSE),
      jsonRoute('POST', /\/decision$/, 200, makeDecision()),
    ])

    renderCasePage('DSP-031597')

    await waitFor(() => expect(screen.getByText('Not on file')).toBeInTheDocument())
  })

  it('shows a not-found state for an unknown case, with no fabricated probability', async () => {
    installFetchMock([jsonRoute('GET', /\/cases\/DSP-999999$/, 404, { detail: "Case 'DSP-999999' not found" })])

    renderCasePage('DSP-999999')

    await waitFor(() => expect(screen.getByText('Case "DSP-999999" not found')).toBeInTheDocument())
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument()
  })

  it('shows "Risk scoring unavailable" and displays NO probability when /score fails', async () => {
    installFetchMock([
      jsonRoute('GET', /\/cases\/DSP-031597$/, 200, CASE_DETAIL),
      jsonRoute('GET', /\/evidence$/, 200, EVIDENCE_LIST),
      jsonRoute('POST', /\/score$/, 503, { detail: 'model not ready' }),
      jsonRoute('POST', /\/decision$/, 503, { detail: 'model not ready' }),
    ])

    renderCasePage('DSP-031597')

    await waitFor(() => expect(screen.getByText('Risk scoring unavailable')).toBeInTheDocument())
    // no calibrated-probability percentage anywhere on the page
    expect(screen.queryByText(/^\d+(\.\d+)?%$/)).not.toBeInTheDocument()
  })

  it('never silently shows a decision when /decision is unavailable and the mock is not enabled', async () => {
    installFetchMock([
      jsonRoute('GET', /\/cases\/DSP-031597$/, 200, CASE_DETAIL),
      jsonRoute('GET', /\/evidence$/, 200, EVIDENCE_LIST),
      jsonRoute('POST', /\/score$/, 200, SCORE_RESPONSE),
      jsonRoute('POST', /\/decision$/, 503, { detail: 'model not ready' }),
    ])

    renderCasePage('DSP-031597')

    await waitFor(() => expect(screen.getByText('Decision engine unavailable')).toBeInTheDocument())
    expect(screen.queryByText('Contest')).not.toBeInTheDocument()
    expect(screen.queryByText('Human Review')).not.toBeInTheDocument()
    expect(screen.queryByText("Don't Contest")).not.toBeInTheDocument()
  })
})
