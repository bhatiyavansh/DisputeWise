"""Phase 4 -- Evidence Intelligence, grounded RAG, and claim-level verification.

    dispute -> evidence gap analysis -> evidence packet -> RAG retrieval
             -> grounded response generation -> claim-level verification
             -> safety policy (DRAFT_READY / DRAFT_FLAGGED / DRAFT_BLOCKED)
             -> human approval (always required; nothing here submits anything)

Design boundary: this package answers "what evidence do we have/need, what
does authoritative guidance say, and is the generated response actually
grounded in that evidence" -- it does not predict winnability (Phase 2 /
app/ml/) and does not decide whether to contest (Phase 3 / app/decision/).
Both are reused here, never re-implemented.

Every material claim in a generated response is checked deterministically
against the case's own evidence and the retrieved reference chunks. The LLM
is never the sole authority on whether its own output is grounded -- see
verifier.py.
"""
