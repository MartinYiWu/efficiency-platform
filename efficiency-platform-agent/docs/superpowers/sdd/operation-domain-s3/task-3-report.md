# S3 Task 3：运营计划契约

状态：已完成（离线契约）。

- 目标文件：`contracts/planning.py`、Task3 单元测试。
- GREEN：`uv run python -m unittest tests.unit.operation.test_planning -q`，5 tests passed。
- 约束：稳定拓扑排序、依赖存在性/环检测、子预算边界、失败行为和模板引用均已校验。
- 计划仅声明步骤，不执行 Agent、Tool、Provider 或 Checkpoint。
