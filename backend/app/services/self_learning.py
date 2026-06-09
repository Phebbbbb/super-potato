"""
自学习纠错引擎 — 从人工修正中学习，自动纠错新数据

三级智能：
  L1 精确匹配 — 同供应商 + 同字段 → 直接复用修正
  L2 模糊匹配 — 相似上下文 + 相似值 → 建议修正
  L3 规律归纳 — 高频修正模式 → 通用规则

置信度分级：
  ≥0.95 静默自动修正（不出现在复审列表）
  ≥0.80 自动修正但标记复审
  <0.80  仅生成建议，不自动修正
"""
import json
import uuid
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional
from collections import defaultdict, Counter
from sqlalchemy.orm import Session
from app.models.correction_learning import CorrectionRecord, LearnedPattern


def record_correction(
    db: Session,
    target_type: str,
    target_id: str,
    field_path: str,
    original_value: str,
    corrected_value: str,
    context: dict = None,
    operator: str = "",
) -> CorrectionRecord:
    """记录一次人工修正 → 这是引擎学习的原料"""
    rec = CorrectionRecord(
        id=str(uuid.uuid4()),
        target_type=target_type,
        target_id=target_id,
        field_path=field_path,
        original_value=str(original_value),
        corrected_value=str(corrected_value),
        context_json=json.dumps(context or {}, ensure_ascii=False),
        operator=operator,
    )
    db.add(rec)
    # 每积累 10 条同类型修正 → 触发一次模式归纳
    count = db.query(CorrectionRecord).filter(
        CorrectionRecord.target_type == target_type
    ).count()
    if count % 10 == 0:
        _induce_patterns(db, target_type)
    return rec


def auto_correct(
    db: Session,
    target_type: str,
    field_path: str,
    value: str,
    context: dict = None,
) -> dict:
    """
    对一条新数据尝试自动纠错

    返回:
      {"corrected": str, "confidence": float, "pattern_name": str, "auto_applied": bool}

    auto_applied:
      True  → 高置信度静默修正
      "review" → 修正但需复审
      False → 仅建议，不自动修正
    """
    context = context or {}
    patterns = db.query(LearnedPattern).filter(
        LearnedPattern.pattern_type == target_type,
        LearnedPattern.confidence >= 0.5,
    ).order_by(LearnedPattern.confidence.desc()).all()

    best_result = {"corrected": value, "confidence": 0, "pattern_name": "", "auto_applied": False}

    for p in patterns:
        try:
            conditions = json.loads(p.conditions_json) if p.conditions_json else {}
        except Exception:
            continue

        if not _match_conditions(conditions, field_path, value, context):
            continue

        try:
            action = json.loads(p.action_json) if p.action_json else {}
        except Exception:
            continue

        corrected = _apply_action(action, value, context)
        if corrected is None or corrected == value:
            continue

        if p.confidence > best_result["confidence"]:
            auto = False
            if p.confidence >= 0.95:
                auto = True
            elif p.confidence >= 0.80:
                auto = "review"
            best_result = {
                "corrected": corrected,
                "confidence": p.confidence,
                "pattern_name": p.name,
                "auto_applied": auto,
            }

    # 如果模式匹配未命中，尝试基于相似值的模糊纠错
    if best_result["confidence"] < 0.8:
        fuzzy = _fuzzy_correct(db, target_type, field_path, value, context)
        if fuzzy["confidence"] > best_result["confidence"]:
            best_result = fuzzy

    return best_result


def _match_conditions(conditions: dict, field_path: str, value: str, context: dict) -> bool:
    """检查条件是否匹配"""
    # 字段路径匹配
    if conditions.get("field_path"):
        if conditions["field_path"] != field_path:
            return False

    # 值模式匹配（正则）
    if conditions.get("value_pattern"):
        try:
            if not re.search(conditions["value_pattern"], str(value)):
                return False
        except re.error:
            pass

    # 上下文精确匹配
    for key, expected in conditions.get("context_exact", {}).items():
        actual = str(context.get(key, ""))
        if actual and expected and actual != expected:
            return False

    # 上下文模糊匹配（相似度阈值）
    for key, cfg in conditions.get("context_fuzzy", {}).items():
        actual = str(context.get(key, ""))
        expected = cfg.get("value", "")
        threshold = cfg.get("threshold", 0.7)
        if actual and expected:
            if SequenceMatcher(None, actual, expected).ratio() < threshold:
                return False

    # 数值范围匹配
    for key, rng in conditions.get("numeric_range", {}).items():
        actual = context.get(key)
        if actual is not None:
            try:
                actual = float(actual)
                lo = rng.get("min")
                hi = rng.get("max")
                if lo is not None and actual < lo:
                    return False
                if hi is not None and actual > hi:
                    return False
            except (ValueError, TypeError):
                pass

    return True


def _apply_action(action: dict, value: str, context: dict) -> Optional[str]:
    """执行纠错动作"""
    action_type = action.get("type", "")

    if action_type == "replace":
        # 直接替换为固定值
        return action.get("value", value)

    elif action_type == "regex_sub":
        # 正则替换
        try:
            pattern = action.get("pattern", "")
            replacement = action.get("replacement", "")
            return re.sub(pattern, replacement, str(value))
        except re.error:
            return None

    elif action_type == "trim_whitespace":
        return str(value).strip()

    elif action_type == "normalize_number":
        # 数字标准化: 全角→半角, 去千分位, 中文数字→阿拉伯
        result = str(value)
        # 全角数字→半角
        trans = str.maketrans("０１２３４５６７８９．－", "0123456789.-")
        result = result.translate(trans)
        # 去千分位逗号
        result = result.replace(",", "").replace("，", "")
        return result

    elif action_type == "map_value":
        # 值映射: {"映射表": {"原值": "新值"}}
        mapping = action.get("mapping", {})
        return mapping.get(str(value), value)

    elif action_type == "template_fill":
        # 从上下文填充模板
        template = action.get("template", "{value}")
        vars_dict = {"value": value, **context}
        try:
            return template.format(**vars_dict)
        except (KeyError, ValueError):
            return value

    return value


def _fuzzy_correct(db: Session, target_type: str, field_path: str, value: str, context: dict) -> dict:
    """基于历史修正记录的模糊匹配纠错"""
    records = db.query(CorrectionRecord).filter(
        CorrectionRecord.target_type == target_type,
        CorrectionRecord.field_path == field_path,
        CorrectionRecord.original_value != "",
    ).order_by(CorrectionRecord.created_at.desc()).limit(200).all()

    best = {"corrected": value, "confidence": 0, "pattern_name": "fuzzy_match", "auto_applied": False}

    for rec in records:
        # 原值相似度
        val_sim = SequenceMatcher(None, str(value), rec.original_value).ratio()
        if val_sim < 0.6:
            continue

        # 上下文相似度
        ctx_sim = 1.0
        try:
            rec_ctx = json.loads(rec.context_json) if rec.context_json else {}
        except Exception:
            rec_ctx = {}

        if context and rec_ctx:
            common_keys = set(context.keys()) & set(rec_ctx.keys())
            if common_keys:
                sims = []
                for k in common_keys:
                    sims.append(SequenceMatcher(None, str(context[k]), str(rec_ctx[k])).ratio())
                ctx_sim = sum(sims) / len(sims) if sims else 1.0

        # 综合置信度 = 值相似度 * 0.6 + 上下文相似度 * 0.4
        confidence = val_sim * 0.6 + ctx_sim * 0.4

        if confidence > best["confidence"]:
            best["corrected"] = rec.corrected_value
            best["confidence"] = min(confidence, 0.85)  # 模糊匹配最多 0.85
            if confidence >= 0.90:
                best["auto_applied"] = "review"
            else:
                best["auto_applied"] = False

    return best


def _induce_patterns(db: Session, target_type: str):
    """从修正记录中归纳模式"""
    records = db.query(CorrectionRecord).filter(
        CorrectionRecord.target_type == target_type
    ).order_by(CorrectionRecord.created_at.desc()).limit(200).all()

    if len(records) < 5:
        return

    # 按 field_path 分组
    by_field = defaultdict(list)
    for r in records:
        by_field[r.field_path].append(r)

    for field_path, field_recs in by_field.items():
        if len(field_recs) < 3:
            continue

        # 策略1: 精确值替换模式 (同一原值被修正为同一目标值 ≥3 次)
        exact_counter = Counter()
        for r in field_recs:
            key = (r.original_value, r.corrected_value)
            exact_counter[key] += 1

        for (orig, corr), cnt in exact_counter.items():
            if cnt >= 3 and orig and corr and orig != corr:
                _upsert_pattern(
                    db, target_type,
                    name=f"{field_path}: '{orig}' → '{corr}'",
                    conditions={"field_path": field_path, "context_exact": {}},
                    action={"type": "map_value", "mapping": {orig: corr}},
                    confidence=min(0.7 + cnt * 0.05, 0.98),
                )

        # 策略2: 供应商模板模式 (同一供应商 + 同字段的修正)
        vendor_patterns = defaultdict(list)
        for r in field_recs:
            try:
                ctx = json.loads(r.context_json) if r.context_json else {}
            except Exception:
                ctx = {}
            vendor = ctx.get("vendor_name") or ctx.get("supplier_name", "")
            if vendor:
                vendor_patterns[vendor].append(r)

        for vendor, vrecs in vendor_patterns.items():
            if len(vrecs) < 2:
                continue
            for r in vrecs:
                orig = r.original_value
                corr = r.corrected_value
                if orig and corr and orig != corr:
                    _upsert_pattern(
                        db, target_type,
                        name=f"供应商'{vendor}' {field_path} 修正",
                        conditions={
                            "field_path": field_path,
                            "context_fuzzy": {
                                "vendor_name": {"value": vendor, "threshold": 0.8}
                            },
                        },
                        action={"type": "map_value", "mapping": {orig: corr}},
                        confidence=0.80,
                    )

        # 策略3: 正则规律归纳 (OCR常见错字模式)
        ocr_mistakes = defaultdict(int)
        for r in field_recs:
            orig = r.original_value
            corr = r.corrected_value
            if len(orig) == 1 and len(corr) == 1 and orig != corr:
                ocr_mistakes[(orig, corr)] += 1
            elif orig and corr:
                # 单字符差异
                diff = _single_char_diff(orig, corr)
                if diff:
                    ocr_mistakes[diff] += 1

        for (wrong, right), cnt in ocr_mistakes.items():
            if cnt >= 3:
                _upsert_pattern(
                    db, target_type,
                    name=f"OCR纠错: '{wrong}' → '{right}'",
                    conditions={"field_path": field_path, "value_pattern": re.escape(wrong)},
                    action={"type": "regex_sub", "pattern": re.escape(wrong), "replacement": right},
                    confidence=min(0.65 + cnt * 0.05, 0.90),
                )


def _single_char_diff(a: str, b: str) -> Optional[tuple]:
    """检测两个字符串是否只有1个字符差异，返回 (错误字符, 正确字符)"""
    if abs(len(a) - len(b)) > 1:
        return None
    diffs = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            diffs.append((a[i] if i < len(a) else "", b[j] if j < len(b) else ""))
            if len(a) > len(b):
                i += 1
            elif len(b) > len(a):
                j += 1
            else:
                i += 1
                j += 1
        else:
            i += 1
            j += 1
        if len(diffs) > 1:
            return None
    return diffs[0] if len(diffs) == 1 else None


def _upsert_pattern(db: Session, pattern_type: str, name: str, conditions: dict, action: dict, confidence: float):
    """插入或更新模式"""
    existing = db.query(LearnedPattern).filter(
        LearnedPattern.pattern_type == pattern_type,
        LearnedPattern.name == name,
    ).first()

    if existing:
        existing.conditions_json = json.dumps(conditions, ensure_ascii=False)
        existing.action_json = json.dumps(action, ensure_ascii=False)
        existing.confidence = min((existing.confidence + confidence) / 2, 0.99)
        existing.match_count += 1
        existing.updated_at = datetime.utcnow()
    else:
        p = LearnedPattern(
            id=str(uuid.uuid4()),
            pattern_type=pattern_type,
            name=name,
            conditions_json=json.dumps(conditions, ensure_ascii=False),
            action_json=json.dumps(action, ensure_ascii=False),
            confidence=confidence,
            match_count=1,
        )
        db.add(p)


def record_pattern_success(db: Session, pattern_id: str):
    """记录一次模式自动纠错被采纳"""
    p = db.query(LearnedPattern).filter(LearnedPattern.id == pattern_id).first()
    if p:
        p.success_count += 1
        p.confidence = min(p.confidence + 0.02, 0.99)
        p.last_applied_at = datetime.utcnow()


def get_learning_stats(db: Session) -> dict:
    """获取自学习统计"""
    total_corrections = db.query(CorrectionRecord).count()
    total_patterns = db.query(LearnedPattern).count()
    patterns_by_type = {}
    for p in db.query(LearnedPattern).all():
        patterns_by_type.setdefault(p.pattern_type, {"count": 0, "avg_confidence": 0, "total_success": 0})
        patterns_by_type[p.pattern_type]["count"] += 1
        patterns_by_type[p.pattern_type]["avg_confidence"] += p.confidence
        patterns_by_type[p.pattern_type]["total_success"] += p.success_count

    for t in patterns_by_type:
        cnt = patterns_by_type[t]["count"]
        patterns_by_type[t]["avg_confidence"] = round(patterns_by_type[t]["avg_confidence"] / cnt, 3) if cnt else 0

    # 计算潜在自动化提升
    high_conf_patterns = db.query(LearnedPattern).filter(LearnedPattern.confidence >= 0.80).count()
    auto_saved = db.query(LearnedPattern).filter(LearnedPattern.confidence >= 0.95).count()

    return {
        "total_corrections_recorded": total_corrections,
        "total_patterns_learned": total_patterns,
        "high_confidence_patterns": high_conf_patterns,
        "fully_auto_patterns": auto_saved,
        "patterns_by_type": patterns_by_type,
        "estimated_manual_savings_pct": min(round(auto_saved / max(total_patterns, 1) * 100, 1), 99),
    }
