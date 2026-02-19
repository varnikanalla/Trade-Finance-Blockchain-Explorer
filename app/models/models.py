from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum
import json


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    bank = "bank"
    corporate = "corporate"
    auditor = "auditor"
    admin = "admin"


class DocType(str, Enum):
    LOC = "LOC"
    INVOICE = "INVOICE"
    BILL_OF_LADING = "BILL_OF_LADING"
    PO = "PO"
    COO = "COO"
    INSURANCE_CERT = "INSURANCE_CERT"


class LedgerAction(str, Enum):
    ISSUED = "ISSUED"
    AMENDED = "AMENDED"
    SHIPPED = "SHIPPED"
    RECEIVED = "RECEIVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    VERIFIED = "VERIFIED"


class TransactionStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    disputed = "disputed"


class IntegrityStatus(str, Enum):
    ok = "ok"
    mismatch = "mismatch"
    missing = "missing"


# ─── Users ────────────────────────────────────────────────────────────────────

class UserBase(SQLModel):
    name: str
    email: str
    role: UserRole
    org_name: str


class User(UserBase, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    documents: List["Document"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"foreign_keys": "[Document.owner_id]"}
    )
    ledger_entries: List["LedgerEntry"] = Relationship(
        back_populates="actor",
        sa_relationship_kwargs={"foreign_keys": "[LedgerEntry.actor_id]"}
    )
    risk_scores: List["RiskScore"] = Relationship(back_populates="user")
    audit_logs: List["AuditLog"] = Relationship(back_populates="admin")


# ─── Documents ────────────────────────────────────────────────────────────────

class DocumentBase(SQLModel):
    doc_type: DocType
    doc_number: str
    issued_at: Optional[datetime] = None


class Document(DocumentBase, table=True):
    __tablename__ = "documents"
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="users.id")
    file_url: Optional[str] = None
    hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    owner: Optional[User] = Relationship(
        back_populates="documents",
        sa_relationship_kwargs={"foreign_keys": "[Document.owner_id]"}
    )
    ledger_entries: List["LedgerEntry"] = Relationship(back_populates="document")
    integrity_logs: List["IntegrityLog"] = Relationship(back_populates="document")


# ─── Ledger Entries ───────────────────────────────────────────────────────────

class LedgerEntry(SQLModel, table=True):
    __tablename__ = "ledger_entries"
    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id")
    action: LedgerAction
    actor_id: int = Field(foreign_key="users.id")
    metadata_json: Optional[str] = Field(default=None)  # JSON string (JSONB in PG)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    document: Optional[Document] = Relationship(back_populates="ledger_entries")
    actor: Optional[User] = Relationship(
        back_populates="ledger_entries",
        sa_relationship_kwargs={"foreign_keys": "[LedgerEntry.actor_id]"}
    )

    @property
    def metadata(self):
        if self.metadata_json:
            return json.loads(self.metadata_json)
        return {}

    @metadata.setter
    def metadata(self, value: dict):
        self.metadata_json = json.dumps(value) if value else None


# ─── Trade Transactions ───────────────────────────────────────────────────────

class TradeTransaction(SQLModel, table=True):
    __tablename__ = "trade_transactions"
    id: Optional[int] = Field(default=None, primary_key=True)
    buyer_id: int = Field(foreign_key="users.id")
    seller_id: int = Field(foreign_key="users.id")
    amount: float
    currency: str = Field(max_length=3)
    status: TransactionStatus = Field(default=TransactionStatus.pending)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Risk Scores ──────────────────────────────────────────────────────────────

class RiskScore(SQLModel, table=True):
    __tablename__ = "risk_scores"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    score: float
    rationale: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(back_populates="risk_scores")


# ─── Audit Logs ───────────────────────────────────────────────────────────────

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    admin_id: int = Field(foreign_key="users.id")
    action: str
    target_type: str
    target_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    admin: Optional[User] = Relationship(back_populates="audit_logs")


# ─── Integrity Logs (Week 6 - New) ────────────────────────────────────────────

class IntegrityLog(SQLModel, table=True):
    """Records results of each scheduled integrity check run."""
    __tablename__ = "integrity_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id")
    status: IntegrityStatus
    stored_hash: Optional[str] = None    # Hash stored in DB
    computed_hash: Optional[str] = None  # Hash recomputed from file
    mismatch_detail: Optional[str] = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    alert_sent: bool = Field(default=False)

    document: Optional[Document] = Relationship(back_populates="integrity_logs")


# ─── Integrity Alerts (Week 6 - New) ──────────────────────────────────────────

class IntegrityAlert(SQLModel, table=True):
    """Stores mismatch alerts for admin/auditor review."""
    __tablename__ = "integrity_alerts"
    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id")
    alert_type: str  # "hash_mismatch", "file_missing", "chain_broken"
    detail: str
    severity: str = Field(default="high")  # low, medium, high, critical
    resolved: bool = Field(default=False)
    resolved_by: Optional[int] = Field(default=None, foreign_key="users.id")
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
