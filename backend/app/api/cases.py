from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.schemas.case import CaseDetail, CaseListItem, CustomerOut, TransactionOut
from app.schemas.common import Page
from app.services import case_service

router = APIRouter(tags=["cases"])
settings = get_settings()


@router.get("/cases", response_model=Page[CaseListItem])
def list_cases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.api_default_page_size, ge=1, le=settings.api_max_page_size),
    reason_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Page[CaseListItem]:
    items, total = case_service.list_cases(
        db, page=page, page_size=page_size, reason_code=reason_code, status=status
    )
    return Page[CaseListItem](
        items=[CaseListItem.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseDetail:
    dispute = case_service.get_case(db, case_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    return CaseDetail(
        dispute_id=dispute.dispute_id,
        reason_code=dispute.reason_code,
        status=dispute.status,
        dispute_amount=dispute.dispute_amount,
        created_at=dispute.created_at,
        response_deadline=dispute.response_deadline,
        scenario_archetype=dispute.scenario_archetype,
        split=dispute.split,
        transaction=TransactionOut.model_validate(dispute.transaction),
        customer=CustomerOut.model_validate(dispute.transaction.customer),
    )
