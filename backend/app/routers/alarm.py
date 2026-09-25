"""监测报警接口：维护报警事件，覆盖确认报警、处置报警、忽略报警等动作。

岗位身份通过请求头传递（顶栏切换账号时写入）：
- X-Operator-Role：值班员 / 调度 / 检修人员
- X-Operator-Zone：值班员所属工区
- X-Operator-Name：账号显示名，用于同一账号动作互斥校验
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.alarm import ROLES, Actor, AlarmService
from app.store import store

router = APIRouter(prefix="/api/alarm", tags=["监测报警"])

service = AlarmService()

LIST_FIELDS = ["报警编号", "报警类型", "报警等级", "触发设备", "触发时间", "确认人员", "处置说明", "报警状态"]
STATUSES = ["待确认", "已确认", "已处置", "已忽略"]


def resolve_actor(
    role: str | None,
    zone: str | None,
    name: str | None,
) -> Actor:
    """读取请求头上的登录身份；缺省时按本工区值班员处理，未知岗位直接拒绝。"""
    role = (role or "值班员").strip()
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"未知岗位「{role}」，合法岗位：{'、'.join(ROLES)}")
    return Actor(role=role, zone=(zone or "一工区").strip(), operator=(name or "值班管理员").strip())


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按报警编号检索"),
    status: str | None = Query(default=None, description="待确认、已确认、已处置、已忽略"),
    mine: bool = Query(default=False, description="只看归属于当前岗位/工区的报警"),
    page: int = 1,
    size: int = 20,
    x_operator_role: str | None = Header(default=None),
    x_operator_zone: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> PageResult[dict]:
    """按报警编号与状态过滤监测报警列表；没有数据时返回空页，不报错。

    返回行带归属标签与每个动作的可执行口径，前端据此禁用越权按钮并说明原因。
    """
    actor = resolve_actor(x_operator_role, x_operator_zone, x_operator_name)
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        actor, keyword=keyword, status=status, mine=mine, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats", response_model=dict)
def alarm_stats(
    x_operator_role: str | None = Header(default=None),
    x_operator_zone: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> dict[str, int]:
    """待确认数量按岗位口径统计；确认/忽略后前端重拉，与列表保持同步。"""
    actor = resolve_actor(x_operator_role, x_operator_zone, x_operator_name)
    return service.statistics(actor)


@router.get("/{entry_id}", response_model=dict)
def get_entry(
    entry_id: int,
    x_operator_role: str | None = Header(default=None),
    x_operator_zone: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> dict:
    """读取单条报警事件明细；不存在时给出可读的错误说明。"""
    actor = resolve_actor(x_operator_role, x_operator_zone, x_operator_name)
    entry = service.get_entry(entry_id, actor)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"报警事件 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条报警事件，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="报警事件已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
    x_operator_zone: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> ActionResult:
    """对单条报警事件执行确认报警、处置报警、忽略报警；不允许的动作会被拦下并说明原因。"""
    actor = resolve_actor(x_operator_role, x_operator_zone, x_operator_name)
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, actor, payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出监测报警清单：返回全量源数据（不带岗位视图口径）。"""
    rows = store.rows("alarm")
    return {"module": "alarm", "total": len(rows), "items": rows}
