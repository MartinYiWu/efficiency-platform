"""官方Saver构造限制在orchestration边界；连接由受信异步组合根持有。"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def create_official_saver(connection):
    return AsyncPostgresSaver(connection)
