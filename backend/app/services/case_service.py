from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.dispute import Dispute
from app.models.evidence import Evidence
from app.models.transaction import Transaction


def list_cases(
    db: Session,
    *,
    page: int,
    page_size: int,
    reason_code: str | None = None,
    status: str | None = None,
) -> tuple[list[Dispute], int]:
    stmt = select(Dispute)
    count_stmt = select(func.count()).select_from(Dispute)

    if reason_code is not None:
        stmt = stmt.where(Dispute.reason_code == reason_code)
        count_stmt = count_stmt.where(Dispute.reason_code == reason_code)
    if status is not None:
        stmt = stmt.where(Dispute.status == status)
        count_stmt = count_stmt.where(Dispute.status == status)

    total = db.execute(count_stmt).scalar_one()

    stmt = stmt.order_by(Dispute.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = list(db.execute(stmt).scalars().all())

    return items, total


def get_case(db: Session, dispute_id: str) -> Dispute | None:
    stmt = (
        select(Dispute)
        .options(joinedload(Dispute.transaction).joinedload(Transaction.customer))
        .where(Dispute.dispute_id == dispute_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def get_case_evidence(db: Session, dispute_id: str) -> list[Evidence] | None:
    dispute = db.execute(select(Dispute).where(Dispute.dispute_id == dispute_id)).scalar_one_or_none()
    if dispute is None:
        return None
    stmt = select(Evidence).where(Evidence.dispute_id == dispute.id).order_by(Evidence.evidence_type)
    return list(db.execute(stmt).scalars().all())
