"""换机助手 API — 数据一键迁移"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.services.auth import get_current_user, require_admin
from app.services import migration_service as mig

router = APIRouter()


class ImportConfirmRequest(BaseModel):
    conflict_strategy: str = "skip"  # skip / update / overwrite


@router.get("/export")
def export_data(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """导出全部业务数据为 Excel"""
    output = mig.export_all(db)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=smart_tax_export.xlsx"},
    )


@router.get("/export-full")
def export_full_dump(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """导出完整数据为 JSON（用于完整迁移）"""
    data = mig.export_full_dump(db)
    return data


@router.get("/template")
def download_template():
    """下载导入模板 Excel"""
    output = mig.generate_template()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=smart_tax_import_template.xlsx"},
    )


@router.post("/preview")
def preview_upload(
    file: UploadFile = File(...),
    _=Depends(require_admin),
):
    """上传文件并预览导入数据"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择文件")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("xlsx", "xls", "json"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls / .json 格式")

    content = file.file.read()

    if ext == "json":
        import json
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="JSON 格式无效")
        issues = mig.validate_dump(data)
        counts = data.get("counts", {})
        total = sum(counts.values()) if counts else sum(len(v) if isinstance(v, list) else 0 for v in data.values())
        return {
            "format": "json",
            "version": data.get("version", "unknown"),
            "exported_at": data.get("exported_at", ""),
            "counts": counts,
            "issues": issues,
            "total_rows": total,
        }
    else:
        preview = mig.preview_import(content)
        preview["format"] = "excel"
        preview["filename"] = file.filename
        return preview


@router.post("/import")
def execute_import(
    file: UploadFile = File(...),
    conflict_strategy: str = Query("skip", description="skip / update / overwrite"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """执行数据导入"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择文件")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("xlsx", "xls", "json"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls / .json 格式")

    if conflict_strategy not in ("skip", "update", "overwrite"):
        raise HTTPException(status_code=400, detail="conflict_strategy 仅支持 skip / update / overwrite")

    content = file.file.read()

    try:
        if ext == "json":
            import json
            data = json.loads(content)
            issues = mig.validate_dump(data)
            if issues:
                raise HTTPException(status_code=400, detail=f"数据校验失败: {'; '.join(issues)}")
            report = mig.import_full_dump(db, data, conflict_strategy)
        else:
            report = mig.execute_import(db, content, conflict_strategy)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "format": ext,
        "strategy": conflict_strategy,
        "report": report,
    }


@router.post("/auto-yqy")
def auto_migrate_yqy(
    username: str = Query(..., description="亿企赢账号"),
    password: str = Query(..., description="亿企赢密码"),
    org_name: str = Query(None, description="企业名称（多企业账号需指定）"),
    conflict_strategy: str = Query("skip", description="skip / update / overwrite"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """全自动亿企赢迁移：登录 → 导出 → 下载 → 解析 → 导入"""
    import asyncio
    from app.services.yqy_scraper import YQYScraper
    from app.services import migration_service as mig

    # 1. Playwright 自动采集
    scraper = YQYScraper(headless=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            scraper.run(username=username, password=password, org_name=org_name)
        )
    finally:
        loop.close()

    if not result.success:
        raise HTTPException(
            status_code=502,
            detail=f"亿企赢数据采集失败: {'; '.join(result.errors[:3])}",
        )

    # 2. 解析并导入
    try:
        report = mig.import_yqy_files(db, result.files, conflict_strategy)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"数据导入失败: {str(e)}")

    return {
        "success": True,
        "source": "亿企赢·亿企代账",
        "strategy": conflict_strategy,
        "files_collected": len(result.files),
        "files_detail": [
            {"category": f.category, "filename": f.filename, "rows": f.row_count}
            for f in result.files
        ],
        "screenshots": result.screenshots,
        "duration_seconds": result.duration_seconds,
        "report": report,
    }
