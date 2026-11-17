"""纯 CPU 窗口判断，不触发压缩、计费或网络。"""

from efficiency_platform_agent.core.context_control import WindowDecision, WindowLimits
from efficiency_platform_agent.core.memory import require_count


def window_pressure(limits: WindowLimits, total: int) -> str:
    require_count(total)
    cap = limits.input_cap()
    if cap <= 0 or total > cap:
        return "OVERFLOW"
    if total * 100 <= cap * 70:
        return "NORMAL"
    return "CPU_TRIM" if total * 100 <= cap * 85 else "CPU_PREPARE"


def evaluate_window(limits: WindowLimits, T: int, F: int) -> WindowDecision:
    require_count(T)
    require_count(F)
    cap = limits.input_cap()
    if cap <= 0 or T > cap or F > cap or F > T:
        status = "REJECT"
    elif T == cap or T * 100 <= cap * 70:
        status = "ALLOW"
    else:
        status = "TRIM"
    return WindowDecision(cap, T, F, status)
