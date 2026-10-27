# 正向迁移 SQL

> 状态：有效  
> 文件命名：`V<版本>__<lower_snake_case说明>.sql`

本目录存放不可变的正向结构或数据迁移脚本。每个脚本开头必须用注释说明所属模块、影响表、前置核验、兼容性、数据回填策略和对应回滚文件。执行前须确认目标库迁移历史；执行后不得修改该文件。

- [V1.1.7 智能客服证据策略](V1.1.7__customer_service_evidence_policy.sql)：2026-10-23 已在开发库执行并核验；其他环境待按迁移流程执行，不回填历史策略或 Release。
- [V1.1.9 引用证据元数据](V1.1.9__customer_service_citation_evidence.sql)：2026-10-23 已在开发库执行并核验；其他环境待按迁移流程执行，父 ID、引用类型与原文偏移入规范引用表，旧行保持 NULL。
- [V1.1.11 会话标题唯一约束](V1.1.11__customer_service_conversation_title_unique.sql)：2026-10-27 已获单独授权，在开发库 `ai_efficiency_platform` 执行并核验。影响表仅 `ai_customer_service_conversation`；Java 停写后先备份原名并为 4 条重复记录追加序号，重名组清零后新增生成列与唯一索引。旧空标题兼容，已删除会话释放名称。对应预检/验证为 [V1.1.11 验证脚本](../verification/V1.1.11__verify_conversation_title_unique.sql)，回滚为 [R__V1.1.11](../rollback/R__V1.1.11__conversation_title_unique.sql)。真实标题备份仅保存在本地验收目录，禁止提交。仓库已有 V1.1.10，本轮迁移文件已更正为独立版本 V1.1.11；开发库采用手工执行，未写入 Flyway 历史，不重复执行 ALTER。
