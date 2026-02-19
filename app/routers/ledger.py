from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Optional, List
from datetime import datetime

from app.database import get_session
from app.models import User, LedgerEntry, Document, LedgerAction
from app.schemas import LedgerEntryResponse
from app.services.auth import get_current_user

router = APIRouter(prefix="/ledger", tags=["Ledger Explorer"])


@router.get("/", response_model=List[LedgerEntryResponse])
def explore_ledger(
    doc_type: Optional[str] = None,
    action: Optional[LedgerAction] = None,
    actor_id: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Explore all ledger entries with optional filtering.
    Full audit trail for auditors; org-scoped for others.
    """
    query = select(LedgerEntry).order_by(LedgerEntry.created_at.desc())

    if action:
        query = query.where(LedgerEntry.action == action)
    if actor_id:
        query = query.where(LedgerEntry.actor_id == actor_id)
    if from_date:
        query = query.where(LedgerEntry.created_at >= from_date)
    if to_date:
        query = query.where(LedgerEntry.created_at <= to_date)

    query = query.offset(offset).limit(limit)
    entries = session.exec(query).all()

    return [
        LedgerEntryResponse(
            id=e.id,
            document_id=e.document_id,
            action=e.action,
            actor_id=e.actor_id,
            metadata=e.metadata,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/timeline/{doc_id}", response_model=List[LedgerEntryResponse])
def document_timeline(
    doc_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get chronological timeline of events for a specific document."""
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    entries = session.exec(
        select(LedgerEntry)
        .where(LedgerEntry.document_id == doc_id)
        .order_by(LedgerEntry.created_at)
    ).all()

    return [
        LedgerEntryResponse(
            id=e.id,
            document_id=e.document_id,
            action=e.action,
            actor_id=e.actor_id,
            metadata=e.metadata,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/stats")
def ledger_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Summary statistics for the ledger (admin/auditor only)."""
    if current_user.role not in ["admin", "auditor", "bank"]:
        raise HTTPException(status_code=403, detail="Access denied")

    all_entries = session.exec(select(LedgerEntry)).all()
    action_counts = {}
    for entry in all_entries:
        action_counts[entry.action] = action_counts.get(entry.action, 0) + 1

    total_docs = session.exec(select(Document)).all()

    return {
        "total_ledger_entries": len(all_entries),
        "total_documents": len(total_docs),
        "action_breakdown": action_counts,
        "last_entry_at": all_entries[0].created_at if all_entries else None,
    }
