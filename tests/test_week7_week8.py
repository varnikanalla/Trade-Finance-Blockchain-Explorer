"""
Tests for Week 7-8: Risk Assessment, Analytics & Exports
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from datetime import datetime, timedelta
from app.main import app
from app.database import get_session
from app.models.models import (
    User, Document, LedgerEntry, TradeTransaction,
    RiskScore, IntegrityAlert, UserRole, DocType,
    LedgerAction, TransactionStatus, IntegrityStatus
)
from app.dependencies import get_current_user


# ─── Test Database Setup ──────────────────────────────────────────────────────

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="test_users")
def create_test_users(session: Session):
    """Create test users with different roles"""
    users = [
        User(
            name="Admin User",
            email="admin@test.com",
            password="hashed_password",
            role=UserRole.admin,
            org_name="Test Admin Org"
        ),
        User(
            name="Auditor User",
            email="auditor@test.com",
            password="hashed_password",
            role=UserRole.auditor,
            org_name="Test Audit Firm"
        ),
        User(
            name="Bank User",
            email="bank@test.com",
            password="hashed_password",
            role=UserRole.bank,
            org_name="Test Bank Corp"
        ),
        User(
            name="Corporate User",
            email="corporate@test.com",
            password="hashed_password",
            role=UserRole.corporate,
            org_name="Test Corporation"
        ),
    ]
    
    for user in users:
        session.add(user)
    session.commit()
    
    for user in users:
        session.refresh(user)
    
    return users


@pytest.fixture(name="test_data")
def create_test_data(session: Session, test_users):
    """Create comprehensive test data"""
    admin, auditor, bank, corporate = test_users
    
    # Documents
    doc1 = Document(
        owner_id=corporate.id,
        doc_type=DocType.INVOICE,
        doc_number="INV-001",
        file_url="https://example.com/doc1.pdf",
        hash="abc123hash",
        issued_at=datetime.utcnow()
    )
    doc2 = Document(
        owner_id=bank.id,
        doc_type=DocType.LOC,
        doc_number="LOC-001",
        file_url="https://example.com/doc2.pdf",
        hash="def456hash",
        issued_at=datetime.utcnow()
    )
    session.add(doc1)
    session.add(doc2)
    session.commit()
    session.refresh(doc1)
    session.refresh(doc2)
    
    # Transactions
    tx1 = TradeTransaction(
        buyer_id=corporate.id,
        seller_id=bank.id,
        amount=100000.00,
        currency="USD",
        status=TransactionStatus.completed
    )
    tx2 = TradeTransaction(
        buyer_id=bank.id,
        seller_id=corporate.id,
        amount=50000.00,
        currency="USD",
        status=TransactionStatus.disputed
    )
    tx3 = TradeTransaction(
        buyer_id=corporate.id,
        seller_id=bank.id,
        amount=75000.00,
        currency="EUR",
        status=TransactionStatus.pending
    )
    session.add_all([tx1, tx2, tx3])
    session.commit()
    
    # Ledger entries
    entry1 = LedgerEntry(
        document_id=doc1.id,
        action=LedgerAction.ISSUED,
        actor_id=corporate.id
    )
    entry2 = LedgerEntry(
        document_id=doc1.id,
        action=LedgerAction.VERIFIED,
        actor_id=auditor.id
    )
    entry3 = LedgerEntry(
        document_id=doc2.id,
        action=LedgerAction.AMENDED,
        actor_id=bank.id
    )
    session.add_all([entry1, entry2, entry3])
    session.commit()
    
    # Integrity alerts
    alert1 = IntegrityAlert(
        document_id=doc1.id,
        alert_type="hash_mismatch",
        detail="Hash verification failed",
        severity="high",
        resolved=False
    )
    session.add(alert1)
    session.commit()
    
    return {
        "users": test_users,
        "documents": [doc1, doc2],
        "transactions": [tx1, tx2, tx3],
        "ledger_entries": [entry1, entry2, entry3],
        "alerts": [alert1]
    }


def mock_get_current_user_admin(test_users):
    """Mock dependency for admin user"""
    def _mock():
        return test_users[0]  # Admin user
    return _mock


def mock_get_current_user_auditor(test_users):
    """Mock dependency for auditor user"""
    def _mock():
        return test_users[1]  # Auditor user
    return _mock


# ─── Week 7 Tests: Risk Assessment ────────────────────────────────────────────

def test_calculate_risk_score(client: TestClient, test_users, test_data):
    """Test risk score calculation endpoint"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    corporate_user = test_users[3]
    response = client.post(f"/api/risk/calculate/{corporate_user.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "risk_level" in data
    assert "factors" in data
    assert 0 <= data["score"] <= 100
    
    app.dependency_overrides.clear()


def test_get_all_risk_scores(client: TestClient, test_users, test_data, session: Session):
    """Test getting all risk scores"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    # First create some risk scores
    for user in test_users:
        score = RiskScore(
            user_id=user.id,
            score=50.0,
            rationale="Test score"
        )
        session.add(score)
    session.commit()
    
    response = client.get("/api/risk/scores")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 4  # At least our 4 test users
    
    app.dependency_overrides.clear()


def test_get_user_risk_score(client: TestClient, test_users, test_data, session: Session):
    """Test getting individual user risk score"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    corporate_user = test_users[3]
    
    # First calculate a score
    client.post(f"/api/risk/calculate/{corporate_user.id}")
    
    # Then retrieve it
    response = client.get(f"/api/risk/user/{corporate_user.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == corporate_user.id
    assert "score" in data
    assert "risk_level" in data
    
    app.dependency_overrides.clear()


def test_refresh_all_risk_scores(client: TestClient, test_users, test_data):
    """Test bulk risk score refresh"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.post("/api/risk/refresh-all")
    
    assert response.status_code == 200
    data = response.json()
    assert "details" in data
    assert data["details"]["total_users"] >= 4
    
    app.dependency_overrides.clear()


def test_get_country_data(client: TestClient, test_users):
    """Test external country data endpoint"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/external-data/country/USA")
    
    assert response.status_code == 200
    data = response.json()
    assert "composite_risk_score" in data
    assert "data_sources" in data
    
    app.dependency_overrides.clear()


def test_get_high_risk_entities(client: TestClient, test_users, test_data, session: Session):
    """Test high risk entities endpoint"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    # Create some high risk scores
    for i, user in enumerate(test_users):
        score = RiskScore(
            user_id=user.id,
            score=70.0 + i * 5,  # Scores from 70 to 85
            rationale="High risk test"
        )
        session.add(score)
    session.commit()
    
    response = client.get("/api/risk/high-risk-entities?threshold=60.0")
    
    assert response.status_code == 200
    data = response.json()
    assert "high_risk_entities" in data
    assert len(data["high_risk_entities"]) >= 4  # All our test scores are >60
    
    app.dependency_overrides.clear()


# ─── Week 8 Tests: Analytics ──────────────────────────────────────────────────

def test_dashboard_stats(client: TestClient, test_users, test_data):
    """Test dashboard statistics endpoint"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/analytics/dashboard")
    
    assert response.status_code == 200
    data = response.json()
    assert "total_users" in data
    assert "total_documents" in data
    assert "total_transactions" in data
    assert data["total_users"] >= 4
    assert data["total_documents"] >= 2
    assert data["total_transactions"] >= 3
    
    app.dependency_overrides.clear()


def test_documents_by_type(client: TestClient, test_users, test_data):
    """Test document breakdown by type"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/analytics/documents/by-type")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == len(DocType)  # One entry per doc type
    
    # Check structure
    for item in data:
        assert "doc_type" in item
        assert "count" in item
        assert "percentage" in item
    
    app.dependency_overrides.clear()


def test_transaction_trends(client: TestClient, test_users, test_data):
    """Test transaction trends analytics"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/analytics/transactions/trends?days=30")
    
    assert response.status_code == 200
    data = response.json()
    assert "trends" in data
    assert "period_days" in data
    assert data["period_days"] == 30
    
    app.dependency_overrides.clear()


def test_risk_distribution(client: TestClient, test_users, test_data, session: Session):
    """Test risk distribution analytics"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    # Create varied risk scores
    risk_scores = [15, 35, 55, 75, 95]
    for i, user in enumerate(test_users[:5] if len(test_users) >= 5 else test_users):
        score = RiskScore(
            user_id=user.id,
            score=risk_scores[i % len(risk_scores)],
            rationale="Test distribution"
        )
        session.add(score)
    session.commit()
    
    response = client.get("/api/analytics/risk/distribution")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5  # 5 risk levels
    
    for item in data:
        assert "risk_level" in item
        assert "count" in item
        assert "percentage" in item
    
    app.dependency_overrides.clear()


def test_ledger_activity(client: TestClient, test_users, test_data):
    """Test ledger activity analytics"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/analytics/ledger/activity?days=30")
    
    assert response.status_code == 200
    data = response.json()
    assert "total_entries" in data
    assert "activity_breakdown" in data
    assert isinstance(data["activity_breakdown"], list)
    
    app.dependency_overrides.clear()


def test_top_traders(client: TestClient, test_users, test_data):
    """Test top traders analytics"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/analytics/top-traders?limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert "top_traders" in data
    assert isinstance(data["top_traders"], list)
    
    if len(data["top_traders"]) > 0:
        trader = data["top_traders"][0]
        assert "user_id" in trader
        assert "total_volume" in trader
        assert "total_transactions" in trader
    
    app.dependency_overrides.clear()


# ─── Week 8 Tests: Exports ────────────────────────────────────────────────────

def test_export_users_csv(client: TestClient, test_users, test_data):
    """Test CSV export of users"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/export/users.csv")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    
    # Check CSV content
    content = response.text
    assert "ID" in content  # Header
    assert "Name" in content
    assert "Email" in content
    
    app.dependency_overrides.clear()


def test_export_documents_csv(client: TestClient, test_users, test_data):
    """Test CSV export of documents"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/export/documents.csv")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    
    content = response.text
    assert "Document Type" in content
    assert "Document Number" in content
    
    app.dependency_overrides.clear()


def test_export_transactions_csv(client: TestClient, test_users, test_data):
    """Test CSV export of transactions"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/export/transactions.csv?days=90")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    
    content = response.text
    assert "Buyer ID" in content
    assert "Seller ID" in content
    assert "Amount" in content
    
    app.dependency_overrides.clear()


def test_export_risk_scores_csv(client: TestClient, test_users, test_data, session: Session):
    """Test CSV export of risk scores"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    # Create some risk scores first
    for user in test_users:
        score = RiskScore(
            user_id=user.id,
            score=45.0,
            rationale="Test export"
        )
        session.add(score)
    session.commit()
    
    response = client.get("/api/export/risk-scores.csv")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    
    content = response.text
    assert "Risk Score" in content
    assert "Risk Level" in content
    
    app.dependency_overrides.clear()


def test_export_compliance_report_pdf(client: TestClient, test_users, test_data):
    """Test PDF compliance report export"""
    app.dependency_overrides[get_current_user] = mock_get_current_user_admin(test_users)
    
    response = client.get("/api/export/compliance-report.pdf")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert "compliance_report" in response.headers["content-disposition"]
    
    # Check it's actually PDF content
    content = response.content
    assert content.startswith(b"%PDF")  # PDF magic number
    
    app.dependency_overrides.clear()


def test_permission_checks(client: TestClient, test_users, test_data):
    """Test that non-admin users cannot access restricted endpoints"""
    # Use corporate user (not admin/auditor)
    app.dependency_overrides[get_current_user] = lambda: test_users[3]
    
    # Should fail for risk calculation
    response = client.post(f"/api/risk/calculate/{test_users[0].id}")
    assert response.status_code == 403
    
    # Should fail for export
    response = client.get("/api/export/users.csv")
    assert response.status_code == 403
    
    app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
