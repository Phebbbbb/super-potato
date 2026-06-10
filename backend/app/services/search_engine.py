"""
全文检索引擎 — BM25 排序 + 中文分词 + 多字段搜索

借鉴: Whoosh / looseene (纯Python, 零依赖)
用于: 税法检索 / 凭证搜索 / 客户搜索 / 科目搜索
"""
import re
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    query: str
    results: list[dict] = field(default_factory=list)
    total: int = 0
    took_ms: float = 0


class FullTextSearch:
    """轻量全文检索引擎 — BM25算法 + 倒排索引"""

    def __init__(self):
        self._indexes: dict[str, dict] = {}  # collection_name → index

    def index(self, collection: str, documents: list[dict],
              fields: list[str] = None, id_field: str = "id"):
        """
        构建索引
        - collection: 索引名 (e.g. "vouchers", "clients", "tax_laws")
        - documents: 文档列表 [{id: "...", field1: "...", field2: "..."}]
        - fields: 需索引的字段，默认全文
        """
        import time
        start = time.time()

        if fields is None:
            fields = list(documents[0].keys()) if documents else []

        doc_tokens: dict[str, list[str]] = {}  # doc_id → tokens
        doc_data: dict[str, dict] = {}         # doc_id → original doc
        field_lengths: dict[str, int] = {}     # field → total length
        doc_count_per_token: dict[str, Counter] = {f: Counter() for f in fields}

        total_docs = len(documents)

        for doc in documents:
            doc_id = str(doc.get(id_field, ""))
            if not doc_id:
                continue
            doc_data[doc_id] = doc
            all_tokens = []

            for field in fields:
                text = str(doc.get(field, ""))
                tokens = self._tokenize(text)
                all_tokens.extend(tokens)
                field_lengths[field] = field_lengths.get(field, 0) + len(tokens)

                for token in set(tokens):
                    doc_count_per_token[field][token] += 1

            doc_tokens[doc_id] = all_tokens

        # 计算IDF
        idf: dict[str, dict[str, float]] = {f: {} for f in fields}
        for field in fields:
            for token, df in doc_count_per_token[field].items():
                idf[field][token] = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)

        # 计算平均文档长度
        avg_lengths = {
            f: field_lengths.get(f, 0) / max(total_docs, 1) for f in fields
        }

        self._indexes[collection] = {
            "doc_tokens": doc_tokens,
            "doc_data": doc_data,
            "idf": idf,
            "avg_lengths": avg_lengths,
            "fields": fields,
            "total_docs": total_docs,
        }

        return {"indexed": total_docs, "took_ms": round((time.time() - start) * 1000, 1)}

    def search(self, collection: str, query: str, top_k: int = 20,
               fields: list[str] = None, filters: dict = None) -> SearchResult:
        """
        搜索
        - collection: 索引名
        - query: 搜索词
        - top_k: 返回数量
        - fields: 限定搜索字段
        - filters: 结果过滤 {field: value}
        """
        import time
        start = time.time()

        index = self._indexes.get(collection)
        if not index:
            return SearchResult(query=query, results=[], total=0)

        search_fields = fields or index["fields"]
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return SearchResult(query=query, results=[], total=0)

        scores: list[tuple[str, float]] = []
        k1, b = 1.5, 0.75

        for doc_id, doc_tokens in index["doc_tokens"].items():
            score = 0.0
            doc_len = len(doc_tokens)
            tf_counter = Counter(doc_tokens)

            for field in search_fields:
                if field not in index["idf"]:
                    continue
                for token in query_tokens:
                    if token in index["idf"][field]:
                        tf = tf_counter.get(token, 0)
                        _idf = index["idf"][field][token]
                        avgdl = max(index["avg_lengths"].get(field, 1), 1)
                        numerator = tf * (k1 + 1)
                        denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
                        score += _idf * numerator / denominator

            if score > 0:
                scores.append((doc_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc_id, score in scores[:top_k]:
            doc = dict(index["doc_data"][doc_id])
            doc["_score"] = round(score, 4)

            # 应用过滤器
            if filters:
                match = True
                for fk, fv in filters.items():
                    if str(doc.get(fk, "")) != str(fv):
                        match = False
                        break
                if not match:
                    continue

            results.append(doc)

        took_ms = round((time.time() - start) * 1000, 1)
        return SearchResult(query=query, results=results, total=len(scores), took_ms=took_ms)

    def _tokenize(self, text: str) -> list[str]:
        """中文混合分词"""
        tokens = []

        # 中文2-4字词
        for i in range(len(text) - 1):
            chunk = text[i:i + 2]
            if re.match(r'[一-鿿]{2}', chunk):
                tokens.append(chunk)

        for i in range(len(text) - 2):
            chunk = text[i:i + 3]
            if re.match(r'[一-鿿]{3}', chunk):
                tokens.append(chunk)

        for i in range(len(text) - 3):
            chunk = text[i:i + 4]
            if re.match(r'[一-鿿]{4}', chunk):
                tokens.append(chunk)

        # 英文词
        tokens.extend(re.findall(r'[a-zA-Z]+', text.lower()))

        # 数字+单位
        tokens.extend(re.findall(r'\d+\.?\d*[万千百元%‰]?', text))

        # 特定关键词保持整体
        compounds = ["增值税", "企业所得税", "个人所得税", "印花税", "小规模纳税人",
                     "一般纳税人", "小微企业", "高新技术企业", "统一社会信用代码",
                     "营业收入", "应纳税所得额", "进项税额", "销项税额", "会计凭证"]
        for kw in compounds:
            if kw in text:
                tokens.append(kw)

        return tokens

    def remove_collection(self, collection: str):
        self._indexes.pop(collection, None)

    def list_collections(self) -> list[str]:
        return list(self._indexes.keys())


# 全局单例
_search_engine: Optional[FullTextSearch] = None


def get_search() -> FullTextSearch:
    global _search_engine
    if _search_engine is None:
        _search_engine = FullTextSearch()
    return _search_engine


def index_vouchers(vouchers: list[dict]):
    return get_search().index("vouchers", vouchers,
                              fields=["voucher_no", "summary", "maker", "reviewer"])


def index_clients(clients: list[dict]):
    return get_search().index("clients", clients,
                              fields=["name", "tax_no", "contact_name", "industry"])


def index_tax_laws(laws: list[dict]):
    return get_search().index("tax_laws", laws,
                              fields=["title", "content", "tags", "category"])


def search_all(query: str, top_k: int = 20) -> dict:
    """跨集合搜索"""
    engine = get_search()
    results = {}
    for coll in engine.list_collections():
        results[coll] = engine.search(coll, query, top_k)
    return results
