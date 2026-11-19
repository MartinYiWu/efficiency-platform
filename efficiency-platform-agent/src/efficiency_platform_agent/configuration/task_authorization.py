"""后继付费能力独立关闭；启用不等于创建或延长授权。"""

import os


def task_authorization_enabled() -> bool:
    return os.environ.get("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "").lower() == "true"
