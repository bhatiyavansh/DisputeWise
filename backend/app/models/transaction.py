from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    device_id: Mapped[str] = mapped_column(String(40), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    billing_address_id: Mapped[str] = mapped_column(String(32), nullable=False)
    shipping_address_id: Mapped[str] = mapped_column(String(32), nullable=False)

    avs_result: Mapped[str] = mapped_column(String(8), nullable=False)
    cvv_result: Mapped[str] = mapped_column(String(8), nullable=False)
    three_ds_authenticated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    customer: Mapped["Customer"] = relationship(back_populates="transactions")
    disputes: Mapped[list["Dispute"]] = relationship(back_populates="transaction")
