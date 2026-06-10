"""
自动化流程工作流引擎 — 节点化执行 + 可回溯修改

每个自动化任务被拆分为多个节点（Node），用户可以：
1. 查看每个节点的执行状态和输出
2. 回到任意已完成的节点修改参数
3. 从任意节点重新执行
4. 最终确认后统一提交
"""
import json
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_HUMAN = "needs_human"  # 需要人工介入


@dataclass
class WorkflowNode:
    """工作流节点"""
    id: str
    name: str                      # 节点名称（用户可见）
    description: str = ""          # 节点描述
    status: NodeStatus = NodeStatus.PENDING
    inputs: dict = field(default_factory=dict)    # 节点输入参数
    outputs: dict = field(default_factory=dict)    # 节点输出结果
    screenshots: list[str] = field(default_factory=list)
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    editable: bool = True          # 是否允许用户修改后重跑
    retry_count: int = 0
    max_retries: int = 3


# ===== 预定义工作流模板 =====

WORKFLOW_TEMPLATES: dict[str, list[dict]] = {
    "annual_report": [
        {
            "id": "search_company",
            "name": "搜索企业",
            "description": "在国家企业信用信息公示系统搜索目标企业",
            "editable": True,
            "inputs_schema": {"company_name": "企业名称"},
        },
        {
            "id": "verify_company",
            "name": "核实企业信息",
            "description": "确认企业名称、统一社会信用代码等信息无误",
            "editable": True,
            "inputs_schema": {"company_name": "企业名称", "tax_no": "统一社会信用代码"},
        },
        {
            "id": "select_year",
            "name": "选择年报年份",
            "description": "选择需要填报的工商年报所属年度",
            "editable": True,
            "inputs_schema": {"year": "年报年份"},
        },
        {
            "id": "fill_financials",
            "name": "填报财务数据",
            "description": "填入营业收入、利润、资产、纳税、人数、负债、权益等",
            "editable": True,
            "inputs_schema": {
                "revenue": "营业收入（万元）",
                "profit": "利润总额（万元）",
                "assets": "资产总额（万元）",
                "tax_total": "纳税总额（万元）",
                "employees": "从业人数",
                "liabilities": "负债总额（万元）",
                "equity": "所有者权益（万元）",
            },
        },
        {
            "id": "fill_shareholder",
            "name": "填报股东出资信息",
            "description": "填入各股东认缴/实缴出资额及出资时间",
            "editable": True,
            "inputs_schema": {"shareholders": "股东出资信息"},
        },
        {
            "id": "fill_social_security",
            "name": "填报社保信息",
            "description": "填入参保人数、缴费基数等社保信息",
            "editable": True,
            "inputs_schema": {"insured_count": "参保人数", "social_base": "社保缴费基数"},
        },
        {
            "id": "preview",
            "name": "预览确认",
            "description": "预览已填报的年报全部内容，确认无误",
            "editable": False,  # 预览后只能确认或返回修改
        },
        {
            "id": "submit",
            "name": "提交公示",
            "description": "⚠️ 正式提交工商年报（提交后不可撤回）",
            "editable": False,
            "needs_human": True,  # 必须人工确认
        },
    ],
    "registration": [
        {
            "id": "name_verification",
            "name": "企业名称核名",
            "description": "在市场监管局系统进行名称预先核准",
            "editable": True,
            "inputs_schema": {"company_name": "拟用企业名称"},
        },
        {
            "id": "fill_basic_info",
            "name": "填写基本信息",
            "description": "住所、法定代表人、注册资本、经营范围等",
            "editable": True,
            "inputs_schema": {
                "address": "住所",
                "legal_person": "法定代表人",
                "registered_capital": "注册资本",
                "business_scope": "经营范围",
            },
        },
        {
            "id": "fill_shareholders",
            "name": "填写股东信息",
            "description": "各股东出资比例、出资方式、出资时间",
            "editable": True,
            "inputs_schema": {"shareholders": "股东信息"},
        },
        {
            "id": "fill_personnel",
            "name": "填写高管信息",
            "description": "法定代表人、董事、监事、经理任职信息",
            "editable": True,
            "inputs_schema": {"legal_person": "法定代表人", "directors": "董事", "supervisors": "监事", "manager": "经理"},
        },
        {
            "id": "upload_docs",
            "name": "上传材料",
            "description": "上传章程、住所证明、身份证明等材料",
            "editable": True,
            "inputs_schema": {"documents": "上传文件列表"},
        },
        {
            "id": "preview",
            "name": "预览确认",
            "description": "预览全部注册材料，确认提交",
            "editable": False,
        },
        {
            "id": "submit",
            "name": "提交工商登记",
            "description": "⚠️ 正式提交公司注册申请",
            "editable": False,
            "needs_human": True,
        },
    ],
    "deregistration": [
        {
            "id": "check_eligibility",
            "name": "检查注销条件",
            "description": "确认是否符合简易注销条件",
            "editable": True,
            "inputs_schema": {"company_name": "企业名称", "tax_no": "统一社会信用代码"},
        },
        {
            "id": "tax_clearance",
            "name": "税务清税",
            "description": "确认所有税款已结清，取得清税证明",
            "editable": True,
            "inputs_schema": {"tax_cleared": "税款是否已结清", "clearance_cert": "清税证明编号"},
        },
        {
            "id": "fill_liquidation",
            "name": "填写清算信息",
            "description": "清算组信息、债权人公告情况",
            "editable": True,
        },
        {
            "id": "fill_dereg_form",
            "name": "填写注销申请",
            "description": "填写企业注销登记申请书",
            "editable": True,
            "inputs_schema": {"reason": "注销原因", "debt_cleared": "债务是否已清偿"},
        },
        {
            "id": "preview",
            "name": "预览确认",
            "description": "预览注销材料",
            "editable": False,
        },
        {
            "id": "submit",
            "name": "提交注销申请",
            "description": "⚠️ 正式提交公司注销申请（不可逆）",
            "editable": False,
            "needs_human": True,
        },
    ],
    "equity": [
        {
            "id": "fill_transfer",
            "name": "填写转让信息",
            "description": "转让方、受让方、转让比例、转让价格",
            "editable": True,
            "inputs_schema": {
                "from_person": "转让方",
                "to_person": "受让方",
                "ratio": "转让比例",
                "amount": "转让金额",
            },
        },
        {
            "id": "tax_calc",
            "name": "税务计算",
            "description": "计算股权转让应缴个人所得税",
            "editable": True,
            "inputs_schema": {"transfer_amount": "转让收入", "original_cost": "原值", "expenses": "合理费用"},
        },
        {
            "id": "fill_resolution",
            "name": "填写决议信息",
            "description": "股东会决议、章程修正案",
            "editable": True,
        },
        {
            "id": "preview",
            "name": "预览确认",
            "description": "预览股权变更全部材料",
            "editable": False,
        },
        {
            "id": "submit",
            "name": "提交变更申请",
            "description": "⚠️ 正式提交股权变更登记",
            "editable": False,
            "needs_human": True,
        },
    ],
}


# ===== 工作流实例管理 =====

# 内存存储（生产环境应迁移至数据库）
_instances: dict[str, dict] = {}
STORAGE_DIR = Path(__file__).parent.parent.parent / "data" / "workflows"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def create_workflow(task_type: str, initial_inputs: dict = None, operator: str = "") -> str:
    """创建新的工作流实例，返回 instance_id"""
    template = WORKFLOW_TEMPLATES.get(task_type)
    if not template:
        raise ValueError(f"未知工作流类型: {task_type}")

    instance_id = uuid.uuid4().hex[:12]
    nodes = []
    for tpl in template:
        node = WorkflowNode(
            id=tpl["id"],
            name=tpl["name"],
            description=tpl.get("description", ""),
            editable=tpl.get("editable", True),
            max_retries=tpl.get("max_retries", 3),
        )
        nodes.append(node)

    instance = {
        "id": instance_id,
        "task_type": task_type,
        "nodes": nodes,
        "current_node_index": 0,
        "status": "pending",
        "operator": operator,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": initial_inputs or {},
        "final_result": None,
    }
    _instances[instance_id] = instance
    _save_instance(instance)
    return instance_id


def get_workflow(instance_id: str) -> dict | None:
    """获取工作流实例"""
    if instance_id in _instances:
        return _instances[instance_id]
    return _load_instance(instance_id)


def update_node(instance_id: str, node_id: str, inputs: dict) -> dict:
    """
    更新指定节点的输入参数，并将该节点及之后所有节点重置为 PENDING
    这样用户可以回到任意节点修改数据后重新执行
    """
    instance = get_workflow(instance_id)
    if not instance:
        raise ValueError(f"工作流实例不存在: {instance_id}")

    found = False
    for i, node in enumerate(instance["nodes"]):
        if node.id == node_id:
            found = True
            # 更新该节点的输入
            node.inputs.update(inputs)
            node.status = NodeStatus.PENDING
            node.outputs = {}
            node.error = ""
            node.screenshots = []
            # 重置该节点之后的所有节点
            for j in range(i, len(instance["nodes"])):
                if j > i:
                    instance["nodes"][j].status = NodeStatus.PENDING
                    instance["nodes"][j].outputs = {}
                    instance["nodes"][j].error = ""
                    instance["nodes"][j].screenshots = []
            instance["current_node_index"] = i
            instance["status"] = "editing"
            break

    if not found:
        raise ValueError(f"节点不存在: {node_id}")

    _save_instance(instance)
    return _instance_to_dict(instance)


def advance_node(instance_id: str, node_id: str, outputs: dict = None,
                 screenshots: list = None, success: bool = True, error: str = "") -> dict:
    """标记节点完成，推进到下一个节点"""
    instance = get_workflow(instance_id)
    if not instance:
        raise ValueError(f"工作流实例不存在: {instance_id}")

    now = datetime.now(timezone.utc).isoformat()
    for node in instance["nodes"]:
        if node.id == node_id:
            if success:
                node.status = NodeStatus.COMPLETED
                node.outputs = outputs or {}
                node.screenshots = screenshots or []
                node.completed_at = now
            else:
                node.status = NodeStatus.FAILED
                node.error = error
                if node.retry_count < node.max_retries:
                    node.retry_count += 1

    # 推进 current_node_index
    for i, node in enumerate(instance["nodes"]):
        if node.id == node_id and node.status == NodeStatus.COMPLETED:
            if i + 1 < len(instance["nodes"]):
                instance["current_node_index"] = i + 1
                instance["nodes"][i + 1].status = NodeStatus.RUNNING
                instance["nodes"][i + 1].started_at = now
            else:
                instance["status"] = "all_nodes_complete"
            break

    _save_instance(instance)
    return _instance_to_dict(instance)


def mark_needs_human(instance_id: str, node_id: str, reason: str = "") -> dict:
    """标记节点需要人工审核"""
    instance = get_workflow(instance_id)
    if not instance:
        raise ValueError(f"工作流实例不存在: {instance_id}")

    for node in instance["nodes"]:
        if node.id == node_id:
            node.status = NodeStatus.NEEDS_HUMAN
            node.error = reason
            break

    instance["status"] = "needs_human_review"
    _save_instance(instance)
    return _instance_to_dict(instance)


def submit_workflow(instance_id: str) -> dict:
    """最终提交工作流"""
    instance = get_workflow(instance_id)
    if not instance:
        raise ValueError(f"工作流实例不存在: {instance_id}")

    # 检查所有节点是否完成
    incomplete = [n.name for n in instance["nodes"]
                  if n.status not in (NodeStatus.COMPLETED, NodeStatus.SKIPPED)]
    if incomplete:
        raise ValueError(f"以下节点尚未完成: {', '.join(incomplete)}")

    # 检查最后一个节点是否已人工确认
    last_node = instance["nodes"][-1]
    if last_node.status != NodeStatus.COMPLETED:
        raise ValueError("最后一步需要人工确认后才能提交")

    instance["status"] = "submitted"
    instance["final_result"] = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "nodes_completed": sum(1 for n in instance["nodes"] if n.status == NodeStatus.COMPLETED),
    }
    _save_instance(instance)
    return _instance_to_dict(instance)


def list_workflows(task_type: str = None) -> list[dict]:
    """列出工作流实例"""
    result = []
    for iid in list(_instances.keys()):
        inst = _instances[iid]
        if task_type and inst["task_type"] != task_type:
            continue
        result.append(_instance_to_dict(inst))
    return result


def _instance_to_dict(instance: dict) -> dict:
    """将工作流实例转换为可序列化的字典"""
    return {
        "id": instance["id"],
        "task_type": instance["task_type"],
        "status": instance["status"],
        "operator": instance.get("operator", ""),
        "current_node_index": instance.get("current_node_index", 0),
        "created_at": instance.get("created_at", ""),
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "description": n.description,
                "status": n.status.value if isinstance(n.status, NodeStatus) else n.status,
                "inputs": n.inputs,
                "outputs": n.outputs,
                "screenshots": n.screenshots,
                "error": n.error,
                "editable": n.editable,
                "retry_count": n.retry_count,
                "started_at": n.started_at,
                "completed_at": n.completed_at,
            }
            for n in instance.get("nodes", [])
        ],
    }


def _save_instance(instance: dict):
    """持久化工作流实例"""
    path = STORAGE_DIR / f"{instance['id']}.json"
    path.write_text(
        json.dumps(_instance_to_dict(instance), ensure_ascii=False, indent=2),
        "utf-8",
    )


def _load_instance(instance_id: str) -> dict | None:
    """从磁盘加载工作流实例"""
    path = STORAGE_DIR / f"{instance_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
        # 重建 WorkflowNode 对象
        nodes = []
        for nd in data.get("nodes", []):
            node = WorkflowNode(
                id=nd["id"],
                name=nd["name"],
                description=nd.get("description", ""),
                status=NodeStatus(nd["status"]),
                inputs=nd.get("inputs", {}),
                outputs=nd.get("outputs", {}),
                screenshots=nd.get("screenshots", []),
                error=nd.get("error", ""),
                editable=nd.get("editable", True),
                retry_count=nd.get("retry_count", 0),
                started_at=nd.get("started_at", ""),
                completed_at=nd.get("completed_at", ""),
            )
            nodes.append(node)
        data["nodes"] = nodes
        _instances[instance_id] = data
        return data
    except Exception:
        return None
