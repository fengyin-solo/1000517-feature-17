"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import operator as router_operator
from app.routers import section as router_section
from app.routers import signal as router_signal
from app.routers import switch as router_switch
from app.routers import track as router_track
from app.routers import interlock as router_interlock
from app.routers import atp as router_atp
from app.routers import plan as router_plan
from app.routers import task as router_task
from app.routers import fault as router_fault
from app.routers import dispose as router_dispose
from app.routers import spare as router_spare
from app.routers import measure as router_measure
from app.routers import patrol as router_patrol
from app.routers import window as router_window
from app.routers import alarm as router_alarm
from app.routers import verify as router_verify
from app.routers import shift as router_shift
from app.routers import assess as router_assess

ROUTERS = [router_operator, router_section, router_signal, router_switch, router_track, router_interlock, router_atp, router_plan, router_task, router_fault, router_dispose, router_spare, router_measure, router_patrol, router_window, router_alarm, router_verify, router_shift, router_assess]
