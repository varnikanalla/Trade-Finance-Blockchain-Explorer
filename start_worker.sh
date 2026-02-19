#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# start_worker.sh  —  Start the Celery integrity-check worker (Week 6)
# Requires Redis running locally:  redis-server
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "==================================================="
echo " Trade Finance — Celery Integrity Check Worker"
echo "==================================================="
echo "  Broker : ${CELERY_BROKER_URL:-redis://localhost:6379/0}"
echo "  Queues : integrity, default"
echo ""
echo "  Make sure Redis is running:  redis-server"
echo ""

celery -A app.workers.celery_app worker \
    --loglevel=info \
    --queues=integrity,default \
    --concurrency=2
