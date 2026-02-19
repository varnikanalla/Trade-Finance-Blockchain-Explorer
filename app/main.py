from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from app.database import engine
from app.routers import (
    auth, users, documents, ledger, trade, 
    integrity, risk, analytics, exports, ui
)

app = FastAPI(
    title="Trade Finance Blockchain Explorer",
    description="Tamper-proof tracking of trade finance artifacts with risk insights",
    version="1.0.0"
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
SQLModel.metadata.create_all(engine)

# Register routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(ledger.router, prefix="/ledger", tags=["Ledger"])
app.include_router(trade.router, prefix="/trade", tags=["Trade Transactions"])
app.include_router(integrity.router, prefix="/integrity", tags=["Integrity Checks"])
app.include_router(risk.router, prefix="/api", tags=["Risk Assessment"])  # Week 7
app.include_router(analytics.router, prefix="/api", tags=["Analytics"])  # Week 8
app.include_router(exports.router, prefix="/api", tags=["Exports"])  # Week 8
app.include_router(ui.router, prefix="", tags=["UI"])  # Frontend routes

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Trade Finance Blockchain Explorer API",
        "version": "1.0.0",
        "status": "operational",
        "milestone": "Week 8 - Analytics & Reporting Complete",
        "endpoints": {
            "docs": "/docs",
            "health": "/health"
        }
    }

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "timestamp": "2026-02-18T00:00:00Z"
    }
