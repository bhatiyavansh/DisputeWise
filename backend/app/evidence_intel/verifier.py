"""Part F -- claim-level grounding verifier.

The single most important safety component in Phase 4. Every claim a
provider generates is checked here with DETERMINISTIC rules against the
case's own evidence packet and retrieved guidance -- never by asking the
same (or another) LLM "is this supported?" An LLM judging its own output is
circular and is not used as the safety mechanism anywhere in this module.

Checks, in order, first match wins:

  1. INVALID_REFERENCE -- cites an evidence_id or source_id that does not
     exist in THIS case's packet/retrieval results at all. This is what
     catches a fabricated ID, a nonexistent evidence_id, AND cross-case
     evidence contamination (an evidence_id that is real for some OTHER
     case is still "does not exist in this packet", by construction --
     packets are built per-case and never merged).
  2. INCOMPLETE (dangling/truncated text) -- the claim text does not end
     with proper terminal punctuation (added in the verifier-v1.1 hardening
     pass after a live run produced a response ending in "Proof of delivery
     is: "). A formatting defect, checked before anything evidentiary.
  3. UNSUPPORTED (outcome guarantee) -- claim asserts a guaranteed/certain
     result; no evidence can ever support a claim about the future.
  4. UNSUPPORTED (inference overreach) -- an `inference`-type claim uses
     absence-language ("despite", "even without", ...) about a required
     evidence type that actually IS missing for this case, while still
     concluding a support/proof word ("supports", "confirms", ...). Added
     in the verifier-v1.1 hardening pass: a live run produced a claim
     arguing other evidence "supports that the goods were delivered"
     *despite* proof_of_delivery being absent -- exactly the rhetorical
     move this catches. Deterministic text-pattern matching only; no NLI,
     no semantic understanding, per Part 3 of the hardening request.
  5. UNSUPPORTED (no citation) -- claim cites nothing at all. EXCEPTION: a
     claim that cites nothing because it is PURELY reporting a genuinely
     missing evidence type by name, with no conclusion drawn from that
     absence, is SUPPORTED instead -- there is no ID to cite for something
     that doesn't exist, and the hardened prompt now explicitly asks the
     model to state absence this way (empty evidence_ids) rather than citing
     the missing item's ID (which check 6 below would otherwise reject).
     Verified against a live model response on DSP-031597 that produced
     exactly this pattern.
  6. UNSUPPORTED (cites unavailable evidence) -- claim cites an evidence_id
     that is real for this case but is marked unavailable ("missing" evidence
     cannot become "cited proof").
  7. UNSUPPORTED (fabricated date) -- claim states a date/timestamp that
     does not appear anywhere in the value of the evidence it cites --
     catches invented delivery dates and contradictory timestamps.
  8. PARTIALLY_SUPPORTED -- every citation is valid and available, but at
     least one has strength below WEAK_EVIDENCE_THRESHOLD.
  9. SUPPORTED -- otherwise.

verify_response_body() applies check 2 (completeness only) to the overall
generated response_body, which is not itself a "claim" in the schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.evidence_intel import versions as v
from app.evidence_intel.generation import GeneratedClaim
from app.evidence_intel.packet import EvidencePacket
from app.evidence_intel.retrieval import RetrievalResult

WEAK_EVIDENCE_THRESHOLD = 0.3

_GUARANTEE_PATTERN = re.compile(
    r"\b("
    r"guarantee[ds]?"
    r"|will (?:definitely |certainly )?win"
    r"|certain(?:ly)? to (?:win|succeed|prevail)"
    r"|100\s?% (?:chance|certain|guaranteed)"
    r"|no doubt (?:this|it|the dispute) will"
    r"|assured (?:win|victory|success)"
    r")\b",
    re.IGNORECASE,
)

_DATE_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # ISO date, e.g. 2026-10-13
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),  # 10/13/2026
    re.compile(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    ),
)

# --- completeness (verifier-v1.1) -------------------------------------------
# A generated string must end with proper terminal punctuation (optionally
# wrapped in a closing quote/paren). Anything else -- a bare colon, semicolon,
# comma, dash, open bracket, or just trailing off mid-word -- is treated as
# truncated. Deliberately strict: "similarly incomplete punctuation" per the
# hardening request is easier to get right by requiring a clear terminator
# than by trying to enumerate every bad one.
_TERMINAL_PUNCTUATION = ".!?"
_CLOSING_WRAPPERS = "\"')]”’"  # straight/curly quotes, parens, brackets


def is_text_complete(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    last = stripped[-1]
    if last in _CLOSING_WRAPPERS:
        return len(stripped) >= 2 and stripped[-2] in _TERMINAL_PUNCTUATION
    return last in _TERMINAL_PUNCTUATION


# --- inference overreach (verifier-v1.1) ------------------------------------
# Catches an inference claim that rhetorically waves away a genuinely-missing
# required evidence type ("despite the absence of proof of delivery, ...
# supports that the goods were delivered") rather than stating cautiously
# what IS present. Both an absence-cue AND a support-conclusion word must be
# present, alongside an actual mention of a required-and-missing evidence
# type's name for THIS case -- three independent, structured/textual signals,
# not a semantic judgment.
_ABSENCE_CUES = re.compile(
    r"\b(despite|notwithstanding|even without|even though|regardless of|in spite of|"
    r"in the absence of|lack(?:ing|s)? of|absence of)\b",
    re.IGNORECASE,
)
_SUPPORT_CONCLUSIONS = re.compile(
    r"\b(support|supports|supported|supporting|prove|proves|proving|confirm|confirms|confirmed|confirming|"
    r"demonstrate|demonstrates|demonstrating|establish|establishes|establishing|indicat\w*|show|shows|showing)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClaimVerification:
    claim_id: str
    status: str  # SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | INVALID_REFERENCE | INCOMPLETE
    evidence_ids: list[str]
    source_ids: list[str]
    explanation: str
    verifier_version: str = v.VERIFIER_VERSION


def _extract_dates(text: str) -> list[str]:
    found: list[str] = []
    for pattern in _DATE_PATTERNS:
        found.extend(pattern.findall(text))
    return found


def _contains_outcome_guarantee(text: str) -> bool:
    return bool(_GUARANTEE_PATTERN.search(text))


def _fabricated_date(text: str, cited_evidence_ids: list[str], evidence_by_id: dict) -> str | None:
    dates = _extract_dates(text)
    if not dates:
        return None
    grounded_blob = " ".join(str(evidence_by_id[e].value) for e in cited_evidence_ids if e in evidence_by_id)
    for date in dates:
        if date not in grounded_blob:
            return date
    return None


def _missing_required_evidence_names(packet: EvidencePacket) -> list[str]:
    return [
        item.evidence_type.replace("_", " ")
        for item in packet.gap.items
        if item.required and item.status == v.STATUS_MISSING
    ]


def _is_inference_overreach(claim: GeneratedClaim, packet: EvidencePacket) -> str | None:
    """Returns the mentioned-missing-evidence phrase if this is an overreach,
    else None. Only applies to claim_type == "inference" -- see module docstring.
    """
    if claim.claim_type != v.CLAIM_TYPE_INFERENCE:
        return None

    lowered = claim.text.lower()
    mentioned = next((name for name in _missing_required_evidence_names(packet) if name in lowered), None)
    if mentioned is None:
        return None

    if _ABSENCE_CUES.search(claim.text) and _SUPPORT_CONCLUSIONS.search(claim.text):
        return mentioned
    return None


def _all_missing_evidence_names(packet: EvidencePacket) -> list[str]:
    return [item.evidence_type.replace("_", " ") for item in packet.evidence if not item.available]


def _is_pure_missing_evidence_statement(claim: GeneratedClaim, packet: EvidencePacket) -> bool:
    """True for a claim that ONLY reports genuinely-missing evidence by name
    and draws no conclusion from it -- the exact pattern prompt-v1.1 now asks
    the model to use (empty evidence_ids for a "this is missing" statement).

    Precondition (checked by the caller): the claim cites zero evidence_ids
    and zero source_ids. Without this carve-out, the "cites nothing" rule
    below would reject a live-verified-correct claim like "Proof of delivery
    ... [is] not available in the case file" purely for having nothing to
    cite -- which is unavoidable when the entire point of the sentence is
    that something doesn't exist to cite.

    Still guarded: if the claim ALSO uses a support/proof conclusion word
    (the same list the overreach check uses), it is NOT treated as a pure
    missing-evidence statement -- an ungrounded conclusion with zero
    citations is exactly what the "no citation" rule exists to catch.
    """
    lowered = claim.text.lower()
    mentioned = any(name in lowered for name in _all_missing_evidence_names(packet))
    if not mentioned:
        return False
    return not _SUPPORT_CONCLUSIONS.search(claim.text)


def verify_claim(
    claim: GeneratedClaim,
    packet: EvidencePacket,
    retrieval_results: list[RetrievalResult],
) -> ClaimVerification:
    evidence_by_id = packet.evidence_by_id()
    valid_source_ids = {r.source_id for r in retrieval_results} | {packet.guidance.source_id}

    cited_evidence_ids = list(dict.fromkeys(claim.evidence_ids))
    cited_source_ids = list(dict.fromkeys(claim.source_ids))

    unknown_evidence = [e for e in cited_evidence_ids if e not in evidence_by_id]
    unknown_sources = [s for s in cited_source_ids if s not in valid_source_ids]
    if unknown_evidence or unknown_sources:
        parts = []
        if unknown_evidence:
            parts.append(f"evidence_id(s) {unknown_evidence}")
        if unknown_sources:
            parts.append(f"source_id(s) {unknown_sources}")
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_INVALID_REFERENCE,
            evidence_ids=cited_evidence_ids,
            source_ids=cited_source_ids,
            explanation=(
                "Claim cites " + " and ".join(parts) + " that do not exist in this case's evidence packet "
                "or retrieved guidance (fabricated ID, or evidence from a different case)."
            ),
        )

    if not is_text_complete(claim.text):
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_INCOMPLETE,
            evidence_ids=cited_evidence_ids,
            source_ids=cited_source_ids,
            explanation=(
                "Claim text is truncated or dangling (does not end with proper terminal punctuation) -- "
                f"got: {claim.text!r}"
            ),
        )

    if _contains_outcome_guarantee(claim.text):
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_UNSUPPORTED,
            evidence_ids=cited_evidence_ids,
            source_ids=cited_source_ids,
            explanation="Claim asserts a guaranteed or certain dispute outcome; no evidence can support a claim about a future result.",
        )

    overreach_target = _is_inference_overreach(claim, packet)
    if overreach_target is not None:
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_UNSUPPORTED,
            evidence_ids=cited_evidence_ids,
            source_ids=cited_source_ids,
            explanation=(
                f"Inference claim rhetorically overcomes the absence of required evidence ('{overreach_target}') "
                "while still concluding the evidence 'supports'/'confirms' the outcome -- rejected without "
                "attempting to semantically verify the inference; other evidence cannot substitute for "
                "explicitly missing required evidence."
            ),
        )

    if not cited_evidence_ids and not cited_source_ids:
        if _is_pure_missing_evidence_statement(claim, packet):
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=v.CLAIM_SUPPORTED,
                evidence_ids=[],
                source_ids=[],
                explanation=(
                    "Claim only reports evidence that is genuinely missing for this case (by name) and draws "
                    "no conclusion from it -- no citation is possible or required for a statement of absence."
                ),
            )
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_UNSUPPORTED,
            evidence_ids=[],
            source_ids=[],
            explanation="Claim cites no evidence or source at all.",
        )

    unavailable_cited = [e for e in cited_evidence_ids if not evidence_by_id[e].available]
    if unavailable_cited:
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_UNSUPPORTED,
            evidence_ids=cited_evidence_ids,
            source_ids=cited_source_ids,
            explanation=(
                f"Claim cites evidence_id(s) {unavailable_cited} which are marked unavailable/missing for this "
                "case -- missing evidence cannot become cited proof."
            ),
        )

    fabricated_date = _fabricated_date(claim.text, cited_evidence_ids, evidence_by_id)
    if fabricated_date:
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_UNSUPPORTED,
            evidence_ids=cited_evidence_ids,
            source_ids=cited_source_ids,
            explanation=(
                f"Claim mentions a date/time ('{fabricated_date}') that does not appear in the value of any "
                "evidence it cites."
            ),
        )

    weak_cited = [e for e in cited_evidence_ids if evidence_by_id[e].strength < WEAK_EVIDENCE_THRESHOLD]
    if weak_cited:
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=v.CLAIM_PARTIALLY_SUPPORTED,
            evidence_ids=cited_evidence_ids,
            source_ids=cited_source_ids,
            explanation=(
                f"All citations exist and are available, but evidence_id(s) {weak_cited} have strength below "
                f"{WEAK_EVIDENCE_THRESHOLD} -- support is weak and warrants human review."
            ),
        )

    return ClaimVerification(
        claim_id=claim.claim_id,
        status=v.CLAIM_SUPPORTED,
        evidence_ids=cited_evidence_ids,
        source_ids=cited_source_ids,
        explanation="All cited evidence/sources exist for this case, are available, and no unsupported content was detected.",
    )


def verify_claims(
    claims: list[GeneratedClaim],
    packet: EvidencePacket,
    retrieval_results: list[RetrievalResult],
) -> list[ClaimVerification]:
    return [verify_claim(claim, packet, retrieval_results) for claim in claims]


RESPONSE_BODY_CLAIM_ID = "RESPONSE_BODY"


def verify_response_body(response_body: str) -> ClaimVerification:
    """Completeness check (verifier-v1.1) for the overall generated
    response_body, which isn't itself an entry in `claims[]`. Uses the same
    is_text_complete() rule as per-claim text, so "Proof of delivery is: "
    as a final response_body is caught even if every individual claim's own
    text happened to be well-formed.
    """
    if is_text_complete(response_body):
        return ClaimVerification(
            claim_id=RESPONSE_BODY_CLAIM_ID,
            status=v.CLAIM_SUPPORTED,
            evidence_ids=[],
            source_ids=[],
            explanation="response_body ends with proper terminal punctuation.",
        )
    return ClaimVerification(
        claim_id=RESPONSE_BODY_CLAIM_ID,
        status=v.CLAIM_INCOMPLETE,
        evidence_ids=[],
        source_ids=[],
        explanation=(
            "response_body is truncated or dangling (does not end with proper terminal punctuation) -- "
            f"got: {response_body!r}"
        ),
    )
