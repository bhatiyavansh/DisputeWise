from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Customer, Dispute, Evidence, Outcome, Transaction
from app.models.evidence import ALL_EVIDENCE_TYPES


def make_case(
    db: Session,
    *,
    dispute_id: str = "DSP-000001",
    reason_code: str = "goods_not_received",
    status: str = "open",
    favorable_outcome: bool = True,
) -> Dispute:
    now = datetime.now(timezone.utc)

    customer = Customer(
        customer_id=f"CUST-{dispute_id}",
        account_created_at=now - timedelta(days=400),
        country="IN",
        account_age_days=400,
        previous_order_count=12,
        previous_successful_order_count=11,
        previous_dispute_count=0,
        previous_refund_count=1,
    )
    db.add(customer)
    db.flush()

    transaction = Transaction(
        transaction_id=f"TXN-{dispute_id}",
        customer_id=customer.id,
        merchant_id="MERCH-0001",
        amount=1999.00,
        currency="INR",
        payment_method="card",
        created_at=now - timedelta(days=20),
        captured_at=now - timedelta(days=20),
        status="captured",
        device_id="DEV-abc123",
        ip_address="203.0.113.5",
        billing_address_id="ADDR-0001",
        shipping_address_id="ADDR-0001",
        avs_result="Y",
        cvv_result="M",
        three_ds_authenticated=True,
    )
    db.add(transaction)
    db.flush()

    dispute = Dispute(
        dispute_id=dispute_id,
        transaction_id=transaction.id,
        reason_code=reason_code,
        dispute_amount=1999.00,
        created_at=now - timedelta(days=5),
        response_deadline=now + timedelta(days=10),
        status=status,
        scenario_archetype="strong_legitimate",
        split="train",
    )
    db.add(dispute)
    db.flush()

    evidence = Evidence(
        evidence_id=f"EVD-{dispute_id}-01",
        dispute_id=dispute.id,
        evidence_type="delivery_confirmed",
        available=True,
        value={"confirmed": True},
        relevance="high",
        strength=0.9,
        created_at=now - timedelta(days=4),
    )
    db.add(evidence)

    outcome = Outcome(
        dispute_id=dispute.id,
        favorable_outcome=favorable_outcome,
        outcome_at=now,
        outcome_source="synthetic",
        recovery_amount=1999.00 if favorable_outcome else None,
    )
    db.add(outcome)

    db.commit()
    return dispute


def add_evidence(
    db: Session,
    dispute: Dispute,
    *,
    evidence_type: str,
    available: bool,
    value: dict | None,
    relevance: str,
    strength: float,
    evidence_id: str | None = None,
) -> Evidence:
    """Attach one additional evidence row to an existing dispute (from
    make_case). Phase 4 tests need finer control over which evidence types
    are available/missing than make_case's single default row provides.
    """
    now = datetime.now(timezone.utc)
    # evidence_id is VARCHAR(32) -- some evidence_type names alone exceed that
    # (e.g. "customer_communication_available" is 33 chars), so default IDs
    # use a short type-index code rather than the full type name.
    type_index = ALL_EVIDENCE_TYPES.index(evidence_type) if evidence_type in ALL_EVIDENCE_TYPES else 99
    evidence = Evidence(
        evidence_id=evidence_id or f"EVD-{dispute.id}-{type_index:02d}",
        dispute_id=dispute.id,
        evidence_type=evidence_type,
        available=available,
        value=value,
        relevance=relevance,
        strength=strength,
        created_at=now,
    )
    db.add(evidence)
    db.commit()
    return evidence
