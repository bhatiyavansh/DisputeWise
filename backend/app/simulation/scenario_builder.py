"""Phase 7A -- apply hypothetical evidence changes to a real case.

Produces a DETACHED copy of a case's evidence rows with some evidence
added or removed. The loaded ORM rows are never mutated: every scenario row
is a frozen SimEvidence dataclass (shared with Phase 6 simulation), so there
is no persistent object holding a modified value that SQLAlchemy could flush.
That is what makes "the production case is unchanged" structural rather than
a convention.

Strength for hypothetically-added evidence reuses Phase 6's documented
midpoint assumption (CORROBORATING_STRENGTH) rather than inventing a second
convention -- see app/simulation/case_builder.py for why that number and not
a random draw.

This module derives no probability, no decision and no relevance. Relevance
for an evidence type the case has no row for is read from data/reference/,
the same authoritative source the gap analyzer uses.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.evidence_intel.reference_data import ReferenceData, load_reference_data
from app.ml import schema
from app.simulation.case_builder import CORROBORATING_STRENGTH, SimEvidence


class UnknownEvidenceTypeError(ValueError):
    """An evidence type outside the Phase 1 taxonomy was requested."""


def _positive_value(evidence_type: str, dispute: Any) -> dict[str, Any]:
    """The JSON value a CORROBORATING instance of this evidence type carries.

    Shapes mirror app/ml/schema.py's EVIDENCE_VALUE_SPEC (and the generator
    that produced the dataset). Where the value is a real property of this
    case rather than a flag -- delivery timing, the customer's own order and
    dispute counts -- it is read off the case, not invented.
    """
    transaction = dispute.transaction
    customer = transaction.customer

    values: dict[str, dict[str, Any]] = {
        "three_ds": {"authenticated": True},
        "avs": {"result": "Y"},
        "cvv": {"result": "M"},
        "device_match": {"match": True},
        "ip_match": {"match": True},
        "delivery_confirmed": {"confirmed": True},
        "tracking_available": {"available": True},
        "delivery_address_match": {"match": True},
        "delivery_timestamp": {"timestamp": (transaction.captured_at + timedelta(days=3)).isoformat()},
        "proof_of_delivery": {"present": True},
        "prior_order_history": {"order_count": customer.previous_order_count},
        "prior_successful_orders": {"count": customer.previous_successful_order_count},
        "prior_disputes": {"count": customer.previous_dispute_count},
        "customer_communication_available": {"present": True},
        # Inverted signals: the corroborating state is that the customer did
        # NOT request a cancellation/refund (mirrors the generator's
        # evd_positive mapping).
        "cancellation_request": {"requested": False},
        "refund_request": {"requested": False},
    }
    return values[evidence_type]


def _to_sim_evidence(row: Any) -> SimEvidence:
    """Detached, immutable copy of a stored evidence row."""
    return SimEvidence(
        evidence_id=row.evidence_id,
        evidence_type=row.evidence_type,
        available=bool(row.available),
        value=row.value,
        relevance=row.relevance,
        strength=float(row.strength or 0.0),
        created_at=row.created_at,
    )


def validate_evidence_types(evidence_types: list[str]) -> None:
    unknown = sorted(set(evidence_types) - set(schema.ALL_EVIDENCE_TYPES))
    if unknown:
        raise UnknownEvidenceTypeError(
            f"unknown evidence types: {unknown}. Valid types: {sorted(schema.ALL_EVIDENCE_TYPES)}"
        )


def apply_evidence_changes(
    dispute: Any,
    evidence_rows: list,
    *,
    add: list[str],
    remove: list[str],
    reference: ReferenceData | None = None,
) -> list[SimEvidence]:
    """Return a detached evidence list with `add` made available and
    `remove` made unavailable. Input rows are never modified.
    """
    validate_evidence_types([*add, *remove])
    overlap = set(add) & set(remove)
    if overlap:
        raise UnknownEvidenceTypeError(f"evidence types listed as both added and removed: {sorted(overlap)}")

    reference = reference or load_reference_data()
    add_set, remove_set = set(add), set(remove)

    scenario: list[SimEvidence] = []
    seen: set[str] = set()

    for row in evidence_rows:
        copy = _to_sim_evidence(row)
        seen.add(copy.evidence_type)

        if copy.evidence_type in add_set:
            copy = SimEvidence(
                evidence_id=copy.evidence_id,
                evidence_type=copy.evidence_type,
                available=True,
                value=_positive_value(copy.evidence_type, dispute),
                # Phase 6's documented midpoint for corroborating evidence.
                strength=CORROBORATING_STRENGTH,
                relevance=copy.relevance,
                created_at=copy.created_at,
            )
        elif copy.evidence_type in remove_set:
            copy = SimEvidence(
                evidence_id=copy.evidence_id,
                evidence_type=copy.evidence_type,
                available=False,
                value=None,
                strength=0.0,
                relevance=copy.relevance,
                created_at=copy.created_at,
            )
        scenario.append(copy)

    # An evidence type the case has no row for at all: only meaningful to
    # add. Relevance comes from reference data for this reason code.
    relevance_by_type = {
        requirement.evidence_type: requirement.relevance
        for requirement in reference.requirements_for(dispute.reason_code)
    }
    for evidence_type in sorted(add_set - seen):
        scenario.append(
            SimEvidence(
                evidence_id=f"SCENARIO-{evidence_type}",
                evidence_type=evidence_type,
                available=True,
                value=_positive_value(evidence_type, dispute),
                relevance=relevance_by_type.get(evidence_type, "low"),
                strength=CORROBORATING_STRENGTH,
                created_at=dispute.created_at,
            )
        )

    return scenario
