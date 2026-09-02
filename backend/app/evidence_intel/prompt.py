"""Part E -- prompt construction.

The model is never asked to "write a chargeback response." It is given a
narrow, structured context (evidence packet + retrieved guidance) and a
strict output contract, with the exact set of evidence_ids / source_ids it
is allowed to cite spelled out explicitly. Nothing here is chain-of-thought
-- the system/user text below IS what gets stored in the trace (Part H),
because it's already concise structured instruction, not hidden reasoning.
"""

from __future__ import annotations

import json
from typing import Any

from app.evidence_intel import versions as v
from app.evidence_intel.packet import EvidencePacket
from app.evidence_intel.retrieval import RetrievalResult

TOOL_NAME = "emit_grounded_draft"

RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "One or two sentence overview of the case for the merchant."},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string", "description": "e.g. C1, C2, ..."},
                    "text": {"type": "string"},
                    "claim_type": {"type": "string", "enum": list(v.CLAIM_TYPES)},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "evidence_id values this claim is grounded in; MUST come only from the 'Evidence IDs you may cite' list (never an ID from the MISSING list, even to state something is absent)",
                    },
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "source_id values this claim relies on for policy/guidance; MUST come only from the Available Source IDs list provided",
                    },
                },
                "required": ["claim_id", "text", "claim_type", "evidence_ids", "source_ids"],
            },
        },
        "missing_evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "evidence_type values you were told are missing -- restate them, do not invent replacements",
        },
        "response_body": {
            "type": "string",
            "description": "The full draft response text, composed only from the claims above. Must be complete sentences ending in proper terminal punctuation -- never truncated or dangling (e.g. never ending in ':').",
        },
    },
    "required": ["summary", "claims", "missing_evidence", "response_body"],
}


SYSTEM_PROMPT = """You are DisputeWise's evidence-grounded response drafting assistant for chargeback disputes.

You are NOT a general chargeback-writing assistant. You draft a structured, evidence-grounded response body for ONE specific case, using ONLY the case data you are given below. You do not have general knowledge about this merchant, this customer, or this transaction beyond what is provided.

STRICT RULES (a downstream verifier checks every one of these mechanically -- violations cause the response to be blocked):

1. Every claim in your `claims` array must cite the evidence_id(s) or source_id(s) it is based on, using ONLY the IDs listed under "Evidence IDs you may cite" / "Available Source IDs" below. Never invent an ID. Never reuse an ID that looks plausible but was not given to you.
2. The evidence_ids you cite in ANY claim must ALL be evidence that is actually AVAILABLE. Missing evidence types are listed separately below under "Evidence types that are MISSING" -- those have NO evidence_id you are allowed to cite, not even to state that they're absent. To mention that something is missing, refer to it BY NAME in the claim text (e.g. "proof of delivery is not on file for this transaction") with EMPTY evidence_ids for that specific statement, or list it in the top-level `missing_evidence` array. Citing a missing item's evidence_id is treated identically whether you're claiming it supports you or claiming it's absent -- don't do either.
3. Do not try to "prove" or fully compensate for a piece of missing critical evidence using other, different evidence. If a required evidence type is missing, state plainly what IS available and separately, cautiously, note what is missing -- do not argue that the available evidence "supports", "confirms", "demonstrates", or "shows" the fact that the missing evidence would have proven, and never use phrasing like "despite the absence of X" or "even without X" followed by a claim that concludes X's absence doesn't matter. Weaker or unrelated evidence does not substitute for an explicitly required item. Prefer this pattern: "The available evidence includes A, B, and C, but <missing item> is currently missing." Do NOT write: "Despite <missing item> being absent, A, B, and C support/confirm/demonstrate [the fact <missing item> would have shown]."
4. Never invent factual details: no dates, amounts, delivery timestamps, customer statements, or transaction details beyond what is given.
5. Never guarantee or predict the outcome of the dispute (no "this will win", "guaranteed", "certain to succeed", etc.). Outcome likelihood is not your job.
6. Never state or imply a network/policy requirement that is not present in the provided guidance chunks.
7. Mark each claim's `claim_type`: "fact" (directly from this case's evidence), "reference" (from the provided guidance), "inference" (a reasonable conclusion you drew from fact+reference -- must still cite the evidence/sources it was inferred from, and must follow rule 3 above), or "summary" (a rollup statement).
8. If you cannot support a sentence with the evidence/guidance you were given, do not include it.
9. Every claim's `text`, and the overall `response_body`, MUST be complete sentences ending in proper punctuation (a period, question mark, or exclamation point). NEVER end a claim or the response_body with a colon, dash, comma, or any other dangling punctuation, and never cut a sentence off mid-thought (e.g. never write something like "Proof of delivery is: " with nothing meaningful after it -- either finish the sentence or omit it entirely). A truncated response is rejected exactly like an unsupported claim.

Output ONLY through the provided tool call, matching its schema exactly."""


def _evidence_lines(packet: EvidencePacket) -> str:
    lines = []
    for item in packet.evidence:
        value = json.dumps(item.value) if item.value is not None else "null"
        lines.append(
            f"  - evidence_id={item.evidence_id} type={item.evidence_type} "
            f"available={str(item.available).lower()} relevance={item.relevance} "
            f"strength={item.strength:.2f} value={value}"
        )
    return "\n".join(lines)


def _guidance_lines(results: list[RetrievalResult]) -> str:
    if not results:
        return "  (no guidance retrieved)"
    return "\n".join(
        f"  - source_id={r.source_id} chunk_id={r.chunk_id} (score={r.relevance_score:.3f}): {r.text}"
        for r in results
    )


def build_user_prompt(packet: EvidencePacket, retrieval_results: list[RetrievalResult]) -> str:
    # Only AVAILABLE evidence may ever be cited -- this is the actual fix for
    # a real bug (verifier-v1.1 hardening pass): the previous version of this
    # list included unavailable evidence_ids under the heading "Available
    # Evidence IDs", so a live model correctly read that as permission to
    # cite them, and did -- citing missing proof_of_delivery's evidence_id
    # while describing it as absent, which the verifier (correctly) still
    # rejects as "cites unavailable evidence". Missing evidence now gets its
    # own section below with NO citable ID at all.
    citable_evidence_ids = [item.evidence_id for item in packet.evidence if item.available]
    missing_evidence_types = [item.evidence_type for item in packet.evidence if not item.available]
    valid_source_ids = sorted({r.source_id for r in retrieval_results} | {packet.guidance.source_id})
    missing_required = [i.evidence_type for i in packet.gap.items if i.required and i.status == "MISSING"]

    return f"""CASE
  dispute_id={packet.case.dispute_id}
  reason_code={packet.case.reason_code} ({packet.guidance.reason_code_name})
  dispute_amount={packet.case.dispute_amount}
  dispute_status={packet.case.dispute_status}

REASON CODE GUIDANCE (source_id={packet.guidance.source_id})
  {packet.guidance.description}

TRANSACTION FACTS
  payment_method={packet.transaction.payment_method}
  transaction_status={packet.transaction.transaction_status}
  three_ds_authenticated={packet.transaction.three_ds_authenticated}
  avs_result={packet.transaction.avs_result}
  cvv_result={packet.transaction.cvv_result}

CUSTOMER HISTORY
  account_age_days={packet.customer.account_age_days}
  previous_order_count={packet.customer.previous_order_count}
  previous_successful_order_count={packet.customer.previous_successful_order_count}
  previous_dispute_count={packet.customer.previous_dispute_count}
  previous_refund_count={packet.customer.previous_refund_count}

EVIDENCE (available and unavailable -- do not contradict the `available` flag)
{_evidence_lines(packet)}

EVIDENCE GAP ANALYSIS
  required={packet.gap.required_count} available={packet.gap.available_count} missing={packet.gap.missing_count}
  missing required evidence types: {missing_required if missing_required else "(none)"}

RETRIEVED GUIDANCE
{_guidance_lines(retrieval_results)}

Evidence IDs you may cite (the ONLY evidence_ids allowed in any claim's evidence_ids -- all of these ARE available): {citable_evidence_ids}
Evidence types that are MISSING for this case (NO evidence_id exists for these that you may cite -- mention by name in text only, with empty evidence_ids for that statement, and/or list in missing_evidence): {missing_evidence_types if missing_evidence_types else "(none)"}
Available Source IDs (the ONLY source_ids you may cite): {valid_source_ids}

Draft a structured, evidence-grounded response for this case now, following every rule in the system prompt. Remember: state what the available evidence shows plainly; for anything in the MISSING list, note its absence in plain text without citing an ID for it, and do not argue that other evidence overcomes or substitutes for it. End every claim and the response_body with a complete sentence and proper terminal punctuation."""
