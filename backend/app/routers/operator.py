"""岗位账号目录接口：给前端头部提供可切换的值班/调度/检修账号。

演示环境不接真实登录：账号列表公开，写操作靠各业务接口校验 X-Operator-Id。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header

from app.access import list_operators, operator_view, resolve_operator

router = APIRouter(prefix="/api/operators", tags=["岗位账号"])


@router.get("")
def list_directory() -> dict[str, Any]:
    """返回全部岗位账号：值班按工区分列、调度不绑工区、检修标注只读。"""
    return {"operators": list_operators()}


@router.get("/me")
def current_operator(
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> dict[str, Any]:
    """按请求头解析当前账号；未识别时返回只读访客。"""
    return operator_view(resolve_operator(x_operator_id))
