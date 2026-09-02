"""Version constants and enums for every Phase 4 schema/config.

Kept in one module (mirrors app/ml/schema.py's MODEL_VERSION /
app/decision/schema.py's DECISION_POLICY_VERSION pattern) so every API
response can report exactly which version of which component produced it,
making a Phase 4 response fully reproducible: given the same case, the same
five version strings below, and the same reference data, the deterministic
parts (gap analysis, packet, retrieval, verification) reproduce byte-for-byte.
Only LLM generation itself is not bit-reproducible (a real model), which is
exactly why everything downstream of it is independently checked.
"""

from __future__ import annotations

EVIDENCE_SCHEMA_VERSION = "evidence-v1"  # evidence-gap + evidence-packet schema
KNOWLEDGE_BASE_VERSION = "knowledge-v1"
RETRIEVAL_CONFIG_VERSION = "retrieval-v1"
# prompt-v1.1: hardening pass after the first live OpenRouter run on DSP-031597
# surfaced two real failures -- (1) the "Available Evidence IDs" list included
# unavailable evidence_ids, so the model could (and did) cite missing evidence
# while describing it as absent; (2) no instruction against incomplete/dangling
# sentences. Same JSON schema (RESPONSE_JSON_SCHEMA is unchanged); only the
# instruction text changed. See docs/phase4.md's hardening-pass notes.
PROMPT_VERSION = "prompt-v1.1"
RESPONSE_SCHEMA_VERSION = "response-v1"
# verifier-v1.1: same hardening pass added two deterministic checks -- response/
# claim-text completeness (INCOMPLETE) and a text-pattern guard against
# inference claims that rhetorically wave away missing critical evidence. All
# prior checks (1-7 below) are unchanged.
VERIFIER_VERSION = "verifier-v1.1"

# ---------------------------------------------------------------------------
# Evidence gap analysis
# ---------------------------------------------------------------------------
STATUS_AVAILABLE = "AVAILABLE"
STATUS_MISSING = "MISSING"

RELEVANCE_HIGH = "HIGH"
RELEVANCE_MEDIUM = "MEDIUM"
RELEVANCE_LOW = "LOW"

PRIORITY_CRITICAL = "CRITICAL"
PRIORITY_IMPORTANT = "IMPORTANT"
PRIORITY_OPTIONAL = "OPTIONAL"
PRIORITY_NONE = "NONE"  # available -- nothing to prioritize

# ---------------------------------------------------------------------------
# Claim-level grounding verification
# ---------------------------------------------------------------------------
CLAIM_SUPPORTED = "SUPPORTED"
CLAIM_PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
CLAIM_UNSUPPORTED = "UNSUPPORTED"
CLAIM_INVALID_REFERENCE = "INVALID_REFERENCE"
# Added in the verifier-v1.1 hardening pass: a claim's text, or the overall
# response_body, is truncated/dangling (e.g. ends with ":" and nothing after)
# -- a formatting/completeness defect, distinct from an evidentiary one, but
# still always blocking (see safety.py). Additive: does not replace or change
# the meaning of the four statuses above.
CLAIM_INCOMPLETE = "INCOMPLETE"

CLAIM_STATUSES = (
    CLAIM_SUPPORTED,
    CLAIM_PARTIALLY_SUPPORTED,
    CLAIM_UNSUPPORTED,
    CLAIM_INVALID_REFERENCE,
    CLAIM_INCOMPLETE,
)

# ---------------------------------------------------------------------------
# Response safety states
# ---------------------------------------------------------------------------
DRAFT_READY = "DRAFT_READY"
DRAFT_FLAGGED = "DRAFT_FLAGGED"
DRAFT_BLOCKED = "DRAFT_BLOCKED"
GENERATION_UNAVAILABLE = "GENERATION_UNAVAILABLE"  # no LLM provider configured

RESPONSE_STATES = (DRAFT_READY, DRAFT_FLAGGED, DRAFT_BLOCKED, GENERATION_UNAVAILABLE)

# ---------------------------------------------------------------------------
# Claim provenance kind -- see docs/phase4.md for the FACT/REFERENCE/
# INFERENCE/UNSUPPORTED distinction this implements.
# ---------------------------------------------------------------------------
CLAIM_TYPE_FACT = "fact"  # directly present in this case's evidence
CLAIM_TYPE_REFERENCE = "reference"  # from authoritative reference/knowledge-base guidance
CLAIM_TYPE_INFERENCE = "inference"  # derived/summarized by the model from FACT+REFERENCE
CLAIM_TYPE_SUMMARY = "summary"  # a rollup statement (e.g. "evidence supports fulfillment")

CLAIM_TYPES = (CLAIM_TYPE_FACT, CLAIM_TYPE_REFERENCE, CLAIM_TYPE_INFERENCE, CLAIM_TYPE_SUMMARY)

DISCLAIMER = (
    "Decision support and response PREPARATION only. Nothing here is submitted, sent to a "
    "customer, or transmitted to a card network automatically. A human must review and approve "
    "this draft before any action is taken."
)
