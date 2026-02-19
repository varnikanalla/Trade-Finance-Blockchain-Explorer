"""
Demo Data Setup Script
Run this to populate database with realistic test data for presentation
"""
from sqlmodel import Session, create_engine
from datetime import datetime, timedelta
from app.models.models import (
    User, Document, LedgerEntry, TradeTransaction,
    RiskScore, IntegrityAlert, UserRole, DocType,
    LedgerAction, TransactionStatus, IntegrityStatus
)
from app.database import engine
import random


def create_demo_data():
    """Create comprehensive demo data for presentation"""
    
    with Session(engine) as session:
        print("🚀 Creating demo data...")
        
        # 1. Create Users (different roles)
        users = [
            User(
                name="Alice Chen",
                email="alice@globalbank.com",
                password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYXqK7H9C2a",  # hashed "demo123"
                role=UserRole.bank,
                org_name="Global Trade Bank"
            ),
            User(
                name="Bob Martinez",
                email="bob@acmecorp.com",
                password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYXqK7H9C2a",
                role=UserRole.corporate,
                org_name="ACME Corporation"
            ),
            User(
                name="Carol Wilson",
                email="carol@auditpro.com",
                password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYXqK7H9C2a",
                role=UserRole.auditor,
                org_name="AuditPro International"
            ),
            User(
                name="David Kim",
                email="admin@platform.com",
                password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYXqK7H9C2a",
                role=UserRole.admin,
                org_name="Platform Administration"
            ),
            User(
                name="Emma Singh",
                email="emma@techimports.com",
                password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYXqK7H9C2a",
                role=UserRole.corporate,
                org_name="Tech Imports Ltd"
            ),
        ]
        
        for user in users:
            session.add(user)
        session.commit()
        
        for user in users:
            session.refresh(user)
        
        print(f"✅ Created {len(users)} users")
        
        # 2. Create Documents
        doc_data = [
            (users[1], DocType.INVOICE, "INV-2024-001", "Commercial Invoice for Electronics"),
            (users[1], DocType.PO, "PO-2024-045", "Purchase Order - Computer Hardware"),
            (users[0], DocType.LOC, "LOC-GB-2024-123", "Letter of Credit - $500,000"),
            (users[4], DocType.BILL_OF_LADING, "BOL-SH-2024-789", "Bill of Lading - Shanghai to LA"),
            (users[1], DocType.COO, "COO-2024-456", "Certificate of Origin - USA"),
            (users[4], DocType.INSURANCE_CERT, "INS-2024-321", "Marine Insurance Certificate"),
            (users[0], DocType.LOC, "LOC-GB-2024-124", "Letter of Credit - $750,000"),
            (users[1], DocType.INVOICE, "INV-2024-002", "Invoice for Textile Goods"),
        ]
        
        documents = []
        for owner, doc_type, doc_num, description in doc_data:
            doc = Document(
                owner_id=owner.id,
                doc_type=doc_type,
                doc_number=doc_num,
                file_url=f"https://s3.example.com/docs/{doc_num}.pdf",
                hash=f"sha256_{random.randint(100000, 999999)}",
                issued_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
            )
            documents.append(doc)
            session.add(doc)
        
        session.commit()
        for doc in documents:
            session.refresh(doc)
        
        print(f"✅ Created {len(documents)} documents")
        
        # 3. Create Ledger Entries
        ledger_entries = []
        for i, doc in enumerate(documents):
            # Each document gets 2-4 ledger entries
            actions = [
                (LedgerAction.ISSUED, doc.owner_id),
                (LedgerAction.VERIFIED, users[2].id),  # Auditor verifies
                (LedgerAction.SHIPPED, users[0].id if i % 2 == 0 else users[4].id),
            ]
            
            if i % 3 == 0:
                actions.append((LedgerAction.RECEIVED, users[1].id))
            
            if i % 4 == 0:
                actions.append((LedgerAction.PAID, users[0].id))
            
            for j, (action, actor_id) in enumerate(actions):
                entry = LedgerEntry(
                    document_id=doc.id,
                    action=action,
                    actor_id=actor_id,
                    created_at=doc.issued_at + timedelta(hours=j*24)
                )
                ledger_entries.append(entry)
                session.add(entry)
        
        session.commit()
        print(f"✅ Created {len(ledger_entries)} ledger entries")
        
        # 4. Create Trade Transactions
        transactions = [
            TradeTransaction(
                buyer_id=users[1].id,
                seller_id=users[4].id,
                amount=125000.00,
                currency="USD",
                status=TransactionStatus.completed,
                created_at=datetime.utcnow() - timedelta(days=20)
            ),
            TradeTransaction(
                buyer_id=users[4].id,
                seller_id=users[1].id,
                amount=87500.00,
                currency="EUR",
                status=TransactionStatus.completed,
                created_at=datetime.utcnow() - timedelta(days=15)
            ),
            TradeTransaction(
                buyer_id=users[1].id,
                seller_id=users[4].id,
                amount=250000.00,
                currency="USD",
                status=TransactionStatus.in_progress,
                created_at=datetime.utcnow() - timedelta(days=5)
            ),
            TradeTransaction(
                buyer_id=users[0].id,
                seller_id=users[1].id,
                amount=500000.00,
                currency="USD",
                status=TransactionStatus.pending,
                created_at=datetime.utcnow() - timedelta(days=2)
            ),
            TradeTransaction(
                buyer_id=users[4].id,
                seller_id=users[0].id,
                amount=45000.00,
                currency="GBP",
                status=TransactionStatus.disputed,
                created_at=datetime.utcnow() - timedelta(days=30)
            ),
        ]
        
        for tx in transactions:
            session.add(tx)
        session.commit()
        
        print(f"✅ Created {len(transactions)} transactions")
        
        # 5. Create Risk Scores
        risk_scores = [
            RiskScore(user_id=users[0].id, score=25.5, rationale="Low risk: Established bank with strong compliance"),
            RiskScore(user_id=users[1].id, score=42.0, rationale="Moderate risk: High transaction volume with one dispute"),
            RiskScore(user_id=users[2].id, score=15.0, rationale="Very low risk: Auditor with no issues"),
            RiskScore(user_id=users[3].id, score=10.0, rationale="Minimal risk: Administrative user"),
            RiskScore(user_id=users[4].id, score=65.0, rationale="Elevated risk: Recent dispute and high amendment rate"),
        ]
        
        for score in risk_scores:
            session.add(score)
        session.commit()
        
        print(f"✅ Created {len(risk_scores)} risk scores")
        
        # 6. Create Integrity Alerts
        alerts = [
            IntegrityAlert(
                document_id=documents[2].id,
                alert_type="hash_mismatch",
                detail="Stored hash does not match recomputed hash",
                severity="high",
                resolved=False,
                created_at=datetime.utcnow() - timedelta(days=3)
            ),
            IntegrityAlert(
                document_id=documents[5].id,
                alert_type="chain_broken",
                detail="Ledger chain integrity violation detected",
                severity="critical",
                resolved=False,
                created_at=datetime.utcnow() - timedelta(days=1)
            ),
            IntegrityAlert(
                document_id=documents[0].id,
                alert_type="hash_mismatch",
                detail="File hash verification failed",
                severity="medium",
                resolved=True,
                resolved_by=users[2].id,
                resolved_at=datetime.utcnow() - timedelta(days=5),
                created_at=datetime.utcnow() - timedelta(days=7)
            ),
        ]
        
        for alert in alerts:
            session.add(alert)
        session.commit()
        
        print(f"✅ Created {len(alerts)} integrity alerts")
        
        print("\n🎉 Demo data created successfully!")
        print(f"\n📊 Summary:")
        print(f"   Users: {len(users)}")
        print(f"   Documents: {len(documents)}")
        print(f"   Ledger Entries: {len(ledger_entries)}")
        print(f"   Transactions: {len(transactions)}")
        print(f"   Risk Scores: {len(risk_scores)}")
        print(f"   Integrity Alerts: {len(alerts)}")
        
        print(f"\n🔐 Login Credentials (all passwords: 'demo123'):")
        for user in users:
            print(f"   {user.email} - {user.role.value}")


if __name__ == "__main__":
    print("🚀 Trade Finance Demo Data Setup")
    print("=" * 50)
    
    # Create tables if they don't exist
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(engine)
    
    try:
        create_demo_data()
        print("\n✅ Setup complete! You can now start your demo.")
        print("\n📝 Next steps:")
        print("   1. Start API: uvicorn app.main:app --reload")
        print("   2. Visit: http://localhost:8000/docs")
        print("   3. Login with any of the credentials above")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("   Try deleting database.db and running again")
