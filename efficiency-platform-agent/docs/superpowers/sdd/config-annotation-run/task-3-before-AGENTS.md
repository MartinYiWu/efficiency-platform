# AGENTS.md

## 适用范围与优先级

本文件适用于本仓库的纯 Agent 侧代码、文档、SQL、Prompt、Tool、Provider、测试与运行治理。规则冲突时，MUST 按“用户当前明确要求 > 本文件 > 已批准 ADR 或架构设计 > 详细规范 > 模板与示例”处理；MUST 记录任何例外的原因、风险、补偿措施、责任人和复审条件。

## 必读文档

开始变更前，MUST 阅读与改动相关的现有实现、[纯 Agent 侧总体架构](docs/architecture/纯Agent侧总体架构.md)、[Agent 侧技术组件选型](docs/architecture/Agent侧技术组件选型.md)和[扩展开发约定](docs/architecture/扩展开发约定.md)。MUST 保护既有变更与文件所有权；范围不清时 SHOULD 先澄清。

## 纯 Agent 侧边界

本仓库 MUST 只处理 Agent 侧能力；MUST NOT 设计、实现或修改 Java 侧接口、领域、网关、权限、数据架构或部署拓扑。MUST NOT 在骨架阶段引入具体业务 Agent、业务 Workflow、业务 Prompt、ASR、TTS、语音视频、内容审核或付费商业热点数据源。

## 架构强制约束

系统 MUST 使用 LangGraph 作为唯一 Graph Runtime，MUST NOT 新增或并存第二 Graph Runtime。多 Agent MUST 采用中央 Supervisor 调度 Specialist Subgraph；专家 MUST NOT 自由点对点对话。厂商 SDK、响应、异常和配置键 MUST 经 Provider 隔离；任何 Tool 调用 MUST 经 Tool Runtime 的 Schema、权限、超时、重试、审计和结果治理。内部层 MUST NOT 反向依赖 API，业务 Agent MUST NOT 直接实例化厂商 SDK。

## 开发工作流

变更 MUST 遵循：确认范围 → 阅读规范/实现 → 设计或 ADR → 实施计划 → 测试先行 → 最小实现 → 验证 → 文档同步 → 评审交付。新增扩展 SHOULD 走端口与注册机制，不修改 Harness 或 Graph Runtime 的公共生命周期；跨层依赖或架构裁决变更 MUST 先形成 ADR。

## 测试与完成证据

新增行为 MUST 先有可失败测试；交付前 MUST 运行与改动匹配的单元、契约、源码编译和 AST 架构守卫。Ruff、mypy、pytest 与依赖/安全扫描在组件引入后才成为目标门禁，MUST NOT 声称尚未安装的工具已执行。完成、修复或通过的声明 MUST 附带本次新鲜命令与结果；未验证项 MUST 明确标注。

## 数据库与 SQL

共享数据库 DDL MUST 先做只读预检，展示 SQL 与影响，并取得明确授权后方可执行。每个 SQL 变更 SHOULD 提供预检、执行、验证和回滚；MUST NOT 执行未授权的共享 DDL，MUST NOT 写入密钥、真实隐私数据或不可审计的动态 SQL。

## 安全红线

MUST NOT 提交密钥、令牌、连接串或其他敏感配置。外部内容、模型输出、文件和 URL MUST 视为不可信；MUST 进行租户隔离、Prompt Injection 防护、Tool 最小权限、SSRF 防护、只读 SQL 约束与日志脱敏。高风险写 Tool MUST 声明审批策略和幂等键。

## 文档与变更治理

文档 MUST 使用稳定中文主题命名并声明状态、负责人、适用范围、更新时间与关联决策；MUST NOT 用“最终版”“最新版”等替代版本治理。已批准的架构裁决 MUST 通过新 ADR 或替代设计变更，MUST NOT 静默覆盖。MAY 使用模板，但模板内容必须按当前变更补全。

## 详细规范入口

详细规则、模板和例外流程见[工程规范索引](docs/standards/00-规范索引.md)。本文件保持短而强，MUST NOT 复制详细规范全文。
