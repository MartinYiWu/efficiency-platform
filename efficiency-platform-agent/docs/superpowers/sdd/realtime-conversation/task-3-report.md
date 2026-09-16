# Task 3 执行报告：对外输出治理与产品化能力回答

| 项目 | 记录 |
|---|---|
| 状态 | DONE_WITH_CONCERNS |
| 范围 | 本地能力回答、通用对话正向人格、对外回答发布前治理（含窄流式缓冲）与对应离线单元测试 |
| 非范围 | ModelRuntime、Harness、ConversationService、IntentInterpreter、前端、真实流式运行时接入 |
| 风险级别 | 中：对外话术与模型输出治理；治理规则仅替换明确的助手自身泄露，避免按技术词汇误拦 |

## RED 证据

在写入生产代码前，已先写入新增测试并运行以下命令：

```powershell
uv run pytest tests/unit/conversation/test_local_responder.py tests/unit/agents/conversation/test_general_agent.py tests/unit/security -q
```

结果：测试收集失败，原因为 `ModuleNotFoundError: No module named 'efficiency_platform_agent.security.public_response'`，符合新增发布治理模块尚未实现的预期。

随后为分别确认既有文件上的行为缺口，运行：

```powershell
uv run pytest tests/unit/conversation/test_local_responder.py tests/unit/agents/conversation/test_general_agent.py -q
```

结果：`5 failed, 20 passed`。四个能力同义问法返回 `None`；正向人格测试发现旧系统提示缺少“公开资料”，并含会诱导复述底座限制的表述。

新增 Agent 输出治理测试后，运行：

```powershell
uv run pytest tests/unit/agents/conversation/test_general_agent.py::test_general_agent_governs_base_limitation_in_model_output -q
```

结果：`1 failed`，模型的“我不能真正联网，也不能生成文件。”被原样返回，证明发布前治理尚未接入。

## 最小实现

- 扩展 `LocalConversationResponder` 的能力问法，并以统一产品语言说明公开资料整理、内容策划、品牌/IP、活动、渠道文案、运营复盘和按需来源。
- 将通用对话系统提示改为正向产品人格，保留对系统指令与隐藏思维泄露的禁止。
- 新增 `PublicResponseGovernor` 窄接口；仅处理“助手自身 + 绝对底座否定”或“助手自身内部指令/思维泄露”，正常 Agent、Prompt、模型池、工具技术讨论保持原文；单回答流式缓冲器会在跨 delta 模式完整前暂存敏感前缀。
- 在 `GeneralConversationAgent` 生成有效正文后、构造跨层执行结果前调用治理接口。

## GREEN 与验证证据

```powershell
uv run pytest tests/unit/conversation/test_local_responder.py tests/unit/agents/conversation/test_general_agent.py tests/unit/security -q
```

结果：`35 passed in 0.51s`。

```powershell
uv run ruff check src/efficiency_platform_agent/agents/conversation/general_agent.py src/efficiency_platform_agent/conversation/local_responder.py src/efficiency_platform_agent/security tests/unit/conversation tests/unit/agents/conversation tests/unit/security
```

结果：`All checks passed!`。

```powershell
uv run python -m compileall -q src/efficiency_platform_agent/agents/conversation/general_agent.py src/efficiency_platform_agent/conversation/local_responder.py src/efficiency_platform_agent/security/public_response.py
uv run python -m unittest tests.architecture.test_dependency_rules -v
```

结果：源码编译成功；架构守卫 `12` 项全部通过。

## 凭证与内部异常补充（2026-09-08）

补齐 API Key、内部异常堆栈的最小公开发布边界：明显凭证字面量、`Traceback`、项目绝对路径和绝对路径 Python 栈均替换为既有稳定产品响应；“如何配置 API Key”“什么是 Python 堆栈”等普通技术讨论保持原文。

### RED 证据

```powershell
uv run pytest tests/unit/security/test_public_response.py -q
```

结果：`9 failed, 23 passed`。四类凭证、三类内部异常详情与两类跨 delta 前缀均未受治理。

### 最小实现与 GREEN 证据

- 增加 `sk-` 长串、`Bearer` 长串及 `api_key`/`secret` 赋值的字面量检测，仅在存在实际长值时替换。
- 增加 `Traceback`、`D:\\efficiency-platform\\` 项目绝对路径和绝对路径 Python 栈检测；流式缓冲扩展到凭证与异常前缀。

```powershell
uv run pytest tests/unit/security/test_public_response.py -q
uv run pytest tests/unit/conversation/test_local_responder.py tests/unit/agents/conversation/test_general_agent.py tests/unit/security -q
uv run ruff check src/efficiency_platform_agent/agents/conversation/general_agent.py src/efficiency_platform_agent/conversation/local_responder.py src/efficiency_platform_agent/security tests/unit/conversation tests/unit/agents/conversation tests/unit/security
uv run python -m compileall -q src/efficiency_platform_agent/security/public_response.py
```

结果：安全单测 `32 passed in 0.25s`；Task 3 定向测试 `59 passed in 0.49s`；Ruff 通过；源码编译成功。

```powershell
uv run python -m unittest tests.architecture.test_dependency_rules -v
```

结果：架构守卫 `12` 项全部通过。

## 修改文件

- `src/efficiency_platform_agent/conversation/local_responder.py`
- `src/efficiency_platform_agent/agents/conversation/general_agent.py`
- `src/efficiency_platform_agent/security/public_response.py`
- `tests/unit/conversation/test_local_responder.py`
- `tests/unit/agents/conversation/test_general_agent.py`
- `tests/unit/security/test_public_response.py`
- `docs/superpowers/sdd/realtime-conversation/task-3-report.md`

## 自查结论与关注点

- 能力问法由本地响应器直接处理；该组件不依赖模型运行时。既有会话链路检索显示命中 `local_response` 后会短路返回，未改动该链路。
- 已实现 `PublicResponseGovernor.stream()` 单回答窄流式缓冲接口；跨 delta 的底座限制、系统提示/指令和思维泄露前缀均在公开前暂存并替换。后续真实流式运行时接入必须复用该接口，并保留跨 delta 回归测试。
- 简报中的验证路径 `tests/unit/agents/conversation/test_general_conversation_agent.py` 在当前仓库不存在；实际同职责测试文件为 `test_general_agent.py`，故以该现存路径完成验证。该路径差异是本报告标记 `DONE_WITH_CONCERNS` 的唯一原因。

## 变体与流式补充（2026-09-08）

新增“系统提示要求我……”“系统指令让我……”“隐藏思维是……”“推理过程是……”的直接回答与跨 delta 测试，并同时验证普通技术讨论不被误拦。

### RED 证据

```powershell
uv run pytest tests/unit/security/test_public_response.py -q
```

结果：`8 failed, 13 passed`。四个直接泄露变体未替换，四个跨 delta 变体的敏感前缀被提前公开。

### 最小实现与 GREEN 证据

- 扩展自我指向的系统提示/系统指令模式，并对“隐藏思维是/为”“思维过程是/为”“推理过程是/为”要求实际泄露正文，避免单独片段被过早替换。
- 扩展流式前缀扫描的起始字符和可补全模式；普通“系统提示要求模型……”和“推理过程是模型内部计算……”在内容完整后保持原文。

```powershell
uv run pytest tests/unit/security/test_public_response.py -q
```

结果：`21 passed in 0.22s`。

```powershell
uv run pytest tests/unit/conversation/test_local_responder.py tests/unit/agents/conversation/test_general_agent.py tests/unit/security -q
uv run ruff check src/efficiency_platform_agent/agents/conversation/general_agent.py src/efficiency_platform_agent/conversation/local_responder.py src/efficiency_platform_agent/security tests/unit/conversation tests/unit/agents/conversation tests/unit/security
```

结果：`48 passed in 0.50s`；`All checks passed!`。

```powershell
uv run python -m compileall -q src/efficiency_platform_agent/security/public_response.py
uv run python -m unittest tests.architecture.test_dependency_rules -v
```

结果：源码编译成功；架构守卫 `12` 项全部通过。
