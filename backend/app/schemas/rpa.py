from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class InvoiceItem(BaseModel):
    name: str = Field(..., description="商品/服务名称")
    unit_price: Optional[float] = None
    quantity: Optional[float] = None
    amount: Optional[float] = None
    tax_rate: Optional[float] = None


class OCRResult(BaseModel):
    invoice_code: Optional[str] = None
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_name: Optional[str] = None
    amount_excluding_tax: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    items: list[InvoiceItem] = []


class IngestDocument(BaseModel):
    file_base64: Optional[str] = None
    file_name: Optional[str] = None
    doc_type: str = "invoice"
    ocr_result: Optional[OCRResult] = None
    ocr_structured: Optional[OCRResult] = None  # 兼容前端/种子数据字段名


class RPAIngestRequest(BaseModel):
    task_id: Optional[str] = None
    task_type: str = "scan_invoice"
    client_id: Optional[str] = None
    documents: list[IngestDocument]


class IngestResult(BaseModel):
    success: bool
    document_id: str
    message: str


class RPAIngestResponse(BaseModel):
    total: int
    success_count: int
    failed_count: int
    results: list[IngestResult]


class RPATaskQuery(BaseModel):
    status: str = "pending"
    task_type: Optional[str] = None


class RPATaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[dict] = None
    assigned_rpa: Optional[str] = None
    error_message: Optional[str] = None
