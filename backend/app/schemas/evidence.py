from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    evidence_type: str
    available: bool
    value: dict | None
    relevance: str
    strength: float
    created_at: datetime
