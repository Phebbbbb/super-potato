"""
RAG 税法检索引擎 — 检索增强生成 + 置信度评分

借鉴 AI Accountant 的 RAG 架构:
- 税法知识库 (内嵌常用法规)
- BM25 关键词匹配检索
- 多级置信度评分
- 引用来源标注

生产环境应迁移至向量数据库 (ChromaDB/Milvus)
"""
import re
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

# ===== 税法知识库 =====
# 按税种/主题组织的法规条文摘要

TAX_LAW_KB: list[dict] = [
    # === 增值税 ===
    {
        "id": "vat_001",
        "title": "增值税暂行条例第一条",
        "category": "增值税",
        "tags": ["增值税", "纳税人", "销售货物", "应税劳务"],
        "content": "在中华人民共和国境内销售货物或者加工、修理修配劳务，销售服务、无形资产、不动产以及进口货物的单位和个人，为增值税的纳税人，应当依照本条例缴纳增值税。",
        "source": "《中华人民共和国增值税暂行条例》第一条",
        "effective_date": "2017-11-19",
    },
    {
        "id": "vat_002",
        "title": "增值税税率",
        "category": "增值税",
        "tags": ["税率", "13%", "9%", "6%", "零税率"],
        "content": "增值税税率：销售货物、劳务、有形动产租赁服务及进口货物税率为13%；交通运输、邮政、建筑、不动产租赁、销售不动产、转让土地使用权税率为9%；金融服务、现代服务、生活服务、无形资产转让税率为6%；出口货物适用零税率。",
        "source": "《增值税暂行条例》第二条及财税〔2018〕32号",
    },
    {
        "id": "vat_003",
        "title": "小规模纳税人标准",
        "category": "增值税",
        "tags": ["小规模纳税人", "500万", "征收率", "3%"],
        "content": "增值税小规模纳税人标准为年应征增值税销售额500万元及以下。小规模纳税人适用简易计税方法，征收率为3%。自2023年1月1日至2027年12月31日，小规模纳税人适用3%征收率的应税销售收入，减按1%征收率征收增值税。月销售额10万元以下（季度30万元以下）免征增值税。",
        "source": "《增值税暂行条例实施细则》及财税〔2023〕1号",
    },
    {
        "id": "vat_004",
        "title": "进项税额抵扣",
        "category": "增值税",
        "tags": ["进项税额", "抵扣", "增值税专用发票", "认证"],
        "content": "一般纳税人购进货物、劳务、服务、无形资产、不动产支付或者负担的增值税额，为进项税额。准予从销项税额中抵扣的进项税额包括：从销售方取得的增值税专用发票上注明的增值税额；从海关取得的海关进口增值税专用缴款书上注明的增值税额；购进农产品按买价和扣除率计算的进项税额。",
        "source": "《增值税暂行条例》第八条",
    },
    # === 企业所得税 ===
    {
        "id": "cit_001",
        "title": "企业所得税税率",
        "category": "企业所得税",
        "tags": ["企业所得税", "税率", "25%", "小微企业", "高新技术"],
        "content": "企业所得税税率为25%。符合条件的小型微利企业，减按20%的税率征收。国家需要重点扶持的高新技术企业，减按15%的税率征收。小型微利企业标准：年应纳税所得额不超过300万元、从业人数不超过300人、资产总额不超过5000万元。",
        "source": "《企业所得税法》第四条、第二十八条",
    },
    {
        "id": "cit_002",
        "title": "小型微利企业优惠",
        "category": "企业所得税",
        "tags": ["小型微利企业", "优惠", "减按", "300万"],
        "content": "自2023年1月1日至2027年12月31日，小型微利企业年应纳税所得额不超过300万元的部分，减按25%计入应纳税所得额，按20%的税率缴纳企业所得税。实际税负为5%。",
        "source": "财政部 税务总局公告2023年第6号",
    },
    {
        "id": "cit_003",
        "title": "税前扣除项目",
        "category": "企业所得税",
        "tags": ["扣除", "成本", "费用", "税金", "损失"],
        "content": "企业实际发生的与取得收入有关的、合理的支出，包括成本、费用、税金、损失和其他支出，准予在计算应纳税所得额时扣除。公益性捐赠支出不超过年度利润总额12%的部分准予扣除；超过部分可结转以后三年扣除。业务招待费按发生额60%扣除，最高不超过当年销售收入的5‰。广告费和业务宣传费不超过当年销售收入15%的部分准予扣除；超过部分可结转以后年度扣除。",
        "source": "《企业所得税法》第八条、第九条及实施条例",
    },
    {
        "id": "cit_004",
        "title": "固定资产折旧",
        "category": "企业所得税",
        "tags": ["固定资产", "折旧", "年限", "加速折旧"],
        "content": "固定资产计算折旧的最低年限：房屋建筑物20年；飞机火车轮船机器机械和其他生产设备10年；器具工具家具5年；飞机火车轮船以外的运输工具4年；电子设备3年。企业持有的单位价值不超过5000元的固定资产，允许一次性计入当期成本费用扣除。制造业企业新购进的固定资产可缩短折旧年限或加速折旧。",
        "source": "《企业所得税法实施条例》第六十条",
    },
    # === 个人所得税 ===
    {
        "id": "pit_001",
        "title": "综合所得税率表",
        "category": "个人所得税",
        "tags": ["个人所得税", "工资薪金", "累计预扣", "起征点", "5000"],
        "content": "居民个人综合所得（工资薪金、劳务报酬、稿酬、特许权使用费）按纳税年度合并计算。基本减除费用标准为每年6万元（每月5000元）。适用3%至45%的七级超额累进税率。专项附加扣除包括：子女教育（每个子女每月2000元）、继续教育（每月400元）、大病医疗（年度超过15000元部分据实扣除，限额80000元）、住房贷款利息（每月1000元）、住房租金（800-1500元/月按城市级别）、赡养老人（每月3000元）、3岁以下婴幼儿照护（每个子女每月2000元）。",
        "source": "《个人所得税法》及国发〔2023〕13号",
    },
    {
        "id": "pit_002",
        "title": "劳务报酬所得",
        "category": "个人所得税",
        "tags": ["劳务报酬", "预扣", "800", "20%"],
        "content": "劳务报酬所得每次收入不超过4000元的，减除费用800元；4000元以上的，减除20%的费用，其余额为应纳税所得额。劳务报酬所得适用20%至40%的三级超额累进预扣税率。年末并入综合所得统一计算，多退少补。",
        "source": "《个人所得税法》第六条",
    },
    # === 印花税 ===
    {
        "id": "stamp_001",
        "title": "印花税法税率表",
        "category": "印花税",
        "tags": ["印花税", "合同", "税率", "借款", "购销"],
        "content": "印花税应税凭证及税率：借款合同按借款金额0.05‰贴花；购销合同按购销金额0.3‰贴花；承揽合同按报酬0.3‰贴花；建设工程合同按价款0.3‰贴花；技术合同按价款0.3‰贴花；租赁合同按租金1‰贴花；运输合同按运费0.3‰贴花；财产保险合同按保费1‰贴花；营业账簿按实收资本和资本公积合计0.25‰贴花。",
        "source": "《中华人民共和国印花税法》(2022年7月1日施行)",
    },
    # === 征管法 ===
    {
        "id": "admin_001",
        "title": "纳税申报期限",
        "category": "税收征管",
        "tags": ["申报", "期限", "逾期", "15日", "罚款"],
        "content": "增值税一般纳税人按月申报，每月结束后15日内申报纳税。企业所得税按季度预缴（4月、7月、10月、1月各15日前），年度汇算清缴在次年5月31日前完成。个人所得税综合所得年度汇算期为次年3月1日至6月30日。未按期申报的，由税务机关责令限期改正，可处2000元以下罚款；情节严重的处2000元以上1万元以下罚款。",
        "source": "《税收征收管理法》第二十五条、第六十二条",
    },
    {
        "id": "admin_002",
        "title": "滞纳金规定",
        "category": "税收征管",
        "tags": ["滞纳金", "逾期", "万分之五", "缴税"],
        "content": "纳税人未按照规定期限缴纳税款的，扣缴义务人未按照规定期限解缴税款的，税务机关除责令限期缴纳外，从滞纳税款之日起，按日加收滞纳税款万分之五的滞纳金。滞纳金计算公式：滞纳金=滞纳税款×0.0005×滞纳天数。",
        "source": "《税收征收管理法》第三十二条",
    },
    {
        "id": "admin_003",
        "title": "偷税漏税处罚",
        "category": "税收征管",
        "tags": ["偷税", "漏税", "罚款", "50%", "5倍", "刑事责任"],
        "content": "纳税人采取欺骗、隐瞒手段进行虚假纳税申报或者不申报，逃避缴纳税款数额较大并且占应纳税额10%以上的，处3年以下有期徒刑或者拘役，并处罚金；数额巨大并且占应纳税额30%以上的，处3年以上7年以下有期徒刑，并处罚金。补缴应纳税款和滞纳金后，已受行政处罚的，可不予追究刑事责任（首违不罚）。",
        "source": "《刑法》第二百零一条及《税收征收管理法》第六十三条",
    },
    # === 公司法（工商相关） ===
    {
        "id": "company_001",
        "title": "有限责任公司注册资本",
        "category": "公司法",
        "tags": ["注册资本", "认缴", "5年", "有限责任"],
        "content": "有限责任公司的注册资本为在公司登记机关登记的全体股东认缴的出资额。全体股东认缴的出资额由股东按照公司章程的规定自公司成立之日起五年内缴足。法律、行政法规以及国务院决定对有限责任公司注册资本实缴、注册资本最低限额另有规定的，从其规定。",
        "source": "2024年《公司法》第四十七条（2024年7月1日施行）",
    },
    {
        "id": "company_002",
        "title": "公司注销条件",
        "category": "公司法",
        "tags": ["注销", "清算", "简易注销", "公告", "20天"],
        "content": "公司注销分为简易注销和一般注销。简易注销适用于未开业或无债权债务的企业，在国家企业信用信息公示系统公告20天，公告期满20日内向登记机关申请注销。一般注销需经清算程序：成立清算组→清算组备案→债权人公告（45天）→清算→税务注销→工商注销。",
        "source": "《公司法》第二百二十九条至第二百四十二条、《市场主体登记管理条例》",
    },
    # === 会计法 ===
    {
        "id": "accounting_001",
        "title": "不相容职务分离",
        "category": "会计法",
        "tags": ["不相容职务", "制单", "审核", "记账", "分离"],
        "content": "各单位应当建立、健全本单位内部会计监督制度。记账人员与经济业务事项和会计事项的审批人员、经办人员、财物保管人员的职责权限应当明确，并相互分离、相互制约。制单人不得兼任审核人。会计凭证应当经过审核才能作为记账依据。",
        "source": "《中华人民共和国会计法》第二十七条",
    },
    {
        "id": "accounting_002",
        "title": "会计凭证保存期限",
        "category": "会计法",
        "tags": ["凭证", "保存", "期限", "30年", "销毁"],
        "content": "原始凭证和记账凭证的保存期限为30年。会计档案包括会计凭证、会计账簿、财务会计报告等。保存期满需要销毁的，应编制销毁清册并经审批。涉及未了事项的原始凭证应单独抽出立卷，保管到未了事项完结为止。",
        "source": "《会计档案管理办法》(财政部令第79号)",
    },
]


@dataclass
class RAGResult:
    """RAG 检索结果"""
    query: str
    laws: list[dict] = field(default_factory=list)  # 检索到的法规
    confidence: float = 0.0  # 综合置信度 0-1
    confidence_label: str = ""  # 高/中/低
    primary_citation: str = ""  # 主要引用
    answer_context: str = ""  # 拼接的上下文(供LLM使用)


class TaxLawRAG:
    """税法 RAG 检索引擎"""

    def __init__(self):
        self.kb = TAX_LAW_KB
        self._build_index()

    def _build_index(self):
        """构建倒排索引（BM25 简化版）"""
        self.doc_freq: dict[str, int] = Counter()  # 词 → 出现在多少文档中
        self.idf: dict[str, float] = {}
        self.doc_tokens: list[list[str]] = []

        for doc in self.kb:
            text = doc["content"] + " " + " ".join(doc["tags"]) + " " + doc["category"]
            tokens = self._tokenize(text)
            self.doc_tokens.append(tokens)
            for token in set(tokens):
                self.doc_freq[token] += 1

        N = len(self.kb)
        for token, df in self.doc_freq.items():
            self.idf[token] = math.log((N - df + 0.5) / (df + 0.5) + 1.0)

    def _tokenize(self, text: str) -> list[str]:
        """中文分词简化版（生产环境应使用 jieba）"""
        # 提取中文词（2-4字）+ 数字 + 英文
        tokens = []
        # 中文双字词
        for i in range(len(text) - 1):
            chunk = text[i:i + 2]
            if re.match(r'[一-鿿]{2}', chunk):
                tokens.append(chunk)
        # 中文三字词
        for i in range(len(text) - 2):
            chunk = text[i:i + 3]
            if re.match(r'[一-鿿]{3}', chunk):
                tokens.append(chunk)
        # 中文字 + 数字组合
        tokens.extend(re.findall(r'[一-鿿]+\d+%?|%\d+|\d+%|\d+\.\d+‰', text))
        # 纯数字
        tokens.extend(re.findall(r'\d{4}|\d{1,2}%\b', text))
        # 关键词
        keywords = ["增值税", "企业所得税", "个人所得税", "印花税", "契税", "消费税",
                     "纳税人", "税率", "征收率", "抵扣", "扣除", "折旧", "滞纳金",
                     "小规模", "一般纳税人", "小微企业", "高新技术", "注册", "注销"]
        for kw in keywords:
            if kw in text:
                tokens.append(kw)
        return tokens

    def search(self, query: str, top_k: int = 5) -> RAGResult:
        """检索相关税法条文"""
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return RAGResult(query=query, confidence=0.0, confidence_label="低")

        # BM25 评分
        scores: list[tuple[int, float]] = []
        avgdl = sum(len(t) for t in self.doc_tokens) / max(len(self.doc_tokens), 1)
        k1, b = 1.5, 0.75

        for idx, doc_tokens in enumerate(self.doc_tokens):
            score = 0.0
            doc_len = len(doc_tokens)
            tf_counter = Counter(doc_tokens)
            for token in query_tokens:
                if token in self.idf:
                    tf = tf_counter[token]
                    idf = self.idf[token]
                    numerator = tf * (k1 + 1)
                    denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
                    score += idf * numerator / denominator
            if score > 0:
                scores.append((idx, score))

        # 按分数排序
        scores.sort(key=lambda x: x[1], reverse=True)
        top = scores[:top_k]

        laws = []
        for idx, score in top:
            law = dict(self.kb[idx])
            law["relevance_score"] = round(score, 4)
            laws.append(law)

        # 置信度计算（多维度）
        confidence = self._calc_confidence(query_tokens, top, len(query))
        label = "高" if confidence >= 0.7 else ("中" if confidence >= 0.4 else "低")

        # 构建上下文
        context_parts = []
        for law in laws:
            context_parts.append(f"[{law['source']}] {law['content']}")
        context = "\n\n".join(context_parts)

        primary = laws[0]["source"] if laws else ""

        return RAGResult(
            query=query,
            laws=laws,
            confidence=confidence,
            confidence_label=label,
            primary_citation=primary,
            answer_context=context,
        )

    def _calc_confidence(self, query_tokens: list[str],
                         top_results: list[tuple[int, float]],
                         query_len: int) -> float:
        """多维度置信度计算"""
        if not top_results:
            return 0.0

        # 维度1: 最佳匹配分数 (归一化)
        best_score = top_results[0][1]
        score_factor = min(best_score / 5.0, 1.0) * 0.35

        # 维度2: 检索结果数量
        count_factor = min(len(top_results) / 5.0, 1.0) * 0.15

        # 维度3: 查询词覆盖率
        matched_query_tokens = set()
        for idx, _ in top_results:
            doc_tokens = set(self.doc_tokens[idx])
            for qt in query_tokens:
                if qt in doc_tokens:
                    matched_query_tokens.add(qt)
        coverage = len(matched_query_tokens) / max(len(query_tokens), 1)
        coverage_factor = coverage * 0.25

        # 维度4: 得分下降率（集中度）
        if len(top_results) >= 2:
            drop = top_results[0][1] / max(top_results[-1][1], 0.001)
            concentration = min(1.0 / max(math.log(drop + 1), 0.1), 1.0)
        else:
            concentration = 0.5
        concentration_factor = concentration * 0.10

        # 维度5: 查询长度惩罚（过短的查询不确定）
        length_factor = min(query_len / 20.0, 1.0) * 0.15

        return round(score_factor + count_factor + coverage_factor +
                     concentration_factor + length_factor, 4)


# 全局单例
_rag_instance: Optional[TaxLawRAG] = None


def get_rag() -> TaxLawRAG:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = TaxLawRAG()
    return _rag_instance


def search_tax_law(query: str, top_k: int = 5) -> RAGResult:
    """便捷接口：检索税法"""
    return get_rag().search(query, top_k)
