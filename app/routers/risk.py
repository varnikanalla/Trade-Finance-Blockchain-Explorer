"""
Risk Assessment Router - Week 7
APIs for risk scoring and external data integration
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from typing import List, Optional
from app.database import get_session
from app.dependencies import get_current_user
from app.models.models import User, UserRole
from app.services.risk_scoring import RiskScoringService
from app.services.external_data import ExternalDataService
from pydantic import BaseModel


router = APIRouter(tags=["Risk Assessment"])


# ─── Request/Response Models ──────────────────────────────────────────────────

class RiskScoreResponse(BaseModel):
    user_id: int
    user_name: str
    org_name: str
    score: float
    risk_level: str
    rationale: str
    factors: dict
    updated_at: str


class BulkRiskScoreResponse(BaseModel):
    user_id: int
    user_name: str
    org_name: str
    score: float
    risk_level: str
    last_updated: str


class ExternalDataResponse(BaseModel):
    country: str
    composite_risk_score: float
    data_sources: dict
    aggregated_at: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/risk/calculate/{user_id}", response_model=RiskScoreResponse)
def calculate_risk_score(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate comprehensive risk score for a specific user
    Combines internal metrics + external data sources
    """
    # Only admin and auditor can calculate risk scores
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    service = RiskScoringService(session)
    try:
        result = service.calculate_user_risk_score(user_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating risk: {str(e)}")


@router.get("/risk/scores", response_model=List[BulkRiskScoreResponse])
def get_all_risk_scores(
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get risk scores for all users, sorted by risk level (highest first)
    """
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    service = RiskScoringService(session)
    scores = service.get_all_risk_scores(limit=limit)
    return scores


@router.get("/risk/user/{user_id}", response_model=RiskScoreResponse)
def get_user_risk_score(
    user_id: int,
    recalculate: bool = Query(False, description="Force recalculation"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get existing risk score for a user, optionally recalculate
    """
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        # Users can only view their own risk score
        if current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    service = RiskScoringService(session)
    
    if recalculate:
        result = service.calculate_user_risk_score(user_id)
    else:
        # Get latest score from database
        from sqlmodel import select
        from app.models.models import RiskScore
        stmt = select(RiskScore).where(RiskScore.user_id == user_id).order_by(
            RiskScore.last_updated.desc()
        )
        score = session.exec(stmt).first()
        
        if not score:
            # No existing score, calculate new one
            result = service.calculate_user_risk_score(user_id)
        else:
            user = session.get(User, user_id)
            result = {
                "user_id": user_id,
                "user_name": user.name,
                "org_name": user.org_name,
                "score": round(score.score, 2),
                "risk_level": service._score_to_level(score.score),
                "rationale": score.rationale,
                "factors": {},  # Not stored in DB
                "updated_at": score.last_updated.isoformat()
            }
    
    return result


@router.post("/risk/refresh-all")
def refresh_all_risk_scores(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Recalculate risk scores for all users (admin only)
    Useful for periodic batch updates
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    service = RiskScoringService(session)
    result = service.refresh_all_risk_scores()
    
    return {
        "message": "Risk scores refreshed",
        "details": result
    }


@router.get("/external-data/country/{country_code}")
async def get_country_data(
    country_code: str,
    current_user: User = Depends(get_current_user)
):
    """
    Fetch composite external data for a country from multiple sources
    (UNCTAD, WTO, BIS, World Bank)
    """
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    service = ExternalDataService()
    data = await service.get_composite_risk_data(country_code)
    return data


@router.get("/external-data/trade-stats/{country_code}")
async def get_trade_statistics(
    country_code: str,
    current_user: User = Depends(get_current_user)
):
    """Fetch UNCTAD trade statistics for a country"""
    if current_user.role not in [UserRole.admin, UserRole.auditor, UserRole.bank]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    service = ExternalDataService()
    data = await service.get_unctad_trade_stats(country_code)
    return data


@router.get("/external-data/wto-indicators/{country_code}")
async def get_wto_indicators(
    country_code: str,
    current_user: User = Depends(get_current_user)
):
    """Fetch WTO trade policy indicators"""
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    service = ExternalDataService()
    data = await service.get_wto_trade_indicators(country_code)
    return data


@router.get("/external-data/forex-rates")
async def get_forex_rates(
    base_currency: str = Query("USD", max_length=3),
    current_user: User = Depends(get_current_user)
):
    """Get real-time foreign exchange rates"""
    service = ExternalDataService()
    data = await service.get_realtime_forex_rates(base_currency)
    return data


@router.get("/external-data/sanctions-check")
async def check_sanctions(
    entity_name: str = Query(..., min_length=2),
    country: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user)
):
    """
    Check if entity is on sanctions lists
    (Admin and compliance use only)
    """
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    service = ExternalDataService()
    data = await service.get_sanctions_check(entity_name, country)
    return data


@router.get("/risk/high-risk-entities")
def get_high_risk_entities(
    threshold: float = Query(60.0, ge=0, le=100, description="Risk score threshold"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get all entities with risk score above threshold
    Useful for compliance monitoring
    """
    if current_user.role not in [UserRole.admin, UserRole.auditor]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    from sqlmodel import select
    from app.models.models import RiskScore
    
    stmt = select(RiskScore).where(RiskScore.score >= threshold).order_by(
        RiskScore.score.desc()
    )
    high_risk_scores = session.exec(stmt).all()
    
    result = []
    for score in high_risk_scores:
        user = session.get(User, score.user_id)
        if user:
            result.append({
                "user_id": user.id,
                "name": user.name,
                "org_name": user.org_name,
                "role": user.role.value,
                "score": round(score.score, 2),
                "risk_level": RiskScoringService(session)._score_to_level(score.score),
                "last_updated": score.last_updated.isoformat()
            })
    
    return {
        "threshold": threshold,
        "count": len(result),
        "high_risk_entities": result
    }
