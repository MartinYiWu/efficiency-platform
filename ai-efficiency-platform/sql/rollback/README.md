# 回滚 SQL

> 状态：有效  
> 文件命名：`R__V<版本>__<lower_snake_case说明>.sql`

本目录存放人工受控回滚脚本。每个回滚脚本必须关联唯一正向迁移、写明数据不可逆风险、执行前条件和执行后核验 SQL。不存在安全回滚方案时，正向迁移必须在头部说明原因与替代恢复方式。

- [V1.1.7 智能客服证据策略回滚](R__V1.1.7__customer_service_evidence_policy.sql)：需先回退应用并备份策略与绑定。
- [V1.1.9 引用证据保护回滚](R__V1.1.9__customer_service_citation_evidence.sql)：存在新引用事实时拒绝丢列；需先回退应用并单独审核备份。
