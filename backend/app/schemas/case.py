from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    account_created_at: datetime
    country: str
    account_age_days: int
    previous_order_count: int
    previous_successful_order_count: int
    previous_dispute_count: int
    previous_refund_count: int


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    merchant_id: str
    amount: Decimal
    currency: str
    payment_method: str
    created_at: datetime
    captured_at: datetime | None
    status: str
    device_id: str
    ip_address: str
    billing_address_id: str
    shipping_address_id: str
    avs_result: str
    cvv_result: str
    three_ds_authenticated: bool


class CaseListItem(BaseModel):
    """Summary row for GET /cases — enough to populate a dashboard list view."""

    model_config = ConfigDict(from_attributes=True)

    dispute_id: str
    reason_code: str
    status: str
    dispute_amount: Decimal
    created_at: datetime
    response_deadline: datetime
    scenario_archetype: str
    split: str


class CaseDetail(BaseModel):
    """Full case: dispute + related transaction + customer."""

    dispute_id: str
    reason_code: str
    status: str
    dispute_amount: Decimal
    created_at: datetime
    response_deadline: datetime
    scenario_archetype: str
    split: str

    transaction: TransactionOut
    customer: CustomerOut
