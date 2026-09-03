import type { DraftResponse } from '../../api/types'
import { formatEvidenceType } from '../../utils/format'
import { ClaimVerificationList } from './ClaimVerificationList'
import { DraftStateBanner } from './DraftStateBanner'
import { Panel } from '../common/Panel'

/**
 * The analyst's response workspace for one case: the drafted body (if
 * generation produced one), what evidence is still missing, and an explicit
 * statement of what this tool does and does not do. This is not a chat UI --
 * there is no message history, no "ask a follow-up" box; /draft is called
 * once per case and the result is reviewed here.
 */
export function ResponseDraftWorkspace({ draft }: { draft: DraftResponse }) {
  return (
    <div className="flex flex-col gap-5">
      <DraftStateBanner state={draft.response_state} reason={draft.response_state_reason} />

      {draft.response_body && (
        <Panel title="Drafted Response" subtitle={`prompt ${draft.prompt_version} -- response schema ${draft.response_schema_version}`}>
          {draft.summary && <p className="mb-3 text-sm font-medium text-ink-200">{draft.summary}</p>}
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-100">{draft.response_body}</p>
        </Panel>
      )}

      {draft.missing_evidence.length > 0 && (
        <Panel title="Missing evidence referenced by this reason code">
          <ul className="flex flex-wrap gap-2">
            {draft.missing_evidence.map((type) => (
              <li key={type} className="rounded border border-avoid-500/30 bg-avoid-50/5 px-2 py-1 text-xs font-medium text-avoid-700">
                {formatEvidenceType(type)}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {draft.claims.length > 0 && (
        <ClaimVerificationList claims={draft.claims} verifications={draft.claim_verifications} />
      )}

      <div className="rounded-lg border border-ink-800 bg-ink-900 px-4 py-3 text-xs text-ink-500">
        <p className="font-medium text-ink-300">Human approval boundary</p>
        <p className="mt-1">
          This tool prepares and verifies a draft response. It does not submit anything to a card network, does not
          contact the customer, and does not close or update the dispute's status. An analyst reviews and sends the
          response through the normal dispute-response process.
        </p>
        {draft.disclaimer && <p className="mt-1 text-ink-600">{draft.disclaimer}</p>}
      </div>
    </div>
  )
}
