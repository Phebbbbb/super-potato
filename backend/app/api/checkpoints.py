"""检查点引擎 API — 查看/恢复/清理自动化运行状态"""
from fastapi import APIRouter, Depends
from app.services.auth import get_current_user
from app.services.automation_checkpoint import get_checkpoint_engine

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/checkpoints")
def list_checkpoints():
    """列出所有活跃的检查点运行"""
    engine = get_checkpoint_engine()
    runs = []
    for run_id, run in engine._runs.items():
        runs.append(run.to_dict())
    return {"runs": runs, "total": len(runs)}


@router.get("/checkpoints/stalled")
def list_stalled():
    """列出所有卡住的运行（超过10分钟未更新）"""
    engine = get_checkpoint_engine()
    return {"stalled": engine.list_stalled_runs()}


@router.post("/checkpoints/{run_id}/recover")
def recover_checkpoint(run_id: str):
    """从磁盘恢复指定的检查点运行"""
    engine = get_checkpoint_engine()
    run = engine.recover_run(run_id)
    if not run:
        return {"error": "运行不存在或已完成"}
    return {"recovered": run.to_dict()}
