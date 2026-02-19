#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# run_tests.sh  —  Run the full test suite (Weeks 1–6)
# Uses SQLite in-memory. No Redis or PostgreSQL required.
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "==================================================="
echo " Trade Finance — Test Suite (Weeks 1–6)"
echo "==================================================="

export DATABASE_URL="sqlite:///:memory:"
export USE_LOCAL_STORAGE="true"
export SECRET_KEY="test-secret-key-32chars-minimum-len"

pytest tests/ -v --tb=short "$@"
