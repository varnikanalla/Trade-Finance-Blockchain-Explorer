#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# start_api.sh  —  Start the Trade Finance FastAPI development server
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "==================================================="
echo " Trade Finance Blockchain Explorer — API Server"
echo "==================================================="

# Copy .env.example if .env doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example — please edit DATABASE_URL if needed."
fi

# Default to SQLite for quick dev start (set DATABASE_URL in .env for PostgreSQL)
export DATABASE_URL=${DATABASE_URL:-sqlite:///./trade_finance.db}

echo "  DB  : $DATABASE_URL"
echo "  Docs: http://localhost:8000/docs"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
