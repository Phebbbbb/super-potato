"""全系统自检 — 覆盖所有 API 模块的 CRUD 操作和认证/鉴权"""
import json
import io


class TestAuthAndUsers:
    """认证 + 用户管理自检"""

    def test_login_success(self, client, auth_headers, db_session):
        """登录成功返回 token"""
        resp = client.post("/api/auth/login", json={"username": "testuser", "password": "Test1234!"})
        assert resp.status_code == 200, f"登录失败: {resp.text}"
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "testuser"

    def test_login_wrong_password(self, client, db_session):
        """错误密码登录失败"""
        resp = client.post("/api/auth/login", json={"username": "testuser", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_empty_fields(self, client, db_session):
        """空用户名密码被 Pydantic 拒绝"""
        resp = client.post("/api/auth/login", json={"username": "", "password": ""})
        assert resp.status_code == 422  # Pydantic validation error

    def test_get_me(self, client, auth_headers):
        """获取当前用户信息"""
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200

    def test_unauthorized_access(self, client):
        """无 token 访问被拒绝"""
        resp = client.get("/api/clients/")
        assert resp.status_code == 401

    def test_weak_password_rejected(self, client, auth_headers):
        """弱密码创建用户被拒"""
        resp = client.post("/api/users/", json={"username": "weak", "password": "123", "role": "reviewer"}, headers=auth_headers)
        assert resp.status_code == 400


class TestClientCRUD:
    """客户管理 CRUD 自检"""

    def test_list_clients(self, client, auth_headers, sample_client):
        """客户列表"""
        resp = client.get("/api/clients/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 1

    def test_get_client(self, client, auth_headers, sample_client):
        """客户详情"""
        resp = client.get(f"/api/clients/{sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "测试科技有限公司"

    def test_create_client_pydantic_validation(self, client, auth_headers):
        """创建客户 — Pydantic 校验必填字段"""
        resp = client.post("/api/clients/", json={"name": ""}, headers=auth_headers)
        assert resp.status_code == 422

    def test_update_client(self, client, auth_headers, sample_client):
        """更新客户信息"""
        resp = client.patch(
            f"/api/clients/{sample_client['id']}",
            json={"contact_phone": "13900139000"},
            headers=auth_headers,
        )
        assert resp.status_code == 200


class TestDocumentUpload:
    """原始凭证上传自检"""

    def test_upload_pdf(self, client, auth_headers, sample_client):
        """上传 PDF 票据"""
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("invoice_001.pdf", io.BytesIO(b"%PDF-1.4 fake pdf content"), "application/pdf")},
            data={"client_id": sample_client["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"上传失败: {resp.text}"
        assert "id" in resp.json()

    def test_upload_image(self, client, auth_headers, sample_client):
        """上传图片票据"""
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("receipt.png", io.BytesIO(b"\x89PNG\r\n\x1a\nfake"), "image/png")},
            data={"client_id": sample_client["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_upload_no_file(self, client, auth_headers, sample_client):
        """无文件上传被拒"""
        resp = client.post("/api/documents/upload", data={"client_id": sample_client["id"]}, headers=auth_headers)
        assert resp.status_code in (400, 422)

    def test_list_documents(self, client, auth_headers, sample_client):
        """票据列表"""
        resp = client.get(f"/api/documents/?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_document(self, client, auth_headers, sample_client):
        """删除票据"""
        # 先上传一个
        up = client.post(
            "/api/documents/upload",
            files={"file": ("to_delete.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
            data={"client_id": sample_client["id"]},
            headers=auth_headers,
        )
        doc_id = up.json()["id"]
        resp = client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
        assert resp.status_code == 200


class TestVoucherWorkflow:
    """记账凭证工作流自检"""

    def _create_test_voucher(self, client, auth_headers, sample_client):
        """手工创建凭证（helper）"""
        resp = client.post("/api/vouchers/", json={
            "client_id": sample_client["id"],
            "voucher_date": "2026-06-01",
            "summary": "测试凭证",
            "entries": [
                {"account_code": "1001", "account_name": "库存现金", "debit": 1000, "credit": 0, "summary": "收现"},
                {"account_code": "4001", "account_name": "实收资本", "debit": 0, "credit": 1000, "summary": "投入资本"},
            ],
        }, headers=auth_headers)
        assert resp.status_code == 200, f"创建凭证失败: {resp.text}"
        return resp

    def test_create_manual_voucher(self, client, auth_headers, sample_client):
        """手工创建凭证"""
        resp = self._create_test_voucher(client, auth_headers, sample_client)
        data = resp.json()
        assert "voucher_no" in data

    def test_confirm_voucher(self, client, auth_headers, sample_client):
        """确认凭证"""
        resp = self._create_test_voucher(client, auth_headers, sample_client)
        v = resp.json()
        resp2 = client.patch(
            f"/api/vouchers/{v['id']}/confirm",
            json={"reviewer": "审核员李四", "comment": "审核通过"},
            headers=auth_headers,
        )
        assert resp2.status_code == 200, f"确认凭证失败: {resp2.text}"
        assert resp2.json()["status"] == "confirmed"

    def test_voucher_balance_validation(self, client, auth_headers, sample_client):
        """借贷不平衡被拒"""
        resp = client.post("/api/vouchers/", json={
            "client_id": sample_client["id"],
            "voucher_date": "2026-06-01",
            "summary": "不平衡凭证",
            "entries": [
                {"account_code": "1001", "account_name": "现金", "debit": 100, "credit": 0, "summary": ""},
                {"account_code": "4001", "account_name": "资本", "debit": 0, "credit": 200, "summary": ""},
            ],
        }, headers=auth_headers)
        assert resp.status_code == 422, f"应该拒绝不平衡凭证: {resp.text}"

    def test_cannot_confirm_confirmed_voucher(self, client, auth_headers, sample_client):
        """已确认的凭证不能重复确认"""
        resp = self._create_test_voucher(client, auth_headers, sample_client)
        v = resp.json()
        client.patch(f"/api/vouchers/{v['id']}/confirm", json={"reviewer": "张三"}, headers=auth_headers)
        resp2 = client.patch(f"/api/vouchers/{v['id']}/confirm", json={"reviewer": "李四"}, headers=auth_headers)
        assert resp2.status_code == 400

    def test_batch_confirm(self, client, auth_headers, sample_client):
        """批量确认"""
        resp = self._create_test_voucher(client, auth_headers, sample_client)
        v1 = resp.json()
        resp2 = client.post(
            "/api/vouchers/batch-confirm",
            json=[v1["id"]],
            params={"reviewer": "批量审核员"},
            headers=auth_headers,
        )
        assert resp2.status_code == 200


class TestInvoiceWorkflow:
    """开票工作流自检"""

    def test_create_invoice(self, client, auth_headers, sample_client):
        """创建开票申请"""
        resp = client.post("/api/invoices/", json={
            "client_id": sample_client["id"],
            "buyer_name": "采购方有限公司",
            "buyer_tax_no": "91110108MA01BUYER",
            "items": [
                {"name": "技术服务", "spec": "", "unit": "次", "quantity": 1, "price": 10000, "amount": 10000, "tax_rate": 0.06, "tax_amount": 600},
            ],
            "remark": "测试开票",
        }, headers=auth_headers)
        assert resp.status_code == 200, f"创建发票失败: {resp.text}"

    def test_invoice_idempotency(self, client, auth_headers, sample_client):
        """幂等key — 重复提交返回已有记录"""
        resp = client.post("/api/invoices/", json={
            "client_id": sample_client["id"],
            "buyer_name": "幂等测试公司",
            "buyer_tax_no": "91110108MA01IDEM",
            "items": [{"name": "商品A", "unit": "个", "quantity": 1, "price": 100, "amount": 100, "tax_rate": 0.13, "tax_amount": 13}],
            "idempotency_key": "test-idempotent-key-001",
        }, headers=auth_headers)
        assert resp.status_code == 200
        id1 = resp.json()["id"]

        resp2 = client.post("/api/invoices/", json={
            "client_id": sample_client["id"],
            "buyer_name": "幂等测试公司",
            "buyer_tax_no": "91110108MA01IDEM",
            "items": [{"name": "商品A", "unit": "个", "quantity": 1, "price": 100, "amount": 100, "tax_rate": 0.13, "tax_amount": 13}],
            "idempotency_key": "test-idempotent-key-001",
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == id1

    def test_invoice_list(self, client, auth_headers, sample_client):
        """开票列表"""
        resp = client.get(f"/api/invoices/?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_invoice(self, client, auth_headers, sample_client):
        """删除开票记录（含已开具状态可红冲）"""
        # 创建发票
        resp = client.post("/api/invoices/", json={
            "client_id": sample_client["id"],
            "buyer_name": "待删除公司",
            "buyer_tax_no": "91110108MA01DELXX",
            "items": [{"name": "商品", "unit": "个", "quantity": 1, "price": 50, "amount": 50, "tax_rate": 0.03, "tax_amount": 1.5}],
        }, headers=auth_headers)
        inv_id = resp.json()["id"]

        # 直接标记为 issued 再删除（模拟红冲场景）
        from app.db import get_db
        from app.models.invoice import Invoice
        db_session = None
        for d in client.app.dependency_overrides.values():
            try:
                db_session = next(d())
                break
            except Exception:
                pass
        if db_session:
            inv = db_session.query(Invoice).filter(Invoice.id == inv_id).first()
            if inv:
                inv.status = "issued"
                db_session.commit()

        resp = client.delete(f"/api/invoices/{inv_id}", headers=auth_headers)
        assert resp.status_code == 200, f"删除失败: {resp.text}"


class TestTaxFilingWorkflow:
    """纳税申报工作流自检"""

    def test_create_filing(self, client, auth_headers, sample_client):
        """创建申报任务"""
        resp = client.post("/api/filings/", json={
            "client_id": sample_client["id"],
            "tax_type": "vat",
            "period": "2026-06",
            "taxpayer_type": "small",
        }, headers=auth_headers)
        assert resp.status_code == 200, f"创建申报失败: {resp.text}"

    def test_filing_idempotency(self, client, auth_headers, sample_client):
        """申报幂等key"""
        resp1 = client.post("/api/filings/", json={
            "client_id": sample_client["id"],
            "tax_type": "vat",
            "period": "2026-07",
            "idempotency_key": "filing-idem-001",
        }, headers=auth_headers)
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        resp2 = client.post("/api/filings/", json={
            "client_id": sample_client["id"],
            "tax_type": "vat",
            "period": "2026-07",
            "idempotency_key": "filing-idem-001",
        }, headers=auth_headers)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == id1

    def test_filing_list(self, client, auth_headers, sample_client):
        """申报列表"""
        resp = client.get(f"/api/filings/?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_preview_filing(self, client, auth_headers, sample_client):
        """预览申报数据"""
        resp = client.post("/api/filings/preview", json={
            "tax_type": "vat", "period": "2026-06", "taxpayer_type": "small",
        }, headers=auth_headers)
        assert resp.status_code == 200

    def test_update_filing_status(self, client, auth_headers, sample_client):
        """更新申报状态（Pydantic schema）"""
        # 创建申报
        resp = client.post("/api/filings/", json={
            "client_id": sample_client["id"],
            "tax_type": "vat",
            "period": "2026-08",
        }, headers=auth_headers)
        filing_id = resp.json()["id"]

        # 更新状态
        resp = client.patch(f"/api/filings/{filing_id}", json={
            "status": "submitted",
            "filing_result": {"tax_payable": 1234.56},
        }, headers=auth_headers)
        assert resp.status_code == 200, f"更新申报失败: {resp.text}"


class TestOtherModules:
    """其他模块自检"""

    def test_accounts_list(self, client, auth_headers):
        """科目列表"""
        resp = client.get("/api/accounts/", headers=auth_headers)
        assert resp.status_code == 200

    def test_accounts_tree(self, client, auth_headers):
        """科目树"""
        resp = client.get("/api/accounts/tree", headers=auth_headers)
        assert resp.status_code == 200

    def test_create_account(self, client, auth_headers):
        """创建科目"""
        resp = client.post("/api/accounts/", json={
            "code": "1002", "name": "银行存款", "category": "asset", "direction": "debit",
        }, headers=auth_headers)
        assert resp.status_code == 200

    def test_agent_chat(self, client, auth_headers):
        """AI 顾问对话"""
        resp = client.post("/api/agent/chat", json={
            "message": "小规模纳税人增值税起征点是多少？",
        }, headers=auth_headers)
        assert resp.status_code == 200, f"agent chat 失败: {resp.text}"
        assert "reply" in resp.json()

    def test_agent_chat_empty_message_rejected(self, client, auth_headers):
        """空消息被 Pydantic 拒绝"""
        resp = client.post("/api/agent/chat", json={"message": ""}, headers=auth_headers)
        assert resp.status_code == 422

    def test_field_tasks_crud(self, client, auth_headers, sample_client):
        """外勤任务 CRUD"""
        # create
        resp = client.post("/api/field-tasks/", json={
            "client_id": sample_client["id"],
            "task_type": "bank_counter",
            "title": "银行柜台办理",
            "priority": "high",
        }, headers=auth_headers)
        assert resp.status_code == 200, f"创建任务失败: {resp.text}"
        task_id = resp.json()["id"]

        # list
        resp = client.get(f"/api/field-tasks/?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

        # update
        resp = client.patch(f"/api/field-tasks/{task_id}", json={"status": "in_progress"}, headers=auth_headers)
        assert resp.status_code == 200

        # delete
        resp = client.delete(f"/api/field-tasks/{task_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_payroll_employee_crud(self, client, auth_headers, sample_client):
        """薪酬员工 CRUD"""
        resp = client.post("/api/payroll/employees/", json={
            "client_id": sample_client["id"],
            "name": "王五",
            "position": "工程师",
            "base_salary": 15000,
        }, headers=auth_headers)
        assert resp.status_code == 200, f"创建员工失败: {resp.text}"
        emp_id = resp.json()["id"]

        resp = client.get(f"/api/payroll/employees/?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

        resp = client.patch(f"/api/payroll/employees/{emp_id}", json={"position": "高级工程师"}, headers=auth_headers)
        assert resp.status_code == 200

    def test_bank_account(self, client, auth_headers, sample_client):
        """银行账户管理"""
        resp = client.post("/api/bank/accounts/", json={
            "client_id": sample_client["id"],
            "bank_name": "中国工商银行",
            "account_no": "6222021234567890",
        }, headers=auth_headers)
        assert resp.status_code == 200, f"创建银行账户失败: {resp.text}"

        resp = client.get(f"/api/bank/accounts/?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_version_history(self, client, auth_headers, sample_client):
        """版本历史"""
        resp = client.get(f"/api/version/history/client/{sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_version_recent(self, client, auth_headers):
        """最近变更"""
        resp = client.get("/api/version/recent", headers=auth_headers)
        assert resp.status_code == 200

    def test_qr_trace(self, client, auth_headers, sample_client):
        """QR 追溯"""
        resp = client.get(f"/api/qr/trace/client/{sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_reports_dashboard(self, client, auth_headers):
        """报表仪表盘"""
        resp = client.get("/api/reports/dashboard", headers=auth_headers)
        assert resp.status_code == 200

    def test_tax_calendar(self, client, auth_headers):
        """税务日历"""
        resp = client.get("/api/tax/calendar", headers=auth_headers)
        assert resp.status_code == 200

    def test_tax_risk(self, client, auth_headers):
        """税务风控"""
        resp = client.get("/api/tax/risk-check", headers=auth_headers)
        assert resp.status_code == 200

    def test_settings_read(self, client, auth_headers):
        """读取系统配置"""
        resp = client.get("/api/settings/tax_username", headers=auth_headers)
        # 可能不存在，但不应该 500
        assert resp.status_code in (200, 404)

    def test_rpa_auto_process(self, client, auth_headers, sample_client):
        """RPA 自动加工"""
        resp = client.post(f"/api/rpa/auto-process?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_rpa_auto_submit(self, client, auth_headers, sample_client):
        """RPA 一键申报"""
        resp = client.post(f"/api/rpa/auto-submit-filings?client_id={sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_feedback_audit_trail(self, client, auth_headers, sample_client):
        """审计日志"""
        resp = client.get(f"/api/feedback/audit/client/{sample_client['id']}", headers=auth_headers)
        assert resp.status_code == 200

    def test_audit_summary(self, client, auth_headers):
        """内审摘要"""
        resp = client.get("/api/audit/summary", headers=auth_headers)
        assert resp.status_code == 200
