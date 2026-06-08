"""演示数据：模拟 RPA 推送发票 → AI 生成凭证 → 审核确认 全流程"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import SessionLocal
from app.models.document import OriginalDocument
from app.models.voucher import AccountingVoucher
from app.models.filing import TaxFiling
from app.models.rpa_task import RPATask
from app.models.qr_trace import QRTrace
from app.services.qr_service import create_trace
from app.services.voucher_service import generate_voucher_no, validate_balance, build_entries_from_documents
from datetime import date
import json
import uuid

db = SessionLocal()

# 清空已有演示数据
db.query(QRTrace).delete()
db.query(AccountingVoucher).delete()
db.query(TaxFiling).delete()
db.query(OriginalDocument).delete()
db.query(RPATask).delete()

# ===== 模拟 3 张发票 =====
invoices = [
    {
        "file_name": "发票_20260601_办公用品.pdf",
        "doc_type": "invoice",
        "ocr": {
            "invoice_code": "3100234567",
            "invoice_no": "87654321",
            "date": "2026-06-01",
            "seller_name": "得力办公用品有限公司",
            "buyer_name": "智能财税科技有限公司",
            "amount_excluding_tax": 5000.00,
            "tax_amount": 650.00,
            "total_amount": 5650.00,
            "items": [{"name": "办公用品", "unit_price": 5000, "quantity": 1}],
        },
    },
    {
        "file_name": "发票_20260603_咨询费.pdf",
        "doc_type": "invoice",
        "ocr": {
            "invoice_code": "3100234568",
            "invoice_no": "87654322",
            "date": "2026-06-03",
            "seller_name": "普华永道咨询有限公司",
            "buyer_name": "智能财税科技有限公司",
            "amount_excluding_tax": 30000.00,
            "tax_amount": 1800.00,
            "total_amount": 31800.00,
            "items": [{"name": "咨询服务费", "unit_price": 30000, "quantity": 1}],
        },
    },
    {
        "file_name": "发票_20260605_服务器采购.pdf",
        "doc_type": "invoice",
        "ocr": {
            "invoice_code": "3100234569",
            "invoice_no": "87654323",
            "date": "2026-06-05",
            "seller_name": "华为云计算有限公司",
            "buyer_name": "智能财税科技有限公司",
            "amount_excluding_tax": 80000.00,
            "tax_amount": 10400.00,
            "total_amount": 90400.00,
            "items": [{"name": "云服务器", "unit_price": 80000, "quantity": 1}],
        },
    },
]

doc_ids = []
for inv in invoices:
    doc = OriginalDocument(
        id=str(uuid.uuid4()),
        source="rpa_scan",
        file_name=inv["file_name"],
        doc_type=inv["doc_type"],
        ocr_structured=json.dumps(inv["ocr"], ensure_ascii=False),
        ocr_status="done",
        client_id="c001",
    )
    db.add(doc)
    db.flush()
    doc_ids.append(doc.id)
    # QR #1: 凭证入库
    trace = create_trace(db, "document", doc.id, "ingest")

print(f"✅ 3 张发票已入库")

# ===== AI 生成 2 张记账凭证 =====
docs_1 = [
    {"id": doc_ids[0], "doc_type": "invoice", "ocr_structured": invoices[0]["ocr"]},
    {"id": doc_ids[1], "doc_type": "invoice", "ocr_structured": invoices[1]["ocr"]},
]

entries_1 = build_entries_from_documents(db, docs_1, "采购办公用品及咨询服务")

# 凭证2: 服务器采购
docs_2 = [{"id": doc_ids[2], "doc_type": "invoice", "ocr_structured": invoices[2]["ocr"]}]
entries_2 = build_entries_from_documents(db, docs_2, "采购云服务器")

vouchers_data = [
    {
        "date": date(2026, 6, 5),
        "summary": "采购办公用品及咨询服务",
        "doc_ids": doc_ids[:2],
        "entries": entries_1,
        "created_by": "ai",
        "status": "confirmed",
        "reviewer": "张会计",
        "comment": "审核通过，分录准确",
    },
    {
        "date": date(2026, 6, 6),
        "summary": "采购云服务器",
        "doc_ids": [doc_ids[2]],
        "entries": entries_2,
        "created_by": "ai",
        "status": "draft",
        "reviewer": None,
        "comment": None,
    },
]

for vd in vouchers_data:
    balanced, td, tc = validate_balance(vd["entries"])
    if not balanced:
        print(f"⚠️  凭证 {vd['summary']} 借贷不平: 借={td}, 贷={tc}，跳过")
        continue

    vno = generate_voucher_no(db, vd["date"])
    voucher = AccountingVoucher(
        id=str(uuid.uuid4()),
        voucher_no=vno,
        voucher_date=vd["date"],
        summary=vd["summary"],
        source_doc_ids=json.dumps(vd["doc_ids"], ensure_ascii=False),
        entries=json.dumps(vd["entries"], ensure_ascii=False),
        total_debit=td,
        total_credit=tc,
        status=vd["status"],
        created_by=vd["created_by"],
        reviewer=vd["reviewer"],
        client_id="c001",
    )
    db.add(voucher)
    db.flush()

    # QR #2: AI 生成
    create_trace(db, "voucher", voucher.id, "ai_voucher")
    # QR #3: 已确认的加审核链
    if vd["status"] == "confirmed":
        create_trace(db, "voucher", voucher.id, "confirm")
    print(f"✅ 凭证 {vno} 已生成 ({vd['status']})")

# ===== 创建一笔申报记录 =====
filing = TaxFiling(
    id=str(uuid.uuid4()),
    tax_type="vat",
    period="2026-06",
    status="pending_review",
    client_id="c001",
)
db.add(filing)
db.flush()
create_trace(db, "tax_filing", filing.id, "file_tax")
print("✅ 增值税申报记录已创建 (2026-06)")

# ===== 创建 RPA 任务 =====
rpa_task = RPATask(
    id=str(uuid.uuid4()),
    task_type="scan_invoice",
    status="done",
    payload=json.dumps({"batch": "202606-batch1", "count": 3}, ensure_ascii=False),
    assigned_rpa="影刀RPA-01",
    client_id="c001",
)
db.add(rpa_task)
print("✅ RPA 扫描任务已完成")

# ===== 新增：薪酬、银行、外勤演示数据 =====
from app.models.payroll import Employee, PayrollBatch, PayrollDetail
from app.models.bank import BankAccount
from app.models.field_task import FieldTask

# 员工数据
emp1 = Employee(id=str(uuid.uuid4()), name="张三", position="开发工程师", department="研发部",
    base_salary=20000, social_insurance_base=12000, housing_fund_base=12000, client_id="c001")
emp2 = Employee(id=str(uuid.uuid4()), name="李四", position="产品经理", department="产品部",
    base_salary=25000, social_insurance_base=15000, housing_fund_base=15000, client_id="c001")
emp3 = Employee(id=str(uuid.uuid4()), name="王五", position="财务主管", department="财务部",
    base_salary=18000, social_insurance_base=10000, housing_fund_base=10000, client_id="c001")
db.add_all([emp1, emp2, emp3])
print("✅ 3 名员工已录入")

# 银行账户
acc = BankAccount(id=str(uuid.uuid4()), bank_name="中国工商银行", account_no="6222021234567890123",
    account_name="智能财税科技有限公司", client_id="c001")
db.add(acc)
print("✅ 银行账户已添加")

# 外勤任务
ft1 = FieldTask(id=str(uuid.uuid4()), title="前往税务局领取发票", task_type="tax_bureau",
    description="前往北京市朝阳区税务局大厅领取增值税专用发票", priority="high",
    deadline=date(2026, 6, 20), status="pending", client_id="c001")
ft2 = FieldTask(id=str(uuid.uuid4()), title="拜访客户签署代账合同", task_type="client_visit",
    description="拜访新客户XX公司，签署代账服务合同", priority="urgent",
    deadline=date(2026, 6, 10), status="assigned", client_id="c001")
db.add_all([ft1, ft2])
print("✅ 2 条外勤任务已创建")

db.commit()
db.close()
print("\n🎉 演示数据灌入完成！刷新浏览器查看效果")
