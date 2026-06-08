import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.qr_trace import QRTrace
from app.services.qr_service import get_trace_chain, get_full_chain_from_qr, generate_qr

router = APIRouter()


@router.get("/trace/{target_type}/{target_id}")
def trace_query(target_type: str, target_id: str, db: Session = Depends(get_db)):
    """查询某个目标实体的完整追溯链"""
    chain = get_trace_chain(db, target_type, target_id)

    if not chain:
        return {"target_type": target_type, "target_id": target_id, "chain": [], "message": "未找到追溯记录"}

    return {
        "target_type": target_type,
        "target_id": target_id,
        "chain_length": len(chain),
        "chain": chain,
    }


@router.get("/scan/{qr_id}")
def scan_qr(qr_id: str, db: Session = Depends(get_db)):
    """扫码后查看全链路追溯（双向展开）"""
    chain = get_full_chain_from_qr(db, qr_id)

    if not chain:
        raise HTTPException(status_code=404, detail="QR 码未找到")

    # 获取目标详情
    qr = db.query(QRTrace).filter(QRTrace.id == qr_id).first()

    return {
        "qr_id": qr_id,
        "scan_time": None,  # 后续可记录扫码日志
        "chain": chain,
        "message": f"追溯链共 {len(chain)} 个环节",
    }


@router.get("/scan/{qr_id}/page", response_class=HTMLResponse)
def scan_qr_page(qr_id: str, db: Session = Depends(get_db)):
    """扫码后展示的可视化追溯页面"""
    chain = get_full_chain_from_qr(db, qr_id)
    qr = db.query(QRTrace).filter(QRTrace.id == qr_id).first()

    stage_names = {
        "ingest": "📥 原始凭证入库",
        "ai_voucher": "🤖 AI 生成凭证",
        "confirm": "✅ 会计复核确认",
        "file_tax": "🏦 RPA 纳税申报",
        "report": "📊 财务报表更新",
    }

    chain_html = ""
    for i, item in enumerate(chain):
        stage_label = stage_names.get(item.get("stage", ""), item.get("stage", ""))
        chain_html += f"""
        <div style="display:flex;align-items:center;margin-bottom:16px;padding:12px;background:#f6ffed;border-radius:8px;border-left:4px solid #52c41a">
            <span style="font-size:24px;margin-right:12px">{i+1}️⃣</span>
            <div>
                <strong>{stage_label}</strong>
                <div style="color:#666;font-size:12px">{item.get('created_at', '')}</div>
                <div style="font-size:12px">目标: {item.get('target_type', '')}/{item.get('target_id', '')}</div>
            </div>
        </div>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>凭证追溯 - 智能财税系统</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f0f2f5; }}
        .card {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        h2 {{ text-align: center; color: #1677ff; margin-bottom: 4px; }}
        .subtitle {{ text-align: center; color: #999; font-size: 13px; margin-bottom: 20px; }}
    </style></head>
    <body>
        <div class="card">
            <h2>📋 凭证全链路追溯</h2>
            <div class="subtitle">QR ID: {qr_id}</div>
            {chain_html}
            <div style="text-align:center;color:#999;font-size:12px;margin-top:16px">
                扫描任一环节 QR 码，可查看完整流转时间线<br>
                智能财税系统 — 全流程可追溯
            </div>
        </div>
    </body>
    </html>"""

    return HTMLResponse(content=html)


@router.post("/batch-export")
def batch_export_qr(target_ids: list[str], target_type: str, db: Session = Depends(get_db)):
    """批量导出 QR 码标签（返回下载链接）"""
    if not target_ids:
        raise HTTPException(status_code=400, detail="请提供目标 ID 列表")

    qr_urls = []
    for tid in target_ids:
        traces = (
            db.query(QRTrace)
            .filter(QRTrace.target_type == target_type, QRTrace.target_id == tid)
            .all()
        )
        for t in traces:
            if t.scan_url:
                qr_urls.append({
                    "qr_id": t.id,
                    "target_id": tid,
                    "stage": t.stage,
                    "scan_url": t.scan_url,
                })

    return {
        "total": len(qr_urls),
        "items": qr_urls,
        "message": "批量导出完成，请使用 scan_url 生成 QR 标签打印",
    }
