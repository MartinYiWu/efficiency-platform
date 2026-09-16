class AgentDefinitionError(ValueError):
    """Agent 定义缺失、冲突或不满足治理约束。"""


class AgentInstanceMismatchError(AgentDefinitionError):
    """运行实例公开的契约与注册定义不一致。"""


class AgentRegistrationConflictError(AgentDefinitionError):
    """同一 Agent ID 被重复或冲突注册。"""


class AgentNotFoundError(LookupError):
    """Registry 中不存在请求的 Agent 或能力。"""


class AgentAssemblyError(RuntimeError):
    """Agent Builder 失败或返回非法实例。"""
