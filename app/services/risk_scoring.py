"""
Risk Scoring Service - Week 7
Combines internal trade data with external economic indicators
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlmodel import Session, select, func
from app.models.models import (
    User, Document, LedgerEntry, TradeTransaction,
    RiskScore, IntegrityAlert, LedgerAction, TransactionStatus
)
import random  # For mock external data - replace with real API calls


class RiskScoringService:
    """
    Calculate risk scores for users/organizations based on:
    - Internal: Transaction history, integrity alerts, ledger events
    - External: Country risk, trade statistics, economic indicators
    """
    
    def __init__(self, session: Session):
        self.session = session
        
    def calculate_user_risk_score(self, user_id: int) -> Dict:
        """
        Calculate comprehensive risk score for a user
        Returns: {score: float (0-100), rationale: str, factors: dict}
        """
        user = self.session.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        factors = {}
        
        # Internal Risk Factors (60% weight)
        factors["transaction_risk"] = self._assess_transaction_history(user_id)
        factors["integrity_risk"] = self._assess_integrity_violations(user_id)
        factors["ledger_anomalies"] = self._detect_ledger_anomalies(user_id)
        factors["document_completeness"] = self._assess_document_quality(user_id)
        
        # External Risk Factors (40% weight)
        factors["country_risk"] = self._get_country_risk(user.org_name)
        factors["industry_risk"] = self._get_industry_risk(user.role.value)
        factors["economic_indicators"] = self._get_economic_indicators(user.org_name)
        
        # Calculate weighted score
        score = self._compute_weighted_score(factors)
        rationale = self._generate_rationale(factors, user)
        
        # Store in database
        risk_record = RiskScore(
            user_id=user_id,
            score=score,
            rationale=rationale,
            last_updated=datetime.utcnow()
        )
        self.session.add(risk_record)
        self.session.commit()
        
        return {
            "user_id": user_id,
            "user_name": user.name,
            "org_name": user.org_name,
            "score": round(score, 2),
            "risk_level": self._score_to_level(score),
            "rationale": rationale,
            "factors": factors,
            "updated_at": datetime.utcnow().isoformat()
        }
    
    def _assess_transaction_history(self, user_id: int) -> Dict:
        """Analyze transaction patterns for risk indicators"""
        # Get transactions where user is buyer or seller
        stmt = select(TradeTransaction).where(
            (TradeTransaction.buyer_id == user_id) | 
            (TradeTransaction.seller_id == user_id)
        )
        transactions = self.session.exec(stmt).all()
        
        if not transactions:
            return {"score": 50, "reason": "No transaction history"}
        
        total = len(transactions)
        disputed = sum(1 for t in transactions if t.status == TransactionStatus.disputed)
        completed = sum(1 for t in transactions if t.status == TransactionStatus.completed)
        
        # Calculate risk based on dispute rate
        dispute_rate = (disputed / total) * 100 if total > 0 else 0
        completion_rate = (completed / total) * 100 if total > 0 else 0
        
        # Higher dispute rate = higher risk
        risk_score = min(100, dispute_rate * 10 + (100 - completion_rate) * 0.5)
        
        return {
            "score": round(risk_score, 2),
            "total_transactions": total,
            "disputed": disputed,
            "completed": completed,
            "dispute_rate": round(dispute_rate, 2),
            "completion_rate": round(completion_rate, 2)
        }
    
    def _assess_integrity_violations(self, user_id: int) -> Dict:
        """Check for document integrity issues"""
        # Get user's documents
        stmt = select(Document).where(Document.owner_id == user_id)
        documents = self.session.exec(stmt).all()
        
        if not documents:
            return {"score": 0, "reason": "No documents"}
        
        # Count integrity alerts
        doc_ids = [d.id for d in documents]
        alert_stmt = select(IntegrityAlert).where(
            IntegrityAlert.document_id.in_(doc_ids),
            IntegrityAlert.resolved == False
        )
        alerts = self.session.exec(alert_stmt).all()
        
        alert_count = len(alerts)
        doc_count = len(documents)
        
        # More unresolved alerts = higher risk
        violation_rate = (alert_count / doc_count) * 100 if doc_count > 0 else 0
        risk_score = min(100, violation_rate * 20)  # Each 5% violation adds 1 point
        
        return {
            "score": round(risk_score, 2),
            "total_documents": doc_count,
            "unresolved_alerts": alert_count,
            "violation_rate": round(violation_rate, 2)
        }
    
    def _detect_ledger_anomalies(self, user_id: int) -> Dict:
        """Detect unusual patterns in ledger entries"""
        # Get recent ledger entries by this user
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        stmt = select(LedgerEntry).where(
            LedgerEntry.actor_id == user_id,
            LedgerEntry.created_at >= thirty_days_ago
        )
        entries = self.session.exec(stmt).all()
        
        if not entries:
            return {"score": 0, "reason": "No recent activity"}
        
        # Count different action types
        actions = {}
        for entry in entries:
            action = entry.action.value
            actions[action] = actions.get(action, 0) + 1
        
        # Detect anomalies: high rate of amendments/cancellations
        total = len(entries)
        amendments = actions.get("AMENDED", 0)
        cancellations = actions.get("CANCELLED", 0)
        
        anomaly_rate = ((amendments + cancellations) / total) * 100 if total > 0 else 0
        risk_score = min(100, anomaly_rate * 2)  # High amendment rate = potential issue
        
        return {
            "score": round(risk_score, 2),
            "total_entries": total,
            "amendments": amendments,
            "cancellations": cancellations,
            "anomaly_rate": round(anomaly_rate, 2),
            "action_breakdown": actions
        }
    
    def _assess_document_quality(self, user_id: int) -> Dict:
        """Assess document completeness and quality"""
        stmt = select(Document).where(Document.owner_id == user_id)
        documents = self.session.exec(stmt).all()
        
        if not documents:
            return {"score": 30, "reason": "No documents submitted"}
        
        total = len(documents)
        missing_hash = sum(1 for d in documents if not d.hash)
        missing_file = sum(1 for d in documents if not d.file_url)
        
        completeness_rate = ((total - missing_hash - missing_file) / total) * 100
        risk_score = 100 - completeness_rate  # Lower completeness = higher risk
        
        return {
            "score": round(risk_score, 2),
            "total_documents": total,
            "missing_hash": missing_hash,
            "missing_file": missing_file,
            "completeness_rate": round(completeness_rate, 2)
        }
    
    def _get_country_risk(self, org_name: str) -> Dict:
        """
        Get country risk from external sources (UNCTAD, WTO, BIS)
        For now using mock data - replace with real API calls
        """
        # Mock country risk scores (0-100, higher = riskier)
        # In production: call UNCTAD API, World Bank, or similar
        country_risks = {
            "USA": 15,
            "UK": 18,
            "Germany": 12,
            "China": 35,
            "India": 40,
            "Brazil": 45,
            "Nigeria": 65,
            "Default": 50
        }
        
        # Simple org name parsing (enhance with geocoding API)
        score = country_risks.get("Default", 50)
        for country, risk in country_risks.items():
            if country.lower() in org_name.lower():
                score = risk
                break
        
        return {
            "score": score,
            "country": "Derived from org_name",  # In prod: use proper country lookup
            "source": "Mock Data - Replace with UNCTAD/WB API"
        }
    
    def _get_industry_risk(self, role: str) -> Dict:
        """Get industry-specific risk factors"""
        # Mock industry risks based on role
        industry_risks = {
            "bank": 20,
            "corporate": 30,
            "auditor": 10,
            "admin": 5
        }
        
        score = industry_risks.get(role, 40)
        
        return {
            "score": score,
            "industry": role,
            "source": "Internal classification"
        }
    
    def _get_economic_indicators(self, org_name: str) -> Dict:
        """
        Fetch economic indicators affecting trade risk
        Mock implementation - replace with real APIs (IMF, World Bank, etc.)
        """
        # In production: fetch real data from:
        # - IMF World Economic Outlook
        # - World Bank Open Data
        # - UNCTAD Stat
        
        return {
            "score": random.randint(20, 60),  # Mock random score
            "gdp_growth": round(random.uniform(-2.0, 5.0), 2),
            "inflation_rate": round(random.uniform(1.0, 8.0), 2),
            "trade_balance": round(random.uniform(-50, 50), 2),
            "currency_stability": random.choice(["stable", "volatile", "declining"]),
            "source": "Mock Data - Replace with IMF/World Bank API"
        }
    
    def _compute_weighted_score(self, factors: Dict) -> float:
        """Calculate final weighted risk score (0-100)"""
        # Internal factors: 60% weight
        internal_score = (
            factors["transaction_risk"]["score"] * 0.25 +
            factors["integrity_risk"]["score"] * 0.20 +
            factors["ledger_anomalies"]["score"] * 0.10 +
            factors["document_completeness"]["score"] * 0.05
        )
        
        # External factors: 40% weight
        external_score = (
            factors["country_risk"]["score"] * 0.20 +
            factors["industry_risk"]["score"] * 0.10 +
            factors["economic_indicators"]["score"] * 0.10
        )
        
        total_score = internal_score + external_score
        return min(100, max(0, total_score))  # Clamp to 0-100
    
    def _generate_rationale(self, factors: Dict, user: User) -> str:
        """Generate human-readable explanation of risk score"""
        lines = [f"Risk assessment for {user.name} ({user.org_name}):"]
        
        # Transaction history
        tx = factors["transaction_risk"]
        if tx["score"] > 50:
            lines.append(f"- High transaction risk ({tx['score']}): {tx['disputed']} disputed out of {tx['total_transactions']} transactions")
        
        # Integrity issues
        integ = factors["integrity_risk"]
        if integ["score"] > 30:
            lines.append(f"- Integrity concerns ({integ['score']}): {integ['unresolved_alerts']} unresolved alerts")
        
        # Ledger anomalies
        ledger = factors["ledger_anomalies"]
        if ledger["score"] > 40:
            lines.append(f"- Ledger anomalies detected ({ledger['score']}): High rate of amendments/cancellations")
        
        # Country risk
        country = factors["country_risk"]
        if country["score"] > 40:
            lines.append(f"- Elevated country risk ({country['score']})")
        
        return " ".join(lines)
    
    def _score_to_level(self, score: float) -> str:
        """Convert numeric score to risk level"""
        if score < 20:
            return "LOW"
        elif score < 40:
            return "MODERATE"
        elif score < 60:
            return "ELEVATED"
        elif score < 80:
            return "HIGH"
        else:
            return "CRITICAL"
    
    def get_all_risk_scores(self, limit: int = 100) -> List[Dict]:
        """Get risk scores for all users, sorted by risk level"""
        stmt = select(RiskScore).order_by(RiskScore.score.desc()).limit(limit)
        scores = self.session.exec(stmt).all()
        
        result = []
        for score in scores:
            user = self.session.get(User, score.user_id)
            result.append({
                "user_id": score.user_id,
                "user_name": user.name if user else "Unknown",
                "org_name": user.org_name if user else "Unknown",
                "score": round(score.score, 2),
                "risk_level": self._score_to_level(score.score),
                "last_updated": score.last_updated.isoformat()
            })
        
        return result
    
    def refresh_all_risk_scores(self) -> Dict:
        """Recalculate risk scores for all active users"""
        stmt = select(User)
        users = self.session.exec(stmt).all()
        
        updated = 0
        errors = []
        
        for user in users:
            try:
                self.calculate_user_risk_score(user.id)
                updated += 1
            except Exception as e:
                errors.append(f"User {user.id}: {str(e)}")
        
        return {
            "total_users": len(users),
            "updated": updated,
            "errors": errors
        }
