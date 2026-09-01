from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Category taxonomy is fixed here so Phase 2's evidence-matrix builder can
# rely on a stable, known set of evidence_type values without touching the schema.
AUTHENTICATION_EVIDENCE_TYPES = ["three_ds", "avs", "cvv", "device_match", "ip_match"]
FULFILLMENT_EVIDENCE_TYPES = [
    "delivery_confirmed",
    "tracking_available",
    "delivery_address_match",
    "delivery_timestamp",
    "proof_of_delivery",
]
CUSTOMER_EVIDENCE_TYPES = ["prior_order_history", "prior_successful_orders", "prior_disputes"]
COMMUNICATION_EVIDENCE_TYPES = [
    "customer_communication_available",
    "cancellation_request",
    "refund_request",
]

ALL_EVIDENCE_TYPES = (
    AUTHENTICATION_EVIDENCE_TYPES
    + FULFILLMENT_EVIDENCE_TYPES
    + CUSTOMER_EVIDENCE_TYPES
    + COMMUNICATION_EVIDENCE_TYPES
)

RELEVANCE_LEVELS = ("high", "medium", "low")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"), nullable=False, index=True)

    evidence_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    relevance: Mapped[str] = mapped_column(String(8), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    dispute: Mapped["Dispute"] = relationship(back_populates="evidence")
