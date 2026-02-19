"""
Week 6: Integrity Check API Endpoints
======================================
Exposes integrity logs, alerts, and manual trigger endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime

from app.database import get_session
from app.models import User, Document, IntegrityLog, IntegrityAlert, IntegrityStatus
from app.schemas import (
    IntegrityLogResponse, IntegrityAlertResponse,
    IntegrityCheckSummary, ResolveAlertRequest
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/integrity", tags=["Integrity Checks"])


@router.post("/trigger", response_model=dict)
def trigger_integrity_check(
    doc_ids: Optional[List[int]] = None,
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger an immediate integrity check.
    - Admins/auditors can check all docs or specific doc_ids.
    - Dispatches Celery task asynchronously.
    """
    if current_user.role not in ["admin", "auditor", "bank"]:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        from app.workers.integrity_worker import run_integrity_check
        task = run_integrity_check.apply_async(
            kwargs={"doc_ids": doc_ids},
            queue="integrity"
        )
        return {
            "message": "Integrity check dispatched",
            "task_id": task.id,
            "doc_ids": doc_ids,
            "dispatched_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        # If Celery/Redis not running, run synchronously as fallback
        return _run_sync_integrity_check(session, doc_ids, current_user)


def _run_sync_integrity_check(session: Session, doc_ids: Optional[List[int]], current_user: User):
    """Synchronous fallback for integrity check (when Redis not available)."""
    from app.services.storage import recompute_hash_for_url
    from app.models import IntegrityLog, IntegrityAlert
    import json

    if doc_ids:
        docs = [session.get(Document, did) for did in doc_ids]
        docs = [d for d in docs if d is not None]
    else:
        docs = session.exec(
            select(Document).where(Document.file_url.isnot(None))
        ).all()

    results = {
        "total_checked": len(docs),
        "ok_count": 0,
        "mismatch_count": 0,
        "missing_count": 0,
        "alerts_created": 0,
        "run_at": datetime.utcnow().isoformat(),
        "mode": "synchronous_fallback",
    }

    for doc in docs:
        stored_hash = doc.hash
        status = IntegrityStatus.ok
        computed_hash = None
        detail = None

        if doc.file_url and stored_hash:
            computed_hash = recompute_hash_for_url(doc.file_url)
            if computed_hash is None:
                status = IntegrityStatus.missing
                detail = f"File not accessible: {doc.file_url}"
            elif computed_hash != stored_hash:
                status = IntegrityStatus.mismatch
                detail = f"Hash mismatch: stored={stored_hash[:16]}... computed={computed_hash[:16]}..."

        log = IntegrityLog(
            document_id=doc.id,
            status=status,
            stored_hash=stored_hash,
            computed_hash=computed_hash,
            mismatch_detail=detail,
            checked_at=datetime.utcnow(),
            alert_sent=False,
        )
        session.add(log)

        if status == IntegrityStatus.ok:
            results["ok_count"] += 1
        else:
            if status == IntegrityStatus.mismatch:
                results["mismatch_count"] += 1
                alert_type = "hash_mismatch"
                severity = "critical"
            else:
                results["missing_count"] += 1
                alert_type = "file_missing"
                severity = "high"

            alert = IntegrityAlert(
                document_id=doc.id,
                alert_type=alert_type,
                detail=detail or "Unknown issue",
                severity=severity,
                resolved=False,
                created_at=datetime.utcnow(),
            )
            session.add(alert)
            log.alert_sent = True
            results["alerts_created"] += 1

    session.commit()
    return results


@router.post("/trigger/{doc_id}", response_model=dict)
def trigger_single_check(
    doc_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Trigger immediate integrity check for a single document."""
    if current_user.role not in ["admin", "auditor", "bank"]:
        raise HTTPException(status_code=403, detail="Access denied")

    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        from app.workers.integrity_worker import check_document_on_demand
        task = check_document_on_demand.apply_async(args=[doc_id], queue="integrity")
        return {"message": "On-demand check dispatched", "task_id": task.id, "doc_id": doc_id}
    except Exception:
        # Sync fallback
        return _run_sync_integrity_check(session, [doc_id], current_user)


@router.get("/health")
def integrity_health(current_user: User = Depends(get_current_user)):
    """
    Check if Celery/Redis are available for scheduled integrity checks.
    Returns system status and whether scheduled checks are enabled.
    """
    try:
        from app.workers.celery_app import celery_app
        # Try to ping Redis via Celery
        celery_app.control.ping(timeout=1.0)
        return {
            "status": "healthy",
            "celery": "connected",
            "redis": "connected",
            "scheduled_checks": "enabled",
            "worker_status": "active"
        }
    except Exception as e:
        return {
            "status": "degraded",
            "celery": "unavailable",
            "redis": "unavailable",
            "scheduled_checks": "disabled",
            "fallback_mode": "synchronous",
            "error": str(e),
            "recommendation": "Start Redis and Celery worker for scheduled checks"
        }


@router.get("/task/{task_id}")
def get_task_status(task_id: str, current_user: User = Depends(get_current_user)):
    """Get the status/result of a dispatched Celery task."""
    try:
        from app.workers.celery_app import celery_app
        result = celery_app.AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
        }
    except Exception as e:
        return {"task_id": task_id, "status": "unknown", "error": str(e)}


@router.get("/logs", response_model=List[IntegrityLogResponse])
def get_integrity_logs(
    doc_id: Optional[int] = None,
    status: Optional[IntegrityStatus] = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List integrity check logs with optional filtering."""
    if current_user.role not in ["admin", "auditor", "bank"]:
        raise HTTPException(status_code=403, detail="Access denied")

    query = select(IntegrityLog).order_by(IntegrityLog.checked_at.desc())
    if doc_id:
        query = query.where(IntegrityLog.document_id == doc_id)
    if status:
        query = query.where(IntegrityLog.status == status)
    query = query.offset(offset).limit(limit)

    logs = session.exec(query).all()
    return logs


@router.get("/alerts", response_model=List[IntegrityAlertResponse])
def get_alerts(
    resolved: Optional[bool] = None,
    severity: Optional[str] = None,
    doc_id: Optional[int] = None,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    List all integrity alerts.
    Unresolved mismatch/missing alerts require immediate attention.
    """
    if current_user.role not in ["admin", "auditor", "bank"]:
        raise HTTPException(status_code=403, detail="Access denied")

    query = select(IntegrityAlert).order_by(IntegrityAlert.created_at.desc())
    if resolved is not None:
        query = query.where(IntegrityAlert.resolved == resolved)
    if severity:
        query = query.where(IntegrityAlert.severity == severity)
    if doc_id:
        query = query.where(IntegrityAlert.document_id == doc_id)
    query = query.limit(limit)

    alerts = session.exec(query).all()
    return alerts


@router.post("/alerts/{alert_id}/resolve", response_model=IntegrityAlertResponse)
def resolve_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Mark an integrity alert as resolved."""
    if current_user.role not in ["admin", "auditor"]:
        raise HTTPException(status_code=403, detail="Only admins/auditors can resolve alerts")

    alert = session.get(IntegrityAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.resolved:
        raise HTTPException(status_code=400, detail="Alert already resolved")

    alert.resolved = True
    alert.resolved_by = current_user.id
    alert.resolved_at = datetime.utcnow()
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


@router.get("/summary", response_model=IntegrityCheckSummary)
def integrity_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get summary of the latest integrity check run.
    Shows aggregate counts from the most recent batch.
    """
    if current_user.role not in ["admin", "auditor", "bank"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get most recent check time
    latest_log = session.exec(
        select(IntegrityLog).order_by(IntegrityLog.checked_at.desc())
    ).first()

    if not latest_log:
        return IntegrityCheckSummary(
            total_checked=0, ok_count=0, mismatch_count=0,
            missing_count=0, alerts_created=0, run_at=datetime.utcnow()
        )

    # Get all logs from the same minute (same batch)
    run_time = latest_log.checked_at
    from datetime import timedelta
    batch_start = run_time - timedelta(minutes=1)

    batch_logs = session.exec(
        select(IntegrityLog)
        .where(IntegrityLog.checked_at >= batch_start)
        .where(IntegrityLog.checked_at <= run_time)
    ).all()

    ok = sum(1 for l in batch_logs if l.status == IntegrityStatus.ok)
    mismatches = sum(1 for l in batch_logs if l.status == IntegrityStatus.mismatch)
    missing = sum(1 for l in batch_logs if l.status == IntegrityStatus.missing)
    alerts = sum(1 for l in batch_logs if l.alert_sent)

    return IntegrityCheckSummary(
        total_checked=len(batch_logs),
        ok_count=ok,
        mismatch_count=mismatches,
        missing_count=missing,
        alerts_created=alerts,
        run_at=run_time,
    )


@router.get("/dashboard")
def integrity_dashboard(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Full integrity dashboard data for UI.
    Returns counts, recent alerts, and check history.
    """
    if current_user.role not in ["admin", "auditor", "bank"]:
        raise HTTPException(status_code=403, detail="Access denied")

    total_docs = len(session.exec(select(Document)).all())
    docs_with_files = len(session.exec(
        select(Document).where(Document.file_url.isnot(None))
    ).all())

    all_alerts = session.exec(select(IntegrityAlert)).all()
    unresolved = [a for a in all_alerts if not a.resolved]
    critical_alerts = [a for a in unresolved if a.severity == "critical"]

    recent_logs = session.exec(
        select(IntegrityLog).order_by(IntegrityLog.checked_at.desc()).limit(20)
    ).all()

    return {
        "overview": {
            "total_documents": total_docs,
            "documents_with_files": docs_with_files,
            "total_alerts": len(all_alerts),
            "unresolved_alerts": len(unresolved),
            "critical_alerts": len(critical_alerts),
        },
        "recent_checks": [
            {
                "id": l.id,
                "document_id": l.document_id,
                "status": l.status,
                "checked_at": l.checked_at.isoformat(),
                "mismatch_detail": l.mismatch_detail,
            }
            for l in recent_logs
        ],
        "unresolved_alerts": [
            {
                "id": a.id,
                "document_id": a.document_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "detail": a.detail,
                "created_at": a.created_at.isoformat(),
            }
            for a in unresolved[:10]
        ],
    }
