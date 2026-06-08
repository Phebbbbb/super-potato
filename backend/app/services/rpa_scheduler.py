"""RPA 调度服务：轮询 RPA 平台、下发任务、接收回调"""
import json
import httpx
from sqlalchemy.orm import Session
from app.models.rpa_task import RPATask
from app.config import settings


class RPAScheduler:
    """RPA 任务调度器"""

    def __init__(self, db: Session, rpa_config: dict):
        self.db = db
        self.config = rpa_config  # {vendor, webhook_url, api_key, poll_interval}

    async def dispatch_task(self, task: RPATask) -> bool:
        """将待处理任务推送给 RPA 平台"""
        payload = {
            "task_id": task.id,
            "task_type": task.task_type,
            "payload": json.loads(task.payload) if task.payload else {},
            "callback_url": f"{settings.base_url}/api/rpa/tasks/{task.id}",
            "api_key": self.config.get("api_key", ""),
        }

        vendor = self.config.get("vendor", "generic")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if vendor == "yingdao":
                    return await self._dispatch_yingdao(client, payload)
                elif vendor == "laiye":
                    return await self._dispatch_laiye(client, payload)
                else:
                    return await self._dispatch_generic(client, payload)
        except Exception as e:
            task.status = "failed"
            task.error_message = f"RPA 调度失败: {str(e)}"
            self.db.commit()
            return False

    async def _dispatch_yingdao(self, client: httpx.AsyncClient, payload: dict) -> bool:
        """影刀 RPA 调用方式：通过 HTTP 触发机器人流程"""
        url = self.config.get("webhook_url", "")
        if not url:
            return False

        resp = await client.post(url, json={
            "robot_name": payload["task_type"],
            "input_data": json.dumps(payload, ensure_ascii=False),
        })
        return resp.status_code == 200

    async def _dispatch_laiye(self, client: httpx.AsyncClient, payload: dict) -> bool:
        """来也 RPA 调用方式：通过 OpenAPI 触发"""
        url = f"{self.config.get('webhook_url', '')}/api/v1/trigger"
        resp = await client.post(
            url,
            json={"process_code": payload["task_type"], "params": payload},
            headers={"Authorization": f"Bearer {self.config.get('api_key', '')}"},
        )
        return resp.status_code == 200

    async def _dispatch_generic(self, client: httpx.AsyncClient, payload: dict) -> bool:
        """
        通用 RPA 调用方式：
        RPA 机器人轮询 GET /api/rpa/tasks 获取任务，
        执行完成后 POST/PATCH 回写结果。
        这种方式最简单，任何 RPA 工具都支持，
        只需要在 RPA 流程中加一个 HTTP 请求步骤。
        """
        # 通用模式不需要主动推送，RPA 自己来拉取
        # 只需确保任务状态为 pending 即可
        return True

    async def auto_dispatch_pending(self):
        """自动下发所有待处理任务"""
        tasks = self.db.query(RPATask).filter(RPATask.status == "pending").all()

        results = []
        for task in tasks:
            task.status = "assigned"
            self.db.commit()

            success = await self.dispatch_task(task)
            if success:
                task.status = "processing"
                results.append({"task_id": task.id, "status": "dispatched"})
            else:
                results.append({"task_id": task.id, "status": "failed"})

            self.db.commit()

        return results


async def call_rpa_webhook(webhook_url: str, payload: dict, api_key: str = "") -> dict:
    """直接调用 RPA Webhook"""
    async with httpx.AsyncClient(timeout=60) as client:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"

        resp = await client.post(webhook_url, json=payload, headers=headers)
        return {"status_code": resp.status_code, "body": resp.text}
