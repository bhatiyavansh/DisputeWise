#!/usr/bin/env python3
"""Part K -- Phase 4 evaluation suite.

A small, controlled benchmark of 8 hand-constructed cases (NOT the locked
test set, NOT the training/validation splits -- entirely synthetic fixtures
built in-process, per docs/phase4.md's honesty note about why exact grounding
labels are constructed rather than mined from real disputes). Each case has
a KNOWN expected outcome for evidence-gap detection, retrieval relevance,
and claim grounding, so this script measures the pipeline against ground
truth rather than just demonstrating one example.

Uses FakeLLMProvider (never a real API call) with hand-authored "generated"
claims per case -- standing in for what a real LLM might produce, including
the adversarial patterns from Part L. This keeps the evaluation deterministic
and reproducible without requiring an LLM API key.

Usage:
    python scripts/evaluate_evidence_intel.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")

from app.evidence_intel import versions as v  # noqa: E402
from app.evidence_intel.generation import generate_draft  # noqa: E402
from app.evidence_intel.llm_provider import FakeLLMProvider  # noqa: E402
from app.evidence_intel.packet import build_packet  # noqa: E402
from app.evidence_intel.retrieval import retrieve_for_case  # noqa: E402
from app.evidence_intel.safety import determine_response_state  # noqa: E402
from app.evidence_intel.verifier import verify_claims  # noqa: E402
from app.ml import schema as ml_schema  # noqa: E402


class _Row:
    def __init__(self, evidence_type, available, value, relevance, strength, evidence_id):
        self.evidence_type = evidence_type
        self.available = available
        self.value = value
        self.relevance = relevance
        self.strength = strength
        self.evidence_id = evidence_id


def _row(evidence_type, available, value, relevance, strength, idx):
    return _Row(evidence_type, available, value, relevance, strength, f"EVD-EVAL-{idx:03d}")


def _base_kwargs(reason_code: str, dispute_id: str, rows: list) -> dict:
    return dict(
        dispute_id=dispute_id,
        reason_code=reason_code,
        dispute_amount=5000.0,
        dispute_status="open",
        created_at="2026-01-01T00:00:00+00:00",
        payment_method="card",
        transaction_status="captured",
        three_ds_authenticated=True,
        avs_result="Y",
        cvv_result="M",
        account_age_days=300,
        previous_order_count=8,
        previous_successful_order_count=7,
        previous_dispute_count=0,
        previous_refund_count=0,
        evidence_rows=rows,
    )


def build_cases() -> list[dict]:
    """8 controlled cases with known expected outcomes."""
    cases = []

    # 1. Complete strong evidence -> full coverage, all claims SUPPORTED, DRAFT_READY
    rows = [
        _row("delivery_confirmed", True, {"confirmed": True}, "high", 0.9, 1),
        _row("tracking_available", True, {"available": True}, "high", 0.85, 2),
        _row("delivery_address_match", True, {"match": True}, "high", 0.9, 3),
        _row("delivery_timestamp", True, {"timestamp": "2026-01-10T00:00:00Z"}, "high", 0.8, 4),
        _row("proof_of_delivery", True, {"present": True}, "high", 0.95, 5),
        _row("customer_communication_available", True, {"present": True}, "medium", 0.7, 6),
        _row("cancellation_request", True, {"requested": False}, "medium", 0.7, 7),
        _row("refund_request", True, {"requested": False}, "medium", 0.7, 8),
    ]
    cases.append(
        {
            "name": "complete_strong_evidence",
            "reason_code": "goods_not_received",
            "rows": rows,
            "expected_missing_critical": False,
            "expected_blocked": False,
            "claims": [
                {"claim_id": "C1", "text": "Delivery was confirmed with tracking.", "claim_type": "fact", "evidence_ids": ["EVD-EVAL-001", "EVD-EVAL-002"], "source_ids": []},
                {"claim_id": "C2", "text": "Proof of delivery is on file.", "claim_type": "fact", "evidence_ids": ["EVD-EVAL-005"], "source_ids": []},
            ],
        }
    )

    # 2. Missing critical evidence -> gap analyzer must flag it; claims still honest (don't fabricate the gap)
    rows2 = [r for r in rows if r.evidence_type != "proof_of_delivery"]
    rows2.append(_row("proof_of_delivery", False, None, "high", 0.0, 9))
    cases.append(
        {
            "name": "missing_critical_evidence",
            "reason_code": "goods_not_received",
            "rows": rows2,
            "expected_missing_critical": True,
            "expected_blocked": False,
            # NOTE: a claim reporting that evidence is ABSENT must not cite the
            # missing evidence_id in `evidence_ids` -- citing an ID always means
            # "this grounds my claim" (see prompt.py's rule 1 and verifier.py's
            # "cites unavailable evidence" check, which treats any such citation
            # as UNSUPPORTED by design: citing missing evidence as if it were
            # support is exactly the failure mode Part L's adversarial case #2
            # tests for). Absence is reported via the separate `missing_evidence`
            # list instead, which this case's `missing_evidence` field already
            # covers (see run_case()) -- there is deliberately no claim here
            # asserting non-existence of proof_of_delivery.
            "claims": [
                {"claim_id": "C1", "text": "Delivery was confirmed with tracking.", "claim_type": "fact", "evidence_ids": ["EVD-EVAL-001", "EVD-EVAL-002"], "source_ids": []},
            ],
        }
    )

    # 3. Contradictory evidence -> claim states a date conflicting with cited evidence's real value
    cases.append(
        {
            "name": "contradictory_evidence",
            "reason_code": "goods_not_received",
            "rows": rows,
            "expected_missing_critical": False,
            "expected_blocked": True,
            "claims": [
                {"claim_id": "C1", "text": "Delivery timestamp shows arrival on 2027-06-15.", "claim_type": "fact", "evidence_ids": ["EVD-EVAL-004"], "source_ids": []},
            ],
        }
    )

    # 4. Weak evidence -> PARTIALLY_SUPPORTED, DRAFT_FLAGGED (not blocked)
    weak_rows = [_row("delivery_confirmed", True, {"confirmed": True}, "high", 0.15, 10)]
    cases.append(
        {
            "name": "weak_evidence",
            "reason_code": "goods_not_received",
            "rows": weak_rows,
            "expected_missing_critical": True,
            "expected_blocked": False,
            "expected_flagged": True,
            "claims": [
                {"claim_id": "C1", "text": "Delivery was confirmed.", "claim_type": "fact", "evidence_ids": ["EVD-EVAL-010"], "source_ids": []},
            ],
        }
    )

    # 5. Unsupported claim opportunity -> claim with zero citations
    cases.append(
        {
            "name": "unsupported_claim_opportunity",
            "reason_code": "unauthorized_transaction",
            "rows": [_row("three_ds", True, {"authenticated": True}, "high", 0.9, 11)],
            "expected_missing_critical": True,
            "expected_blocked": True,
            "claims": [
                {"claim_id": "C1", "text": "The customer has a long history of legitimate purchases.", "claim_type": "inference", "evidence_ids": [], "source_ids": []},
            ],
        }
    )

    # 6. Unknown/missing field -> claim cites an evidence_id that doesn't exist in this packet
    cases.append(
        {
            "name": "unknown_missing_field",
            "reason_code": "duplicate_charge",
            "rows": [_row("prior_order_history", True, {"order_count": 5}, "high", 0.8, 12)],
            "expected_missing_critical": True,
            "expected_blocked": True,
            "claims": [
                {"claim_id": "C1", "text": "Signed receipt confirms a single charge.", "claim_type": "fact", "evidence_ids": ["EVD-DOES-NOT-EXIST"], "source_ids": []},
            ],
        }
    )

    # 7. Reason-code mismatch -> retrieval must stay scoped to the case's own reason code
    cases.append(
        {
            "name": "reason_code_mismatch_guard",
            "reason_code": "unauthorized_transaction",
            "rows": [_row("three_ds", True, {"authenticated": True}, "high", 0.9, 13)],
            "expected_missing_critical": True,
            "expected_blocked": False,
            "claims": [
                {"claim_id": "C1", "text": "3-D Secure authentication succeeded for this transaction.", "claim_type": "fact", "evidence_ids": ["EVD-EVAL-013"], "source_ids": []},
            ],
        }
    )

    # 8. Multiple evidence sources supporting one claim -> positive control
    cases.append(
        {
            "name": "multiple_evidence_sources",
            "reason_code": "goods_not_received",
            "rows": rows,
            "expected_missing_critical": False,
            "expected_blocked": False,
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Delivery confirmation, tracking, and address match all support fulfillment.",
                    "claim_type": "fact",
                    "evidence_ids": ["EVD-EVAL-001", "EVD-EVAL-002", "EVD-EVAL-003"],
                    "source_ids": [],
                },
            ],
        }
    )

    return cases


def run_case(case: dict) -> dict:
    packet = build_packet(**_base_kwargs(case["reason_code"], f"DSP-EVAL-{case['name']}", case["rows"]))
    retrieval_results = retrieve_for_case(reason_code=case["reason_code"], gap=packet.gap, top_k=6)

    provider = FakeLLMProvider(
        response={
            "summary": f"Evaluation case: {case['name']}",
            "claims": case["claims"],
            "missing_evidence": [i.evidence_type for i in packet.gap.missing_critical],
            "response_body": "Evaluation fixture response body.",
        }
    )
    draft = generate_draft(packet, retrieval_results, provider)
    verifications = verify_claims(draft.claims, packet, retrieval_results)
    response_state, reason = determine_response_state(verifications)

    reason_code_leak = [r for r in retrieval_results if r.metadata["reason_code_id"] != case["reason_code"]]
    addresses_gap = any(r.metadata["addresses_gap"] for r in retrieval_results) if packet.gap.missing_critical else None

    return {
        "name": case["name"],
        "reason_code": case["reason_code"],
        "gap": {
            "required": packet.gap.required_count,
            "available": packet.gap.available_count,
            "missing": packet.gap.missing_count,
            "coverage_ratio": round(packet.gap.coverage_ratio, 4),
            "has_critical_gap": packet.gap.has_critical_gap,
            "expected_missing_critical": case["expected_missing_critical"],
            "gap_detection_correct": packet.gap.has_critical_gap == case["expected_missing_critical"],
        },
        "retrieval": {
            "n_results": len(retrieval_results),
            "reason_code_leaks": len(reason_code_leak),
            "addresses_gap": addresses_gap,
        },
        "grounding": {
            "claim_statuses": {c.claim_id: c.status for c in verifications},
            "response_state": response_state,
            "response_state_reason": reason,
            "expected_blocked": case["expected_blocked"],
            "blocked_prediction_correct": (response_state == v.DRAFT_BLOCKED) == case["expected_blocked"],
        },
    }


def main() -> None:
    print("DisputeWise Phase 4 -- evidence intelligence evaluation")
    print(f"knowledge_base={v.KNOWLEDGE_BASE_VERSION} verifier={v.VERIFIER_VERSION} response_schema={v.RESPONSE_SCHEMA_VERSION}\n")

    results = [run_case(case) for case in build_cases()]

    for r in results:
        print(f"[{r['name']}]")
        print(f"  gap: required={r['gap']['required']} available={r['gap']['available']} missing={r['gap']['missing']} "
              f"critical_gap={r['gap']['has_critical_gap']} (expected={r['gap']['expected_missing_critical']}) "
              f"{'OK' if r['gap']['gap_detection_correct'] else 'MISMATCH'}")
        print(f"  retrieval: n={r['retrieval']['n_results']} reason_code_leaks={r['retrieval']['reason_code_leaks']} "
              f"addresses_gap={r['retrieval']['addresses_gap']}")
        print(f"  grounding: {r['grounding']['claim_statuses']} -> {r['grounding']['response_state']} "
              f"(expected_blocked={r['grounding']['expected_blocked']}) "
              f"{'OK' if r['grounding']['blocked_prediction_correct'] else 'MISMATCH'}")
        print()

    # ---- aggregate metrics -----------------------------------------------
    n_cases = len(results)
    gap_correct = sum(1 for r in results if r["gap"]["gap_detection_correct"])
    blocked_correct = sum(1 for r in results if r["grounding"]["blocked_prediction_correct"])
    total_reason_code_leaks = sum(r["retrieval"]["reason_code_leaks"] for r in results)
    total_retrieved = sum(r["retrieval"]["n_results"] for r in results)

    cases_with_gap = [r for r in results if r["gap"]["has_critical_gap"]]
    hit_rate = (
        sum(1 for r in cases_with_gap if r["retrieval"]["addresses_gap"]) / len(cases_with_gap)
        if cases_with_gap
        else None
    )

    all_claim_statuses = [status for r in results for status in r["grounding"]["claim_statuses"].values()]
    n_claims = len(all_claim_statuses)
    status_counts = {status: all_claim_statuses.count(status) for status in v.CLAIM_STATUSES}

    n_blocked = sum(1 for r in results if r["grounding"]["response_state"] == v.DRAFT_BLOCKED)

    summary = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "n_cases": n_cases,
        "knowledge_base_version": v.KNOWLEDGE_BASE_VERSION,
        "verifier_version": v.VERIFIER_VERSION,
        "response_schema_version": v.RESPONSE_SCHEMA_VERSION,
        "note": (
            "This is a hand-constructed, deterministic benchmark (8 synthetic cases), NOT the "
            "locked test set and NOT training/validation data. It exists because exact grounding "
            "labels for real disputes don't exist -- see docs/phase4.md for the full rationale."
        ),
        "evidence_gap": {
            "critical_gap_detection_accuracy": round(gap_correct / n_cases, 4),
            "cases_with_expected_gap": sum(1 for r in results if r["gap"]["expected_missing_critical"]),
        },
        "retrieval": {
            "reason_code_relevance": round(1 - (total_reason_code_leaks / total_retrieved), 4) if total_retrieved else None,
            "total_reason_code_leaks": total_reason_code_leaks,
            "required_guidance_hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        },
        "grounding": {
            "n_claims": n_claims,
            "claim_status_counts": status_counts,
            "supported_rate": round(status_counts[v.CLAIM_SUPPORTED] / n_claims, 4) if n_claims else None,
            "unsupported_rate": round(status_counts[v.CLAIM_UNSUPPORTED] / n_claims, 4) if n_claims else None,
            "invalid_reference_rate": round(status_counts[v.CLAIM_INVALID_REFERENCE] / n_claims, 4) if n_claims else None,
            "partially_supported_rate": round(status_counts[v.CLAIM_PARTIALLY_SUPPORTED] / n_claims, 4) if n_claims else None,
            "blocked_response_rate": round(n_blocked / n_cases, 4),
            "blocked_prediction_accuracy": round(blocked_correct / n_cases, 4),
        },
        "cases": results,
    }

    print("=== Summary ===")
    print(f"Evidence-gap critical-detection accuracy: {summary['evidence_gap']['critical_gap_detection_accuracy']:.0%}")
    print(f"Retrieval reason-code relevance:           {summary['retrieval']['reason_code_relevance']:.0%}")
    print(f"Retrieval required-guidance hit rate:      {summary['retrieval']['required_guidance_hit_rate']:.0%}")
    print(f"Grounding supported rate:                  {summary['grounding']['supported_rate']:.0%}")
    print(f"Grounding unsupported rate:                {summary['grounding']['unsupported_rate']:.0%}")
    print(f"Grounding invalid-reference rate:           {summary['grounding']['invalid_reference_rate']:.0%}")
    print(f"Blocked-response rate:                      {summary['grounding']['blocked_response_rate']:.0%}")
    print(f"Blocked-prediction accuracy (vs. expected):  {summary['grounding']['blocked_prediction_accuracy']:.0%}")

    out_path = ml_schema.evaluation_dir() / "evidence_intel_evaluation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
