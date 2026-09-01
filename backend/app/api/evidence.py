from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.evidence import EvidenceOut
from app.services import case_service

router = APIRouter(tags=["evidence"])


@router.get("/cases/{case_id}/evidence", response_model=list[EvidenceOut])
def get_case_evidence(case_id: str, db: Session = Depends(get_db)) -> list[EvidenceOut]:
    evidence = case_service.get_case_evidence(db, case_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return [EvidenceOut.model_validate(e) for e in evidence]
