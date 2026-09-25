"""监测报警接口：维护报警事件，覆盖确认报警、处置报警、忽略报警等动作。

所有列表与动作接口都按 X-Operator-Id 请求头解析当前账号；
缺账号时列表照常只读可见，动作会被服务端拒绝并说明原因。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.access import resolve_operator
from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.alarm import DISPLAY_FIELDS, MODULE, AlarmService

router = APIRouter(prefix="/api/alarm", tags=["监测报警"])

service = AlarmService()

LIST_FIELDS = DISPLAY_FIELDS


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按报警编号检索"),
    status: str | None = Query(default=None, description="待确认、已确认、已处置、已忽略"),
    scope: str | None = Query(default=None, description="mine 时只看我的报警，其余为全部（跨工区只读可见）"),
    page: int = 1,
    size: int = 20,
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> PageResult[dict]:
    """按报警编号与状态过滤监测报警列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    operator = resolve_operator(x_operator_id)
    items, total = service.list_entries(
        operator, keyword=keyword, status=status, scope=scope, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats/summary")
def stats_summary(
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> dict[str, Any]:
    """报警统计：今日报警、待确认、高等级、我的待确认；与列表同源实时计算。"""
    operator = resolve_operator(x_operator_id)
    return {"stats": service.stats(operator), "operator": operator.name}


@router.get("/export")
def export_entries(
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> dict[str, Any]:
    """导出监测报警清单：返回当前账号视角下的全量数据（含跨工区只读报警）。"""
    operator = resolve_operator(x_operator_id)
    items, total = service.list_entries(operator, page=1, size=10000)
    return {"module": MODULE, "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(
    entry_id: int,
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> dict:
    """读取单条报警事件明细；不存在时给出可读的错误说明。"""
    operator = resolve_operator(x_operator_id)
    entry = service.get_entry(entry_id, operator)
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
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> ActionResult:
    """对单条报警执行确认、处置、忽略；越权或状态不符会被拦下并在 message 里说明原因。"""
    operator = resolve_operator(x_operator_id)
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, operator, payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message)
    view = service.get_entry(entry_id, operator)
    return ActionResult(ok=True, message=message, entry=view)
