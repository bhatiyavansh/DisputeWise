import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { CaseLayout } from './CaseLayout'
import { CaseOverviewPage } from './CaseOverviewPage'
import { CaseDecisionPage } from './CaseDecisionPage'
import { CaseEvidencePage } from './CaseEvidencePage'
import { CaseResponsePage } from './CaseResponsePage'
import { clearResourceCache } from '../../hooks/useAsyncResource'
import {
  CASE_DETAIL,
  EVIDENCE_GAP_RESPONSE,
  EVIDENCE_LIST,
  EVIDENCE_PACKET_RESPONSE,
  SCORE_RESPONSE,
  makeDecision,
  makeDraft,
} from '../../tests/fixtures'
import { installFetchMock, jsonRoute } from '../../tests/mockFetch'

afterEach(() => {
  vi.unstubAllGlobals()
  clearResourceCache()
})

function renderCaseRoute(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/case/:caseId" element={<CaseLayout />}>
          <Route index element={<CaseOverviewPage />} />
          <Route path="decision" element={<CaseDecisionPage />} />
          <Route path="evidence" element={<CaseEvidencePage />} />
          <Route path="response" element={<CaseResponsePage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

const BASE_ROUTES = [
  jsonRoute('GET', /\/cases\/DSP-031597$/, 200, CASE_DETAIL),
  jsonRoute('GET', /\/evidence$/, 200, EVIDENCE_LIST),
  jsonRoute('POST', /\/score$/, 200, SCORE_RESPONSE),
  jsonRoute('POST', /\/decision$/, 200, makeDecision()),
]

describe('CaseLayout + CaseOverviewPage', () => {
  it('renders the case header and calibrated probability', async () => {
    installFetchMock(BASE_ROUTES)
    renderCaseRoute('/case/DSP-031597')

    await waitFor(() => expect(screen.getAllByText('DSP-031597').length).toBeGreaterThan(0))
    expect(screen.getAllByText('Goods Not Received').length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getAllByText('96.8%').length).toBeGreaterThan(0))
  })

  it('shows a not-found state for an unknown case, with no fabricated probability', async () => {
    installFetchMock([jsonRoute('GET', /\/cases\/DSP-999999$/, 404, { detail: "Case 'DSP-999999' not found" })])
    renderCaseRoute('/case/DSP-999999')

    await waitFor(() => expect(screen.getByText('Case "DSP-999999" not found')).toBeInTheDocument())
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument()
  })

  it('shows "Risk scoring unavailable" and displays no probability when /score fails', async () => {
    installFetchMock([
      jsonRoute('GET', /\/cases\/DSP-031597$/, 200, CASE_DETAIL),
      jsonRoute('GET', /\/evidence$/, 200, EVIDENCE_LIST),
      jsonRoute('POST', /\/score$/, 503, { detail: 'model not ready' }),
      jsonRoute('POST', /\/decision$/, 503, { detail: 'model not ready' }),
    ])
    renderCaseRoute('/case/DSP-031597')

    await waitFor(() => expect(screen.getByText('Risk scoring unavailable')).toBeInTheDocument())
    expect(screen.queryByText(/^\d+(\.\d+)?%$/)).not.toBeInTheDocument()
  })
})

describe('CaseDecisionPage', () => {
  it('never silently shows a decision when /decision is unavailable', async () => {
    installFetchMock([
      jsonRoute('GET', /\/cases\/DSP-031597$/, 200, CASE_DETAIL),
      jsonRoute('GET', /\/evidence$/, 200, EVIDENCE_LIST),
      jsonRoute('POST', /\/score$/, 200, SCORE_RESPONSE),
      jsonRoute('POST', /\/decision$/, 503, { detail: 'model not ready' }),
    ])
    renderCaseRoute('/case/DSP-031597/decision')

    await waitFor(() => expect(screen.getByText('Decision engine unavailable')).toBeInTheDocument())
    expect(screen.queryByText('Contest')).not.toBeInTheDocument()
  })
})

describe('CaseEvidencePage', () => {
  it('renders missing evidence and the gap coverage from /evidence-gap', async () => {
    installFetchMock([
      ...BASE_ROUTES,
      jsonRoute('POST', /\/evidence-gap$/, 200, EVIDENCE_GAP_RESPONSE),
      jsonRoute('POST', /\/evidence-packet$/, 200, EVIDENCE_PACKET_RESPONSE),
    ])
    renderCaseRoute('/case/DSP-031597/evidence')

    await waitFor(() => expect(screen.getByText('Not on file')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('75%')).toBeInTheDocument())
  })
})

describe('CaseResponsePage', () => {
  it('requires an explicit action before generating a draft, then renders claim verification', async () => {
    installFetchMock([...BASE_ROUTES, jsonRoute('POST', /\/draft$/, 200, makeDraft())])
    renderCaseRoute('/case/DSP-031597/response')

    expect(screen.queryByText('Draft ready')).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Generate response draft' }))

    await waitFor(() => expect(screen.getByText('Draft ready')).toBeInTheDocument())
    expect(screen.getByText(/authenticated via 3-D Secure/)).toBeInTheDocument()
  })

  it('never softens a blocked draft state', async () => {
    installFetchMock([
      ...BASE_ROUTES,
      jsonRoute(
        'POST',
        /\/draft$/,
        200,
        makeDraft({
          response_state: 'DRAFT_BLOCKED',
          response_state_reason: 'A generated claim could not be verified against the evidence on file.',
          response_body: null,
        }),
      ),
    ])
    renderCaseRoute('/case/DSP-031597/response')

    await userEvent.click(await screen.findByRole('button', { name: 'Generate response draft' }))
    await waitFor(() => expect(screen.getByText('Draft blocked by verifier')).toBeInTheDocument())
    expect(screen.queryByText('Draft ready')).not.toBeInTheDocument()
  })

  it('"Regenerate draft" fires exactly one fresh POST and replaces the displayed state -- an old blocked draft never lingers', async () => {
    let draftCallCount = 0
    installFetchMock([
      ...BASE_ROUTES,
      {
        method: 'POST',
        pattern: /\/draft$/,
        handler: () => {
          draftCallCount += 1
          if (draftCallCount === 1) {
            return {
              status: 200,
              body: makeDraft({
                response_state: 'DRAFT_BLOCKED',
                response_state_reason:
                  "Generation failed: provider 'openrouter' failed to generate: OpenRouter reported an upstream error: Upstream error from Nvidia: Service temporarily overloaded (code=502)",
                claims: [],
                claim_verifications: [],
                response_body: null,
              }),
            }
          }
          return { status: 200, body: makeDraft() } // second call: fresh DRAFT_READY
        },
      },
    ])
    renderCaseRoute('/case/DSP-031597/response')

    await userEvent.click(await screen.findByRole('button', { name: 'Generate response draft' }))
    await waitFor(() => expect(screen.getByText(/Service temporarily overloaded/)).toBeInTheDocument())
    expect(draftCallCount).toBe(1)

    await userEvent.click(await screen.findByRole('button', { name: 'Regenerate draft' }))

    await waitFor(() => expect(screen.getByText('Draft ready')).toBeInTheDocument())
    expect(screen.queryByText(/Service temporarily overloaded/)).not.toBeInTheDocument()
    expect(draftCallCount).toBe(2)
  })
})
