from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime
from typing import List
import json

from app.database import get_session
from app.models import (
    User, Document, LedgerEntry, TradeTransaction,
    DocType, LedgerAction, TransactionStatus
)
from app.schemas import (
    CreatePORequest, IssueLocRequest, VerifyDocumentsRequest,
    UploadBolRequest, IssueInvoiceRequest, MarkReceivedRequest,
    PayInvoiceRequest, TransactionResponse, TransactionDetailResponse,
    DocumentResponse, LedgerEntryResponse
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/trade", tags=["Trade Transactions"])


def _make_doc(owner_id, doc_type, doc_number, extra_hash=None):
    """Helper to create a document record without file upload (for in-flow docs)."""
    import hashlib
    content = f"{doc_type}:{doc_number}:{owner_id}:{datetime.utcnow().isoformat()}"
    doc_hash = extra_hash or hashlib.sha256(content.encode()).hexdigest()
    return Document(
        owner_id=owner_id,
        doc_type=doc_type,
        doc_number=doc_number,
        hash=doc_hash,
        issued_at=datetime.utcnow(),
    )


def _add_ledger(session, doc_id, action, actor_id, metadata: dict):
    entry = LedgerEntry(
        document_id=doc_id,
        action=action,
        actor_id=actor_id,
        metadata_json=json.dumps(metadata),
    )
    session.add(entry)
    return entry


# ─── Step 1: Buyer creates PO ─────────────────────────────────────────────────

@router.post("/create-po")
def create_po(
    payload: CreatePORequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "corporate":
        raise HTTPException(403, "Only corporate users can create POs")

    seller = session.get(User, payload.seller_id)
    if not seller:
        raise HTTPException(404, "Seller not found")

    # Create the PO document
    po_doc = _make_doc(current_user.id, DocType.PO, payload.doc_number)
    session.add(po_doc)
    session.flush()

    # Create transaction in pending state
    tx = TradeTransaction(
        buyer_id=current_user.id,
        seller_id=payload.seller_id,
        amount=payload.amount,
        currency=payload.currency,
        status=TransactionStatus.pending,
    )
    session.add(tx)
    session.flush()

    _add_ledger(session, po_doc.id, LedgerAction.ISSUED, current_user.id, {
        "event": "PO_CREATED",
        "transaction_id": tx.id,
        "buyer_id": current_user.id,
        "seller_id": payload.seller_id,
        "amount": payload.amount,
        "currency": payload.currency,
    })

    session.commit()
    return {"po_id": po_doc.id, "transaction_id": tx.id, "status": "pending", "message": "Purchase Order created"}


# ─── Step 2: Bank issues LOC ──────────────────────────────────────────────────

@router.post("/issue-loc")
def issue_loc(
    payload: IssueLocRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "bank":
        raise HTTPException(403, "Only bank users can issue LOCs")

    po_doc = session.get(Document, payload.po_id)
    if not po_doc or po_doc.doc_type != DocType.PO:
        raise HTTPException(404, "PO document not found")

    loc_doc = _make_doc(current_user.id, DocType.LOC, payload.doc_number)
    session.add(loc_doc)
    session.flush()

    _add_ledger(session, loc_doc.id, LedgerAction.ISSUED, current_user.id, {
        "event": "LOC_ISSUED",
        "po_id": payload.po_id,
        "bank_id": current_user.id,
    })

    session.commit()
    return {"loc_id": loc_doc.id, "message": "Letter of Credit issued"}


# ─── Step 3: Auditor verifies documents ──────────────────────────────────────

@router.post("/verify-documents")
def verify_documents(
    payload: VerifyDocumentsRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ["auditor", "bank"]:
        raise HTTPException(403, "Only auditors/banks can verify documents")

    po_doc = session.get(Document, payload.po_id)
    loc_doc = session.get(Document, payload.loc_id)

    if not po_doc:
        raise HTTPException(404, f"PO document {payload.po_id} not found")
    if not loc_doc:
        raise HTTPException(404, f"LOC document {payload.loc_id} not found")

    # Find related transaction via po ledger
    po_ledger = session.exec(
        select(LedgerEntry)
        .where(LedgerEntry.document_id == payload.po_id)
        .where(LedgerEntry.action == LedgerAction.ISSUED)
    ).first()

    if po_ledger and po_ledger.metadata:
        tx_id = po_ledger.metadata.get("transaction_id")
        if tx_id:
            tx = session.get(TradeTransaction, tx_id)
            if tx:
                tx.status = TransactionStatus.in_progress
                tx.updated_at = datetime.utcnow()
                session.add(tx)

    # Mark both documents as verified
    for doc_id in [payload.po_id, payload.loc_id]:
        _add_ledger(session, doc_id, LedgerAction.VERIFIED, current_user.id, {
            "event": "DOCUMENT_VERIFIED",
            "verified_by": current_user.id,
            "verifier_role": current_user.role,
        })

    session.commit()
    return {"message": "Documents verified. Transaction moved to in_progress."}


# ─── Step 4: Seller uploads BOL ──────────────────────────────────────────────

@router.post("/upload-bol")
def upload_bol(
    payload: UploadBolRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "corporate":
        raise HTTPException(403, "Only corporate users can upload BOL")

    tx = session.get(TradeTransaction, payload.transaction_id)
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if tx.seller_id != current_user.id:
        raise HTTPException(403, "Only the seller can upload BOL for this transaction")

    bol_doc = _make_doc(current_user.id, DocType.BILL_OF_LADING, payload.doc_number)
    session.add(bol_doc)
    session.flush()

    _add_ledger(session, bol_doc.id, LedgerAction.SHIPPED, current_user.id, {
        "event": "BOL_UPLOADED",
        "transaction_id": payload.transaction_id,
        "tracking_id": payload.tracking_id,
    })

    session.commit()
    return {"bol_id": bol_doc.id, "message": "Bill of Lading uploaded"}


# ─── Step 5: Seller issues Invoice ───────────────────────────────────────────

@router.post("/issue-invoice")
def issue_invoice(
    payload: IssueInvoiceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "corporate":
        raise HTTPException(403, "Only corporate users can issue invoices")

    tx = session.get(TradeTransaction, payload.transaction_id)
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if tx.seller_id != current_user.id:
        raise HTTPException(403, "Only the seller can issue invoices for this transaction")

    inv_doc = _make_doc(current_user.id, DocType.INVOICE, payload.doc_number)
    session.add(inv_doc)
    session.flush()

    _add_ledger(session, inv_doc.id, LedgerAction.ISSUED, current_user.id, {
        "event": "INVOICE_ISSUED",
        "transaction_id": payload.transaction_id,
        "amount": payload.amount,
    })

    session.commit()
    return {"invoice_id": inv_doc.id, "message": "Invoice issued"}


# ─── Step 6: Buyer marks BOL received ────────────────────────────────────────

@router.post("/mark-received")
def mark_received(
    payload: MarkReceivedRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "corporate":
        raise HTTPException(403, "Only corporate users can mark BOL received")

    bol_doc = session.get(Document, payload.bol_id)
    if not bol_doc or bol_doc.doc_type != DocType.BILL_OF_LADING:
        raise HTTPException(404, "BOL document not found")

    _add_ledger(session, bol_doc.id, LedgerAction.RECEIVED, current_user.id, {
        "event": "BOL_RECEIVED",
        "received_by": current_user.id,
        "received_at": datetime.utcnow().isoformat(),
    })

    session.commit()
    return {"message": "BOL marked as received"}


# ─── Step 7: Bank pays invoice ────────────────────────────────────────────────

@router.post("/pay-invoice")
def pay_invoice(
    payload: PayInvoiceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "bank":
        raise HTTPException(403, "Only bank users can pay invoices")

    inv_doc = session.get(Document, payload.invoice_id)
    if not inv_doc or inv_doc.doc_type != DocType.INVOICE:
        raise HTTPException(404, "Invoice document not found")

    # Get the ledger to find the transaction
    inv_ledger = session.exec(
        select(LedgerEntry)
        .where(LedgerEntry.document_id == payload.invoice_id)
        .where(LedgerEntry.action == LedgerAction.ISSUED)
    ).first()

    if inv_ledger and inv_ledger.metadata:
        tx_id = inv_ledger.metadata.get("transaction_id")
        if tx_id:
            tx = session.get(TradeTransaction, tx_id)
            if tx:
                tx.status = TransactionStatus.completed
                tx.updated_at = datetime.utcnow()
                session.add(tx)

    _add_ledger(session, inv_doc.id, LedgerAction.PAID, current_user.id, {
        "event": "INVOICE_PAID",
        "paid_by_bank": current_user.id,
        "paid_at": datetime.utcnow().isoformat(),
    })

    session.commit()
    return {"message": "Invoice paid. Transaction completed."}


# ─── View transaction details ─────────────────────────────────────────────────

@router.get("/transactions/{tx_id}", response_model=TransactionDetailResponse)
def get_transaction(
    tx_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    tx = session.get(TradeTransaction, tx_id)
    if not tx:
        raise HTTPException(404, "Transaction not found")

    # Find docs linked via ledger
    all_ledger = session.exec(select(LedgerEntry)).all()
    doc_ids = set()
    for entry in all_ledger:
        if entry.metadata and str(tx_id) in json.dumps(entry.metadata):
            doc_ids.add(entry.document_id)

    docs = [session.get(Document, did) for did in doc_ids if session.get(Document, did)]
    ledger_entries = session.exec(
        select(LedgerEntry).where(LedgerEntry.document_id.in_(list(doc_ids)))
        .order_by(LedgerEntry.created_at)
    ).all()

    return TransactionDetailResponse(
        transaction=TransactionResponse(
            id=tx.id,
            buyer_id=tx.buyer_id,
            seller_id=tx.seller_id,
            amount=tx.amount,
            currency=tx.currency,
            status=tx.status,
            created_at=tx.created_at,
            updated_at=tx.updated_at,
        ),
        documents=[DocumentResponse(
            id=d.id, owner_id=d.owner_id, doc_type=d.doc_type,
            doc_number=d.doc_number, file_url=d.file_url, hash=d.hash,
            issued_at=d.issued_at, created_at=d.created_at
        ) for d in docs],
        ledger_entries=[LedgerEntryResponse(
            id=e.id, document_id=e.document_id, action=e.action,
            actor_id=e.actor_id, metadata=e.metadata, created_at=e.created_at
        ) for e in ledger_entries],
    )


@router.get("/transactions", response_model=List[TransactionResponse])
def list_transactions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List trade transactions relevant to the current user."""
    query = select(TradeTransaction)
    if current_user.role == "corporate":
        query = query.where(
            (TradeTransaction.buyer_id == current_user.id) |
            (TradeTransaction.seller_id == current_user.id)
        )
    txns = session.exec(query).all()
    return [TransactionResponse(
        id=t.id, buyer_id=t.buyer_id, seller_id=t.seller_id,
        amount=t.amount, currency=t.currency, status=t.status,
        created_at=t.created_at, updated_at=t.updated_at
    ) for t in txns]
