"""创建默认管理员和客户 — bcrypt 密码 + 强密码策略"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import SessionLocal, Base, engine
from app.db import init_db
from app.models.client import Client
from app.models.user import User, UserClientAssignment
from app.services.auth import hash_password

init_db()

db = SessionLocal()

# 创建默认管理员（强密码）
admin = db.query(User).filter(User.username == "admin").first()
if not admin:
    admin = User(id="u001", username="admin", password_hash=hash_password("Admin@2026"),
                 display_name="系统管理员", role="admin")
    db.add(admin)
    print("管理员创建成功 (admin / Admin@2026)")

# 创建测试用户
if not db.query(User).filter(User.username == "accountant").first():
    u = User(id="u002", username="accountant", password_hash=hash_password("Demo@2026"),
             display_name="张会计", role="accountant")
    db.add(u)
    print("记账会计创建成功 (accountant / Demo@2026)")

if not db.query(User).filter(User.username == "reviewer").first():
    u = User(id="u003", username="reviewer", password_hash=hash_password("Demo@2026"),
             display_name="李审核", role="reviewer")
    db.add(u)
    print("审核员创建成功 (reviewer / Demo@2026)")

# 创建默认客户
client = db.query(Client).filter(Client.tax_no == "91110108MA01ABCDE").first()
if not client:
    client = Client(id="c001", name="智能财税科技有限公司（演示）",
                    tax_no="91110108MA01ABCDE", taxpayer_type="small",
                    industry="it", contact_person="王总",
                    contact_phone="13800138000")
    db.add(client)
    print("默认演示客户创建成功")

db.commit()

# 分配用户到默认客户
for uid in ["u001", "u002", "u003"]:
    existing = db.query(UserClientAssignment).filter(
        UserClientAssignment.user_id == uid,
        UserClientAssignment.client_id == "c001",
    ).first()
    if not existing:
        db.add(UserClientAssignment(id=f"a_{uid}_c001", user_id=uid, client_id="c001"))
db.commit()
print("用户-客户分配完成")

db.close()
print("\n可用账号：")
print("  admin      / Admin@2026  (管理员)")
print("  accountant / Demo@2026  (记账会计)")
print("  reviewer   / Demo@2026  (审核员)")
