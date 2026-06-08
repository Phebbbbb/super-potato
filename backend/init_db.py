"""初始化数据库：创建所有表并预置标准会计科目表"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import init_db, SessionLocal
from app.models.account import ChartOfAccount

# 2024 企业会计准则 — 标准科目表
DEFAULT_ACCOUNTS = [
    # ========== 资产类 (1xxx) ==========
    ("1001", "库存现金", "资产", None, "debit"),
    ("1002", "银行存款", "资产", None, "debit"),
    ("1012", "其他货币资金", "资产", None, "debit"),
    ("1101", "交易性金融资产", "资产", None, "debit"),
    ("1121", "应收票据", "资产", None, "debit"),
    ("1122", "应收账款", "资产", None, "debit"),
    ("1123", "预付账款", "资产", None, "debit"),
    ("1131", "应收股利", "资产", None, "debit"),
    ("1132", "应收利息", "资产", None, "debit"),
    ("1221", "其他应收款", "资产", None, "debit"),
    ("1231", "坏账准备", "资产", None, "credit"),
    ("1401", "材料采购", "资产", None, "debit"),
    ("1402", "在途物资", "资产", None, "debit"),
    ("1403", "原材料", "资产", None, "debit"),
    ("1405", "库存商品", "资产", None, "debit"),
    ("1406", "发出商品", "资产", None, "debit"),
    ("1408", "委托加工物资", "资产", None, "debit"),
    ("1411", "周转材料", "资产", None, "debit"),
    ("1471", "存货跌价准备", "资产", None, "credit"),
    ("1501", "债权投资", "资产", None, "debit"),
    ("1502", "其他债权投资", "资产", None, "debit"),
    ("1511", "长期股权投资", "资产", None, "debit"),
    ("1512", "长期股权投资减值准备", "资产", None, "credit"),
    ("1521", "投资性房地产", "资产", None, "debit"),
    ("1531", "长期应收款", "资产", None, "debit"),
    ("1601", "固定资产", "资产", None, "debit"),
    ("1602", "累计折旧", "资产", None, "credit"),
    ("1603", "固定资产减值准备", "资产", None, "credit"),
    ("1604", "在建工程", "资产", None, "debit"),
    ("1605", "工程物资", "资产", None, "debit"),
    ("1606", "固定资产清理", "资产", None, "debit"),
    ("1701", "无形资产", "资产", None, "debit"),
    ("1702", "累计摊销", "资产", None, "credit"),
    ("1703", "无形资产减值准备", "资产", None, "credit"),
    ("1711", "商誉", "资产", None, "debit"),
    ("1801", "长期待摊费用", "资产", None, "debit"),
    ("1811", "递延所得税资产", "资产", None, "debit"),
    ("1901", "待处理财产损溢", "资产", None, "debit"),

    # ========== 负债类 (2xxx) ==========
    ("2001", "短期借款", "负债", None, "credit"),
    ("2101", "交易性金融负债", "负债", None, "credit"),
    ("2201", "应付票据", "负债", None, "credit"),
    ("2202", "应付账款", "负债", None, "credit"),
    ("2203", "预收账款", "负债", None, "credit"),
    ("2211", "应付职工薪酬", "负债", None, "credit"),
    ("2221", "应交税费", "负债", None, "credit"),
    ("222101", "应交增值税", "负债", "2221", "credit"),
    ("222102", "应交企业所得税", "负债", "2221", "credit"),
    ("222103", "应交个人所得税", "负债", "2221", "credit"),
    ("222104", "应交城市维护建设税", "负债", "2221", "credit"),
    ("222105", "应交教育费附加", "负债", "2221", "credit"),
    ("222106", "应交地方教育附加", "负债", "2221", "credit"),
    ("222107", "应交印花税", "负债", "2221", "credit"),
    ("2231", "应付利息", "负债", None, "credit"),
    ("2232", "应付股利", "负债", None, "credit"),
    ("2241", "其他应付款", "负债", None, "credit"),
    ("2401", "长期借款", "负债", None, "credit"),
    ("2501", "应付债券", "负债", None, "credit"),
    ("2701", "长期应付款", "负债", None, "credit"),
    ("2801", "预计负债", "负债", None, "credit"),
    ("2901", "递延所得税负债", "负债", None, "credit"),

    # ========== 权益类 (3xxx / 4xxx) ==========
    ("4001", "实收资本", "权益", None, "credit"),
    ("4002", "资本公积", "权益", None, "credit"),
    ("4101", "盈余公积", "权益", None, "credit"),
    ("4103", "本年利润", "权益", None, "credit"),
    ("4104", "利润分配", "权益", None, "credit"),
    ("410401", "未分配利润", "权益", "4104", "credit"),

    # ========== 成本类 (5xxx) ==========
    ("5001", "生产成本", "成本", None, "debit"),
    ("5101", "制造费用", "成本", None, "debit"),
    ("5201", "劳务成本", "成本", None, "debit"),
    ("5301", "研发支出", "成本", None, "debit"),

    # ========== 收入类 (6xxx) ==========
    ("6001", "主营业务收入", "收入", None, "credit"),
    ("6051", "其他业务收入", "收入", None, "credit"),
    ("6101", "公允价值变动损益", "收入", None, "credit"),
    ("6111", "投资收益", "收入", None, "credit"),
    ("6301", "营业外收入", "收入", None, "credit"),

    # ========== 费用类 (6xxx 支出) ==========
    ("6401", "主营业务成本", "费用", None, "debit"),
    ("6402", "其他业务成本", "费用", None, "debit"),
    ("6403", "税金及附加", "费用", None, "debit"),
    ("6601", "销售费用", "费用", None, "debit"),
    ("6602", "管理费用", "费用", None, "debit"),
    ("660201", "办公费", "费用", "6602", "debit"),
    ("660202", "差旅费", "费用", "6602", "debit"),
    ("660203", "业务招待费", "费用", "6602", "debit"),
    ("660204", "通讯费", "费用", "6602", "debit"),
    ("660205", "交通费", "费用", "6602", "debit"),
    ("660206", "折旧费", "费用", "6602", "debit"),
    ("660207", "工资", "费用", "6602", "debit"),
    ("660208", "社保费", "费用", "6602", "debit"),
    ("660209", "咨询服务费", "费用", "6602", "debit"),
    ("660210", "租赁费", "费用", "6602", "debit"),
    ("660211", "物业费", "费用", "6602", "debit"),
    ("660212", "水电费", "费用", "6602", "debit"),
    ("6603", "财务费用", "费用", None, "debit"),
    ("660301", "利息费用", "费用", "6603", "debit"),
    ("660302", "手续费", "费用", "6603", "debit"),
    ("6701", "资产减值损失", "费用", None, "debit"),
    ("6711", "营业外支出", "费用", None, "debit"),
    ("6801", "所得税费用", "费用", None, "debit"),
]


def seed_accounts():
    db = SessionLocal()
    try:
        existing = db.query(ChartOfAccount).count()
        if existing > 0:
            print(f"科目表已存在 {existing} 条记录，跳过初始化")
            return

        for code, name, category, parent_code, direction in DEFAULT_ACCOUNTS:
            account = ChartOfAccount(
                code=code,
                name=name,
                category=category,
                parent_code=parent_code,
                direction=direction,
            )
            db.add(account)

        db.commit()
        print(f"成功预置 {len(DEFAULT_ACCOUNTS)} 个会计科目")
    except Exception as e:
        db.rollback()
        print(f"初始化科目表失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("初始化数据库...")
    init_db()
    print("数据库表创建完成")
    seed_accounts()
    print("初始化完成")
