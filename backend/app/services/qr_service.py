"""QR 码生成与追溯服务"""
import os
import uuid
import qrcode
from sqlalchemy.orm import Session
from app.models.qr_trace import QRTrace
from app.config import settings


def generate_qr(data: str, file_name: str = None) -> str:
    """生成二维码图片，返回相对路径"""
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    safe_name = file_name or f"{uuid.uuid4().hex}.png"
    rel_path = os.path.join(settings.qrcode_dir, safe_name)
    abs_path = os.path.join(os.getcwd(), rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    img.save(abs_path)
    return rel_path


def create_trace(
    db: Session,
    target_type: str,
    target_id: str,
    stage: str,
    parent_qr_id: str | None = None,
) -> QRTrace:
    """创建一条 QR 追溯记录"""
    qr_id = str(uuid.uuid4())
    scan_url = f"{settings.base_url}/api/qr/scan/{qr_id}"

    # 生成 QR 码图片
    qr_path = generate_qr(scan_url, f"{target_type}_{target_id}_{stage}.png")

    trace = QRTrace(
        id=qr_id,
        target_type=target_type,
        target_id=target_id,
        stage=stage,
        qr_code_path=qr_path,
        scan_url=scan_url,
        parent_qr_id=parent_qr_id,
    )
    db.add(trace)
    db.flush()
    return trace


def get_trace_chain(db: Session, target_type: str, target_id: str) -> list[dict]:
    """获取某个目标的完整追溯链"""
    # 查找该目标的所有 QR 记录
    traces = (
        db.query(QRTrace)
        .filter(QRTrace.target_type == target_type, QRTrace.target_id == target_id)
        .order_by(QRTrace.created_at)
        .all()
    )

    chain = []
    for t in traces:
        # 同时查找父级追溯
        parent = None
        if t.parent_qr_id:
            parent = db.query(QRTrace).filter(QRTrace.id == t.parent_qr_id).first()

        chain.append({
            "qr_id": t.id,
            "stage": t.stage,
            "target_type": t.target_type,
            "target_id": t.target_id,
            "qr_code_path": t.qr_code_path,
            "scan_url": t.scan_url,
            "parent_qr_id": t.parent_qr_id,
            "parent_stage": parent.stage if parent else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return chain


def get_full_chain_from_qr(db: Session, qr_id: str) -> list[dict]:
    """从任意一个 QR 码开始，追溯全链路（双向：向上找父级，向下找子级）"""
    start = db.query(QRTrace).filter(QRTrace.id == qr_id).first()
    if not start:
        return []

    # 向上追溯父级链
    chain = []
    current = start
    while current:
        chain.insert(0, {
            "qr_id": current.id,
            "stage": current.stage,
            "target_type": current.target_type,
            "scan_url": current.scan_url,
            "created_at": current.created_at.isoformat() if current.created_at else None,
        })
        if current.parent_qr_id:
            current = db.query(QRTrace).filter(QRTrace.id == current.parent_qr_id).first()
        else:
            break

    # 向下追溯子级链
    child = db.query(QRTrace).filter(QRTrace.parent_qr_id == start.id).first()
    while child:
        chain.append({
            "qr_id": child.id,
            "stage": child.stage,
            "target_type": child.target_type,
            "scan_url": child.scan_url,
            "created_at": child.created_at.isoformat() if child.created_at else None,
        })
        child = db.query(QRTrace).filter(QRTrace.parent_qr_id == child.id).first()

    return chain
