from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DocumentQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    doc_type: Optional[str] = None
    source: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    source: str
    file_name: Optional[str]
    doc_type: str
    ocr_status: str
    ocr_structured: Optional[dict]
    qr_code_path: Optional[str]
    rpa_task_id: Optional[str]
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
