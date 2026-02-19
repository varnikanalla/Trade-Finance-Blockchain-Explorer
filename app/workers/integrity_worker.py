"""
Week 6: Integrity Check Worker
================================
Celery tasks that:
1. Periodically recompute SHA-256 hashes of stored documents
2. Compare against hashes recorded at upload time
3. Detect and log mismatches
4. Raise IntegrityAlert records + send email notifications
5. Expose results via API
"""

import logging
import smtplib
import json
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from celery import Task
from sqlmodel import Session, select

from app.workers.celery_app import celery_app
from app.database import engine
from app.models import (
    Document, IntegrityLog, IntegrityAlert, IntegrityStatus,
    User
)
from app.services.storage import recompute_hash_for_url

logger = logging.getLogger(__name__)

# ─── Email Configuration ──────────────────────────────────────────────────────

ALERTS_ENABLED = os.getenv("ALERTS_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "alerts@tradefinance.com")
ADMIN_ALERT_EMAILS = [e.strip() for e in os.getenv("ADMIN_ALERT_EMAILS", "").split(",") if e.strip()]

# Validate email config on import
if ALERTS_ENABLED and not SMTP_USER:
    logger.warning(
        "⚠️  Email alerts are ENABLED but SMTP_USER is not configured. "
        "Alerts will be logged but not sent. Set ALERTS_ENABLED=false to disable this warning."
    )


# ─── Alert Email Sender ───────────────────────────────────────────────────────

def send_alert_email(subject: str, body: str, recipients: List[str]):
    """Send HTML alert email via SMTP."""
    if not ALERTS_ENABLED:
        logger.info("Email alerts disabled (ALERTS_ENABLED=false). Alert logged only.")
        return False
    
    if not SMTP_USER:
        logger.warning(
            "SMTP not configured. Alert logged but not sent. "
            "Set SMTP_USER, SMTP_PASSWORD, and ADMIN_ALERT_EMAILS in .env"
        )
        return False
    
    if not recipients or recipients == [""]:
        logger.warning("No alert recipients configured. Set ADMIN_ALERT_EMAILS in .env")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = ALERT_EMAIL_FROM
        msg["To"] = ", ".join(recipients)

        html_body = f"""
        <html><body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto;">
          <div style="background: #dc2626; color: white; padding: 16px; border-radius: 8px 8px 0 0;">
            <h2>🚨 Trade Finance Integrity Alert</h2>
          </div>
          <div style="background: #fef2f2; padding: 20px; border: 1px solid #fca5a5; border-radius: 0 0 8px 8px;">
            <pre style="white-space: pre-wrap; font-family: monospace; font-size: 13px;">{body}</pre>
          </div>
          <p style="color: #6b7280; font-size: 12px; margin-top: 12px;">
            Trade Finance Blockchain Explorer — Automated Integrity Monitor
          </p>
        </div>
        </body></html>
        """

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, recipients, msg.as_string())

        logger.info(f"✅ Alert email sent to {', '.join(recipients)}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send alert email: {e}")
        logger.error(
            "Check your SMTP settings: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD"
        )
        return False


# ─── Core Integrity Check Logic ───────────────────────────────────────────────

def _check_single_document(session: Session, doc: Document) -> IntegrityLog:
    """
    Check a single document's hash integrity.
    Returns an IntegrityLog record (not yet committed).
    """
    stored_hash = doc.hash
    computed_hash = None
    status = IntegrityStatus.ok
    mismatch_detail = None

    if not doc.file_url:
        # No file stored — only metadata doc (e.g., inline LOC/PO created via trade flow)
        status = IntegrityStatus.ok  # No file to verify
        mismatch_detail = "No file_url; metadata-only document."
    elif not stored_hash:
        status = IntegrityStatus.missing
        mismatch_detail = "Document has no stored hash."
    else:
        computed_hash = recompute_hash_for_url(doc.file_url)

        if computed_hash is None:
            status = IntegrityStatus.missing
            mismatch_detail = f"File not accessible at URL: {doc.file_url}"
        elif computed_hash != stored_hash:
            status = IntegrityStatus.mismatch
            mismatch_detail = (
                f"HASH MISMATCH!\n"
                f"  Stored:   {stored_hash}\n"
                f"  Computed: {computed_hash}\n"
                f"  Document: {doc.doc_number} (ID={doc.id}, type={doc.doc_type})"
            )

    return IntegrityLog(
        document_id=doc.id,
        status=status,
        stored_hash=stored_hash,
        computed_hash=computed_hash,
        mismatch_detail=mismatch_detail,
        checked_at=datetime.utcnow(),
        alert_sent=False,
    )


def _create_alert(session: Session, doc: Document, log: IntegrityLog) -> IntegrityAlert:
    """Create an IntegrityAlert for a failed document check."""
    alert_type_map = {
        IntegrityStatus.mismatch: "hash_mismatch",
        IntegrityStatus.missing: "file_missing",
    }

    severity_map = {
        IntegrityStatus.mismatch: "critical",
        IntegrityStatus.missing: "high",
    }

    alert = IntegrityAlert(
        document_id=doc.id,
        alert_type=alert_type_map.get(log.status, "unknown"),
        detail=log.mismatch_detail or "Unknown integrity issue",
        severity=severity_map.get(log.status, "medium"),
        resolved=False,
        created_at=datetime.utcnow(),
    )
    session.add(alert)
    return alert


# ─── Celery Tasks ─────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.workers.integrity_worker.run_integrity_check",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="integrity",
)
def run_integrity_check(self: Task, doc_ids: Optional[List[int]] = None):
    """
    Hourly integrity check task.
    
    Checks documents uploaded in the last 24 hours (or specific doc_ids if provided).
    Creates IntegrityLog entries and alerts on mismatches.
    """
    logger.info(f"[IntegrityCheck] Starting incremental check at {datetime.utcnow().isoformat()}")
    
    results = {
        "total_checked": 0,
        "ok_count": 0,
        "mismatch_count": 0,
        "missing_count": 0,
        "alerts_created": 0,
        "run_at": datetime.utcnow().isoformat(),
    }
    
    alert_messages = []

    try:
        with Session(engine) as session:
            if doc_ids:
                docs = [session.get(Document, did) for did in doc_ids]
                docs = [d for d in docs if d is not None]
            else:
                # Check docs from last 24 hours that have file_url
                from datetime import timedelta
                cutoff = datetime.utcnow() - timedelta(hours=24)
                docs = session.exec(
                    select(Document)
                    .where(Document.file_url.isnot(None))
                    .where(Document.created_at >= cutoff)
                ).all()

            results["total_checked"] = len(docs)
            logger.info(f"[IntegrityCheck] Checking {len(docs)} documents...")

            for doc in docs:
                log = _check_single_document(session, doc)
                session.add(log)
                session.flush()

                if log.status == IntegrityStatus.ok:
                    results["ok_count"] += 1
                elif log.status == IntegrityStatus.mismatch:
                    results["mismatch_count"] += 1
                    alert = _create_alert(session, doc, log)
                    log.alert_sent = True
                    results["alerts_created"] += 1
                    alert_messages.append(
                        f"[MISMATCH] Doc ID={doc.id} | {doc.doc_type} | {doc.doc_number}\n"
                        f"  {log.mismatch_detail}"
                    )
                    logger.warning(f"[IntegrityCheck] ⚠️  MISMATCH: {log.mismatch_detail}")
                elif log.status == IntegrityStatus.missing:
                    results["missing_count"] += 1
                    alert = _create_alert(session, doc, log)
                    log.alert_sent = True
                    results["alerts_created"] += 1
                    alert_messages.append(
                        f"[MISSING] Doc ID={doc.id} | {doc.doc_type} | {doc.doc_number}\n"
                        f"  {log.mismatch_detail}"
                    )
                    logger.warning(f"[IntegrityCheck] ⚠️  MISSING: {log.mismatch_detail}")

            session.commit()

        # Send email alert if there are issues
        if alert_messages:
            total_issues = results["mismatch_count"] + results["missing_count"]
            subject = f"🚨 Trade Finance: {total_issues} Integrity Issue(s) Detected"
            body = (
                f"Integrity Check Run: {results['run_at']}\n"
                f"Documents Checked: {results['total_checked']}\n"
                f"Issues Found: {total_issues}\n\n"
                + "\n\n".join(alert_messages)
                + "\n\nPlease review at your Trade Finance Explorer dashboard."
            )
            email_sent = send_alert_email(subject, body, [e for e in ADMIN_ALERT_EMAILS if e])
            if email_sent:
                logger.info(f"[IntegrityCheck] Alert email sent for {total_issues} issues")

        logger.info(
            f"[IntegrityCheck] ✅ Complete: "
            f"{results['ok_count']} ok, "
            f"{results['mismatch_count']} mismatches, "
            f"{results['missing_count']} missing, "
            f"{results['alerts_created']} alerts created"
        )
        return results

    except Exception as exc:
        logger.error(f"[IntegrityCheck] Task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.integrity_worker.run_full_integrity_check",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="integrity",
)
def run_full_integrity_check(self: Task):
    """
    Daily full integrity sweep — checks ALL documents with file_url.
    Runs at 02:00 UTC daily.
    """
    logger.info(f"[FullIntegrityCheck] Starting full sweep at {datetime.utcnow().isoformat()}")
    
    results = {
        "total_checked": 0,
        "ok_count": 0,
        "mismatch_count": 0,
        "missing_count": 0,
        "alerts_created": 0,
        "run_at": datetime.utcnow().isoformat(),
        "type": "full_sweep",
    }
    
    alert_messages = []

    try:
        with Session(engine) as session:
            docs = session.exec(
                select(Document).where(Document.file_url.isnot(None))
            ).all()

            results["total_checked"] = len(docs)
            logger.info(f"[FullIntegrityCheck] Full sweep: {len(docs)} documents")

            for doc in docs:
                log = _check_single_document(session, doc)
                session.add(log)
                session.flush()

                if log.status == IntegrityStatus.ok:
                    results["ok_count"] += 1
                else:
                    # Check if unresolved alert already exists to avoid duplicates
                    existing_alert = session.exec(
                        select(IntegrityAlert)
                        .where(IntegrityAlert.document_id == doc.id)
                        .where(IntegrityAlert.resolved == False)
                    ).first()

                    if not existing_alert:
                        alert = _create_alert(session, doc, log)
                        results["alerts_created"] += 1
                        alert_messages.append(
                            f"[{log.status.upper()}] Doc ID={doc.id} | {doc.doc_type} | {doc.doc_number}\n"
                            f"  {log.mismatch_detail}"
                        )

                    if log.status == IntegrityStatus.mismatch:
                        results["mismatch_count"] += 1
                    else:
                        results["missing_count"] += 1
                    
                    log.alert_sent = bool(not existing_alert)

            session.commit()

        # Send summary email
        total_issues = results["mismatch_count"] + results["missing_count"]
        subject = (
            f"✅ Trade Finance: Daily Integrity Report — {results['total_checked']} docs checked"
            if total_issues == 0
            else f"🚨 Trade Finance: Daily Report — {total_issues} ISSUES FOUND"
        )
        body = (
            f"=== DAILY FULL INTEGRITY CHECK ===\n"
            f"Run Time: {results['run_at']}\n"
            f"Total Documents: {results['total_checked']}\n"
            f"✅ Clean: {results['ok_count']}\n"
            f"❌ Mismatches: {results['mismatch_count']}\n"
            f"⚠️  Missing: {results['missing_count']}\n"
            f"New Alerts Created: {results['alerts_created']}\n"
        )
        if alert_messages:
            body += "\n=== ISSUES ===\n" + "\n\n".join(alert_messages)
        
        send_alert_email(subject, body, [e for e in ADMIN_ALERT_EMAILS if e])
        logger.info(f"[FullIntegrityCheck] ✅ Complete: {results}")
        return results

    except Exception as exc:
        logger.error(f"[FullIntegrityCheck] Task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.integrity_worker.check_document_on_demand",
    queue="integrity",
)
def check_document_on_demand(doc_id: int):
    """
    On-demand integrity check for a single document.
    Triggered via API endpoint for immediate verification.
    """
    logger.info(f"[OnDemandCheck] Checking document ID={doc_id}")
    
    with Session(engine) as session:
        doc = session.get(Document, doc_id)
        if not doc:
            return {"error": f"Document {doc_id} not found"}

        log = _check_single_document(session, doc)
        session.add(log)

        alert_created = False
        if log.status != IntegrityStatus.ok:
            alert = _create_alert(session, doc, log)
            log.alert_sent = True
            alert_created = True

        session.commit()

        return {
            "document_id": doc_id,
            "status": log.status,
            "stored_hash": log.stored_hash,
            "computed_hash": log.computed_hash,
            "mismatch_detail": log.mismatch_detail,
            "alert_created": alert_created,
            "checked_at": log.checked_at.isoformat(),
        }
