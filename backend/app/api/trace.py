"""记账追溯 — 基于业务关系的线性追溯：原始凭证 → 记账凭证 → 纳税申报"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.qr_service import get_trace_chain

router = APIRouter()

STAGE_NAMES = {
    # 核心四步流程：原始凭证 → 记账凭证 → 会计复核 → 纳税申报
    "ingest": "① 原始凭证入库",
    "email_collect": "① 原始凭证入库（邮件）",
    "tax_pull": "① 原始凭证入库（税务局拉取）",
    "zip_import": "① 原始凭证入库（批量导入）",
    "ai_voucher": "② 记账凭证（AI生成）",
    "manual_voucher": "② 记账凭证（手工录入）",
    "auto_depreciation": "② 记账凭证（自动折旧）",
    "depreciation": "② 记账凭证（折旧计提）",
    "confirm": "③ 会计复核确认",
    "file_tax": "④ 纳税申报",
    "report": "⑤ 财务报表更新",
    "created": "发票创建",
    "issued": "发票开具",
    "auto_created": "发票创建（自动）",
    "auto_issued": "发票开具（自动）",
}


@router.get("/{target_type}/{target_id}")
def get_accounting_trace(target_type: str, target_id: str, db: Session = Depends(get_db)):
    """查询某个实体的完整记账追溯链"""
    chain = get_trace_chain(db, target_type, target_id)

    # enrich stage names
    for item in chain:
        item["stage_name"] = STAGE_NAMES.get(item.get("stage", ""), item.get("stage", ""))

    return {
        "target_type": target_type,
        "target_id": target_id,
        "chain_length": len(chain),
        "chain": chain,
    }
