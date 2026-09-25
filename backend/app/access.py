"""岗位与工区身份模型：监测报警按岗位分流的口径都收在这里。

账号不接真实登录，前端通过 X-Operator-Id 请求头带上当前账号；
未识别或缺失的身份按只读访客处理，任何改动都会被拦下并说明原因。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 高等级报警的等级取值：高等级一律由调度确认，工区值班无权确认。
HIGH_LEVEL = "高"

# 工区值班可确认的非高等级取值。
NORMAL_LEVELS = {"中", "低"}

ROLE_DUTY = "值班"
ROLE_DISPATCH = "调度"
ROLE_MAINTAIN = "检修"
ROLES = (ROLE_DUTY, ROLE_DISPATCH, ROLE_MAINTAIN)

WORKSITES = ("一工区", "二工区", "三工区")

# 触发设备 -> 所属工区。报警登记时若未直接给出工区，就按设备反查。
DEVICE_WORKSITE: dict[str, str] = {
    "XHJ-A01": "一工区",
    "ZZJ-A03": "一工区",
    "GDJL-A05": "一工区",
    "XHJ-B02": "二工区",
    "ZZJ-B07": "二工区",
    "GDJL-B02": "二工区",
    "LSB-C01": "三工区",
    "ATP-C03": "三工区",
}


@dataclass(frozen=True)
class Operator:
    """当前登录账号：角色决定可做的动作，工区决定能管哪些设备。"""

    operator_id: str
    name: str
    role: str
    worksite: str | None = None

    @property
    def is_duty(self) -> bool:
        return self.role == ROLE_DUTY

    @property
    def is_dispatch(self) -> bool:
        return self.role == ROLE_DISPATCH

    @property
    def is_maintain(self) -> bool:
        return self.role == ROLE_MAINTAIN

    @property
    def read_only(self) -> bool:
        return self.is_maintain


def _build_directory() -> dict[str, Operator]:
    # 每个工区给两个值班账号：确认与处置分开时，同一条报警必须能落到另一个值班身上。
    operators = [
        Operator("U1001", "张值班", ROLE_DUTY, "一工区"),
        Operator("U1005", "吴值班", ROLE_DUTY, "一工区"),
        Operator("U1002", "李值班", ROLE_DUTY, "二工区"),
        Operator("U1004", "周值班", ROLE_DUTY, "二工区"),
        Operator("U1003", "王值班", ROLE_DUTY, "三工区"),
        Operator("U2001", "陈调度", ROLE_DISPATCH),
        Operator("U3001", "赵检修", ROLE_MAINTAIN, "一工区"),
        Operator("U3002", "孙检修", ROLE_MAINTAIN, "二工区"),
    ]
    return {op.operator_id: op for op in operators}


DIRECTORY = _build_directory()

# 未带头或账号无法识别时的只读身份，所有写动作都会被拒。
ANONYMOUS = Operator("", "未识别身份", "访客")


def resolve_operator(operator_id: str | None) -> Operator:
    """按账号解析身份；识别不到时返回只读访客，而不是默认给高权限。"""
    if operator_id:
        operator = DIRECTORY.get(operator_id.strip())
        if operator is not None:
            return operator
    return ANONYMOUS


def operator_view(operator: Operator) -> dict[str, Any]:
    """账号目录的对外结构，给前端头部切换与按钮判权使用。"""
    return {
        "id": operator.operator_id,
        "name": operator.name,
        "role": operator.role,
        "worksite": operator.worksite,
        "readOnly": operator.read_only,
    }


def list_operators() -> list[dict[str, Any]]:
    return [operator_view(operator) for operator in DIRECTORY.values()]
