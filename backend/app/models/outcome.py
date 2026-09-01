from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    dispute_id: Mapped[int] = mapped_column(
        ForeignKey("disputes.id"), nullable=False, unique=True, index=True
    )

    favorable_outcome: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome_source: Mapped[str] = mapped_column(String(32), nullable=False)
    recovery_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    dispute: Mapped["Dispute"] = relationship(back_populates="outcome")
