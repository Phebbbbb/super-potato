"""RPA 数据接入服务：负责接收 RPA 推送的原始凭证数据，进行校验、去重、入库 + 自学习纠错"""
import json
import os
import base64
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.document import OriginalDocument
from app.models.rpa_task import RPATask
from app.services.self_learning import auto_correct
from app.config import settings

# 允许的文件类型
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


class IngestValidationError(Exception):
    """数据校验异常"""


def validate_document(doc: dict) -> list[str]:
    """校验单个原始凭证数据，返回错误列表"""
    errors = []

    # 文件名校验
    file_name = doc.get("file_name", "")
    if file_name:
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"不支持的文件类型: {ext}，允许: {ALLOWED_EXTENSIONS}")

    # doc_type 校验
    valid_types = {"invoice", "receipt", "bank_receipt", "contract", "tax_cert", "other"}
    if doc.get("doc_type", "") not in valid_types:
        errors.append(f"无效的凭证类型: {doc.get('doc_type')}")

    # OCR 结果基础校验
    ocr = doc.get("ocr_result") or {}
    if ocr:
        total = ocr.get("total_amount")
        excluding_tax = ocr.get("amount_excluding_tax")
        tax = ocr.get("tax_amount")

        # 金额逻辑校验：不含税金额 + 税额 ≈ 总金额（允许 0.02 误差）
        if total is not None and excluding_tax is not None and tax is not None:
            expected_total = round(excluding_tax + tax, 2)
            if abs(expected_total - total) > 0.02:
                errors.append(
                    f"金额校验不平: 不含税({excluding_tax}) + 税额({tax}) = {expected_total} ≠ 总金额({total})"
                )

        # 发票号码去重
        invoice_no = ocr.get("invoice_no")
        if invoice_no:
            pass  # 去重在 ingest 中通过 DB 查询处理

    return errors


def save_base64_file(data: str, file_name: str) -> str:
    """将 Base64 编码的文件保存到 uploads 目录，返回相对路径"""
    ext = os.path.splitext(file_name)[1].lower() or ".jpg"
    safe_name = f"{uuid.uuid4().hex}{ext}"
    rel_path = os.path.join(settings.upload_dir, safe_name)
    abs_path = os.path.join(os.getcwd(), rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(base64.b64decode(data))
    return rel_path


def check_invoice_duplicate(db: Session, client_id: str | None, invoice_code: str, invoice_no: str) -> bool:
    """检查发票是否重复 — 使用 DB 查询而非全表扫描"""
    if not invoice_no:
        return False

    # 先用 client_id + 非空 ocr_structured 缩小范围
    q = db.query(OriginalDocument).filter(
        OriginalDocument.client_id == client_id,
        OriginalDocument.ocr_structured.isnot(None),
        OriginalDocument.ocr_structured.like(f'%"{invoice_no}"%'),
    )
    if invoice_code:
        q = q.filter(OriginalDocument.ocr_structured.like(f'%"{invoice_code}"%'))

    docs = q.limit(10).all()
    for doc in docs:
        try:
            structured = json.loads(doc.ocr_structured)
        except json.JSONDecodeError:
            continue
        if isinstance(structured, dict):
            if structured.get("invoice_no") == invoice_no:
                if not invoice_code or structured.get("invoice_code") == invoice_code:
                    return True
    return False


def ingest_documents(
    db: Session,
    task_id: str | None,
    task_type: str,
    documents: list[dict],
    client_id: str | None = None,
) -> list[dict]:
    """
    核心入库方法：逐个处理 RPA 推送的原始凭证
    返回处理结果列表
    """
    results = []

    # 如果有关联 RPA 任务，更新其状态为 processing
    if task_id:
        task = db.query(RPATask).filter(RPATask.id == task_id).first()
        if task and task.status == "pending":
            task.status = "processing"

    for doc_data in documents:
        try:
            # 1. 数据校验
            errors = validate_document(doc_data)

            ocr = doc_data.get("ocr_result") or doc_data.get("ocr_structured") or {}
            invoice_code = ocr.get("invoice_code", "")
            invoice_no = ocr.get("invoice_no", "")

            if invoice_no:
                if errors:
                    pass
                if check_invoice_duplicate(db, client_id, invoice_code, invoice_no):
                    errors.append(f"发票 {invoice_code}-{invoice_no} 已存在，跳过")

            if errors:
                results.append({
                    "success": False,
                    "document_id": "",
                    "message": "; ".join(errors),
                })
                continue

            # 2. 处理文件
            file_path = None
            file_name = doc_data.get("file_name")
            file_base64 = doc_data.get("file_base64")

            if file_base64:
                file_path = save_base64_file(file_base64, file_name or "document.jpg")

            # 2.5 自学习纠错: 对 OCR 结果逐字段尝试自动修正
            auto_fixes_applied = 0
            if ocr:
                context = {
                    "doc_type": doc_data.get("doc_type", ""),
                    "file_name": file_name or "",
                }
                for vendor_key in ["seller_name", "buyer_name", "vendor_name"]:
                    if ocr.get(vendor_key):
                        context["vendor_name"] = ocr[vendor_key]
                        break
                corrected_ocr = dict(ocr)
                for field, value in ocr.items():
                    if not isinstance(value, str) or not value:
                        continue
                    result = auto_correct(db, "ocr", field, value, context)
                    if result["auto_applied"] and result["corrected"] != value:
                        corrected_ocr[field] = result["corrected"]
                        auto_fixes_applied += 1
                ocr = corrected_ocr
                if auto_fixes_applied > 0:
                    print(f"[自学习] {file_name}: 自动修正 {auto_fixes_applied} 个字段")

            # 3. 创建原始凭证记录
            doc = OriginalDocument(
                id=str(uuid.uuid4()),
                source="rpa_scan" if task_type == "scan_invoice" else "rpa_bank",
                file_path=file_path,
                file_name=file_name,
                doc_type=doc_data.get("doc_type", "other"),
                rpa_task_id=task_id,
                client_id=client_id,
                ocr_structured=json.dumps(ocr, ensure_ascii=False) if ocr else None,
                ocr_status="done" if ocr else "pending",
            )
            db.add(doc)
            db.flush()

            results.append({
                "success": True,
                "document_id": doc.id,
                "message": "入库成功",
            })

        except Exception as e:
            # 单条失败不回滚整个批次，仅记录失败
            results.append({
                "success": False,
                "document_id": "",
                "message": f"处理异常: {str(e)}",
            })

    # 更新 RPA 任务状态
    if task_id:
        task = db.query(RPATask).filter(RPATask.id == task_id).first()
        if task:
            all_success = all(r["success"] for r in results)
            task.status = "done" if all_success else "failed"
            task.updated_at = datetime.now()
            if not all_success:
                task.error_message = "; ".join(
                    r["message"] for r in results if not r["success"]
                )

    db.commit()
    return results
