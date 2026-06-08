#!/usr/bin/env python3
"""
RPA 任务监控脚本
检测超时的 RPA 任务，输出 JSON 告警信息。
供 Hermes cron 或手动调用。

用法:
  python scripts/rpa_monitor.py [--db sqlite:///./smart_tax.db] [--timeout-min 30]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# 确保 backend/ 在 Python 搜索路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def check_rpa_tasks(database_url: str, timeout_minutes: int = 30) -> dict:
    """检查超时 RPA 任务，返回告警汇总"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        from app.models.rpa_task import RPATask

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale = (
            session.query(RPATask)
            .filter(
                RPATask.status.in_(["pending", "running"]),
                RPATask.created_at < cutoff,
            )
            .order_by(RPATask.created_at.asc())
            .all()
        )

        alerts = []
        for task in stale:
            age_min = int((datetime.now(timezone.utc) - task.created_at).total_seconds() / 60)
            alerts.append({
                "task_id": task.id,
                "type": task.task_type,
                "status": task.status,
                "age_minutes": age_min,
                "created_at": task.created_at.isoformat(),
            })

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_stale": len(alerts),
            "timeout_threshold_min": timeout_minutes,
            "alerts": alerts,
            "severity": "critical" if len(alerts) > 3 else ("warning" if alerts else "ok"),
        }

        return summary

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="RPA 任务监控")
    parser.add_argument("--db", default="sqlite:///./backend/smart_tax.db", help="数据库连接 URL")
    parser.add_argument("--timeout-min", type=int, default=30, help="超时阈值(分钟)")
    parser.add_argument("--json", action="store_true", help="纯 JSON 输出(供程序消费)")
    args = parser.parse_args()

    result = check_rpa_tasks(args.db, args.timeout_min)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        emoji = {"ok": "✓", "warning": "⚠️", "critical": "🚨"}
        print(f"{emoji.get(result['severity'], '?')} RPA 任务监控 超时>{args.timeout_min}分钟")
        print(f"   异常任务: {result['total_stale']} 个 | {result['severity']}")
        for a in result["alerts"]:
            print(f"   - {a['task_id'][:8]}... {a['type']} {a['status']} 已{a['age_minutes']}分钟")

    sys.exit(1 if result["severity"] == "critical" else 0)


if __name__ == "__main__":
    main()
