"""Phase 6 -- turn a hypothetical dispute description into in-memory case
parts that the existing Phase 2/3/4 pipeline can consume unchanged.

This module builds objects, it does not compute anything the rest of the
system already computes. Specifically it does NOT:
  - build features (app/ml/features.py does, via scoring_service.score_parts)
  - score, calibrate, or band (app/ml/model.py does)
  - decide (app/decision/policy.py does)
  - analyze gaps or assign evidence relevance (app/evidence_intel does, from
    data/reference/) -- relevance here is *read* from reference data, never
    invented per evidence type.

Nothing built here is persisted. The objects are duck-typed to match
app.models.{dispute,transaction,customer,evidence} closely enough for
scoring_service._to_frames(), gap_analyzer.case_evidence_state_from_rows()
and packet.build_packet() to consume them, which is what lets simulation
share one code path with stored cases.

TWO DELIBERATE MODELLING CHOICES, both documented because they are the only
places where simulation must supply something a real intake form could not
read directly off the wire:

1. `strength` (0-1 per evidence row). In the Phase 1 dataset this is a
   random draw -- uniform(0.6, 1.0) when the evidence is corroborating,
   uniform(0.0, 0.5) when it is on file but unhelpful (see
   scripts/generate_dataset.py). A simulation cannot draw randomly without
   becoming non-reproducible, so it uses the MIDPOINT of each of those two
   documented ranges (0.8 / 0.25). These are the expected values of the
   distribution the model was trained on -- not a new business rule, and not
   tuned to make any scenario look better.

2. Timestamps. Features only ever use *differences* between timestamps
   (capture lag, transaction->dispute days, dispute->deadline days -- see
   app/ml/features.py, which reads no wall clock), so simulation anchors
   them to a fixed instant. That makes a simulation byte-reproducible: the
   same request always yields the same features. Real wall-clock time
   appears only in trace/packet `generated_at` metadata, never in a feature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.evidence_intel.reference_data import ReferenceData, load_reference_data
from app.ml import schema

# Midpoints of the generator's two documented strength ranges (see module docstring).
CORROBORATING_STRENGTH = 0.8
UNHELPFUL_STRENGTH = 0.25

# Fixed anchor so identical requests produce identical features (see docstring).
SIMULATION_ANCHOR = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SimCustomer:
    customer_id: str
    account_age_days: int
    previous_order_count: int
    previous_successful_order_count: int
    previous_dispute_count: int
    previous_refund_count: int


@dataclass(frozen=True)
class SimTransaction:
    transaction_id: str
    customer: SimCustomer
    amount: float
    payment_method: str
    created_at: datetime
    captured_at: datetime
    status: str
    billing_address_id: str
    shipping_address_id: str
    avs_result: str
    cvv_result: str
    three_ds_authenticated: bool


@dataclass(frozen=True)
class SimDispute:
    dispute_id: str
    transaction: SimTransaction
    reason_code: str
    dispute_amount: float
    status: str
    created_at: datetime
    response_deadline: datetime


@dataclass(frozen=True)
class SimEvidence:
    evidence_id: str
    evidence_type: str
    available: bool
    value: dict[str, Any] | None
    relevance: str
    strength: float
    created_at: datetime


@dataclass(frozen=True)
class SimulationCase:
    """Everything the downstream pipeline needs, with no DB row behind it."""

    dispute: SimDispute
    evidence: list[SimEvidence] = field(default_factory=list)


def _positive_flags(spec: Any) -> dict[str, bool]:
    """Whether each evidence type CORROBORATES the merchant's position.

    Mirrors `evd_positive` in scripts/generate_dataset.py exactly, including
    the two inverted signals (a cancellation/refund request having been made
    counts against the merchant, so 'positive' is its absence).
    """
    return {
        "three_ds": spec.three_ds_authenticated,
        "avs": spec.avs_result == "Y",
        "cvv": spec.cvv_result == "M",
        "device_match": spec.device_match,
        "ip_match": spec.ip_match,
        "delivery_confirmed": spec.delivery_confirmed,
        "tracking_available": spec.tracking_available,
        "delivery_address_match": spec.delivery_address_match,
        "delivery_timestamp": spec.delivery_confirmed,
        "proof_of_delivery": spec.proof_of_delivery,
        "prior_order_history": spec.previous_order_count > 0,
        "prior_successful_orders": spec.previous_successful_order_count > 0,
        "prior_disputes": spec.previous_dispute_count == 0,
        "customer_communication_available": spec.customer_communication_available,
        "cancellation_request": not spec.cancellation_request,
        "refund_request": not spec.refund_request,
    }


def _default_on_file(spec: Any) -> dict[str, bool]:
    """Which evidence types the merchant has a record of, by default.

    For fulfillment and communication signals the fact *is* the record: a
    merchant with no delivery confirmation has no delivery-confirmation
    evidence to file, which is exactly the gap the product exists to surface.
    Authentication and customer-history records exist regardless of whether
    they help (an AVS mismatch is still an AVS record on file).

    Every entry can be overridden per request via `evidence_on_file` /
    `evidence_not_on_file`.
    """
    return {
        # Authentication + customer history: the record exists either way.
        "three_ds": True,
        "avs": True,
        "cvv": True,
        "device_match": True,
        "ip_match": True,
        "prior_order_history": True,
        "prior_successful_orders": True,
        "prior_disputes": True,
        # Fulfillment: the merchant only has it if it happened / was captured.
        "delivery_confirmed": spec.delivery_confirmed,
        "tracking_available": spec.tracking_available,
        "delivery_address_match": spec.delivery_address_match,
        "delivery_timestamp": spec.delivery_confirmed,
        "proof_of_delivery": spec.proof_of_delivery,
        # Communication: a stored exchange only exists if there was one, but
        # whether the customer asked to cancel / asked for a refund is
        # something the merchant can attest to either way -- and "no request
        # was made" is the state that CORROBORATES the merchant (see
        # _positive_flags), so it must be filable rather than counted as a
        # missing record.
        "customer_communication_available": spec.customer_communication_available,
        "cancellation_request": True,
        "refund_request": True,
    }


def _evidence_value(evidence_type: str, spec: Any, delivered_at: datetime) -> dict[str, Any]:
    """The evidence row's JSON value, in the exact shape app/ml/schema.py's
    EVIDENCE_VALUE_SPEC parses (and scripts/generate_dataset.py emits)."""
    values: dict[str, dict[str, Any]] = {
        "three_ds": {"authenticated": spec.three_ds_authenticated},
        "avs": {"result": spec.avs_result},
        "cvv": {"result": spec.cvv_result},
        "device_match": {"match": spec.device_match},
        "ip_match": {"match": spec.ip_match},
        "delivery_confirmed": {"confirmed": spec.delivery_confirmed},
        "tracking_available": {"available": spec.tracking_available},
        "delivery_address_match": {"match": spec.delivery_address_match},
        "delivery_timestamp": {"timestamp": delivered_at.isoformat()},
        "proof_of_delivery": {"present": spec.proof_of_delivery},
        "prior_order_history": {"order_count": spec.previous_order_count},
        "prior_successful_orders": {"count": spec.previous_successful_order_count},
        "prior_disputes": {"count": spec.previous_dispute_count},
        "customer_communication_available": {"present": spec.customer_communication_available},
        "cancellation_request": {"requested": spec.cancellation_request},
        "refund_request": {"requested": spec.refund_request},
    }
    return values[evidence_type]


def build_simulation_case(spec: Any, reference: ReferenceData | None = None) -> SimulationCase:
    """Materialize a hypothetical dispute as in-memory case parts.

    `spec` is a validated SimulationRequest (app/schemas/simulation.py) --
    taken as a duck type so this module doesn't import the API schema layer.
    """
    reference = reference or load_reference_data()

    # Evidence relevance is authoritative reference data, per reason code --
    # never invented here. Types with no reference entry for this reason code
    # fall back to "low", matching how the gap analyzer treats them.
    relevance_by_type = {
        requirement.evidence_type: requirement.relevance
        for requirement in reference.requirements_for(spec.reason_code)
    }

    transaction_created = SIMULATION_ANCHOR
    captured = transaction_created + timedelta(minutes=spec.capture_lag_minutes)
    dispute_created = transaction_created + timedelta(days=spec.days_transaction_to_dispute)
    response_deadline = dispute_created + timedelta(days=spec.days_to_respond)
    delivered_at = captured + timedelta(days=spec.delivery_days_after_capture)

    address_id = "SIM-ADDR-1"
    customer = SimCustomer(
        customer_id="SIM-CUST",
        account_age_days=spec.account_age_days,
        previous_order_count=spec.previous_order_count,
        previous_successful_order_count=spec.previous_successful_order_count,
        previous_dispute_count=spec.previous_dispute_count,
        previous_refund_count=spec.previous_refund_count,
    )
    transaction = SimTransaction(
        transaction_id="SIM-TXN",
        customer=customer,
        amount=spec.transaction_amount,
        payment_method=spec.payment_method,
        created_at=transaction_created,
        captured_at=captured,
        status=spec.transaction_status,
        billing_address_id=address_id,
        shipping_address_id=address_id if spec.billing_shipping_match else "SIM-ADDR-2",
        avs_result=spec.avs_result,
        cvv_result=spec.cvv_result,
        three_ds_authenticated=spec.three_ds_authenticated,
    )
    dispute = SimDispute(
        dispute_id=spec.simulation_case_id,
        transaction=transaction,
        reason_code=spec.reason_code,
        dispute_amount=spec.dispute_amount,
        status=spec.dispute_status,
        created_at=dispute_created,
        response_deadline=response_deadline,
    )

    positive = _positive_flags(spec)
    on_file = _default_on_file(spec)
    for evidence_type in spec.evidence_on_file:
        on_file[evidence_type] = True
    for evidence_type in spec.evidence_not_on_file:
        on_file[evidence_type] = False

    evidence: list[SimEvidence] = []
    for index, evidence_type in enumerate(schema.ALL_EVIDENCE_TYPES, start=1):
        available = on_file[evidence_type]
        strength = 0.0
        if available:
            strength = CORROBORATING_STRENGTH if positive[evidence_type] else UNHELPFUL_STRENGTH

        evidence.append(
            SimEvidence(
                evidence_id=f"SIM-EVD-{index:03d}",
                evidence_type=evidence_type,
                available=available,
                value=_evidence_value(evidence_type, spec, delivered_at) if available else None,
                relevance=relevance_by_type.get(evidence_type, "low"),
                strength=strength,
                created_at=dispute_created,
            )
        )

    return SimulationCase(dispute=dispute, evidence=evidence)
