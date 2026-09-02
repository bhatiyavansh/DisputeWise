"""Phase 3 cost-sensitive decision engine.

Consumes the Phase 2 calibrated winnability probability and turns it into a
transparent, auditable CONTEST / HUMAN_REVIEW / DO_NOT_CONTEST recommendation
based on expected net value.

Scope boundary: this package is decision SUPPORT only. It never submits,
contests, or otherwise acts on a dispute; the highest-confidence output is
still just a label the routers/api layer returns to a human. RAG, LLM
drafting, and automatic submission are explicitly out of scope (Phase 4+).
"""
