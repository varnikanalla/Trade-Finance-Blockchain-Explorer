from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import get_session
from app.models import Document, LedgerEntry

router = APIRouter(prefix="/ui", tags=["UI"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/documents")
def list_documents(request: Request, session: Session = Depends(get_session)):
    docs = session.exec(select(Document)).all()
    return templates.TemplateResponse(
        "documents.html",
        {"request": request, "documents": docs}
    )


@router.get("/documents/{doc_id}")
def document_detail(doc_id: int, request: Request, session: Session = Depends(get_session)):
    doc = session.get(Document, doc_id)
    ledger = session.exec(
        select(LedgerEntry).where(LedgerEntry.doc_id == doc_id)
    ).all()

    return templates.TemplateResponse(
        "document_detail.html",
        {
            "request": request,
            "document": doc,
            "ledger": ledger
        }
    )


@router.get("/upload")
def upload_page(request: Request):
    return templates.TemplateResponse(
        "upload_document.html",
        {"request": request}
    )
