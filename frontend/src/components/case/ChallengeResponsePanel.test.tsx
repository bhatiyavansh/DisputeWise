import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChallengeResponsePanel } from './ChallengeResponsePanel'
import { installFetchMock, jsonRoute } from '../../tests/mockFetch'
import type { ClaimVerificationStatus } from '../../api/types'

afterEach(() => vi.unstubAllGlobals())

/** A /verify response shaped exactly like the backend's, for one claim. */
function verifyResponse(status: ClaimVerificationStatus, explanation: string, responseState = 'DRAFT_BLOCKED') {
  return {
    case_id: 'DSP-031597',
    verifier_version: 'verifier-v1.1',
    claim_verifications: [
      {
        claim_id: 'CHALLENGE-1',
        status,
        evidence_ids: [],
        source_ids: [],
        explanation,
        verifier_version: 'verifier-v1.1',
      },
    ],
    response_state: responseState,
    response_state_reason: `Response contains 1 claim with status ${status}.`,
    disclaimer: 'Decision support only.',
  }
}

async function fillAndVerify(claim = 'Proof of delivery confirms the customer received the order.', evidenceId = 'EVD-999999') {
  if (claim) await userEvent.type(screen.getByLabelText('Claim'), claim)
  if (evidenceId) await userEvent.type(screen.getByLabelText('Evidence ID cited'), evidenceId)
  await userEvent.click(screen.getByRole('button', { name: 'Verify claim' }))
}

describe('ChallengeResponsePanel', () => {
  it('renders the verification form', () => {
    installFetchMock([])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)

    expect(screen.getByText('Challenge the response')).toBeInTheDocument()
    expect(screen.getByLabelText('Claim')).toBeInTheDocument()
    expect(screen.getByLabelText('Evidence ID cited')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Verify claim' })).toBeInTheDocument()
  })

  it('does not pre-fill a claim or an evidence ID', () => {
    installFetchMock([])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)

    expect(screen.getByLabelText('Claim')).toHaveValue('')
    expect(screen.getByLabelText('Evidence ID cited')).toHaveValue('')
  })

  it('posts the claim to the existing /cases/{id}/verify endpoint', async () => {
    const fetchMock = installFetchMock([
      jsonRoute('POST', /\/verify$/, 200, verifyResponse('INVALID_REFERENCE', 'Claim cites evidence that does not exist.')),
    ])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify()

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/cases/DSP-031597/verify')
    expect(init?.method).toBe('POST')

    const body = JSON.parse(init?.body as string)
    expect(body.claims).toHaveLength(1)
    expect(body.claims[0].text).toBe('Proof of delivery confirms the customer received the order.')
    expect(body.claims[0].evidence_ids).toEqual(['EVD-999999'])
  })

  it('renders a supported claim exactly as the backend returned it', async () => {
    installFetchMock([
      jsonRoute(
        'POST',
        /\/verify$/,
        200,
        verifyResponse('SUPPORTED', 'All cited evidence exists for this case and is available.', 'DRAFT_READY'),
      ),
    ])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify('Delivery was confirmed.', 'EVD-0081597')

    await waitFor(() => expect(screen.getByText('SUPPORTED')).toBeInTheDocument())
    expect(screen.getByText(/All cited evidence exists/)).toBeInTheDocument()
    expect(screen.getByText('DRAFT READY')).toBeInTheDocument()
  })

  it('renders INVALID_REFERENCE for a fabricated evidence ID, and the resulting blocked state', async () => {
    installFetchMock([
      jsonRoute(
        'POST',
        /\/verify$/,
        200,
        verifyResponse('INVALID_REFERENCE', "Claim cites evidence_id(s) ['EVD-999999'] that do not exist for this case."),
      ),
    ])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify()

    await waitFor(() => expect(screen.getByText('INVALID REFERENCE')).toBeInTheDocument())
    expect(screen.getByText(/do not exist for this case/)).toBeInTheDocument()
    // the fabricated-evidence -> blocked chain is visible
    expect(screen.getByText('DRAFT BLOCKED')).toBeInTheDocument()
  })

  it('renders UNSUPPORTED', async () => {
    installFetchMock([
      jsonRoute('POST', /\/verify$/, 200, verifyResponse('UNSUPPORTED', 'No evidence on file supports this claim.')),
    ])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify()

    await waitFor(() => expect(screen.getByText('UNSUPPORTED')).toBeInTheDocument())
    expect(screen.getByText(/No evidence on file supports this claim/)).toBeInTheDocument()
  })

  it('shows an error state when the API fails, without inventing a verdict', async () => {
    installFetchMock([jsonRoute('POST', /\/verify$/, 500, { detail: 'boom' })])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify()

    await waitFor(() => expect(screen.getByText('Verification could not run')).toBeInTheDocument())
    for (const status of ['SUPPORTED', 'UNSUPPORTED', 'INVALID REFERENCE']) {
      expect(screen.queryByText(status)).not.toBeInTheDocument()
    }
  })

  it('shows a network failure without inventing a verdict', async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify()

    await waitFor(() => expect(screen.getByText('Verification could not run')).toBeInTheDocument())
    expect(screen.queryByText('INVALID REFERENCE')).not.toBeInTheDocument()
  })

  it('rejects an empty claim without calling the API', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/verify$/, 200, verifyResponse('SUPPORTED', 'ok'))])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify('', 'EVD-999999')

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a claim to test.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects an empty evidence ID without calling the API', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/verify$/, 200, verifyResponse('SUPPORTED', 'ok'))])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await fillAndVerify('Some claim.', '')

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter an evidence ID')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects both fields empty without calling the API', async () => {
    const fetchMock = installFetchMock([jsonRoute('POST', /\/verify$/, 200, verifyResponse('SUPPORTED', 'ok'))])
    render(<ChallengeResponsePanel caseId="DSP-031597" />)
    await userEvent.click(screen.getByRole('button', { name: 'Verify claim' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a claim and an evidence ID to test.')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
