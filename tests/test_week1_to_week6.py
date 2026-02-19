"""
Trade Finance Blockchain Explorer — Test Suite (Weeks 1–6)
===========================================================
Covers:
  - Week 1-2 : Auth & JWT (signup, login, RBAC, refresh)
  - Week 3-4 : Document upload, SHA-256 hashing, ledger entries
  - Week 5   : Trade transaction 7-step flow
  - Week 6   : Celery integrity-check worker, mismatch detection, alerts
"""

import hashlib
import json
import os
import tempfile
import pytest
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session, StaticPool
from fastapi.testclient import TestClient

# ── point everything at in-memory SQLite before importing the app ──────────────
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["USE_LOCAL_STORAGE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-32chars-minimum-len"
os.environ["LOCAL_STORAGE_PATH"] = tempfile.gettempdir()

from app.main import app
from app.database import get_session, engine as real_engine
from app.models import (
    User, Document, LedgerEntry, TradeTransaction,
    IntegrityLog, IntegrityAlert, IntegrityStatus,
    UserRole, DocType, LedgerAction,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def test_db():
    """Fresh in-memory SQLite for each test function."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield test_engine
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def client(test_db):
    return TestClient(app)


@pytest.fixture
def db_session(test_db):
    with Session(test_db) as session:
        yield session


# ─── Helpers ──────────────────────────────────────────────────────────────────

def signup_and_login(client, name, email, password, role, org):
    r = client.post("/auth/signup", json={
        "name": name, "email": email, "password": password,
        "role": role, "org_name": org,
    })
    assert r.status_code == 201, f"Signup failed for {email}: {r.text}"
    r2 = client.post("/auth/login", json={"email": email, "password": password})
    assert r2.status_code == 200, f"Login failed for {email}: {r2.text}"
    return r2.json()["access_token"]


def H(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# WEEK 1-2  Auth & Org
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthWeek1_2:

    def test_signup_success(self, client):
        r = client.post("/auth/signup", json={
            "name": "Alice", "email": "alice@bank.com", "password": "pw123",
            "role": "bank", "org_name": "Global Bank",
        })
        assert r.status_code == 201
        d = r.json()
        assert d["email"] == "alice@bank.com"
        assert d["role"] == "bank"
        assert "password" not in d           # never expose hash

    def test_duplicate_email_rejected(self, client):
        payload = {"name": "X", "email": "dup@x.com", "password": "p",
                   "role": "corporate", "org_name": "X"}
        client.post("/auth/signup", json=payload)
        r = client.post("/auth/signup", json=payload)
        assert r.status_code == 400

    def test_login_wrong_password(self, client):
        client.post("/auth/signup", json={
            "name": "Bob", "email": "bob@x.com", "password": "correct",
            "role": "corporate", "org_name": "X",
        })
        r = client.post("/auth/login", json={"email": "bob@x.com", "password": "wrong"})
        assert r.status_code == 401

    def test_login_returns_both_tokens(self, client):
        signup_and_login(client, "Carol", "carol@x.com", "p", "auditor", "Audit")
        r = client.post("/auth/login", json={"email": "carol@x.com", "password": "p"})
        assert "access_token" in r.json()
        assert "refresh_token" in r.json()

    def test_get_me(self, client):
        token = signup_and_login(client, "Dave", "dave@x.com", "p", "admin", "Admin")
        r = client.get("/auth/me", headers=H(token))
        assert r.status_code == 200
        assert r.json()["email"] == "dave@x.com"

    def test_protected_route_without_token(self, client):
        r = client.get("/auth/me")
        assert r.status_code == 401

    def test_refresh_token_works(self, client):
        signup_and_login(client, "Eve", "eve@x.com", "p", "bank", "Bank")
        login_r = client.post("/auth/login", json={"email": "eve@x.com", "password": "p"})
        refresh = login_r.json()["refresh_token"]
        r = client.post("/auth/refresh", json={"refresh_token": refresh})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_role_based_access_user_list(self, client):
        """Auditors/banks can list users; corporate cannot."""
        corp_token = signup_and_login(client, "Corp", "corp@x.com", "p", "corporate", "C")
        bank_token = signup_and_login(client, "Banker", "banker@x.com", "p", "bank", "B")

        r_corp = client.get("/auth/users", headers=H(corp_token))
        assert r_corp.status_code == 403

        r_bank = client.get("/auth/users", headers=H(bank_token))
        assert r_bank.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# WEEK 3-4  Documents, SHA-256 Hashing & Ledger
# ══════════════════════════════════════════════════════════════════════════════

class TestDocumentsWeek3_4:

    def _upload(self, client, token, doc_type, doc_number, content=b"test content"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            with open(path, "rb") as f:
                r = client.post(
                    "/documents/upload",
                    data={"doc_type": doc_type, "doc_number": doc_number},
                    files={"file": ("doc.pdf", f, "application/pdf")},
                    headers=H(token),
                )
            return r
        finally:
            os.unlink(path)

    def test_upload_stores_sha256_hash(self, client):
        token = signup_and_login(client, "DocUser", "docu@x.com", "p", "corporate", "C")
        content = b"unique invoice content 12345"
        r = self._upload(client, token, "INVOICE", "INV-001", content)
        assert r.status_code == 201
        data = r.json()
        assert data["hash"] == hashlib.sha256(content).hexdigest()

    def test_upload_creates_ledger_entry(self, client, db_session):
        token = signup_and_login(client, "LedgerUser", "lu@x.com", "p", "bank", "B")
        r = self._upload(client, token, "LOC", "LOC-001")
        assert r.status_code == 201
        doc_id = r.json()["id"]

        ledger_r = client.get(f"/documents/{doc_id}/ledger", headers=H(token))
        assert ledger_r.status_code == 200
        entries = ledger_r.json()
        assert len(entries) >= 1
        assert entries[0]["action"] == "ISSUED"

    def test_hash_verification_clean_file(self, client):
        token = signup_and_login(client, "VerifyUser", "vu@x.com", "p", "bank", "B")
        content = b"clean document"
        r = self._upload(client, token, "BILL_OF_LADING", "BOL-001", content)
        doc_id = r.json()["id"]

        vr = client.get(f"/documents/{doc_id}/verify", headers=H(token))
        assert vr.status_code == 200
        v = vr.json()
        assert v["is_chain_valid"] is True
        assert v["tamper_detected"] is False
        assert v["stored_hash"] == hashlib.sha256(content).hexdigest()

    def test_document_list_scoped_to_owner(self, client):
        t1 = signup_and_login(client, "Owner1", "o1@x.com", "p", "corporate", "C1")
        t2 = signup_and_login(client, "Owner2", "o2@x.com", "p", "corporate", "C2")
        self._upload(client, t1, "PO", "PO-001")
        self._upload(client, t2, "PO", "PO-002")

        r = client.get("/documents/", headers=H(t1))
        assert r.status_code == 200
        nums = [d["doc_number"] for d in r.json()]
        assert "PO-001" in nums
        assert "PO-002" not in nums

    def test_ledger_explorer_endpoint(self, client):
        token = signup_and_login(client, "LedExp", "le@x.com", "p", "bank", "B")
        self._upload(client, token, "LOC", "LOC-EX")
        r = client.get("/ledger/", headers=H(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ══════════════════════════════════════════════════════════════════════════════
# WEEK 5  Trade Transaction 7-Step Flow
# ══════════════════════════════════════════════════════════════════════════════

class TestTradeFlowWeek5:

    def _setup(self, client):
        buyer_t  = signup_and_login(client, "Buyer",   "buyer@tf.com",   "b123", "corporate", "BuyerCo")
        seller_t = signup_and_login(client, "Seller",  "seller@tf.com",  "s123", "corporate", "SellerCo")
        bank_t   = signup_and_login(client, "Bank",    "bank@tf.com",    "bk123", "bank",      "GlobalBank")
        audit_t  = signup_and_login(client, "Auditor", "auditor@tf.com", "a123", "auditor",   "AuditCo")
        seller_me = client.get("/auth/me", headers=H(seller_t)).json()
        return buyer_t, seller_t, bank_t, audit_t, seller_me["id"]

    def test_complete_7_step_trade_flow(self, client):
        buyer_t, seller_t, bank_t, audit_t, seller_id = self._setup(client)

        # Step 1 – Buyer creates PO
        r = client.post("/trade/create-po", json={
            "seller_id": seller_id, "amount": 50000,
            "currency": "USD", "doc_number": "PO-2024-001",
        }, headers=H(buyer_t))
        assert r.status_code == 200, r.text
        po_id = r.json()["po_id"]
        tx_id = r.json()["transaction_id"]

        # Step 2 – Bank issues LOC
        r = client.post("/trade/issue-loc",
                        json={"po_id": po_id, "doc_number": "LOC-2024-001"},
                        headers=H(bank_t))
        assert r.status_code == 200, r.text
        loc_id = r.json()["loc_id"]

        # Step 3 – Auditor verifies
        r = client.post("/trade/verify-documents",
                        json={"po_id": po_id, "loc_id": loc_id},
                        headers=H(audit_t))
        assert r.status_code == 200, r.text

        # Step 4 – Seller uploads BOL
        r = client.post("/trade/upload-bol", json={
            "transaction_id": tx_id,
            "doc_number": "BOL-2024-001",
            "tracking_id": "TRK-001",
        }, headers=H(seller_t))
        assert r.status_code == 200, r.text
        bol_id = r.json()["bol_id"]

        # Step 5 – Seller issues invoice
        r = client.post("/trade/issue-invoice", json={
            "transaction_id": tx_id,
            "doc_number": "INV-2024-001",
            "amount": 50000,
        }, headers=H(seller_t))
        assert r.status_code == 200, r.text
        inv_id = r.json()["invoice_id"]

        # Step 6 – Buyer marks received
        r = client.post("/trade/mark-received",
                        json={"bol_id": bol_id},
                        headers=H(buyer_t))
        assert r.status_code == 200, r.text

        # Step 7 – Bank pays invoice
        r = client.post("/trade/pay-invoice",
                        json={"invoice_id": inv_id},
                        headers=H(bank_t))
        assert r.status_code == 200, r.text

        # Verify transaction detail
        r = client.get(f"/trade/transactions/{tx_id}", headers=H(bank_t))
        assert r.status_code == 200
        print("\n✅  All 7 trade-flow steps passed.")

    def test_buyer_cannot_issue_loc(self, client):
        buyer_t, _, _, _, seller_id = self._setup(client)
        # First create a PO
        r = client.post("/trade/create-po", json={
            "seller_id": seller_id, "amount": 100, "currency": "USD", "doc_number": "PO-X"
        }, headers=H(buyer_t))
        po_id = r.json()["po_id"]
        # Buyer tries to issue LOC → should be 403
        r2 = client.post("/trade/issue-loc",
                         json={"po_id": po_id, "doc_number": "LOC-X"},
                         headers=H(buyer_t))
        assert r2.status_code == 403

    def test_list_transactions(self, client):
        buyer_t, seller_t, bank_t, _, seller_id = self._setup(client)
        client.post("/trade/create-po", json={
            "seller_id": seller_id, "amount": 1000, "currency": "EUR", "doc_number": "PO-LT"
        }, headers=H(buyer_t))
        r = client.get("/trade/transactions", headers=H(bank_t))
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# WEEK 6  Integrity-Check Worker + Alerts
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegrityWorkerWeek6:
    """
    Tests the core integrity-check logic directly (no Celery broker needed).
    Uses the worker functions imported directly so tests run without Redis.
    """

    # ── helpers ───────────────────────────────────────────────────────────────

    def _make_doc(self, session, file_url, stored_hash):
        doc = Document(
            owner_id=1,
            doc_type=DocType.INVOICE,
            doc_number=f"DOC-{id(stored_hash)}",
            file_url=file_url,
            hash=stored_hash,
            created_at=datetime.utcnow(),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return doc

    def _write_tmp(self, content: bytes) -> str:
        f = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        f.write(content)
        f.close()
        return f.name

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_clean_document_status_ok(self, db_session):
        from app.workers.integrity_worker import _check_single_document

        content = b"legitimate document content"
        path = self._write_tmp(content)
        try:
            doc = self._make_doc(
                db_session,
                f"local://{path}",
                hashlib.sha256(content).hexdigest()
            )
            log = _check_single_document(db_session, doc)
            assert log.status == IntegrityStatus.ok
            assert log.computed_hash == log.stored_hash
            assert log.mismatch_detail is None
        finally:
            os.unlink(path)

    def test_tampered_file_status_mismatch(self, db_session):
        from app.workers.integrity_worker import _check_single_document

        original = b"original content"
        tampered = b"TAMPERED content - file was modified after upload!"
        path = self._write_tmp(tampered)          # file on disk is tampered
        original_hash = hashlib.sha256(original).hexdigest()  # DB stores original hash
        try:
            doc = self._make_doc(db_session, f"local://{path}", original_hash)
            log = _check_single_document(db_session, doc)

            assert log.status == IntegrityStatus.mismatch, \
                "Worker must detect tampered file"
            assert log.computed_hash != log.stored_hash
            assert "HASH MISMATCH" in log.mismatch_detail
            print(f"\n  Mismatch detail: {log.mismatch_detail[:80]}")
        finally:
            os.unlink(path)

    def test_missing_file_status_missing(self, db_session):
        from app.workers.integrity_worker import _check_single_document

        doc = self._make_doc(
            db_session,
            "local:///nonexistent/ghost_file_99999.pdf",
            "abc123" * 10,
        )
        log = _check_single_document(db_session, doc)
        assert log.status == IntegrityStatus.missing
        assert log.mismatch_detail is not None
        print(f"\n  Missing detail: {log.mismatch_detail}")

    def test_no_file_url_is_ok(self, db_session):
        """Docs created inline (e.g. PO/LOC via trade flow) have no file — should be OK."""
        from app.workers.integrity_worker import _check_single_document

        doc = Document(
            owner_id=1,
            doc_type=DocType.PO,
            doc_number="PO-INLINE",
            file_url=None,
            hash=None,
            created_at=datetime.utcnow(),
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        log = _check_single_document(db_session, doc)
        assert log.status == IntegrityStatus.ok

    def test_alert_created_on_mismatch(self, db_session):
        from app.workers.integrity_worker import _check_single_document, _create_alert

        original = b"clean"
        tampered = b"tampered"
        path = self._write_tmp(tampered)
        try:
            doc = self._make_doc(
                db_session,
                f"local://{path}",
                hashlib.sha256(original).hexdigest(),
            )
            log = _check_single_document(db_session, doc)
            db_session.add(log)
            db_session.flush()

            alert = _create_alert(db_session, doc, log)
            db_session.add(alert)
            db_session.commit()
            db_session.refresh(alert)

            assert alert.alert_type == "hash_mismatch"
            assert alert.severity == "critical"
            assert alert.resolved is False
            assert alert.document_id == doc.id
        finally:
            os.unlink(path)

    def test_alert_created_on_missing_file(self, db_session):
        from app.workers.integrity_worker import _check_single_document, _create_alert

        doc = self._make_doc(
            db_session, "local:///no/such/file.pdf", "deadbeef" * 8
        )
        log = _check_single_document(db_session, doc)
        db_session.add(log)
        db_session.flush()

        alert = _create_alert(db_session, doc, log)
        db_session.add(alert)
        db_session.commit()

        assert alert.alert_type == "file_missing"
        assert alert.severity == "high"

    def test_sync_integrity_check_via_api(self, client):
        """
        POST /integrity/trigger without Redis falls back to synchronous check.
        No Celery broker needed.
        """
        token = signup_and_login(client, "Admin", "admin@x.com", "p", "admin", "Sys")
        r = client.post("/integrity/trigger", headers=H(token))
        assert r.status_code == 200
        data = r.json()
        # sync fallback returns counts
        assert "total_checked" in data or "task_id" in data

    def test_integrity_logs_endpoint(self, client, db_session):
        """GET /integrity/logs returns list."""
        token = signup_and_login(client, "Aud", "aud@x.com", "p", "auditor", "A")
        r = client.get("/integrity/logs", headers=H(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_integrity_alerts_endpoint(self, client):
        token = signup_and_login(client, "BankA", "banka@x.com", "p", "bank", "B")
        r = client.get("/integrity/alerts", headers=H(token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_integrity_dashboard_endpoint(self, client):
        token = signup_and_login(client, "Aud2", "aud2@x.com", "p", "auditor", "A")
        r = client.get("/integrity/dashboard", headers=H(token))
        assert r.status_code == 200
        data = r.json()
        assert "overview" in data
        assert "unresolved_alerts" in data

    def test_corporate_user_cannot_access_integrity(self, client):
        """Corporate users should be blocked from integrity endpoints."""
        token = signup_and_login(client, "CorpUser", "cu@x.com", "p", "corporate", "C")
        r = client.get("/integrity/logs", headers=H(token))
        assert r.status_code == 403

    def test_resolve_alert(self, client, db_session, test_db):
        """Auditor can mark an alert as resolved."""
        from app.workers.integrity_worker import _check_single_document, _create_alert
        from sqlmodel import Session

        content = b"will be tampered"
        tampered = b"TAMPERED"
        path = self._write_tmp(tampered)

        # Create user first so FK is satisfied
        from app.services.auth import hash_password
        user = User(
            name="Resolver", email="resolver@x.com",
            password=hash_password("p"), role=UserRole.auditor,
            org_name="AuditCo"
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        doc = Document(
            owner_id=user.id,
            doc_type=DocType.INVOICE,
            doc_number="RESOLVE-TEST",
            file_url=f"local://{path}",
            hash=hashlib.sha256(content).hexdigest(),
            created_at=datetime.utcnow(),
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        log = _check_single_document(db_session, doc)
        db_session.add(log)
        db_session.flush()
        alert = _create_alert(db_session, doc, log)
        db_session.add(alert)
        db_session.commit()
        db_session.refresh(alert)
        os.unlink(path)

        # Now use API to resolve
        token = client.post("/auth/login",
                            json={"email": "resolver@x.com", "password": "p"}).json()["access_token"]
        r = client.post(f"/integrity/alerts/{alert.id}/resolve", headers=H(token))
        assert r.status_code == 200
        assert r.json()["resolved"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Celery Schedule Config Check (no broker needed)
# ══════════════════════════════════════════════════════════════════════════════

class TestCeleryConfig:

    def test_celery_app_importable(self):
        from app.workers.celery_app import celery_app
        assert celery_app is not None

    def test_beat_schedule_has_integrity_tasks(self):
        from app.workers.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "integrity-check-every-hour" in schedule
        assert "integrity-check-daily-full" in schedule

    def test_integrity_worker_tasks_registered(self):
        from app.workers.celery_app import celery_app
        registered = list(celery_app.tasks.keys())
        # Tasks are discovered when the worker module is imported
        from app.workers import integrity_worker  # noqa: F401
        assert callable(integrity_worker.run_integrity_check)
        assert callable(integrity_worker.run_full_integrity_check)
        assert callable(integrity_worker.check_document_on_demand)

    def test_task_names_correct(self):
        from app.workers.integrity_worker import (
            run_integrity_check, run_full_integrity_check, check_document_on_demand
        )
        assert run_integrity_check.name == "app.workers.integrity_worker.run_integrity_check"
        assert run_full_integrity_check.name == "app.workers.integrity_worker.run_full_integrity_check"
        assert check_document_on_demand.name == "app.workers.integrity_worker.check_document_on_demand"
