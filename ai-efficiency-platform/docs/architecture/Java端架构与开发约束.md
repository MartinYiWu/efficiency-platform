# Java端架构与开发约束

> 状态：**基线**。本文件约束 `ai-efficiency-platform` 的 Java 代码、Maven 依赖、数据库迁移和 Java–Agent 接合面。违反“必须”条款，代码不得合并。工程执行入口见 [AGENTS.md](../../AGENTS.md)，持续规则见 [rule/](../../rule/README.md)。

## 1. 总体边界

1. 服务名固定为 `ai-efficiency-platform`，根包固定为 `com.aiep`，Maven 模块统一使用 `aiep-` 前缀。
2. Java 侧是单体应用：13 个 Maven 模块最终由 `aiep-boot` 打包为一个 Jar、一个进程；不得以模块名创建 Java 微服务。
3. Java 拥有身份权限、业务实体、业务状态、文件元数据、会话与消息持久化、任务业务状态和 AI 调用审计；Python Agent 不得成为这些数据的真相源。
4. Java 到 `efficiency-platform-agent` 的调用严格单向。Python 不回调 Java；前端也不得直接访问 Agent。

## 2. 模块与依赖约束

| 层级 | 模块 | 允许依赖 |
|---|---|---|
| L0 | `platform-*` | `platform-core`，不得依赖 L1/L2/L3 |
| L1 | `identity` | `platform-core`，不得依赖 L2/L3 |
| L2 | `biz-*` | L0、L1；仅 `biz-aihub → biz-knowledge` 例外 |
| L3 | `agg-*` | L0、L1、L2；不得被 L0/L1/L2 反向依赖 |
| 启动层 | `aiep-boot` | 可组装全部模块，不写业务领域逻辑 |

1. 跨模块调用必须只引用 `其他模块.api`，并通过 `XxxFacade` 注入。
2. 禁止跨模块引用 `controller`、`facade` 实现、`domain`、`repository`、`config`、Entity、PO、Mapper。
3. 所有版本仅在根 `pom.xml` 统一管理；子模块不得单独覆写公共组件版本。
4. 未经 ADR 批准，禁止引入 Spring Cloud、Nacos、OpenFeign、Kafka、XXL-Job、Spring AI、Sa-Token、Fastjson/Fastjson2。

## 3. 包、接口与代码约束

每个模块统一采用如下包结构：

```text
api/          对外 Facade、DTO、Request/Response、枚举
facade/       Facade 实现
controller/   HTTP 入口
domain/       领域服务、实体、转换器
repository/   Mapper、PO、SQL/XML
config/       模块内部配置
```

1. `api` 是唯一可跨模块访问的包；不得暴露 PO、Mapper、持久化分页对象或 ORM 条件对象。
2. Controller 只做 HTTP 参数绑定、调用领域服务和响应返回；不得直接注入或访问 Repository。
3. 领域服务使用构造器注入；禁止字段注入。
4. 对外对象使用 `XxxDTO`、`XxxRequest`、`XxxResponse`；持久化对象统一为 `XxxPO`。
5. HTTP 公共路径遵循 `/api/<模块>/<资源>`；`/internal/**` 不得被反向代理公开。
6. 统一使用 `ApiResponse` 和 `X-Trace-Id`；任何错误响应必须带 traceId。

## 4. 数据与事务约束

| 表前缀 | 归属 |
|---|---|
| `pf_` | platform-content / ai / file / task |
| `org_` | identity |
| `kb_` | knowledge |
| `as_` | asset |
| `ai_` | aihub |
| `sys_` | system |

1. 一个数据库事务只能写本模块表；跨模块写入使用主操作加补偿，不得开启跨模块事务。
2. 跨模块不得 Join 业务表、不得建立物理外键、不得写入对方表；只允许对 `org_user`、`org_dept` 做展示用途的只读 Join。
3. 所有 DDL 必须通过根 `sql/migration/V<版本>__<描述>.sql` 交付；不得人工修改已执行的迁移文件。启用 Flyway 时必须将此唯一位置纳入 `aiep-boot` 的构建资源，禁止复制出第二份迁移脚本。
4. 删除业务对象时必须清理其 `platform-content` 关联数据。向量删除先于业务删除；其失败补偿与对账规则尚未定稿。

## 5. AI 接合面约束

1. `aiep-platform-ai` 是唯一 AI 调用出口；业务模块只能注入 `AiInvokeFacade`。
2. `com.aiep.platformai.agent` 是唯一可出现 Agent 地址、端点、HTTP 客户端、内部鉴权 Header 的包。
3. Agent 业务端点固定为 7 个：文本生成、对话流、Skill、知识库问答、文档入库、任务查询、向量删除；新增交互形态必须先写 ADR。
4. Java 负责模型配置选择、权限过滤范围计算、调用记录、引用落库、会话摘要持久化和业务降级；Agent 只执行 Java 传入的请求。
5. Java 非 AI 业务不得因 Agent 不可用而整体失败。

## 6. 测试与交付约束

1. 新增生产行为必须先有失败测试；单元测试不依赖真实数据库、模型服务或外部网络。
2. 真实数据库、对象存储、Agent 联调测试统一使用 `*IntegrationTest` 命名，并仅在受控 Profile 下执行。
3. `aiep-boot` 的 ArchUnit 测试是强制门禁：平台反向依赖、L2/L3 越层、Controller→Repository、API 泄露 Repository、Agent WebClient 越界和包循环均必须失败。
4. 每次交付至少执行 `mvn clean test`；可发布构建额外执行 `mvn package -DskipTests`。
5. 不得把密钥、Token、连接串、个人信息或 Agent 请求正文写入日志、测试断言快照或 Git。

## 7. 本轮不定稿的运行约束

以下事项必须在进入真实 Agent、任务和向量实现前单独成文并评审，本文件不替代其具体设计：

1. 云模型密钥的保管、轮换与 Agent 读取机制。
2. `filter_scope` 的空集、全量和无权限语义。
3. 任务轮询退避、最大超时及 Agent 重启后的幂等恢复。
4. 向量已删除、业务删除失败时的补偿与对账。
5. Java–Agent 内部请求的时间戳、签名、重放防护与密钥轮换。

## 8. 当前自动化门禁映射

| 规范 | 自动化位置 |
|---|---|
| 平台/身份不得依赖业务或聚合层 | `ArchitectureTest#enforces_platform_and_identity_direction` |
| L2 不得依赖 L3 | `ArchitectureTest#prevents_business_modules_from_reading_aggregation_modules` |
| L2 仅允许 aihub → knowledge | `ArchitectureTest#permits_only_aihub_to_knowledge_l2_dependency` |
| Controller 不得直连 Repository | `ArchitectureTest#prevents_controller_repository_shortcuts` |
| API 不得泄露 Repository | `ArchitectureTest#prevents_repository_leaks_from_public_apis` |
| 只有 Agent 包可使用 WebClient | `ArchitectureTest#confines_agent_transport_client_to_platform_ai_agent_package` |
| 包级无循环 | `ArchitectureTest#keeps_top_level_packages_free_of_cycles` |
