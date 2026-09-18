# 架构基线索引

> 状态：有效  
> 适用范围：Java 工程已确认的稳定架构事实

本目录保存已确认的架构基线。工程协作入口见 [AGENTS.md](../../AGENTS.md)，持续规则见 [rule/](../../rule/README.md)，架构调整的设计与实施计划分别进入 [md/](../../md/README.md) 和 [plan/](../../plan/README.md)。

- [Java 端架构与开发约束](Java端架构与开发约束.md)：模块分层、数据所有权、Agent 边界和自动化门禁。

可执行架构基线由 `aiep-boot` 的 ArchUnit 测试守护。任何改变模块所有权、依赖方向、Agent 边界或 SQL 唯一真相位置的决策，必须在实施前形成设计和计划。
