### Task 2: 补齐模板与本机配置说明，并写入 DeepSeek 非敏感默认值

**Files:**
- Modify: `D:\efficiency-platform\efficiency-platform-agent\.env.example`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\.env`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\config\llm-routing.toml`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\pyproject.toml`

**Interfaces:**
- Consumes: Task 1 的结构性配置测试和 `AGENT_LLM_DEEPSEEK_*` 环境变量名称。
- Produces: 具有逐项中文说明的共享模板、模型路由配置和本机配置；本机 API Key 继续为空。

- [ ] **Step 1: 为 `.env.example` 的每个变量添加紧邻中文说明**

将每个变量拆为“说明行 + 变量行”。例如：

```dotenv
# 向量数据库连接地址；仅在本机 .env 或受信任 Secret 注入中填写，模板不得包含真实连接串。
AGENT_VECTOR_DATABASE_URL=

# DeepSeek 官方 OpenAI 兼容服务地址；当前使用 https://api.deepseek.com。
AGENT_LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com

# DeepSeek API 密钥；敏感值必须为空，由本机 .env 或 Secret 注入。
AGENT_LLM_DEEPSEEK_API_KEY=

# 快模型的官方模型标识；用于低复杂度任务。
AGENT_LLM_DEEPSEEK_FAST_MODEL=deepseek-v4-flash
```

所有遗留基础设施变量和未来模型池变量也必须各自具有说明，且仅 DeepSeek 的非敏感地址/模型 ID 写入值。

- [ ] **Step 2: 为 `.env` 添加说明且只填充 DeepSeek 非敏感值**

对已存在的每个环境变量插入紧邻中文说明，保持现有基础设施值逐字不变。仅设置下列 DeepSeek 值：

```dotenv
# DeepSeek 官方 OpenAI 兼容服务地址；不含密钥。
AGENT_LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com

# DeepSeek API 密钥；必须由使用者后续填写，当前保持为空。
AGENT_LLM_DEEPSEEK_API_KEY=

# 快模型的官方模型标识；用于低复杂度任务。
AGENT_LLM_DEEPSEEK_FAST_MODEL=deepseek-v4-flash

# 平衡模型的官方模型标识；当前复用快模型，保留独立逻辑层以支持后续替换。
AGENT_LLM_DEEPSEEK_BALANCED_MODEL=deepseek-v4-flash

# 强模型的官方模型标识；用于高复杂度任务。
AGENT_LLM_DEEPSEEK_STRONG_MODEL=deepseek-v4-pro
```

不得打印、复制、改写或移动 `.env` 中已有敏感值；未来模型池变量保持空值。

- [ ] **Step 3: 为 `config/llm-routing.toml` 和 `pyproject.toml` 的每个配置项添加说明**

TOML 中每个配置项必须有紧邻中文注释。例如：

```toml
# 选择模式：Agent 提议逻辑能力层，Harness 施加硬性约束。
selection_mode = "agent_proposed_with_harness_guardrails"

# 是否允许在可重试失败后向较低能力层降级。
allow_lower_tier_degrade_on_retry = true
```

`pyproject.toml` 的每个 `[project]` 与 `[tool.unittest]` 配置项也必须有紧邻中文说明。不得修改依赖、Python 版本范围或工具语义。

- [ ] **Step 4: 运行新增测试并确认通过**

执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v
```

预期：所有配置说明测试和 DeepSeek 映射测试通过；不输出本机 `.env` 的值。

