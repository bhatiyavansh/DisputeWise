from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    account_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    account_age_days: Mapped[int] = mapped_column(Integer, nullable=False)

    previous_order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    previous_successful_order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    previous_dispute_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    previous_refund_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="customer")
