"""HR组合根端口：执行控制必须由服务器按租户与run统一装配。"""

from efficiency_platform_agent.agents.hr.service import HrRunControlStore

__all__ = ["HrRunControlStore"]
