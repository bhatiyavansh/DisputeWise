import type { ClaimVerificationStatus } from '../../api/types'

/**
 * Badge colours for the verifier's per-claim result, shared by every surface
 * that renders one so a status can never read as "green" in one place and
 * "amber" in another. The mapping is presentational only -- the status
 * itself always comes from the backend verifier.
 */
export const CLAIM_STATUS_CLASSES: Record<ClaimVerificationStatus, string> = {
  SUPPORTED: 'bg-contest-50 text-contest-700',
  PARTIALLY_SUPPORTED: 'bg-review-50 text-review-700',
  UNSUPPORTED: 'bg-avoid-50 text-avoid-700',
  INVALID_REFERENCE: 'bg-avoid-50 text-avoid-700',
  INCOMPLETE: 'bg-review-50 text-review-700',
}
