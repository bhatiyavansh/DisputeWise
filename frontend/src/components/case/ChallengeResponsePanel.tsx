import { useState } from 'react'
import { ApiError } from '../../api/client'
import { verifyClaims } from '../../api/response'
import type { VerifyResponse } from '../../api/types'
import { ErrorState } from '../common/ErrorState'
import { InlineSpinner } from '../common/LoadingStates'
import { Panel } from '../common/Panel'
import { CLAIM_STATUS_CLASSES } from './claimStatus'

/**
 * A thin interface over the EXISTING POST /cases/{id}/verify endpoint, so the
 * deterministic verifier can be exercised directly against a case rather than
 * only as a by-product of generation.
 *
 * There is no verification logic here. This component does not decide whether
 * an evidence ID exists, whether a claim is supported, or what the resulting
 * response state should be -- it submits the claim and renders exactly what
 * the backend verifier returns. The only client-side check is that both
 * fields were filled in, which is form validation, not verification.
 */

// The /verify request envelope needs a claim id and type alongside the text.
// These are request scaffolding for a single ad-hoc claim, not case data.
const CHALLENGE_CLAIM_ID = 'CHALLENGE-1'
const CHALLENGE_CLAIM_TYPE = 'fact'

export function ChallengeResponsePanel({ caseId }: { caseId: string }) {
  const [claimText, setClaimText] = useState('')
  const [evidenceId, setEvidenceId] = useState('')
  const [result, setResult] = useState<VerifyResponse | null>(null)
  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [error, setError] = useState<ApiError | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

  const trimmedClaim = claimText.trim()
  const trimmedEvidenceId = evidenceId.trim()

  async function verify() {
    if (!trimmedClaim || !trimmedEvidenceId) {
      setValidationError(
        !trimmedClaim && !trimmedEvidenceId
          ? 'Enter a claim and an evidence ID to test.'
          : !trimmedClaim
            ? 'Enter a claim to test.'
            : 'Enter an evidence ID for the claim to cite.',
      )
      return
    }

    setValidationError(null)
    setStatus('running')
    setError(null)
    try {
      const response = await verifyClaims(caseId, [
        {
          claim_id: CHALLENGE_CLAIM_ID,
          text: trimmedClaim,
          claim_type: CHALLENGE_CLAIM_TYPE,
          evidence_ids: [trimmedEvidenceId],
          source_ids: [],
        },
      ])
      setResult(response)
      setStatus('done')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError('network', 'Unexpected error', null, caught))
      setStatus('error')
    }
  }

  function reset() {
    setClaimText('')
    setEvidenceId('')
    setResult(null)
    setError(null)
    setStatus('idle')
    setValidationError(null)
  }

  return (
    <Panel
      title="Challenge the response"
      subtitle="Test whether a claim can be supported by this case's evidence."
    >
      <div className="flex flex-col gap-3">
        <div>
          <label htmlFor="challenge-claim" className="mb-1 block text-xs font-medium text-ink-400">
            Claim
          </label>
          <textarea
            id="challenge-claim"
            rows={2}
            value={claimText}
            onChange={(e) => setClaimText(e.target.value)}
            placeholder="Proof of delivery confirms the customer received the order."
            className="w-full resize-y rounded border border-ink-700 bg-ink-900 px-2.5 py-1.5 text-sm text-ink-100 placeholder:text-ink-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
          />
        </div>

        <div>
          <label htmlFor="challenge-evidence-id" className="mb-1 block text-xs font-medium text-ink-400">
            Evidence ID cited
          </label>
          <input
            id="challenge-evidence-id"
            type="text"
            value={evidenceId}
            onChange={(e) => setEvidenceId(e.target.value)}
            placeholder="EVD-…"
            className="w-full max-w-xs rounded border border-ink-700 bg-ink-900 px-2.5 py-1.5 font-mono text-sm text-ink-100 placeholder:text-ink-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={verify}
            disabled={status === 'running'}
            className="rounded bg-accent-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500"
          >
            Verify claim
          </button>
          {(result || status === 'error') && (
            <button
              type="button"
              onClick={reset}
              className="rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-sm font-medium text-ink-200 transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
            >
              Clear
            </button>
          )}
          {status === 'running' && <InlineSpinner label="Verifying…" />}
        </div>

        {validationError && (
          <p role="alert" className="text-xs text-avoid-600">
            {validationError}
          </p>
        )}
      </div>

      {status === 'error' && (
        <div className="mt-4">
          <ErrorState error={error} title="Verification could not run" onRetry={() => void verify()} compact />
        </div>
      )}

      {status === 'done' && result && <ChallengeResult result={result} />}
    </Panel>
  )
}

/** Renders the verifier's own response. Nothing is recomputed here. */
function ChallengeResult({ result }: { result: VerifyResponse }) {
  const verification = result.claim_verifications.find((v) => v.claim_id === CHALLENGE_CLAIM_ID)

  return (
    <div className="mt-5 border-t border-ink-800 pt-4">
      {verification ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded px-2 py-1 text-sm font-semibold uppercase ${CLAIM_STATUS_CLASSES[verification.status]}`}
            >
              {verification.status.replace(/_/g, ' ')}
            </span>
            <span aria-hidden="true" className="text-ink-600">
              →
            </span>
            <span className="text-sm font-medium text-ink-200">
              {result.response_state.replace(/_/g, ' ')}
            </span>
          </div>

          <p className="mt-2.5 text-sm leading-relaxed text-ink-300">{verification.explanation}</p>
          <p className="mt-2 text-xs text-ink-500">{result.response_state_reason}</p>
        </>
      ) : (
        <p className="text-sm text-ink-400">
          The verifier returned no result for this claim. Raw response state: {result.response_state}.
        </p>
      )}

      <p className="mt-3 text-xs text-ink-600">verifier {result.verifier_version}</p>
    </div>
  )
}
