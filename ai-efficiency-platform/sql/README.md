# SQL 资产索引

> 状态：有效  
> 适用范围：`ai-efficiency-platform` 的数据库变更和核验资产

本目录是本单体多模块工程唯一的 SQL 治理入口。当前仅建立目录与规范，未配置真实数据库或自动迁移执行；创建或执行任何 SQL 前必须遵循 [文档规则](../rule/文档规则.md#3-sql-规则)。

| 目录 | 内容 | 是否可自动执行 |
|---|---|---|
| [migration/](migration/README.md) | 版本化正向 DDL、数据迁移和索引变更 | 后续由唯一 Flyway 位置决定 |
| [rollback/](rollback/README.md) | 对应迁移的人工回滚方案 | 否 |
| [verification/](verification/README.md) | 只读结构、行数和业务核验 | 否 |
| [manual/](manual/README.md) | 需明确授权的人工脚本 | 否 |
| [seed/](seed/README.md) | 开发、测试环境初始化数据 | 否 |

禁止在 `aiep-boot/src/main/resources/db/migration/` 与本目录同时维护相同迁移脚本。启用 Flyway 时，通过构建资源配置纳入唯一权威目录。
