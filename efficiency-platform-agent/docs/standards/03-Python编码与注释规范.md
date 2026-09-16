# Python 编码与注释规范

| 属性 | 内容 |
|---|---|
| 标题 | Python 编码与注释规范 |
| 状态 | 评审中 |
| 作者/负责人 | Agent 平台维护者 |
| 创建日期 | 2026-09-01 |
| 最后更新日期 | 2026-09-02 |
| 评审人/批准人 | 评审人：尚未指定；批准人：尚未批准 |
| 关联 ADR/设计/计划 | [Agent 侧技术组件选型](../architecture/Agent侧技术组件选型.md)、[架构与依赖规范](02-架构与依赖规范.md)、[Agent 侧工程规范体系实施计划](../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md) |
| 替代关系 | 无 |
| 适用范围 | `efficiency-platform-agent` 纯 Agent 侧 Python 源码、测试和代码内文档 |
| 不适用范围 | Java 代码与部署脚本 |

## 1. Python 基线与兼容性声明

Python 3.12 MUST 是项目目标运行基线。当前零第三方依赖骨架 MAY 使用 Python 3.11 执行标准库编译和测试，以验证源码未依赖 3.12 专有语法。

在第三方依赖写入 `pyproject.toml`、生成并评审 `uv.lock`，且在 Python 3.12 环境完成安装、编译、测试与相关集成验证前，交付者 MUST NOT 声称“Python 3.12 兼容性已验收”。报告 MUST 分开写明执行解释器版本、目标版本和未验证依赖。

生产代码 MUST NOT 依赖未声明的本地包、全局环境或解释器私有实现。使用 3.12 专有能力时 MUST 在项目元数据中声明最低版本，并提供 3.12 下的新鲜验证证据。

## 2. 命名

代码标识符 MUST 使用英文；项目自行编写的 Python Docstring 和注释 MUST 使用中文，并 MAY 保留 Graph、Checkpoint、Provider、Tool、Prompt、Schema 等标准英文技术术语。同一模块 MUST 保持一致的语言和术语风格。

| 对象 | 规则 | 示例 |
|---|---|---|
| 包、模块 | MUST 使用小写 `snake_case`；名称 MUST 表达单一职责 | `error_mapping.py`、`plan_execute` |
| 类 | MUST 使用 `PascalCase`；名称 SHOULD 使用名词或名词短语 | `RunContext`、`ProviderResponse` |
| Protocol | MUST 使用 `PascalCase` 角色名；MUST NOT 使用 `I` 前缀 | `ToolExecutor`、`CheckpointStore` |
| 函数、方法 | MUST 使用小写 `snake_case`；名称 SHOULD 以动词开头并表达结果 | `select_strategy`、`normalize_error` |
| 布尔变量 | SHOULD 使用 `is_`、`has_`、`can_`、`should_` | `is_retryable` |
| 变量、参数 | MUST 使用小写 `snake_case` 和领域含义；MUST NOT 使用无意义缩写 | `request_timeout_seconds` |
| 常量 | MUST 使用大写 `UPPER_SNAKE_CASE`；单位 SHOULD 进入名称 | `DEFAULT_TIMEOUT_SECONDS` |
| 枚举类型 | MUST 使用 `PascalCase`；成员 MUST 使用大写 `UPPER_SNAKE_CASE` | `RunStatus.WAITING_TOOL` |
| 类型参数 | MUST 简短且有语义；SHOULD 使用 `TResult` 等形式 | `TResult` |

稳定 ID、Provider 名称、模型逻辑名、Prompt ID 和 Tool 名 MUST 与展示名称分离；稳定 ID MUST NOT 随中文文案调整而改变。

## 3. 魔法数字与魔法字符串

协议常量、状态值、事件名、Tool/Prompt/Provider 标识、模型逻辑名、超时、重试次数、最大步骤、Token/费用预算和质量/安全阈值 MUST 使用具名常量、`StrEnum` 或类型化配置字段表达。相同领域含义 MUST 有单一所有者，MUST NOT 以裸数字或裸字符串散落在调用点。

- 稳定协议值和状态 MUST 由最接近所有权的 `core` / `contracts` 枚举或常量定义；MUST NOT 放入无所有权的全局常量文件。
- 可按环境、租户或运行策略调整的超时、步数、重试、预算和阈值 MUST 配置化，并 MUST 在配置对象校验范围与单位。
- 具名数值常量 MUST 在名称中表达单位或边界，例如 `DEFAULT_TOOL_TIMEOUT_SECONDS`、`MAX_REACT_STEPS`；MUST NOT 依赖注释补足单位。
- 模型、Provider、Prompt、Tool 和事件的稳定标识 MUST 与展示文案分离；厂商实际模型名 MUST 只在 Provider 配置边界映射。
- 明显数学常量或单一局部、不可复用且不承载协议/业务/安全含义的字面量 MAY 保留，例如循环起点 `0` 或二维坐标索引 `1`。
- 任何影响状态、兼容性、超时、步骤、重试、预算、权限、质量或安全判定的字面量 MUST NOT 视为“局部简单值”。

坏例子：

```python
if state.status == "waiting_approval" and attempt < 3:
    return await provider.complete(model="deepseek-v4-pro", timeout=30)
```

好例子：

```python
MAX_PROVIDER_ATTEMPTS = 3

if state.status is RunStatus.WAITING_APPROVAL and attempt < MAX_PROVIDER_ATTEMPTS:
    return await provider.complete(
        model=settings.primary_model,
        timeout=settings.provider_timeout_seconds,
    )
```

具名常量只解决稳定代码常量；运行期可调值 MUST 使用配置对象，MUST NOT 为绕过配置治理而改成模块常量。

## 4. 类型与数据模型

- 所有公共边界 MUST 完整标注参数类型和返回类型，包括公开函数、方法、Protocol、Graph Node、Strategy、Agent Plugin、Tool、Provider、Repository 和事件处理器。
- 内部复杂函数 SHOULD 完整标注；局部变量在类型显然时 MAY 由检查器推断。
- `Any`、无界 `dict[str, object]` 和字符串约定 MUST NOT 用于逃避稳定 Schema。确需 `Any` 时 MUST 把它限制在反序列化或厂商边界，并立即校验、归一化。
- `Protocol` MUST 用于定义跨层端口和可替换行为；它 MUST 描述调用方需要的最小能力，MUST NOT 复制具体实现的全部方法。
- `@dataclass(frozen=True, slots=True)` SHOULD 用于框架中立、不可变的领域值对象、命令和结果；字段可变或存在资源生命周期时 MUST 选择更合适的对象模型。
- `StrEnum` SHOULD 用于需要稳定字符串序列化的有限状态或模式。枚举值 MUST 视为契约，修改时 MUST 考虑持久化和兼容性。
- `TypedDict` MAY 用于 LangGraph State 的静态结构，但状态更新 MUST 有明确字段和合并语义。对外边界 SHOULD 使用经过验证的 Schema 对象。
- `None` MUST 表示真实可空语义；MUST NOT 用空字符串、`0` 或空容器混充“未提供”。
- 可变默认值 MUST 使用工厂，MUST NOT 直接放在函数参数或 dataclass 字段默认值中。

模型或外部输入 MUST 在进入 Graph State、Tool Runtime 或持久化前通过 Schema 校验。未经验证的自由文本 MUST NOT 作为路由、权限、SQL 或 Tool 控制指令。

### 4.1 当前 Core 稳定契约

当前标准库骨架已在 `core/run.py` 与 `core/ports.py` 建立版本化、框架中立的稳定契约，但尚未接入真实 Graph Runtime、Tool、Provider 或数据库实现：

- 稳定 JSON 边界只接受 `str`、`int`、有限 `float`、`bool`、`None`、不可变 `tuple` 与 `JsonObject`；可变 `list` / `dict`、非有限数和重复对象键 MUST 失败关闭；
- `ExecutionBudget` 对最大循环、Tool 调用、输入/输出 Token、毫秒超时和微单位费用执行非负/正值校验；
- `ExtensionDescriptor` 固定名称、语义版本、输入/输出 Schema 版本、不可变权限、预算、终止条件与 Checkpoint 版本；
- `SupervisorTask` 只携带子任务 ID、父 Run、目标 Agent、受控 JSON 输入、裁剪上下文、Tool 白名单和子预算，MUST NOT 携带完整用户 `RunRequest` / `RunContext`；
- Tool 与 Provider 使用版本化请求/结果、结构化参数/消息/options、归一化 usage/error、超时、审批/幂等/副作用和输出限制字段；`ApprovalBinding` 将审批绑定到主体、Tool、参数摘要与失效时间；厂商对象 MUST NOT 出现在端口返回值；
- 所有稳定边界 dataclass MUST 使用 `frozen=True, slots=True`，集合 MUST 使用不可变形式，`Any` MUST NOT 出现在这些稳定端口。

这些代码契约证明字段、不可变性和拒绝语义已经建立；它们 MUST NOT 被表述为真实 Provider、LLM、数据库、OCR 或 LangGraph 已接入。

## 5. 异步、超时与资源生命周期

- API、Graph Runtime、异步 Provider、数据库、HTTP、缓存、对象存储和外部 Tool 的 I/O 边界 SHOULD 使用 `async`；纯 CPU 或纯转换函数 SHOULD 保持同步。
- 异步函数 MUST NOT 直接执行阻塞 I/O。无法替换的同步 SDK、文件解析或 CPU 密集任务 MUST 通过受控线程池、进程池或任务队列隔离，并声明并发与取消限制。
- 网络、模型、数据库、Tool、Checkpoint 和锁等待 MUST 有显式超时；MUST NOT 依赖厂商或库的无限默认超时。
- 客户端和数据库连接 MUST 复用有界连接池；MUST NOT 为每个 Token、Node 或小查询无界创建连接。
- 取消信号 MUST 从 API/Harness 传播到 Graph、Node、Tool 和 Provider。代码捕获取消异常时 MUST 完成必要清理后继续传播，MUST NOT 把取消转换为普通成功。
- 资源 MUST 使用同步或异步上下文管理器关闭；流式响应、临时文件、游标、事务、锁和 Span 在异常、超时与取消路径也 MUST 释放。
- 并发 MUST 有上限并受 Run 预算约束；`gather`、任务组和 Supervisor 并行调度 MUST 定义部分失败、取消和结果顺序语义。
- 重试 MUST 只用于经过分类的临时错误，并受次数、退避、总超时和幂等性约束。外部写操作没有幂等键时 MUST NOT 自动重试。

## 6. 异常与错误归一化

错误 MUST 在产生它的边界分类，并在更高层通过稳定契约映射。项目 MUST 至少区分：

| 类别 | 典型来源 | 处理要求 |
|---|---|---|
| 输入错误 | Schema、范围、文件类型、状态冲突 | MUST 返回可定位但不泄密的稳定错误；MUST NOT 重试 |
| 领域错误 | 非法 Run 转换、预算耗尽、未满足前置条件 | MUST 保留领域语义，由 Harness/API 统一映射 |
| Provider 错误 | 厂商超时、限流、认证、不可用、响应非法 | Provider MUST 归一化类别、可重试性、厂商关联 ID 与安全消息 |
| Tool 错误 | 参数、权限、审批、超时、副作用、结果超限 | Tool Runtime MUST 记录审计并按幂等/风险策略决定重试 |
| Persistence 错误 | 连接、事务、并发、Checkpoint 冲突 | MUST 保持权威状态一致；MUST NOT 伪造成功 |
| 取消与超时 | 用户取消、Run/Node/Tool 截止时间 | MUST 保留 `CANCELLED` 或 `TIMED_OUT` 语义并传播清理 |

- `except Exception: pass`、空返回、伪造默认成功和仅记录后继续 MUST NOT 用于吞异常。
- 捕获异常 MUST 有明确目的：添加上下文、归一化、补偿或在边界记录；无新增语义时 SHOULD 使用裸 `raise` 保留原 traceback。
- 错误消息 MUST NOT 包含 Secret、连接串、完整 Prompt、原始敏感文档或跨租户标识。
- Provider SDK 异常 MUST NOT 穿过 Provider 端口；HTTP/框架异常 MUST NOT 进入 Core。
- 自定义异常 SHOULD 使用稳定错误码和结构化字段，MUST NOT 让调用方依赖可变的人类文案分支。

## 7. Import 与循环依赖

每个模块的 import MUST 按以下分组排列，组间留一空行：

1. `__future__`；
2. Python 标准库；
3. 第三方库；
4. `efficiency_platform_agent` 内部绝对导入；
5. 仅类型检查所需且可能形成运行期环的导入。

跨一级包 MUST 使用绝对导入，使依赖方向可被 AST 守卫识别。同一小包内部 MAY 使用显式相对导入；相对导入 SHOULD 限于当前包或一级父包，MUST NOT 用于隐藏跨层依赖。

循环依赖 MUST 通过提取稳定端口、移动真实所有权或构造注入消除。局部 import、`TYPE_CHECKING`、字符串注解和 `__init__.py` 重导出 MAY 解决纯类型或导入时机问题，但 MUST NOT 用来掩盖架构循环。

星号导入和依赖 `__init__.py` 隐式副作用 MUST NOT 使用。公共重导出 SHOULD 保持极小并明确兼容承诺。

## 8. Docstring 必填范围

以下对象 MUST 有 Docstring：

- 公共模块、公共类、公共函数和公共方法；
- Protocol 及其非显然成员；
- Graph Node、Graph/Strategy 构建器；
- Strategy、Agent Plugin、Workflow 公共入口；
- Tool、Provider 和 Persistence Adapter 公共入口；
- 安全关键函数、错误归一化、权限与租户边界；
- 行为、失败语义或单位无法由类型与名称完整表达的内部函数。

Docstring MUST 说明契约、约束和失败语义，MUST NOT 机械复述函数名、类型标注或实现步骤。Docstring 与代码行为冲突时视为缺陷，变更行为时 MUST 同步更新。

### 8.1 Graph Node Docstring

Graph Node Docstring MUST 明确：输入状态、输出更新、副作用、暂停点、幂等性和异常。合规示例：

```python
async def request_tool_approval(state: RunState) -> StateUpdate:
    """为待审批 Tool 调用构建受治理的审批请求。

    输入状态：
        必须包含 ``run_id``、租户作用域身份和一个已经校验的
        ``pending_tool_call``；该调用尚未执行。
    输出更新：
        将 ``status`` 设置为 ``WAITING_APPROVAL`` 并追加审批事件；
        不替换无关状态字段。
    副作用：
        通过注入的 checkpoint port 持久化审批事件；
        不调用 Tool，也不调用任何 Provider。
    暂停点：
        checkpoint 持久化后中断；审批决策到达后使用相同的
        ``run_id`` 和 checkpoint 恢复。
    幂等性：
        使用相同 ``run_id`` 和 Tool 调用 ID 重放时复用已有审批事件，
        MUST NOT 创建第二个外部请求。
    异常：
        InvalidRunStateError: 必需状态缺失或不一致。
        CheckpointError: 暂停状态无法持久化。
    """
```

Node Docstring MUST NOT 声称底层不具备的事务、幂等或暂停保证；保证不足时 MUST 明确边界和补偿策略。

### 8.2 Tool Docstring

Tool Docstring MUST 明确：参数、权限、副作用、超时、重试和返回结构。合规示例：

```python
async def fetch_public_page(request: FetchPageRequest) -> FetchPageResult:
    """抓取一个已通过策略审批的公开 HTTP 页面。

    参数：
        request: 已校验 URL、租户上下文、最大字节数和截止时间。
    权限：
        需要 ``public_web.read`` 能力。Tool Runtime 在调用前应用
        DNS/IP SSRF 策略和租户作用域限流。
    副作用：
        执行只读外部 HTTP 请求并发出审计事件；
        不向目标站点写入内容。
    超时：
        使用请求截止时间与运行时策略上限中的较小值。
    重试：
        仅在总截止时间内重试已分类的临时连接失败；
        DNS 策略拒绝和 4xx 响应不重试。
    返回：
        归一化结果，包含最终 URL、状态、安全响应头、
        有界内容、内容哈希和来源元数据。
    异常：
        ToolPermissionError: URL 或调用方不被允许。
        ToolTimeoutError: 受治理的截止时间已到期。
        ToolResultLimitError: 响应超过配置的字节上限。
    """
```

### 8.3 Provider Docstring

Provider 公共适配器 Docstring MUST 说明内部能力到厂商 API/SDK 的映射、连接池和超时、厂商错误归一化、重试/限流及降级行为。它 MUST 明确哪些厂商字段不会向上泄露。配置键和 Secret 名称 MAY 在配置对象文档中说明，但真实值 MUST NOT 出现。

## 9. 行内注释

行内注释 SHOULD 解释原因、不变量、边界、风险和非显而易见的取舍，MUST NOT 逐行翻译代码。

坏注释与好注释对比：

```python
# 坏：把重试次数加一
retry_count += 1

# 好：首次调用也消耗预算，防止 Provider 在限流时形成无界重试。
retry_count += 1
```

```python
# 坏：检查 URL
if not policy.allows(url):
    raise ToolPermissionError()

# 好：安全不变量要求重定向后的目标 MUST 复查，避免公开 URL 跳转到内网地址。
if not policy.allows(url):
    raise ToolPermissionError()
```

代码足够清晰时 MAY 不写注释。复杂算法 SHOULD 在模块或函数 Docstring 说明来源、假设与复杂度；MUST NOT 用大量行内注释补救职责混乱的函数。

## 10. 待办、死代码与敏感内容

- `TODO`、`FIXME`、`HACK` 等待办标记 MUST 包含任务编号或责任人，并写明移除条件，例如 `TODO(AGENT-123, owner:platform): remove after checkpoint migration`。
- 没有跟踪信息、没有退出条件或永久性豁免语义的待办 MUST NOT 合入或交付。
- 被注释掉的死代码、旧实现和导入 MUST NOT 保留；历史追踪由版本管理或正式替代文档承担。
- 注释和 Docstring MUST NOT 包含密钥、令牌、连接串、个人信息、真实客户数据、完整 Prompt 或可还原的敏感文档。
- 为解释 Prompt 行为，文档 SHOULD 使用最小、合成、脱敏片段并说明变量与安全边界，MUST NOT 复制生产 Prompt 全文。

## 11. 结构化日志

日志 MUST 使用结构化事件，而不是依赖字符串拼接解析。与场景相关时 SHOULD 包含以下标准字段：

| 字段 | 含义 |
|---|---|
| `run_id`、`trace_id` | Run 与跨组件 Trace 关联 |
| `tenant_id`、`user_id` | 经批准且可脱敏的租户与用户上下文 |
| `strategy`、`agent_name` | 执行模式与受控 Agent 标识 |
| `graph_name`、`node_name` | Graph 与 Node 位置 |
| `tool_name`、`provider`、`model` | 外部调用和模型逻辑标识 |
| `event_name`、`status`、`error_code` | 稳定事件、状态与错误分类 |
| `duration_ms`、`attempt`、`token_usage` | 延迟、重试和用量；只在真实可得时记录 |

日志 MUST NOT 记录 Secret、Authorization/Cookie、连接串、完整 Prompt、模型完整原始响应、原始敏感文档、未脱敏个人信息或跨租户正文。`tenant_id`、`user_id` 等字段的采集和保留 MUST 符合最小必要原则；需要关联而无需明文时 SHOULD 使用稳定脱敏标识。

异常日志 MUST 使用稳定 `error_code` 和安全消息；堆栈只 MAY 出现在受控内部日志，且 MUST 在输出前经过敏感信息检查。高频 Token/流事件 SHOULD 聚合或采样，MUST NOT 造成成本与隐私风险。
