from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Dispute(Base):
    """A dispute row is the "case" referenced throughout the API and docs."""

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False, index=True)

    reason_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dispute_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Data-generation provenance, not part of the future ML feature set.
    scenario_archetype: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    split: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="disputes")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="dispute")
    outcome: Mapped["Outcome"] = relationship(back_populates="dispute", uselist=False)
