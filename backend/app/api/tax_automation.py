"""自动申报 API — 基于 Playwright，零成本替代商用 RPA"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.filing import TaxFiling
from app.services.tax_service import preview_filing
from app.services.tax_automation import TaxAutomationEngine, TAX_BUREAU_CONFIGS
from app.services.auth import require_modify
from datetime import datetime

router = APIRouter()


@router.post("/file")
async def auto_file_tax(
    filing_id: str = Query(...),
    profile: str = Query("generic"),
    headless: bool = Query(True),
    db: Session = Depends(get_db),
    _=Depends(require_modify),
):
    """
    自动申报：用 Playwright 打开电子税务局，自动登录+填表+提交

    需要先安装: pip install playwright && playwright install chromium

    Args:
        filing_id: 申报记录 ID
        profile: 省份配置 (beijing/shanghai/guangdong/generic)
        headless: 是否无头模式（true=后台静默, false=显示浏览器便于调试）
    """
    filing = db.query(TaxFiling).filter(TaxFiling.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="申报记录不存在")

    if filing.status in ("submitted", "success"):
        raise HTTPException(status_code=400, detail=f"申报状态为 {filing.status}，不可重复申报")

    # 获取申报数据
    try:
        tax_data = json.loads(filing.filing_result) if filing.filing_result else {}
    except (json.JSONDecodeError, TypeError):
        # 重新计算
        tax_data = preview_filing(db, filing.tax_type, filing.period)

    if not tax_data:
        raise HTTPException(status_code=400, detail="无法获取申报数据")

    # 从系统配置读登录凭据（实际应加密存储）
    from app.models.system_config import SystemConfig
    creds = {}
    cred_cfg = db.query(SystemConfig).filter(SystemConfig.config_key == "tax_bureau_credentials").first()
    if cred_cfg:
        try:
            creds = json.loads(cred_cfg.config_value)
        except (json.JSONDecodeError, TypeError):
            pass

    if not creds.get("username") or not creds.get("password"):
        return {
            "success": False,
            "message": "未配置电子税务局登录凭据。请在系统设置中配置 tax_bureau_credentials",
            "suggestion": "在系统设置 → RPA 配置中添加: {\"username\": \"社会信用代码\", \"password\": \"电子税务局密码\"}",
        }

    # 执行自动申报
    engine = TaxAutomationEngine(profile=profile, headless=headless)
    result = await engine.run_filing(
        tax_type=filing.tax_type,
        period=filing.period,
        tax_data=tax_data,
        credentials=creds,
    )

    # 更新申报记录
    if result.success:
        filing.status = "submitted"
        filing.filed_at = datetime.now()
        filing.review_comment = f"Playwright 自动申报 | {profile} | {result.transaction_id}"
    else:
        filing.review_comment = f"自动申报失败: {result.message}"

    db.commit()

    return {
        "success": result.success,
        "message": result.message,
        "transaction_id": result.transaction_id,
        "screenshots": result.screenshot_paths,
        "tax_type": filing.tax_type,
        "period": filing.period,
    }


@router.get("/profiles")
def list_profiles():
    """列出支持的省份配置"""
    return {
        "profiles": [
            {"key": k, "name": v["name"], "configured": bool(v["login_url"])}
            for k, v in TAX_BUREAU_CONFIGS.items()
        ],
        "hint": "使用 generic 模板需自行填写选择器。在 TAX_BUREAU_CONFIGS 中添加新省份配置即可扩展。",
    }


@router.get("/screenshot/{filename}")
def get_screenshot(filename: str):
    """获取申报截图"""
    import glob
    from pathlib import Path
    for path in Path("uploads/tax_screenshots").glob(f"*{filename}*"):
        return FileResponse(str(path))
    raise HTTPException(status_code=404, detail="截图不存在")
