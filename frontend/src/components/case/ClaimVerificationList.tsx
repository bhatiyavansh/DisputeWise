import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import type { ClaimVerification, ClaimVerificationStatus, GeneratedClaim } from '../../api/types'
import { Panel } from '../common/Panel'

const STATUS_CLASSES: Record<ClaimVerificationStatus, string> = {
  SUPPORTED: 'bg-contest-50 text-contest-700',
  PARTIALLY_SUPPORTED: 'bg-review-50 text-review-700',
  UNSUPPORTED: 'bg-avoid-50 text-avoid-700',
  INVALID_REFERENCE: 'bg-avoid-50 text-avoid-700',
  INCOMPLETE: 'bg-review-50 text-review-700',
}

/**
 * Each generated claim, joined to its own independent verification result.
 * This is the claim-level grounding view: every claim is expandable to show
 * exactly which evidence_ids/source_ids it cites and what the verifier
 * (running as a separate step from generation) concluded, so nothing here
 * is "trust the model" -- it's "check what the verifier checked."
 */
export function ClaimVerificationList({
  claims,
  verifications,
}: {
  claims: GeneratedClaim[]
  verifications: ClaimVerification[]
}) {
  const verificationByClaimId = new Map(verifications.map((v) => [v.claim_id, v]))

  return (
    <Panel title="Claim Verification" subtitle={`${claims.length} claim(s) generated, independently checked against the evidence packet`}>
      <ul className="flex flex-col divide-y divide-ink-800 overflow-hidden rounded border border-ink-800">
        {claims.map((claim) => (
          <ClaimRow key={claim.claim_id} claim={claim} verification={verificationByClaimId.get(claim.claim_id) ?? null} />
        ))}
      </ul>
    </Panel>
  )
}

function ClaimRow({ claim, verification }: { claim: GeneratedClaim; verification: ClaimVerification | null }) {
  const [open, setOpen] = useState(false)

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-3 px-3 py-2.5 text-left transition-colors hover:bg-ink-800/50 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-500"
      >
        <span className="text-sm text-ink-100">{claim.text}</span>
        <span className="flex shrink-0 items-center gap-2">
          {verification && (
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium uppercase ${STATUS_CLASSES[verification.status]}`}>
              {verification.status.replace(/_/g, ' ')}
            </span>
          )}
          <ChevronIcon open={open} />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="border-t border-ink-800 bg-ink-950/40 px-3 py-3 text-xs text-ink-400">
              <p>
                <span className="font-medium text-ink-300">Claim type:</span> {claim.claim_type}
              </p>
              {claim.evidence_ids.length > 0 && (
                <p className="mt-1">
                  <span className="font-medium text-ink-300">Evidence cited:</span> {claim.evidence_ids.join(', ')}
                </p>
              )}
              {claim.source_ids.length > 0 && (
                <p className="mt-1">
                  <span className="font-medium text-ink-300">Sources cited:</span> {claim.source_ids.join(', ')}
                </p>
              )}
              {verification ? (
                <p className="mt-2 border-t border-ink-800 pt-2 text-ink-300">{verification.explanation}</p>
              ) : (
                <p className="mt-2 border-t border-ink-800 pt-2 text-ink-500">No independent verification result for this claim.</p>
              )}
              {verification && <p className="mt-1 text-ink-600">verifier {verification.verifier_version}</p>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  )
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="12"
      height="12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      className={`mt-0.5 shrink-0 text-ink-500 transition-transform ${open ? 'rotate-180' : ''}`}
      aria-hidden="true"
    >
      <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
