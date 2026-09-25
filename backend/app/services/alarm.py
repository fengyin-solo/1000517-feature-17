"""监测报警业务规则：状态流转、岗位分流与职责分离的口径都收在这里。

分流口径（确认环节）：
- 值班：只能确认本工区设备触发的非高等级报警；
- 调度：高等级报警只能由调度确认；
- 检修：全程只读，只能查看不能改动。

处置环节与确认环节角色分离：处置报警不能由本条报警的确认人执行。
同一账号也不能既确认又忽略同一条：忽略只允许在「待确认」阶段进行，
一旦该账号已确认，报警离开待确认，忽略通道即关闭。
跨工区报警对所有人只读可见，越权确认会带着原因拒绝。
"""
from __future__ import annotations

from typing import Any

from app.access import (
    ANONYMOUS,
    HIGH_LEVEL,
    DEVICE_WORKSITE,
    Operator,
)
from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["报警编号", "报警类型", "报警等级", "触发设备", "触发时间"]
STATUS_ORDER = ["待确认", "已确认", "已处置", "已忽略"]
ACTION_RULES = {"确认报警": "已确认", "处置报警": "已处置", "忽略报警": "已忽略"}
NEGATIVE_ACTIONS = ["忽略报警"]

CONFIRM_ACTION = "确认报警"
DISPOSE_ACTION = "处置报警"
IGNORE_ACTION = "忽略报警"

DISPLAY_FIELDS = [
    "报警编号", "报警类型", "报警等级", "所属工区", "触发设备",
    "触发时间", "确认人员", "处置人员", "处置说明", "报警状态",
]


def _is_pending(entry: dict[str, Any]) -> bool:
    """待确认数量口径：只有「待确认」计入待确认。"""
    return entry.get("status") == STATUS_ORDER[0]


def _device_worksite(device: str) -> str:
    return DEVICE_WORKSITE.get(str(device), "")


def _is_high_level(entry: dict[str, Any]) -> bool:
    return str(entry.get("报警等级") or "").strip() == HIGH_LEVEL


def _entry_worksite(entry: dict[str, Any]) -> str:
    worksite = str(entry.get("所属工区") or "").strip()
    if worksite:
        return worksite
    return _device_worksite(str(entry.get("触发设备") or ""))


def _same_work_site(operator: Operator, entry: dict[str, Any]) -> bool:
    return bool(operator.worksite) and operator.worksite == _entry_worksite(entry)


def _confirm_operator_id(entry: dict[str, Any]) -> str:
    return str(entry.get("确认人ID") or "")


class AlarmService:
    # ---- 读取 ----------------------------------------------------------------

    def _view(self, entry: dict[str, Any], operator: Operator) -> dict[str, Any]:
        """给前端的行视图：补齐展示字段，并逐动作给出可执行性与拒绝原因。"""
        view = {field: entry.get(field) for field in DISPLAY_FIELDS}
        view["id"] = entry.get("id")
        view["status"] = entry.get("status")
        view["报警状态"] = entry.get("status")
        worksite = _entry_worksite(entry)
        view["所属工区"] = worksite
        view["跨工区"] = bool(worksite) and not _same_work_site(operator, entry)
        view["我的报警"] = self.is_mine(entry, operator)
        view["高等级"] = _is_high_level(entry)
        if not view.get("确认人员"):
            view["确认人员"] = "—"
        if not view.get("处置人员"):
            view["处置人员"] = "—"
        if not view.get("处置说明"):
            view["处置说明"] = "—"

        actions: dict[str, dict[str, Any]] = {}
        for action in ACTION_RULES:
            allowed, reason = self.check_action(entry, action, operator)
            actions[action] = {"allowed": allowed, "reason": reason}
        view["actions"] = actions
        return view

    def is_mine(self, entry: dict[str, Any], operator: Operator) -> bool:
        """「我的报警」归属口径，只取账号角色/工区与报警工区/等级，与是否已操作无关，
        因此确认之后、返回列表之后归属保持不变。"""
        if operator.is_duty:
            return _same_work_site(operator, entry)
        if operator.is_dispatch:
            return _is_high_level(entry)
        return False

    def list_entries(
        self,
        operator: Operator,
        *,
        keyword: str | None = None,
        status: str | None = None,
        scope: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """跨工区报警也出现在列表里（只读可见），scope=mine 时只保留我的归属。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("报警编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if scope == "mine":
            rows = [row for row in rows if self.is_mine(row, operator)]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self._view(row, operator) for row in page_rows], total

    def get_entry(self, entry_id: int, operator: Operator | None = None) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        if operator is None:
            return entry
        return self._view(entry, operator)

    def stats(self, operator: Operator) -> dict[str, int]:
        """确认之后待确认数量与列表同源同步，统计全部按当前仓库实时计算。"""
        rows = store.rows(MODULE)
        today_prefix = self._today_prefix()
        return {
            "今日报警": sum(1 for row in rows if str(row.get("触发时间") or "").startswith(today_prefix)),
            "待确认报警": sum(1 for row in rows if _is_pending(row)),
            "高等级报警": sum(1 for row in rows if _is_high_level(row)),
            "我的待确认": sum(
                1 for row in rows if _is_pending(row) and self.is_mine(row, operator)
            ),
        }

    @staticmethod
    def _today_prefix() -> str:
        """示例服务不引第三方时间库，直接取本机日期（与种子数据日期一致即可）。"""
        from datetime import date

        return date.today().isoformat()

    # ---- 写入 ----------------------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        worksite = str(values.get("所属工区") or "").strip() or _device_worksite(
            str(values.get("触发设备") or "")
        )
        if worksite:
            entry["所属工区"] = worksite
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["确认人ID"] = ""
        entry["处置人ID"] = ""
        rows.append(entry)
        return entry, []

    def check_action(
        self, entry: dict[str, Any], action: str, operator: Operator
    ) -> tuple[bool, str]:
        """判权：返回（是否可执行, 拒绝原因）。拒绝原因要能直接讲清「为什么不能点」。"""
        if action not in ACTION_RULES:
            return False, f"动作「{action}」不属于监测报警可执行范围"

        # 未识别身份：没有任何改动权限。
        if operator == ANONYMOUS or not operator.operator_id:
            return False, "当前身份未识别，请先在右上角选择值班账号"

        # 检修岗位：只能查看不能改动。
        if operator.is_maintain:
            return False, "检修岗位只有查看权限，确认、处置与忽略请联系值班或调度"

        status = str(entry.get("status") or "")
        worksite = _entry_worksite(entry)
        in_work_site = _same_work_site(operator, entry)

        if action == CONFIRM_ACTION:
            if status != STATUS_ORDER[0]:
                return False, f"报警状态已为{status}，不能重复确认"
            if operator.is_duty:
                if not worksite:
                    return False, "该报警未标注所属工区，值班无法按工区确认，请报调度核实"
                if not in_work_site:
                    return (
                        False,
                        f"越权确认被拒绝：该报警属于{worksite}，你只有{operator.worksite}的确认权限，"
                        "跨工区报警只读可见",
                    )
                if _is_high_level(entry):
                    return (
                        False,
                        "越权确认被拒绝：高等级报警由调度确认，工区值班无权确认",
                    )
                return True, ""
            if operator.is_dispatch:
                if not _is_high_level(entry):
                    return False, "该报警不是高等级，由所属工区值班确认，调度只确认高等级报警"
                return True, ""
            return False, "当前岗位不允许确认报警"

        if action == IGNORE_ACTION:
            # 职责分离：同一账号不能既确认又忽略同一条。确认后状态离开待确认，
            # 忽略通道关闭；这里再显式拦一道并点名账号。
            if _confirm_operator_id(entry) == operator.operator_id:
                return False, "确认与忽略的角色必须分开，你已确认本条报警，不能再忽略同一条"
            if status != STATUS_ORDER[0]:
                return False, f"报警状态已为{status}，仅待确认阶段可以忽略"
            # 忽略沿用确认的岗位分流口径（老的忽略动作照旧，只是按岗位把住入口）。
            if operator.is_duty:
                if not worksite:
                    return False, "该报警未标注所属工区，无法按工区判定忽略权限"
                if not in_work_site:
                    return (
                        False,
                        f"越权忽略被拒绝：该报警属于{worksite}，跨工区报警只读可见",
                    )
                if _is_high_level(entry):
                    return False, "高等级报警由调度负责，工区值班不能忽略"
                return True, ""
            if operator.is_dispatch:
                if not _is_high_level(entry):
                    return False, "该报警不是高等级，忽略请由所属工区值班处理"
                return True, ""
            return False, "当前岗位不允许忽略报警"

        if action == DISPOSE_ACTION:
            if status != STATUS_ORDER[1]:
                if status == STATUS_ORDER[0]:
                    return False, "报警尚未确认，需先确认才能处置"
                return False, f"报警状态已为{status}，不能重复处置"
            # 确认与处置角色分开：本条确认人不能再处置。
            confirmer = _confirm_operator_id(entry)
            if confirmer and confirmer == operator.operator_id:
                return False, "确认与处置的角色必须分开，你已确认本条报警，处置需由其他账号执行"
            if operator.is_duty:
                if not in_work_site:
                    return (
                        False,
                        f"越权处置被拒绝：该报警属于{worksite}，你只能处置{operator.worksite}的报警",
                    )
                return True, ""
            if operator.is_dispatch:
                # 确认与处置角色分开：调度负责确认高等级报警，处置交由设备所属工区值班。
                return False, "高等级报警由调度确认、由设备所属工区值班处置，调度不直接处置报警"
            return False, "当前岗位不允许处置报警"

        return False, "动作暂不支持"

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: Operator,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"报警事件 {entry_id} 不存在或已归档"
        allowed, reason = self.check_action(entry, action, operator)
        if not allowed:
            return None, reason
        target = ACTION_RULES[action]

        if action == CONFIRM_ACTION:
            entry["确认人ID"] = operator.operator_id
            entry["确认人员"] = operator.name
        elif action == DISPOSE_ACTION:
            entry["处置人ID"] = operator.operator_id
            entry["处置人员"] = operator.name
            if str(remark or "").strip():
                entry["处置说明"] = str(remark).strip()
        entry["status"] = target
        entry["pending"] = _is_pending(entry)
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        done = action[:-2] if action.endswith("报警") else action
        return entry, f"报警事件已{done}"
