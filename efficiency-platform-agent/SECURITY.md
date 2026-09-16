# 安全基线

本基线适用于纯 Agent 侧。内容审核当前暂不建设，但租户隔离、输入处理、Tool 治理、SSRF、文件、SQL、日志、模型输出和依赖安全控制仍 MUST 强制适用。

## 安全问题报告

发现疑似漏洞、Secret 泄露、跨租户访问、未授权 Tool 或数据暴露时，MUST 停止扩大影响并联系项目负责人。MUST NOT 在仓库中虚构邮箱、公开敏感复现数据或披露可被直接滥用的凭据；报告 SHOULD 包含影响范围、可复现条件、证据、缓解措施和修复验证建议，并 MAY 在不含敏感数据时附最小复现。

## Secret 与配置

密钥、令牌、密码、连接串和私有端点 MUST 通过环境或受控 Secret 注入，MUST NOT 写入源码、Prompt、SQL、测试样本、日志、文档或提交历史。Provider MUST 隔离厂商配置键；示例 MUST 使用明显无效的占位值，且 MUST NOT 看起来像真实凭据。

## 租户与用户上下文

每次 Run MUST 建立并传播 `tenant_id`、`user_id`、权限与审计上下文。Context、Memory、Tool、Provider 与 Persistence MUST 按租户和用户执行最小权限隔离；Tool MUST NOT 读取当前主体无权访问的资源。跨租户访问 MUST 默认拒绝，只有显式策略和审计记录可构成受控例外。

## Prompt Injection 与外部内容

网页、文件、检索结果、Tool 返回和模型文本 MUST 视为不可信数据，MUST 与系统指令、权限规则和 Tool 策略分区。系统 MUST NOT 将外部文本或未经 Schema 校验的模型输出当作控制指令；高风险操作 MUST 重新检查策略、身份、授权与审批，而不是依赖模型自我声明。

## Tool 权限与外部副作用

所有 Tool MUST 经 Tool Runtime 执行 Schema 校验、身份/租户授权、最小权限、超时、重试、审计、结果限制与脱敏。写操作或高风险 Tool MUST 声明副作用、审批策略和幂等键；MUST NOT 让 MCP 或直接 SDK 调用绕过 Runtime。Tool 白名单、预算与终止条件 SHOULD 与 Strategy/Agent 契约一并测试。

## SSRF 与网络访问

外部 URL MUST 经 SSRF Policy 校验协议、主机、端口、DNS 解析结果和重定向链。MUST NOT 访问回环、链路本地、私网、云元数据或其他受限地址；网络客户端 MUST 设置超时、大小上限、限速和审计。公开采集 SHOULD 遵守 robots、站点条款和版权边界。

## 文件与文档处理

上传或外部文件 MUST 校验文件签名、MIME、大小、页数/解压限制与解析器异常；不可信 XML MUST 使用安全解析，HTML MUST 清洗。文件内容、元数据和 OCR 文本 MUST 按敏感数据处理，MUST NOT 直接写入日志或无边界地注入上下文。文件上传场景 SHOULD 接入恶意文件扫描适配器。

## SQL 与持久化

当前禁止 Text2SQL、模型生成 SQL 和面向业务数据库的直接分析。模型文本、Prompt 或 Tool 返回 MUST NOT 被拼接、解释或转换为可执行 SQL；Agent 自有查询 MUST 通过受控 Repository 使用参数化语句，且只能访问 Agent 所有的数据对象。共享数据库 DDL MUST 先做只读预检，展示影响并取得明确授权；变更 MUST 具备验证与回滚边界。Agent 数据 MUST 使用独立命名空间，MUST NOT 与 Java 表混写。未来如需引入 Text2SQL，必须重新完成组件选型、威胁建模和明确批准，当前不存在默认兜底实现。

## 日志、审计与隐私

日志与 Trace SHOULD 包含 `run_id`、`trace_id`、`tenant_id`、策略、Agent、Tool、Provider 与模型等可追溯字段。MUST NOT 记录 Secret、完整 Prompt、原始敏感文档、受限 Tool 参数或未经脱敏的个人数据；审计记录 MUST 能追溯 Tool 授权、审批、模型选择、Prompt 版本、数据来源和产物。

## 模型输出与产物

模型输出 MUST 经结构化 Schema、内容边界和权限校验后才能驱动状态、Tool 或持久化。系统 SHOULD 保存证据、来源和版本以支持复核；产物 MUST 具备访问控制、生命周期和删除边界。MUST NOT 将模型自称的权限、来源或成功状态作为安全证据。

## 依赖与安全验收

新增依赖 MUST 有明确能力归属、维护状态、许可证与最小版本评估，MUST NOT 为便利引入第二 Graph Runtime 或未知来源执行器。每次安全相关变更 MUST 验证对应拒绝路径、权限、超时、审计与脱敏；依赖与安全扫描是组件引入后的目标能力，MUST NOT 虚构其已安装或已通过。
