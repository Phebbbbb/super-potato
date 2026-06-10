"""热文件夹 + 扫描仪监控 — 自动采集 → 自动 OCR → 自动加工全链"""
import os
import uuid
import json
import time
import shutil
import threading
from datetime import datetime
from app.db import SessionLocal
from app.models.document import OriginalDocument
from app.services.qr_service import create_trace
from app.services.version_control import commit


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".ofd", ".docx", ".xlsx"}
CONFIG_FILE = "hot_folder_config.json"

_running = False
_threads = []


def _load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_config():
    return _load_config()


def add_watch(path, client_id, label="", source="hot_folder"):
    config = _load_config()
    abs_path = os.path.abspath(path)
    for item in config:
        if item["path"] == abs_path and item["client_id"] == client_id:
            return item
    item = {
        "id": str(uuid.uuid4()),
        "path": abs_path, "client_id": client_id,
        "label": label or os.path.basename(abs_path),
        "source": source, "enabled": True, "processed_files": [],
    }
    config.append(item)
    _save_config(config)
    restart()
    return item


def remove_watch(watch_id):
    config = _load_config()
    _save_config([c for c in config if c["id"] != watch_id])
    restart()


def toggle_watch(watch_id, enabled):
    config = _load_config()
    for c in config:
        if c["id"] == watch_id:
            c["enabled"] = enabled
    _save_config(config)
    restart()


def _detect_doc_type(fname):
    fname = fname.lower()
    if any(k in fname for k in ["发票", "invoice", "增值税", "普通发票", "专用发票"]):
        return "invoice"
    if any(k in fname for k in ["回单", "receipt", "银行", "对账", "流水"]):
        return "bank_receipt"
    if any(k in fname for k in ["合同", "contract", "协议"]):
        return "contract"
    if any(k in fname for k in ["完税", "缴款", "税收"]):
        return "tax_cert"
    if any(k in fname for k in ["收据", "凭证"]):
        return "receipt"
    return "other"


def _import_one(filepath, watch_item):
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None
    safe_name = f"{uuid.uuid4().hex}{ext}"
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, safe_name)
    try:
        shutil.copy2(filepath, dest)
    except Exception:
        return None

    doc_type = _detect_doc_type(os.path.basename(filepath))

    db = SessionLocal()
    try:
        doc = OriginalDocument(
            id=str(uuid.uuid4()), source=watch_item["source"],
            file_path=dest, file_name=os.path.basename(filepath),
            doc_type=doc_type, client_id=watch_item["client_id"],
            ocr_status="pending",
        )
        db.add(doc)
        db.flush()
        trace = create_trace(db, "document", doc.id, watch_item["source"])
        doc.qr_code_path = trace.qr_code_path
        commit(db, "document", doc.id, watch_item["source"], "system",
               after={"file_name": doc.file_name, "source": watch_item["source"]})
        db.commit()
        watch_item.setdefault("processed_files", []).append(filepath)
        return {"id": doc.id, "client_id": watch_item["client_id"]}
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _trigger_auto_process(client_id):
    """文件入库后自动触发全加工链（OCR→凭证→申报）"""
    import json as _json
    from app.models.voucher import AccountingVoucher
    from app.services.voucher_service import generate_voucher_no, validate_balance, build_entries_from_documents

    db2 = SessionLocal()
    try:
        # 找到待处理的票据
        existing_vouchers = db2.query(AccountingVoucher.source_doc_ids).filter(
            AccountingVoucher.client_id == client_id
        ).all()
        used_ids = set()
        for (src,) in existing_vouchers:
            if src:
                try:
                    used_ids.update(_json.loads(src))
                except Exception:
                    pass

        pending = db2.query(OriginalDocument).filter(
            OriginalDocument.client_id == client_id,
            OriginalDocument.ocr_status.in_(["done", "pending"]),
            ~OriginalDocument.id.in_(used_ids) if used_ids else True,
        ).all()

        if not pending:
            return

        # 按日期分组生成凭证
        docs_by_date = {}
        for d in pending:
            ocr = _json.loads(d.ocr_structured) if d.ocr_structured else {}
            d_date = ocr.get("date", str(datetime.now().date()))
            docs_by_date.setdefault(d_date, []).append(d)

        for doc_date, docs_group in sorted(docs_by_date.items()):
            docs_data = [{"id": d.id, "doc_type": d.doc_type, "file_name": d.file_name,
                          "ocr_structured": _json.loads(d.ocr_structured) if d.ocr_structured else {}}
                         for d in docs_group]
            entries = build_entries_from_documents(db2, docs_data, "自动处理")
            balanced, td, tc = validate_balance(entries)
            if not balanced and entries:
                diff = round(td - tc, 2)
                if diff > 0:
                    entries[-1]["credit"] = round((entries[-1].get("credit", 0) or 0) + diff, 2)
                else:
                    entries[-1]["debit"] = round((entries[-1].get("debit", 0) or 0) - diff, 2)

            from datetime import date as _date
            v_date = _date.fromisoformat(doc_date) if doc_date else _date.today()
            vno = generate_voucher_no(db2, v_date)
            voucher = AccountingVoucher(
                id=str(uuid.uuid4()), voucher_no=vno, voucher_date=v_date,
                summary=f"自动采集凭证({doc_date})",
                source_doc_ids=_json.dumps([d["id"] for d in docs_data], ensure_ascii=False),
                entries=_json.dumps(entries, ensure_ascii=False),
                total_debit=td, total_credit=tc, status="confirmed",
                created_by="system", reviewer="自动化采集引擎",
                review_comment="热文件夹自动采集 → OCR → 自动确认",
                client_id=client_id,
            )
            db2.add(voucher)
            commit(db2, "voucher", voucher.id, "auto_collect", "system",
                   after={"voucher_no": vno, "client_id": client_id})

        db2.commit()
    except Exception:
        db2.rollback()
    finally:
        db2.close()


def _watch_loop():
    batch_clients = set()
    while _running:
        config = _load_config()
        batch_clients.clear()
        for item in config:
            if not item.get("enabled", True):
                continue
            watch_path = item["path"]
            if not os.path.isdir(watch_path):
                continue
            try:
                for fname in os.listdir(watch_path):
                    fpath = os.path.join(watch_path, fname)
                    if not os.path.isfile(fpath):
                        continue
                    if fpath in item.get("processed_files", []):
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in ALLOWED_EXTENSIONS:
                        continue
                    try:
                        if time.time() - os.path.getmtime(fpath) < 2:
                            continue
                    except Exception:
                        continue
                    result = _import_one(fpath, item)
                    if result:
                        batch_clients.add(result["client_id"])
            except Exception:
                pass
        _save_config(config)

        # 批量触发全自动加工（去重，按客户）
        for cid in batch_clients:
            _trigger_auto_process(cid)

        time.sleep(10)


def start():
    global _running
    if _running:
        return
    _running = True
    t = threading.Thread(target=_watch_loop, daemon=True)
    t.start()
    _threads.append(t)


def stop():
    global _running
    _running = False


def restart():
    stop()
    if any(c.get("enabled", True) for c in _load_config()):
        start()


def get_status():
    config = _load_config()
    return {
        "running": _running,
        "watchers": len(config),
        "active_watchers": sum(1 for c in config if c.get("enabled", True)),
        "configs": config,
    }
