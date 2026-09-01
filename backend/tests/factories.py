from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Customer, Dispute, Evidence, Outcome, Transaction


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
