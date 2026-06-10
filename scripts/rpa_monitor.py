"""RPA Task Monitor — detect stale tasks running >30 minutes"""
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db import SessionLocal
from app.models.rpa_task import RPATask

STALE_THRESHOLD_MINUTES = 30

def main():
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)
        stale = (
            db.query(RPATask)
            .filter(
                RPATask.status.in_(["processing", "assigned"]),
                RPATask.updated_at < cutoff,
            )
            .all()
        )
        if not stale:
            print("[RPA Monitor] OK — no stale tasks detected")
            return 0

        print(f"[RPA Monitor] ALERT — {len(stale)} stale task(s) detected:")
        for t in stale:
            duration = datetime.now(timezone.utc) - t.updated_at
            minutes = int(duration.total_seconds() / 60)
            print(f"  ⚠  Task {t.id[:12]} | type={t.task_type} | status={t.status} | stale_for={minutes}min | client={t.client_id or 'N/A'} | error={t.error_message or 'none'}")
        return len(stale)
    except Exception as e:
        print(f"[RPA Monitor] ERROR — {e}")
        return 1
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())
