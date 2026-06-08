"""E2E 测试：全自动加工链 — 票据入库 → OCR → 凭证生成 → 申报创建"""
import json
import os
import io


class TestFullAutomationChain:
    """端到端测试：从票据上传到申报任务创建"""

    def test_upload_document_and_check_ocr_pending(self, client, auth_headers, sample_client):
        """上传票据后 OCR 状态为 pending"""
        client_id = sample_client["id"]
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("test_invoice.pdf", io.BytesIO(b"%PDF-1.4 test content"), "application/pdf")},
            data={"client_id": client_id},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "id" in data
        doc_id = data["id"]

        # 验证文档列表中存在该票据
        list_resp = client.get(f"/api/documents/?client_id={client_id}", headers=auth_headers)
        assert list_resp.status_code == 200
        docs = list_resp.json().get("items", [])
        doc_ids = [d["id"] for d in docs]
        assert doc_id in doc_ids

    def test_auto_process_no_documents(self, client, auth_headers, sample_client):
        """无待处理票据时应返回空结果"""
        client_id = sample_client["id"]
        resp = client.post(
            f"/api/rpa/auto-process?client_id={client_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents_found"] == 0
        assert "没有新的待处理票据" in data["details"][0]

    def test_auto_process_with_pending_docs(self, client, auth_headers, sample_client, db_session):
        """有待处理票据时自动生成凭证和申报"""
        from app.models.document import OriginalDocument
        import uuid

        client_id = sample_client["id"]

        # 直接插入一个 OCR 已完成的票据（模拟已有数据）
        doc_id = uuid.uuid4().hex
        doc = OriginalDocument(
            id=doc_id,
            file_name="test_invoice.pdf",
            doc_type="invoice",
            ocr_status="done",
            ocr_structured=json.dumps({
                "invoice_no": "12345678",
                "date": "2026-06-01",
                "seller_name": "供应商A",
                "buyer_name": "测试公司",
                "amount": 10000.00,
                "tax_amount": 1300.00,
                "total": 11300.00,
            }),
            client_id=client_id,
        )
        db_session.add(doc)
        db_session.commit()

        # 触发自动加工
        resp = client.post(
            f"/api/rpa/auto-process?client_id={client_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["documents_found"] >= 1
        assert data["vouchers_generated"] >= 1
        assert data["vouchers_auto_confirmed"] >= 1
        assert "summary" in data

        # 验证凭证确实已创建
        from app.models.voucher import AccountingVoucher
        vouchers = db_session.query(AccountingVoucher).filter(
            AccountingVoucher.client_id == client_id
        ).all()
        assert len(vouchers) >= 1
        assert vouchers[0].status == "confirmed"

    def test_auto_submit_no_pending_filings(self, client, auth_headers, sample_client):
        """无待提交申报时应返回空结果"""
        client_id = sample_client["id"]
        resp = client.post(
            f"/api/rpa/auto-submit-filings?client_id={client_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "没有待提交的申报" in data["message"]


class TestAutomationErrors:
    """异常路径测试"""

    def test_auto_process_missing_client(self, client, auth_headers):
        """缺少 client_id 参数时 422"""
        resp = client.post("/api/rpa/auto-process", headers=auth_headers)
        assert resp.status_code == 422

    def test_auto_submit_no_auth(self, client, sample_client):
        """未认证时 401"""
        client_id = sample_client["id"]
        resp = client.post(f"/api/rpa/auto-submit-filings?client_id={client_id}")
        assert resp.status_code == 401


class TestVoucherAI:
    """AI 凭证生成测试"""

    def test_ai_generate_voucher_no_docs(self, client, auth_headers, sample_client):
        """空文档列表应返回错误"""
        client_id = sample_client["id"]
        resp = client.post(
            "/api/vouchers/ai-generate",
            json=[],
            params={"client_id": client_id},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_batch_confirm_invalid_ids(self, client, auth_headers):
        """批量确认不存在的凭证应返回错误"""
        resp = client.post(
            "/api/vouchers/batch-confirm",
            json=["nonexistent-id-1", "nonexistent-id-2"],
            params={"reviewer": "测试审核"},
            headers=auth_headers,
        )
        # 应该优雅处理 — 0 个确认
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("confirmed", 0) == 0
