"""监测报警业务规则：状态流转、字段校验与按岗位分流的口径都收在这里。

岗位分流要点：
- 值班员绑定一个工区，只能确认本工区触发设备的非高等级报警；跨工区报警只读。
- 高等级报警统一由调度确认。
- 检修人员只能查看，任何写动作都会被拒绝并说明原因。
- 确认与处置/忽略的角色分开：同一条报警上，同一账号不能既确认又处置或忽略。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["报警编号", "报警类型", "报警等级"]
OPTIONAL_FIELDS = ["触发设备", "所属工区", "触发时间"]
STATUS_ORDER = ["待确认", "已确认", "已处置", "已忽略"]
ACTION_RULES = {"确认报警": "已确认", "处置报警": "已处置", "忽略报警": "已忽略"}
NEGATIVE_ACTIONS = ["忽略报警"]
WRITE_ACTIONS = list(ACTION_RULES)

ROLE_DUTY = "值班员"
ROLE_DISPATCH = "调度"
ROLE_REPAIR = "检修人员"
ROLES = [ROLE_DUTY, ROLE_DISPATCH, ROLE_REPAIR]
# 高等级的等级名称都带“高”字（高、紧急/高等级），普通等级为一般/低。
HIGH_LEVEL_KEYWORD = "高"


@dataclass(frozen=True)
class Actor:
    """当前登录账号：岗位、所属工区与账号显示名。"""

    role: str = ROLE_DUTY
    zone: str = "一工区"
    operator: str = "值班管理员"

    @property
    def is_duty(self) -> bool:
        return self.role == ROLE_DUTY

    @property
    def is_dispatch(self) -> bool:
        return self.role == ROLE_DISPATCH

    @property
    def is_repair(self) -> bool:
        return self.role == ROLE_REPAIR


def is_high_level(level: Any) -> bool:
    return HIGH_LEVEL_KEYWORD in str(level or "")


class AlarmService:
    # ---- 列表与统计 -------------------------------------------------
    def list_entries(
        self,
        actor: Actor,
        *,
        keyword: str | None = None,
        status: str | None = None,
        mine: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("报警编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if mine:
            rows = [row for row in rows if self._is_mine(row, actor)]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._view_row(row, actor) for row in rows[start:start + size]]
        return page_rows, total

    def statistics(self, actor: Actor) -> dict[str, int]:
        """统计卡片：确认后由前端重新拉取，保证数量与列表同步。"""
        rows = store.rows(MODULE)
        today = date.today().isoformat()
        pending = [row for row in rows if row.get("status") == "待确认"]
        return {
            "today": sum(1 for row in rows if str(row.get("触发时间", ""))[:10] == today),
            "pending": len(pending),
            "highPending": sum(1 for row in pending if is_high_level(row.get("报警等级"))),
            "minePending": sum(
                1 for row in pending if self._is_mine(row, actor)
            ),
        }

    def get_entry(self, entry_id: int, actor: Actor) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._view_row(entry, actor)

    # ---- 登记 -------------------------------------------------------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            entry[field] = values.get(field)
        entry["触发时间"] = entry.get("触发时间") or date.today().isoformat()
        entry["所属工区"] = entry.get("所属工区") or "未分配工区"
        entry["status"] = STATUS_ORDER[0]
        entry["报警状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["操作记录"] = []
        rows.append(entry)
        return entry, []

    # ---- 动作：确认 / 处置 / 忽略 -----------------------------------
    def run_action(
        self,
        entry_id: int,
        action: str,
        actor: Actor,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"报警事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于监测报警可执行范围"
        entry.setdefault("操作记录", [])

        reason = self._permission_denied(entry, action, actor)
        if reason:
            return None, reason

        previous = [
            record["action"]
            for record in entry["操作记录"]
            if record.get("operator") == actor.operator
        ]
        if previous:
            # 同一账号在同一条报警上只能留下一种动作，确认与处置/忽略必须分开。
            if action in previous:
                return None, f"账号 {actor.operator} 已{action}过该报警，请勿重复操作"
            return None, (
                f"账号 {actor.operator} 已执行过「{'、'.join(dict.fromkeys(previous))}」，"
                f"确认与处置/忽略须由不同账号执行，{action}已被拒绝"
            )

        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        entry["status"] = target
        entry["报警状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry["操作记录"].append(
            {"operator": actor.operator, "role": actor.role, "action": action}
        )
        if action == "确认报警":
            entry["确认人员"] = actor.operator
            entry["确认时间"] = date.today().isoformat()
        elif action == "处置报警":
            entry["处置说明"] = str(remark or "").strip() or f"{actor.operator} 已完成现场处置"
        return entry, f"报警事件已{action}"

    # ---- 岗位分流口径 -----------------------------------------------
    def _permission_denied(self, entry: dict[str, Any], action: str, actor: Actor) -> str | None:
        """返回 None 表示放行；否则返回拒绝原因（越权确认必须说明原因）。"""
        if actor.role not in ROLES:
            return f"未知岗位「{actor.role}」，无法执行{action}"
        if actor.is_repair:
            return "检修岗位仅可查看报警，确认、处置或忽略请联系值班员或调度"

        zone = str(entry.get("所属工区") or "")
        high = is_high_level(entry.get("报警等级"))

        if action == "确认报警":
            if entry.get("status") != "待确认":
                return f"报警当前为「{entry.get('status')}」，无需重复确认"
            if actor.is_duty:
                if high:
                    return f"高等级报警由调度确认，{zone}值班员无权确认"
                if zone != actor.zone:
                    return f"该报警由{zone}的触发设备产生，跨工区报警只读，值班员无权确认"
            elif actor.is_dispatch and not high:
                return (
                    f"该报警等级为「{entry.get('报警等级')}」，由{zone}值班员确认，"
                    "调度仅确认高等级报警"
                )
            return None

        # 处置报警 / 忽略报警：动作照旧，仅受工区只读边界约束。
        if actor.is_duty and zone != actor.zone:
            return f"该报警属{zone}管辖，跨工区报警只读，不能{action}"
        return None

    def _is_mine(self, entry: dict[str, Any], actor: Actor) -> bool:
        """归属是（岗位 + 工区 + 报警等级/所属工区）的纯函数：

        不随状态变化，所以确认之后再返回列表，归属仍然不变。
        """
        if actor.is_repair:
            return False
        zone = str(entry.get("所属工区") or "")
        high = is_high_level(entry.get("报警等级"))
        if actor.is_dispatch:
            return high
        return zone == actor.zone and not high

    def _ownership(self, entry: dict[str, Any], actor: Actor) -> str:
        zone = str(entry.get("所属工区") or "")
        high = is_high_level(entry.get("报警等级"))
        if actor.is_repair:
            return "只读"
        if actor.is_dispatch:
            return "我的报警" if high else "工区值班确认"
        if zone != actor.zone:
            return "跨工区只读"
        return "我的报警" if not high else "高等级·调度确认"

    def _view_row(self, entry: dict[str, Any], actor: Actor) -> dict[str, Any]:
        """给列表/明细附加归属与每个动作的可执行口径，源数据不丢字段。"""
        view = dict(entry)
        view.pop("操作记录", None)
        view["归属"] = self._ownership(entry, actor)
        view["mine"] = self._is_mine(entry, actor)
        allowed: list[dict[str, Any]] = []
        for action in WRITE_ACTIONS:
            # 已留下动作记录的账号，重复/交叉动作也要在按钮上说明原因。
            reason = self._permission_denied(entry, action, actor)
            previous = [
                record["action"]
                for record in entry.get("操作记录", [])
                if record.get("operator") == actor.operator
            ]
            if reason is None and previous:
                if action in previous:
                    reason = f"账号 {actor.operator} 已{action}过该报警"
                else:
                    reason = "确认与处置/忽略须由不同账号执行"
            allowed.append({"action": action, "allowed": reason is None, "reason": reason or ""})
        view["allowedActions"] = allowed
        return view
