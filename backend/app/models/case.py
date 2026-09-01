"""A "case" is a dispute plus its related transaction/customer/evidence/outcome.

There is no separate `cases` table: `Dispute` (see dispute.py) is the case
record. This module re-exports it under the name used by the API layer so
call sites can talk about "cases" without conflating the ORM table name.
"""

from app.models.dispute import Dispute as Case

__all__ = ["Case"]
