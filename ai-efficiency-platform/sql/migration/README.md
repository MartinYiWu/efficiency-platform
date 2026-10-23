# 正向迁移 SQL

> 状态：有效  
> 文件命名：`V<版本>__<lower_snake_case说明>.sql`

本目录存放不可变的正向结构或数据迁移脚本。每个脚本开头必须用注释说明所属模块、影响表、前置核验、兼容性、数据回填策略和对应回滚文件。执行前须确认目标库迁移历史；执行后不得修改该文件。

- [V1.1.7 智能客服证据策略](V1.1.7__customer_service_evidence_policy.sql)：离线待预检，不回填历史策略或 Release。
- [V1.1.9 引用证据元数据](V1.1.9__customer_service_citation_evidence.sql)：未执行；父 ID、引用类型与原文偏移入规范引用表，旧行保持 NULL。
