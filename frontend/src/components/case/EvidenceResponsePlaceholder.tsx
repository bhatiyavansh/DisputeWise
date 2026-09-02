import { Panel } from '../common/Panel'

/**
 * Phase 4 placeholder ONLY. No RAG, no LLM, no generated text -- this
 * intentionally renders nothing but a static notice and the prepared slot
 * structure a future EvidenceResponse feature would fill in:
 *
 *   - evidence packet          (structured evidence bundle for the response)
 *   - retrieved policy         (RAG-retrieved network/reason-code guidance)
 *   - generated response       (LLM-drafted contest response)
 *   - claim-level grounding    (per-claim evidence citations)
 *   - unsupported claim warnings
 *   - human approval           (explicit human sign-off before anything is used)
 *
 * Each slot below is a labeled empty state, not a fake preview -- there is
 * no synthetic "AI-generated" content anywhere in this component.
 */
export function EvidenceResponsePlaceholder() {
  return (
    <Panel title="Evidence Response" subtitle="Phase 4 -- not yet implemented">
      <p className="text-sm text-ink-400">Response generation will appear here.</p>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <PreparedSlot label="Evidence packet" />
        <PreparedSlot label="Retrieved policy" />
        <PreparedSlot label="Generated response" />
        <PreparedSlot label="Claim-level grounding" />
        <PreparedSlot label="Unsupported claim warnings" />
        <PreparedSlot label="Human approval" />
      </div>
    </Panel>
  )
}

function PreparedSlot({ label }: { label: string }) {
  return (
    <div className="rounded border border-dashed border-ink-700 px-3 py-2.5 text-xs text-ink-600">
      <p className="font-medium text-ink-500">{label}</p>
      <p className="mt-0.5">Reserved for Phase 4</p>
    </div>
  )
}
