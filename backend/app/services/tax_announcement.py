"""抓取国家税务总局最新法规公告"""
import re
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from app.models.tax_announcement import TaxAnnouncement

# 国家税务总局法规公告列表页
SOURCE_URLS = [
    "https://www.chinatax.gov.cn/chinatax/n810341/n810755/index.html",   # 最新文件
    "https://www.chinatax.gov.cn/chinatax/n810341/n810825/index.html",   # 政策解读
]


def fetch_announcements() -> list[dict]:
    """从国家税务总局抓取最新公告"""
    items = []
    for base_url in SOURCE_URLS:
        try:
            resp = httpx.get(base_url, timeout=15, follow_redirects=True, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            # 查找公告列表项（不同页面结构略有差异，先按常见选择器匹配）
            for li in soup.select("ul li, .news-list li, .list li"):
                link = li.select_one("a[href]")
                date_span = li.select_one("span, .date, .time")
                if not link:
                    continue

                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not title or len(title) < 6:
                    continue

                # 补齐相对路径
                if href.startswith("/"):
                    href = "https://www.chinatax.gov.cn" + href
                elif href.startswith("./"):
                    href = base_url.rsplit("/", 1)[0] + "/" + href[2:]

                date_str = ""
                if date_span:
                    date_str = date_span.get_text(strip=True)

                items.append({
                    "title": title,
                    "url": href,
                    "pub_date": date_str,
                    "source": "国家税务总局",
                })

                if len(items) >= 20:
                    break
            if items:
                break
        except Exception:
            continue

    return items


def parse_chinese_date(text: str):
    """解析 2026-06-08 或 2026年06月08日 格式的日期"""
    for pattern in [r"(\d{4})-(\d{2})-(\d{2})", r"(\d{4})年(\d{1,2})月(\d{1,2})日"]:
        m = re.search(pattern, text)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def refresh_announcements(db: Session) -> int:
    """抓取并存入数据库，返回新增数量"""
    items = fetch_announcements()
    if not items:
        # 没抓到新数据，返回已有数量
        return db.query(TaxAnnouncement).count()

    saved = 0
    for item in items:
        exists = db.query(TaxAnnouncement).filter(TaxAnnouncement.url == item["url"]).first()
        if exists:
            continue
        parsed = parse_chinese_date(item.get("pub_date", ""))
        ann = TaxAnnouncement(
            title=item["title"],
            url=item["url"],
            source=item.get("source", "国家税务总局"),
            pub_date=item.get("pub_date", ""),
            pub_date_parsed=parsed,
        )
        db.add(ann)
        saved += 1

    db.commit()

    # 清理超过 90 天的旧公告
    cutoff = datetime.now() - timedelta(days=90)
    db.query(TaxAnnouncement).filter(
        TaxAnnouncement.pub_date_parsed != None,
        TaxAnnouncement.pub_date_parsed < cutoff,
    ).delete()
    db.commit()

    return saved


def get_latest_announcements(db: Session, limit: int = 10) -> list[dict]:
    """获取最新公告"""
    items = (
        db.query(TaxAnnouncement)
        .order_by(TaxAnnouncement.pub_date_parsed.desc().nullslast(), TaxAnnouncement.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": item.id,
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "pub_date": item.pub_date,
        }
        for item in items
    ]
