# AI 效能平台 Java 服务

`ai-efficiency-platform` 是 AI 效能平台的 Java 业务服务。工程采用 Java 21、Spring Boot 3.2.5 和 Maven 多模块单体架构，最终由 `aiep-boot` 打包为一个可执行 Jar。

## 模块分层

- `aiep-platform-*`：共享平台能力，不得依赖业务模块。
- `aiep-identity`：组织、身份、角色、权限、菜单和登录会话的所有者。
- `aiep-biz-*`：知识库、资产、AI Hub 和系统管理等业务域。
- `aiep-agg-*`：工作台和分析读模型聚合。
- `aiep-boot`：应用组装、配置、运行与 ArchUnit 测试。

`aiep-platform-ai` 是唯一的 AI 调用边界。只有 `com.aiep.platformai.agent` 可以保存 Agent 端点常量和未来的 HTTP 客户端实现，其他模块必须通过 `AiInvokeFacade` 调用。

## 本地验证

```powershell
mvn -pl :aiep-boot -am test
mvn package
```

初始健康入口为 `GET /api/platform/ping`，返回统一响应信封，并透传或生成 `X-Trace-Id`。

## 工程治理入口

- [协作总则](AGENTS.md)
- [工程规则](rule/README.md)
- [项目级设计文档](md/README.md)
- [实施计划](plan/README.md)
- [SQL 资产](sql/README.md)
- [Java 端架构与开发约束](docs/architecture/Java端架构与开发约束.md)

可自动验证的架构子集由 `aiep-boot` 中的 ArchUnit 测试守护。

## 当前未实施能力

业务 CRUD、真实数据库结构、Agent HTTP 实现、流式持久化、任务轮询策略，以及五项运行期约束仍处于未实施或待定稿状态。
