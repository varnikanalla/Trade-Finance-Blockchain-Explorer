from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlmodel import Session, select
import shutil, os
from datetime import datetime

from app.database import engine
from app.models import (
    Document,
    LedgerEntry,
    LedgerAction,
    DocumentType
)


router = APIRouter(prefix="/documents", tags=["Documents"])




@router.post("/upload")
def upload_document(
    doc_number: str = Form(...),
    doc_type: DocumentType = Form(...),
    seller_id: int = Form(...),
    file: UploadFile = File(...),
):
    try:
        os.makedirs("files", exist_ok=True)
        file_path = f"files/{file.filename}"

        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        with Session(engine) as session:
            doc = Document(
                doc_number=doc_number,
                doc_type=doc_type,
                owner_id=1,  # demo buyer
                file_url=file_path,
                created_at=datetime.utcnow()
            )
            session.add(doc)
            session.commit()
            session.refresh(doc)

            ledger = LedgerEntry(
                doc_id=doc.id,
                actor_id=1,
                action=LedgerAction.ISSUED,
                extra_data=f"seller_id={seller_id}",
                timestamp=datetime.utcnow()
            )
            session.add(ledger)
            session.commit()

        return {"message": "Document uploaded successfully", "doc_id": doc.id}

    except Exception as e:
        print("UPLOAD ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))



# ---------- DOCUMENT DETAILS ----------
@router.get("/{doc_id}")
def get_document(doc_id: int):
    with Session(engine) as session:
        doc = session.get(Document, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        ledger = session.exec(
            select(LedgerEntry).where(LedgerEntry.doc_id == doc_id)
        ).all()

    return {
        "id": doc.id,
        "doc_number": doc.doc_number,
        "doc_type": doc.doc_type,
        "file_url": doc.file_url,
        "ledger": ledger,
    }


# ---------- PERFORM ACTION ----------
@router.post("/action")
def perform_action(
    doc_id: int = Form(...),
    action: LedgerAction = Form(...),
):
    with Session(engine) as session:
        doc = session.get(Document, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        entry = LedgerEntry(
            doc_id=doc_id,
            actor_id=1,  # demo user
            action=action,
            timestamp=datetime.utcnow()
        )
        session.add(entry)
        session.commit()

    return {"message": f"Action {action} recorded"}
