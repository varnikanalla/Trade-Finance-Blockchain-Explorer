"""
Analytics & Dashboard Router - Week 8
APIs for analytics dashboards and reporting
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select, func
from typing import List, Optional
from datetime import datetime, timedelta
from app.database import get_session
from app.dependencies import get_current_user
from app.models.models import (
    User, Document, LedgerEntry, TradeTransaction,
    RiskScore, IntegrityAlert, UserRole, TransactionStatus,
    DocType, LedgerAction
)
from pydantic import BaseModel
import io
import csv
from collections import defaultdict


router = APIRouter(tags=["Analytics & Dashboards"])


# ─── Response Models ──────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_users: int
    total_documents: int
    total_transactions: int
    pending_transactions: int
    completed_transactions: int
    disputed_transactions: int
    integrity_alerts: int
    high_risk_users: int
    avg_risk_score: float


class DocumentStats(BaseModel):
    doc_type: str
    count: int
    percentage: float


class TransactionTrend(BaseModel):
    date: str
    count: int
    total_amount: float
    avg_amount: float


class RiskDistribution(BaseModel):
    risk_level: str
    count: int
    percentage: float


# ─── Dashboard Endpoints ──────────────────────────────────────────────────────

@router.get("/analytics/dashboard", response_model=DashboardStats)
def get_dashboard_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get overall dashboard statistics
    High-level KPIs for the landing page
    """
    # Total counts
    total_users = session.exec(select(func.count(User.id))).one()
    total_documents = session.exec(select(func.count(Document.id))).one()
    total_transactions = session.exec(select(func.count(TradeTransaction.id))).one()
    
    # Transaction status breakdown
    pending = session.exec(
        select(func.count(TradeTransaction.id))
        .where(TradeTransaction.status == TransactionStatus.pending)
    ).one()
    
    completed = session.exec(
        select(func.count(TradeTransaction.id))
        .where(TradeTransaction.status == TransactionStatus.completed)
    ).one()
    
    disputed = session.exec(
        select(func.count(TradeTransaction.id))
        .where(TradeTransaction.status == TransactionStatus.disputed)
    ).one()
    
    # Unresolved integrity alerts
    integrity_alerts = session.exec(
        select(func.count(IntegrityAlert.id))
        .where(IntegrityAlert.resolved == False)
    ).one()
    
    # High risk users (score > 60)
    high_risk_users = session.exec(
        select(func.count(RiskScore.id))
        .where(RiskScore.score >= 60)
    ).one()
    
    # Average risk score
    avg_risk = session.exec(select(func.avg(RiskScore.score))).one() or 0.0
    
    return DashboardStats(
        total_users=total_users,
        total_documents=total_documents,
        total_transactions=total_transactions,
        pending_transactions=pending,
        completed_transactions=completed,
        disputed_transactions=disputed,
        integrity_alerts=integrity_alerts,
        high_risk_users=high_risk_users,
        avg_risk_score=round(avg_risk, 2)
    )


@router.get("/analytics/documents/by-type", response_model=List[DocumentStats])
def get_documents_by_type(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get document count breakdown by type
    Useful for pie charts
    """
    total = session.exec(select(func.count(Document.id))).one()
    
    results = []
    for doc_type in DocType:
        count = session.exec(
            select(func.count(Document.id))
            .where(Document.doc_type == doc_type)
        ).one()
        
        results.append(DocumentStats(
            doc_type=doc_type.value,
            count=count,
            percentage=round((count / total * 100) if total > 0 else 0, 2)
        ))
    
    return results


@router.get("/analytics/transactions/trends")
def get_transaction_trends(
    days: int = Query(30, ge=7, le=365, description="Number of days to analyze"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get transaction volume and value trends over time
    For line charts showing activity patterns
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    stmt = select(TradeTransaction).where(
        TradeTransaction.created_at >= start_date
    ).order_by(TradeTransaction.created_at)
    
    transactions = session.exec(stmt).all()
    
    # Group by date
    daily_stats = defaultdict(lambda: {"count": 0, "total_amount": 0.0, "amounts": []})
    
    for tx in transactions:
        date_key = tx.created_at.date().isoformat()
        daily_stats[date_key]["count"] += 1
        daily_stats[date_key]["total_amount"] += tx.amount
        daily_stats[date_key]["amounts"].append(tx.amount)
    
    # Convert to list
    trends = []
    for date_str in sorted(daily_stats.keys()):
        stats = daily_stats[date_str]
        avg_amount = stats["total_amount"] / stats["count"] if stats["count"] > 0 else 0
        
        trends.append({
            "date": date_str,
            "count": stats["count"],
            "total_amount": round(stats["total_amount"], 2),
            "avg_amount": round(avg_amount, 2)
        })
    
    return {
        "period_days": days,
        "start_date": start_date.date().isoformat(),
        "end_date": datetime.utcnow().date().isoformat(),
        "trends": trends
    }


@router.get("/analytics/risk/distribution", response_model=List[RiskDistribution])
def get_risk_distribution(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get distribution of users across risk levels
    """
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    total = session.exec(select(func.count(RiskScore.id))).one()
    
    # Define risk levels
    risk_levels = [
        ("LOW", 0, 20),
        ("MODERATE", 20, 40),
        ("ELEVATED", 40, 60),
        ("HIGH", 60, 80),
        ("CRITICAL", 80, 100)
    ]
    
    distribution = []
    for level_name, min_score, max_score in risk_levels:
        count = session.exec(
            select(func.count(RiskScore.id))
            .where(RiskScore.score >= min_score)
            .where(RiskScore.score < max_score if max_score < 100 else RiskScore.score <= 100)
        ).one()
        
        distribution.append(RiskDistribution(
            risk_level=level_name,
            count=count,
            percentage=round((count / total * 100) if total > 0 else 0, 2)
        ))
    
    return distribution


@router.get("/analytics/ledger/activity")
def get_ledger_activity(
    days: int = Query(30, ge=7, le=365),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get ledger activity breakdown by action type
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    stmt = select(LedgerEntry).where(LedgerEntry.created_at >= start_date)
    entries = session.exec(stmt).all()
    
    # Count by action type
    action_counts = defaultdict(int)
    for entry in entries:
        action_counts[entry.action.value] += 1
    
    total = len(entries)
    
    return {
        "period_days": days,
        "total_entries": total,
        "activity_breakdown": [
            {
                "action": action,
                "count": count,
                "percentage": round((count / total * 100) if total > 0 else 0, 2)
            }
            for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True)
        ]
    }


@router.get("/analytics/users/by-role")
def get_users_by_role(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get user count by role"""
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    total = session.exec(select(func.count(User.id))).one()
    
    role_stats = []
    for role in UserRole:
        count = session.exec(
            select(func.count(User.id)).where(User.role == role)
        ).one()
        
        role_stats.append({
            "role": role.value,
            "count": count,
            "percentage": round((count / total * 100) if total > 0 else 0, 2)
        })
    
    return {"total_users": total, "role_distribution": role_stats}


@router.get("/analytics/integrity/alerts-summary")
def get_integrity_alerts_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get summary of integrity alerts"""
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    total = session.exec(select(func.count(IntegrityAlert.id))).one()
    resolved = session.exec(
        select(func.count(IntegrityAlert.id)).where(IntegrityAlert.resolved == True)
    ).one()
    unresolved = total - resolved
    
    # Count by severity
    severity_counts = {}
    for severity in ["low", "medium", "high", "critical"]:
        count = session.exec(
            select(func.count(IntegrityAlert.id))
            .where(IntegrityAlert.severity == severity)
            .where(IntegrityAlert.resolved == False)
        ).one()
        severity_counts[severity] = count
    
    return {
        "total_alerts": total,
        "resolved": resolved,
        "unresolved": unresolved,
        "resolution_rate": round((resolved / total * 100) if total > 0 else 0, 2),
        "by_severity": severity_counts
    }


@router.get("/analytics/top-traders")
def get_top_traders(
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get top traders by transaction volume
    """
    # Query all transactions and aggregate
    stmt = select(TradeTransaction)
    transactions = session.exec(stmt).all()
    
    # Aggregate by user
    user_stats = defaultdict(lambda: {"buy_count": 0, "sell_count": 0, "buy_volume": 0.0, "sell_volume": 0.0})
    
    for tx in transactions:
        user_stats[tx.buyer_id]["buy_count"] += 1
        user_stats[tx.buyer_id]["buy_volume"] += tx.amount
        
        user_stats[tx.seller_id]["sell_count"] += 1
        user_stats[tx.seller_id]["sell_volume"] += tx.amount
    
    # Calculate total volume and sort
    user_totals = []
    for user_id, stats in user_stats.items():
        total_volume = stats["buy_volume"] + stats["sell_volume"]
        total_count = stats["buy_count"] + stats["sell_count"]
        
        user = session.get(User, user_id)
        if user:
            user_totals.append({
                "user_id": user_id,
                "name": user.name,
                "org_name": user.org_name,
                "total_transactions": total_count,
                "total_volume": round(total_volume, 2),
                "buy_transactions": stats["buy_count"],
                "sell_transactions": stats["sell_count"],
                "buy_volume": round(stats["buy_volume"], 2),
                "sell_volume": round(stats["sell_volume"], 2)
            })
    
    # Sort by total volume descending
    user_totals.sort(key=lambda x: x["total_volume"], reverse=True)
    
    return {
        "top_traders": user_totals[:limit],
        "total_analyzed": len(user_totals)
    }


@router.get("/analytics/time-series/daily")
def get_daily_time_series(
    days: int = Query(90, ge=7, le=365),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive daily time series data
    Includes transactions, documents, ledger entries
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get all relevant data
    transactions = session.exec(
        select(TradeTransaction).where(TradeTransaction.created_at >= start_date)
    ).all()
    
    documents = session.exec(
        select(Document).where(Document.created_at >= start_date)
    ).all()
    
    ledger_entries = session.exec(
        select(LedgerEntry).where(LedgerEntry.created_at >= start_date)
    ).all()
    
    # Aggregate by date
    daily_data = defaultdict(lambda: {
        "transactions": 0,
        "documents": 0,
        "ledger_entries": 0,
        "transaction_volume": 0.0
    })
    
    for tx in transactions:
        date_key = tx.created_at.date().isoformat()
        daily_data[date_key]["transactions"] += 1
        daily_data[date_key]["transaction_volume"] += tx.amount
    
    for doc in documents:
        date_key = doc.created_at.date().isoformat()
        daily_data[date_key]["documents"] += 1
    
    for entry in ledger_entries:
        date_key = entry.created_at.date().isoformat()
        daily_data[date_key]["ledger_entries"] += 1
    
    # Convert to sorted list
    time_series = [
        {
            "date": date_str,
            **stats,
            "transaction_volume": round(stats["transaction_volume"], 2)
        }
        for date_str, stats in sorted(daily_data.items())
    ]
    
    return {
        "period_days": days,
        "start_date": start_date.date().isoformat(),
        "end_date": datetime.utcnow().date().isoformat(),
        "data_points": len(time_series),
        "time_series": time_series
    }
