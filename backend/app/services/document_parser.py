"""
文档解析引擎 — 底层 Kreuzberg + 业务增强层

Kreuzberg: 50+格式支持, 多OCR引擎fallback (Tesseract→EasyOCR→PaddleOCR)
我们增强: 发票/凭证字段提取, 中文优化, 结构化JSON输出
"""
import json
import re
from pathlib import Path
from typing import Optional

# Kreuzberg 可选依赖
try:
    from kreuzberg import extract
    KREUZBERG_AVAILABLE = True
except ImportError:
    KREUZBERG_AVAILABLE = False


def parse_document(file_path: str, extract_tables: bool = True) -> dict:
    """
    通用文档解析 → 结构化Markdown/JSON
    支持: PDF, DOCX, XLSX, 图片(JPG/PNG), HTML, CSV, PPTX...
    """
    if not KREUZBERG_AVAILABLE:
        return _fallback_parse(file_path)

    try:
        result = extract(file_path, extract_tables=extract_tables)
        return {
            "success": True,
            "engine": "kreuzberg",
            "markdown": result.markdown if hasattr(result, 'markdown') else str(result),
            "tables": result.tables if hasattr(result, 'tables') else [],
            "metadata": result.metadata if hasattr(result, 'metadata') else {},
        }
    except Exception as e:
        return {"success": False, "engine": "kreuzberg", "error": str(e)[:300]}


def parse_invoice(file_path: str) -> dict:
    """
    发票专用解析 → 结构化字段提取
    返回: {invoice_type, invoice_no, date, seller, buyer, items, total_amount, tax_amount, ...}
    """
    parsed = parse_document(file_path)
    text = parsed.get("markdown", "")

    if not text:
        return {"success": False, "error": "无法提取文本"}

    # 字段正则提取（中文发票格式）
    patterns = {
        "invoice_no": r"发票号码[：:]\s*(\d+)",
        "invoice_code": r"发票代码[：:]\s*(\d+)",
        "invoice_date": r"开票日期[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2})",
        "seller_name": r"(?:销售方|卖方)[名称：:]*\s*(.+?)(?:\n|$)",
        "seller_tax_no": r"(?:纳税人识别号|统一社会信用代码)[：:]\s*([A-Z0-9]{18})",
        "buyer_name": r"(?:购买方|买方)[名称：:]*\s*(.+?)(?:\n|$)",
        "buyer_tax_no": r"(?:纳税人识别号)[：:]\s*([A-Z0-9]{18})",
        "total_amount": r"(?:价税合计|合计金额).*?[¥￥]\s*([\d,]+\.?\d*)",
        "tax_amount": r"(?:税额|增值税额).*?[¥￥]\s*([\d,]+\.?\d*)",
        "amount_no_tax": r"(?:不含税金额|金额\(不含税\)).*?[¥￥]\s*([\d,]+\.?\d*)",
        "check_code": r"校验码[：:]\s*(\d+)",
    }

    fields = {"success": True, "engine": parsed.get("engine", "kreuzberg")}
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            fields[key] = m.group(1).replace(",", "")

    # 提取商品明细
    items = _extract_invoice_items(text)
    if items:
        fields["items"] = items

    return fields


def _extract_invoice_items(text: str) -> list[dict]:
    """提取发票商品明细行"""
    items = []
    # 匹配常见格式: 名称 规格 数量 单价 金额 税率 税额
    item_pattern = re.compile(
        r'(?:[货物应税劳务服务名称]+[：:])?\s*(.+?)\s+'
        r'(?:[规格型号]+[：:])?\s*(.*?)\s+'
        r'(?:[单位]+[：:])?\s*(.*?)\s+'
        r'(\d+\.?\d*)\s+'      # 数量
        r'(\d+\.?\d*)\s+'      # 单价
        r'(\d+\.?\d*)\s+'      # 金额
        r'(\d+%)?\s*'          # 税率
        r'(\d+\.?\d*)',        # 税额
        re.MULTILINE
    )

    for m in item_pattern.finditer(text):
        items.append({
            "name": m.group(1).strip()[:50],
            "spec": m.group(2).strip()[:30],
            "unit": m.group(3).strip()[:10],
            "quantity": float(m.group(4)),
            "price": float(m.group(5)),
            "amount": float(m.group(6)),
            "tax_rate": m.group(7) or "",
            "tax_amount": float(m.group(8)),
        })

    return items


def parse_receipt(file_path: str) -> dict:
    """收据/小票解析"""
    parsed = parse_document(file_path)
    text = parsed.get("markdown", "")

    patterns = {
        "merchant": r"(?:商户|商家|店铺)[名称：:]*\s*(.+)",
        "date": r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{1,2}:\d{2})",
        "total": r"(?:合计|总计|应收|实收).*?[¥￥]\s*([\d,]+\.?\d*)",
    }

    fields = {"success": True}
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            fields[key] = m.group(1)

    return fields


def parse_bank_statement(file_path: str) -> dict:
    """银行流水解析 → 结构化交易列表"""
    parsed = parse_document(file_path, extract_tables=True)
    tables = parsed.get("tables", [])

    transactions = []
    for table in tables:
        for row in table:
            if len(row) >= 4:
                transactions.append({
                    "date": str(row[0]) if row else "",
                    "description": str(row[1]) if len(row) > 1 else "",
                    "debit": _parse_amount(str(row[2])) if len(row) > 2 else 0,
                    "credit": _parse_amount(str(row[3])) if len(row) > 3 else 0,
                    "balance": _parse_amount(str(row[4])) if len(row) > 4 else 0,
                })

    return {
        "success": True,
        "engine": parsed.get("engine", ""),
        "transactions": transactions,
        "count": len(transactions),
    }


def _parse_amount(text: str) -> float:
    """金额字符串 → float"""
    text = text.replace(",", "").replace("¥", "").replace("￥", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _fallback_parse(file_path: str) -> dict:
    """Kreuzberg 不可用时的兜底方案"""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        text = path.read_text("utf-8", errors="ignore")
    elif suffix == ".csv":
        import csv
        rows = list(csv.reader(open(file_path, "r", encoding="utf-8-sig", errors="ignore")))
        text = "\n".join(["\t".join(r) for r in rows[:100]])
    else:
        text = f"[需要安装 Kreuzberg 以解析 {suffix} 文件: pip install kreuzberg]"

    return {
        "success": False,
        "engine": "fallback",
        "markdown": text,
        "error": "Kreuzberg 未安装 — 仅支持 TXT/CSV 纯文本解析",
    }
