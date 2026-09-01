"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(32), nullable=False),
        sa.Column("account_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("account_age_days", sa.Integer(), nullable=False),
        sa.Column("previous_order_count", sa.Integer(), nullable=False),
        sa.Column("previous_successful_order_count", sa.Integer(), nullable=False),
        sa.Column("previous_dispute_count", sa.Integer(), nullable=False),
        sa.Column("previous_refund_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_customers_customer_id", "customers", ["customer_id"], unique=True)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.String(32), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("merchant_id", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_method", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("device_id", sa.String(40), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("billing_address_id", sa.String(32), nullable=False),
        sa.Column("shipping_address_id", sa.String(32), nullable=False),
        sa.Column("avs_result", sa.String(8), nullable=False),
        sa.Column("cvv_result", sa.String(8), nullable=False),
        sa.Column("three_ds_authenticated", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_transactions_transaction_id", "transactions", ["transaction_id"], unique=True)
    op.create_index("ix_transactions_customer_id", "transactions", ["customer_id"])
    op.create_index("ix_transactions_merchant_id", "transactions", ["merchant_id"])

    op.create_table(
        "disputes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dispute_id", sa.String(32), nullable=False),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("dispute_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scenario_archetype", sa.String(32), nullable=False),
        sa.Column("split", sa.String(16), nullable=False),
    )
    op.create_index("ix_disputes_dispute_id", "disputes", ["dispute_id"], unique=True)
    op.create_index("ix_disputes_transaction_id", "disputes", ["transaction_id"])
    op.create_index("ix_disputes_reason_code", "disputes", ["reason_code"])
    op.create_index("ix_disputes_status", "disputes", ["status"])
    op.create_index("ix_disputes_scenario_archetype", "disputes", ["scenario_archetype"])
    op.create_index("ix_disputes_split", "disputes", ["split"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evidence_id", sa.String(32), nullable=False),
        sa.Column("dispute_id", sa.Integer(), sa.ForeignKey("disputes.id"), nullable=False),
        sa.Column("evidence_type", sa.String(48), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=True),
        sa.Column("relevance", sa.String(8), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_evidence_id", "evidence", ["evidence_id"], unique=True)
    op.create_index("ix_evidence_dispute_id", "evidence", ["dispute_id"])
    op.create_index("ix_evidence_evidence_type", "evidence", ["evidence_type"])

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dispute_id", sa.Integer(), sa.ForeignKey("disputes.id"), nullable=False),
        sa.Column("favorable_outcome", sa.Boolean(), nullable=False),
        sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_source", sa.String(32), nullable=False),
        sa.Column("recovery_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.create_index("ix_outcomes_dispute_id", "outcomes", ["dispute_id"], unique=True)


def downgrade() -> None:
    op.drop_table("outcomes")
    op.drop_table("evidence")
    op.drop_table("disputes")
    op.drop_table("transactions")
    op.drop_table("customers")
