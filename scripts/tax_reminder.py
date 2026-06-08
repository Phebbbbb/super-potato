#!/usr/bin/env python3
"""
税务申报日历提醒脚本
查询即将到期的申报任务，输出提醒列表。
供 Hermes cron 调用 — 可推送 Slack / Telegram / 钉钉。

用法:
  python scripts/tax_reminder.py [--db sqlite:///./smart_tax.db] [--days 3]
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, timedelta, timezone

# 确保 backend/ 在 Python 搜索路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# 中国税务申报截止日参考（月报简化版，实际以当地国税通知为准）
# 增值税: 次月 15 日  |  企业所得税季报: 次季首月 15 日
def get_due_date(period: str, tax_type: str) -> date:
    """根据所属期推算申报截止日（简化版）"""
    try:
        y, m = map(int, period.split("-"))
    except (ValueError, AttributeError):
        return date.today() + timedelta(days=99)

    # 次月 15 日
    if m == 12:
        return date(y + 1, 1, 15)
    return date(y, m + 1, 15)


def check_upcoming_deadlines(database_url: str, days_ahead: int = 3) -> dict:
    """查询即将到期的申报任务"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        from app.models.filing import TaxFiling

        today = date.today()
        deadline = today + timedelta(days=days_ahead)

        # 查找待处理的申报
        pending = (
            session.query(TaxFiling)
            .filter(TaxFiling.status.in_(["pending", "draft"]))
            .order_by(TaxFiling.period.asc())
            .all()
        )

        reminders = []
        for f in pending:
            due = get_due_date(f.period, f.tax_type)
            days_left = (due - today).days

            if days_left <= days_ahead:
                urgency = "overdue" if days_left < 0 else ("today" if days_left == 0 else "upcoming")
                reminders.append({
                    "filing_id": f.id,
                    "tax_type": f.tax_type,
                    "period": f.period,
                    "status": f.status,
                    "due_date": due.isoformat(),
                    "days_left": days_left,
                    "urgency": urgency,
                })

        reminders.sort(key=lambda r: r["days_left"])

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "check_date": today.isoformat(),
            "look_ahead_days": days_ahead,
            "total_reminders": len(reminders),
            "reminders": reminders,
            "severity": "critical" if any(r["urgency"] == "overdue" for r in reminders) else (
                "warning" if reminders else "ok"
            ),
        }

        return summary

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="税务申报日历提醒")
    parser.add_argument("--db", default="sqlite:///./backend/smart_tax.db", help="数据库连接 URL")
    parser.add_argument("--days", type=int, default=3, help="提前几天开始提醒")
    parser.add_argument("--json", action="store_true", help="纯 JSON 输出")
    args = parser.parse_args()

    result = check_upcoming_deadlines(args.db, args.days)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"📅 税务日历提醒 未来{args.days}天 | {result['check_date']}")
        if not result["reminders"]:
            print("   ✓ 无即将到期的申报")
        for r in result["reminders"]:
            icon = {"overdue": "🔴", "today": "🟡", "upcoming": "🔵"}
            label = {"overdue": "已逾期", "today": "今天到期", "upcoming": "即将到期"}
            print(f"   {icon.get(r['urgency'], '?')} [{r['tax_type']}] {r['period']} {label.get(r['urgency'], '')} "
                  f"({r['due_date']} | {'逾期' if r['days_left'] < 0 else f'剩{r['days_left']}天'})")

    sys.exit(1 if result["severity"] == "critical" else 0)


if __name__ == "__main__":
    main()
