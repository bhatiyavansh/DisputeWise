import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DisputeInboxPage } from './DisputeInboxPage'
import { CASE_PAGE, makeDecision, SCORE_RESPONSE } from '../tests/fixtures'
import { installFetchMock, jsonRoute } from '../tests/mockFetch'

afterEach(() => vi.unstubAllGlobals())

function renderInbox() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <DisputeInboxPage />
    </MemoryRouter>,
  )
}

describe('DisputeInboxPage', () => {
  it('renders the dispute list from the real /cases API', async () => {
    installFetchMock([
      jsonRoute('GET', /\/cases$/, 200, CASE_PAGE),
      jsonRoute('POST', /\/score$/, 200, SCORE_RESPONSE),
      jsonRoute('POST', /\/decision$/, 200, makeDecision()),
    ])

    renderInbox()

    await waitFor(() => expect(screen.getByText('DSP-031597')).toBeInTheDocument())
    expect(screen.getByText('DSP-041961')).toBeInTheDocument()
    expect(screen.getAllByText('50,000').length).toBeGreaterThan(0) // total, dataset-wide
  })

  it('shows an error state with retry when /cases fails', async () => {
    installFetchMock([jsonRoute('GET', /\/cases$/, 500, { detail: 'boom' })])

    renderInbox()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('shows an empty state when no disputes match the filters', async () => {
    installFetchMock([jsonRoute('GET', /\/cases$/, 200, { items: [], total: 0, page: 1, page_size: 20 })])

    renderInbox()

    await waitFor(() => expect(screen.getByText('No disputes match these filters')).toBeInTheDocument())
  })
})
