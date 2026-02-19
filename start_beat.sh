#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# start_beat.sh  —  Start the Celery Beat scheduler (periodic integrity checks)
# Schedule:
#   • Every hour  — incremental check (docs uploaded in last 24h)
#   • Daily 02:00 UTC — full sweep of all documents
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "==================================================="
echo " Trade Finance — Celery Beat Scheduler"
echo "==================================================="
echo "  Schedules:"
echo "    • Hourly  : incremental integrity check"
echo "    • 02:00 UTC daily : full document sweep"
echo ""

celery -A app.workers.celery_app beat \
    --loglevel=info \
    --scheduler celery.beat:PersistentScheduler \
    --schedule celerybeat-schedule
