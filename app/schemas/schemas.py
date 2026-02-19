from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Any
from datetime import datetime
from app.models import UserRole, DocType, LedgerAction, TransactionStatus, IntegrityStatus


# ─── Auth Schemas ─────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    role: UserRole
    org_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    org_name: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Document Schemas ─────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: int
    owner_id: int
    doc_type: DocType
    doc_number: str
    file_url: Optional[str]
    hash: Optional[str]
    issued_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentUploadMeta(BaseModel):
    doc_type: DocType
    doc_number: str
    issued_at: Optional[datetime] = None


# ─── Ledger Schemas ───────────────────────────────────────────────────────────

class LedgerEntryResponse(BaseModel):
    id: int
    document_id: int
    action: LedgerAction
    actor_id: int
    metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LedgerVerifyResponse(BaseModel):
    document_id: int
    doc_number: str
    doc_type: str
    stored_hash: Optional[str]
    entries: List[LedgerEntryResponse]
    is_chain_valid: bool
    tamper_detected: bool


# ─── Trade Transaction Schemas ────────────────────────────────────────────────

class CreatePORequest(BaseModel):
    seller_id: int
    amount: float
    currency: str
    doc_number: str


class IssueLocRequest(BaseModel):
    po_id: int
    doc_number: str


class VerifyDocumentsRequest(BaseModel):
    po_id: int
    loc_id: int


class UploadBolRequest(BaseModel):
    transaction_id: int
    doc_number: str
    tracking_id: Optional[str] = None


class IssueInvoiceRequest(BaseModel):
    transaction_id: int
    doc_number: str
    amount: float


class MarkReceivedRequest(BaseModel):
    bol_id: int


class PayInvoiceRequest(BaseModel):
    invoice_id: int


class TransactionResponse(BaseModel):
    id: int
    buyer_id: int
    seller_id: int
    amount: float
    currency: str
    status: TransactionStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransactionDetailResponse(BaseModel):
    transaction: TransactionResponse
    documents: List[DocumentResponse]
    ledger_entries: List[LedgerEntryResponse]


# ─── Risk Score Schemas ───────────────────────────────────────────────────────

class RiskScoreResponse(BaseModel):
    id: int
    user_id: int
    score: float
    rationale: Optional[str]
    last_updated: datetime

    class Config:
        from_attributes = True


# ─── Integrity / Week 6 Schemas ───────────────────────────────────────────────

class IntegrityLogResponse(BaseModel):
    id: int
    document_id: int
    status: IntegrityStatus
    stored_hash: Optional[str]
    computed_hash: Optional[str]
    mismatch_detail: Optional[str]
    checked_at: datetime
    alert_sent: bool

    class Config:
        from_attributes = True


class IntegrityAlertResponse(BaseModel):
    id: int
    document_id: int
    alert_type: str
    detail: str
    severity: str
    resolved: bool
    resolved_by: Optional[int]
    resolved_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class IntegrityCheckSummary(BaseModel):
    total_checked: int
    ok_count: int
    mismatch_count: int
    missing_count: int
    alerts_created: int
    run_at: datetime


class ResolveAlertRequest(BaseModel):
    alert_id: int
