import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { ErrorState } from '../../components/common/ErrorState'
import { InlineSpinner, SkeletonCard } from '../../components/common/LoadingStates'
import { ChallengeResponsePanel } from '../../components/case/ChallengeResponsePanel'
import { RetrievedKnowledgePanel } from '../../components/case/RetrievedKnowledgePanel'
import { ResponseDraftWorkspace } from '../../components/case/ResponseDraftWorkspace'
import { classifyDraftError } from '../../components/case/draftOutcome'
import { useDraft } from '../../hooks/useCaseWorkspace'
import type { CaseOutletContext } from './CaseLayout'

/**
 * Draft generation is a live LLM call and can take up to ~90s, unlike every
 * other case resource -- so it is gated behind an explicit action rather
 * than auto-firing when this tab opens. Once requested, the result is
 * cached in-memory for the tab's session (useAsyncResource's module-level
 * cache), so revisiting this tab is instant -- but that also means it is
 * NEVER re-fetched on its own. A generation attempt is a point-in-time
 * result (the backend, the provider, and even the response_state can differ
 * request to request for the same case), so the "Regenerate draft" button
 * below is the only way to see anything newer than the first successful
 * response this tab ever got -- there is no polling, no auto-refresh, and
 * no cache expiry.
 */
export function CaseResponsePage() {
  const { caseId } = useOutletContext<CaseOutletContext>()
  const [requested, setRequested] = useState(false)
  const draftQuery = useDraft(caseId, requested)

  function regenerate() {
    // refetch() clears this case's cached draft and bumps the resource's
    // generation counter, which is exactly one fresh POST /draft -- the
    // component doesn't construct a second request of its own.
    draftQuery.refetch()
  }

  if (!requested) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-lg border border-ink-800 bg-ink-900 p-6">
        <p className="text-sm text-ink-300">
          Generate a grounded response draft for this case: retrieves relevant policy guidance, drafts a response, and
          independently verifies every generated claim against the evidence packet.
        </p>
        <button
          type="button"
          onClick={() => setRequested(true)}
          className="rounded bg-accent-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500"
        >
          Generate response draft
        </button>
      </div>
    )
  }

  if (draftQuery.status === 'loading') {
    return (
      <div className="flex flex-col gap-5">
        <div className="rounded-lg border border-ink-800 bg-ink-900 p-6">
          <InlineSpinner label="Generating and verifying response -- this can take up to a minute…" />
        </div>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  if (draftQuery.status === 'error') {
    // No response arrived, so this is a transport/backend failure -- the
    // only case where "unreachable" wording can be correct. Anything the
    // backend actually answered is classified from the response instead
    // (see ResponseDraftWorkspace / classifyDraftResponse).
    const outcome = classifyDraftError(draftQuery.error)
    return (
      <ErrorState
        error={draftQuery.error}
        title={outcome.title}
        message={outcome.message}
        retryLabel="Try again"
        onRetry={draftQuery.refetch}
      />
    )
  }

  if (draftQuery.status !== 'success' || !draftQuery.data) return null

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-ink-500">Generated {draftQuery.data.trace.generated_at}</p>
        <button
          type="button"
          onClick={regenerate}
          className="rounded border border-ink-700 bg-ink-800 px-3 py-1.5 text-xs font-medium text-ink-200 transition-colors hover:bg-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        >
          Regenerate draft
        </button>
      </div>
      <ResponseDraftWorkspace draft={draftQuery.data} />
      {draftQuery.data.retrieved_sources.length > 0 && (
        <RetrievedKnowledgePanel sources={draftQuery.data.retrieved_sources} />
      )}
      {/* Secondary to the draft above: an interface over the same /verify
          endpoint, so the verifier can be exercised against an arbitrary
          claim. Rendered for every generation outcome (ready, blocked, or
          unavailable) because the verifier is deterministic and works even
          when the LLM provider does not. */}
      <ChallengeResponsePanel caseId={caseId} />
    </div>
  )
}
