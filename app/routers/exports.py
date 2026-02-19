"""
Export Router - Week 8
APIs for exporting data to CSV and PDF formats
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timedelta
from app.database import get_session
from app.dependencies import get_current_user
from app.models.models import (
    User, Document, LedgerEntry, TradeTransaction,
    RiskScore, IntegrityAlert, UserRole
)
import io
import csv
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


router = APIRouter(tags=["Exports"])


# ─── CSV Export Functions ─────────────────────────────────────────────────────

def generate_csv_users(session: Session) -> io.StringIO:
    """Generate CSV export of all users"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "ID", "Name", "Email", "Role", "Organization", "Created At"
    ])
    
    # Data
    stmt = select(User)
    users = session.exec(stmt).all()
    
    for user in users:
        writer.writerow([
            user.id,
            user.name,
            user.email,
            user.role.value,
            user.org_name,
            user.created_at.isoformat()
        ])
    
    output.seek(0)
    return output


def generate_csv_documents(session: Session, user_id: Optional[int] = None) -> io.StringIO:
    """Generate CSV export of documents"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "ID", "Document Type", "Document Number", "Owner ID", "Owner Name",
        "Hash", "File URL", "Issued At", "Created At"
    ])
    
    # Data
    stmt = select(Document)
    if user_id:
        stmt = stmt.where(Document.owner_id == user_id)
    
    documents = session.exec(stmt).all()
    
    for doc in documents:
        owner = session.get(User, doc.owner_id)
        writer.writerow([
            doc.id,
            doc.doc_type.value,
            doc.doc_number,
            doc.owner_id,
            owner.name if owner else "Unknown",
            doc.hash or "N/A",
            doc.file_url or "N/A",
            doc.issued_at.isoformat() if doc.issued_at else "N/A",
            doc.created_at.isoformat()
        ])
    
    output.seek(0)
    return output


def generate_csv_transactions(session: Session, days: int = 90) -> io.StringIO:
    """Generate CSV export of transactions"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "ID", "Buyer ID", "Buyer Name", "Seller ID", "Seller Name",
        "Amount", "Currency", "Status", "Created At", "Updated At"
    ])
    
    # Data
    start_date = datetime.utcnow() - timedelta(days=days)
    stmt = select(TradeTransaction).where(
        TradeTransaction.created_at >= start_date
    ).order_by(TradeTransaction.created_at.desc())
    
    transactions = session.exec(stmt).all()
    
    for tx in transactions:
        buyer = session.get(User, tx.buyer_id)
        seller = session.get(User, tx.seller_id)
        
        writer.writerow([
            tx.id,
            tx.buyer_id,
            buyer.name if buyer else "Unknown",
            tx.seller_id,
            seller.name if seller else "Unknown",
            tx.amount,
            tx.currency,
            tx.status.value,
            tx.created_at.isoformat(),
            tx.updated_at.isoformat()
        ])
    
    output.seek(0)
    return output


def generate_csv_risk_scores(session: Session) -> io.StringIO:
    """Generate CSV export of risk scores"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "User ID", "User Name", "Organization", "Risk Score",
        "Risk Level", "Rationale", "Last Updated"
    ])
    
    # Data
    stmt = select(RiskScore).order_by(RiskScore.score.desc())
    scores = session.exec(stmt).all()
    
    for score in scores:
        user = session.get(User, score.user_id)
        risk_level = (
            "LOW" if score.score < 20 else
            "MODERATE" if score.score < 40 else
            "ELEVATED" if score.score < 60 else
            "HIGH" if score.score < 80 else
            "CRITICAL"
        )
        
        writer.writerow([
            score.user_id,
            user.name if user else "Unknown",
            user.org_name if user else "Unknown",
            round(score.score, 2),
            risk_level,
            score.rationale or "N/A",
            score.last_updated.isoformat()
        ])
    
    output.seek(0)
    return output


def generate_csv_ledger(session: Session, days: int = 90) -> io.StringIO:
    """Generate CSV export of ledger entries"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "ID", "Document ID", "Document Type", "Action", "Actor ID",
        "Actor Name", "Created At"
    ])
    
    # Data
    start_date = datetime.utcnow() - timedelta(days=days)
    stmt = select(LedgerEntry).where(
        LedgerEntry.created_at >= start_date
    ).order_by(LedgerEntry.created_at.desc())
    
    entries = session.exec(stmt).all()
    
    for entry in entries:
        document = session.get(Document, entry.document_id)
        actor = session.get(User, entry.actor_id)
        
        writer.writerow([
            entry.id,
            entry.document_id,
            document.doc_type.value if document else "Unknown",
            entry.action.value,
            entry.actor_id,
            actor.name if actor else "Unknown",
            entry.created_at.isoformat()
        ])
    
    output.seek(0)
    return output


# ─── PDF Export Functions ─────────────────────────────────────────────────────

def generate_pdf_compliance_report(session: Session, user_id: Optional[int] = None) -> io.BytesIO:
    """
    Generate comprehensive PDF compliance report
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=1  # Center
    )
    
    story.append(Paragraph("Trade Finance Compliance Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Executive Summary
    story.append(Paragraph("Executive Summary", styles['Heading2']))
    
    total_users = session.exec(select(User)).all()
    total_docs = session.exec(select(Document)).all()
    total_txs = session.exec(select(TradeTransaction)).all()
    
    summary_data = [
        ["Metric", "Value"],
        ["Total Users", str(len(total_users))],
        ["Total Documents", str(len(total_docs))],
        ["Total Transactions", str(len(total_txs))],
        ["Report Period", f"Last 90 days"],
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Risk Assessment Section
    story.append(Paragraph("Risk Assessment Overview", styles['Heading2']))
    
    risk_scores = session.exec(select(RiskScore).order_by(RiskScore.score.desc()).limit(10)).all()
    
    if risk_scores:
        risk_data = [["User", "Organization", "Risk Score", "Level"]]
        for score in risk_scores:
            user = session.get(User, score.user_id)
            level = (
                "LOW" if score.score < 20 else
                "MODERATE" if score.score < 40 else
                "ELEVATED" if score.score < 60 else
                "HIGH" if score.score < 80 else
                "CRITICAL"
            )
            risk_data.append([
                user.name if user else "Unknown",
                user.org_name if user else "Unknown",
                f"{score.score:.2f}",
                level
            ])
        
        risk_table = Table(risk_data, colWidths=[1.5*inch, 2*inch, 1*inch, 1*inch])
        risk_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(risk_table)
    else:
        story.append(Paragraph("No risk scores available.", styles['Normal']))
    
    story.append(Spacer(1, 0.3*inch))
    
    # Integrity Alerts
    story.append(Paragraph("Integrity Alerts", styles['Heading2']))
    
    alerts = session.exec(
        select(IntegrityAlert).where(IntegrityAlert.resolved == False).limit(15)
    ).all()
    
    if alerts:
        alert_data = [["Document ID", "Alert Type", "Severity", "Created"]]
        for alert in alerts:
            alert_data.append([
                str(alert.document_id),
                alert.alert_type,
                alert.severity,
                alert.created_at.strftime('%Y-%m-%d')
            ])
        
        alert_table = Table(alert_data, colWidths=[1.2*inch, 2*inch, 1*inch, 1.3*inch])
        alert_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgoldenrodyellow),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(alert_table)
    else:
        story.append(Paragraph("No unresolved integrity alerts.", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


# ─── Export Endpoints ─────────────────────────────────────────────────────────

@router.get("/export/users.csv")
def export_users_csv(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export all users to CSV (admin only)"""
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    csv_data = generate_csv_users(session)
    
    return StreamingResponse(
        iter([csv_data.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=users_{datetime.utcnow().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/documents.csv")
def export_documents_csv(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export documents to CSV"""
    # Users can only export their own documents unless admin/auditor
    if user_id and user_id != current_user.id:
        if current_user.role not in [UserRole.admin, UserRole.auditor]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    csv_data = generate_csv_documents(session, user_id)
    
    filename = f"documents_{user_id or 'all'}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([csv_data.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/transactions.csv")
def export_transactions_csv(
    days: int = Query(90, ge=1, le=365, description="Number of days to export"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export transactions to CSV"""
    if current_user.role not in [UserRole.admin, UserRole.auditor, UserRole.bank]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    csv_data = generate_csv_transactions(session, days)
    
    return StreamingResponse(
        iter([csv_data.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=transactions_{days}days_{datetime.utcnow().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/risk-scores.csv")
def export_risk_scores_csv(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export risk scores to CSV (admin/auditor only)"""
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    csv_data = generate_csv_risk_scores(session)
    
    return StreamingResponse(
        iter([csv_data.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=risk_scores_{datetime.utcnow().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/ledger.csv")
def export_ledger_csv(
    days: int = Query(90, ge=1, le=365),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export ledger entries to CSV"""
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    csv_data = generate_csv_ledger(session, days)
    
    return StreamingResponse(
        iter([csv_data.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ledger_{days}days_{datetime.utcnow().strftime('%Y%m%d')}.csv"}
    )


@router.get("/export/compliance-report.pdf")
def export_compliance_report_pdf(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Generate comprehensive compliance report in PDF format
    (admin/auditor only)
    """
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    pdf_buffer = generate_pdf_compliance_report(session)
    
    return StreamingResponse(
        iter([pdf_buffer.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=compliance_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf"}
    )
