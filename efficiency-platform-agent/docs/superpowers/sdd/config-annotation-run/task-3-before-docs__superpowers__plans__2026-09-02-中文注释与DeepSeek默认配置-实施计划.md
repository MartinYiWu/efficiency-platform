# 中文注释与 DeepSeek 默认配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将中文技术注释和逐项配置说明固化为纯 Agent 侧工程约束，并在不填入 DeepSeek API Key 的前提下配置 DeepSeek 官方默认端点和模型层级。

**Architecture:** 配置的敏感值保留在本机忽略的 `.env`，可共享模板保留在 `.env.example`，不含密钥的模型路由策略保留在 `config/llm-routing.toml`。每个项目自维护且支持注释语法的配置项都使用紧邻上方的中文说明；自动化测试校验共享模板、路由文件及本机 `.env`（若存在）的说明结构。

**Tech Stack:** Python 3.13 标准库 `unittest`、`tomllib`、TOML、dotenv 格式、Markdown。

## Global Constraints

- 仅覆盖 `D:\efficiency-platform\efficiency-platform-agent` 纯 Agent 侧工程；不得修改 Java 侧、部署、业务 Agent、Provider 或模型路由运行时代码。
- 项目自行编写的 Python 注释、Docstring、SQL 注释和配置注释 MUST 使用中文；标识符、环境变量、Provider 名和模型 ID 保持英文。
- 每个项目自维护且支持注释语法的配置项 MUST 具有紧邻上方的中文说明；注释不得包含真实密钥、密码、连接串或个人数据。
- `.env` 必须继续被 Git 忽略；`.env.example` 不得含真实运行时值；`uv.lock` 为工具生成文件，不得人工加注释。
- DeepSeek 仅配置官方 OpenAI 兼容端点 `https://api.deepseek.com`、`deepseek-v4-flash` 和 `deepseek-v4-pro`；`AGENT_LLM_DEEPSEEK_API_KEY` 必须为空。
- 不发起 DeepSeek、PostgreSQL、Redis、COS、DashScope 或其他外部服务调用。
- 当前目录不是 Git 仓库；不得执行提交、推送或声称已提交。

---

### Task 1: 先建立配置说明与 DeepSeek 映射的失败测试

**Files:**
- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\config\test_llm_configuration_template.py`

**Interfaces:**
- Consumes: 项目根目录 `.env.example`、可选的本机 `.env`、`config/llm-routing.toml`。
- Produces: `assert_assignments_have_chinese_comments(lines: list[str]) -> None`，用于断言每个 `KEY=value` 或 `key = value` 配置项具有紧邻中文注释。

- [ ] **Step 1: 写入失败测试**

在 `LlmConfigurationTemplateTest` 中新增下列测试和辅助方法；注释与断言文本均使用中文：

```python
    @staticmethod
    def assert_assignments_have_chinese_comments(lines: list[str]) -> None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            previous = lines[index - 1].strip() if index else ""
            has_chinese_comment = previous.startswith("#") and any(
                "\u4e00" <= character <= "\u9fff" for character in previous
            )
            if not has_chinese_comment:
                raise AssertionError(f"配置项缺少紧邻的中文说明：{stripped.split('=', 1)[0]}")

    def test_shared_configuration_assignments_have_chinese_comments(self) -> None:
        self.assert_assignments_have_chinese_comments(
            (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        )
        self.assert_assignments_have_chinese_comments(
            (PROJECT_ROOT / "config" / "llm-routing.toml")
            .read_text(encoding="utf-8")
            .splitlines()
        )

    def test_local_env_assignments_have_chinese_comments_when_present(self) -> None:
        local_env = PROJECT_ROOT / ".env"
        if local_env.exists():
            self.assert_assignments_have_chinese_comments(
                local_env.read_text(encoding="utf-8").splitlines()
            )

    def test_deepseek_default_mapping_uses_current_official_model_ids(self) -> None:
        values = self.read_env_values(PROJECT_ROOT / ".env.example")

        self.assertEqual(values["AGENT_LLM_DEEPSEEK_BASE_URL"], "https://api.deepseek.com")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_API_KEY"], "")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_FAST_MODEL"], "deepseek-v4-flash")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_BALANCED_MODEL"], "deepseek-v4-flash")
        self.assertEqual(values["AGENT_LLM_DEEPSEEK_STRONG_MODEL"], "deepseek-v4-pro")
```

同时将既有 `.env.example` 解析推导为复用方法：

```python
    @staticmethod
    def read_env_values(path: Path) -> dict[str, str]:
        return {
            key: value
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
            for key, value in [line.split("=", maxsplit=1)]
        }
```

- [ ] **Step 2: 运行测试并确认失败**

执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v
```

预期：因现有配置项没有逐项紧邻中文说明，或 DeepSeek 值尚为空，新增测试失败；旧测试仍可执行。

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

### Task 3: 固化工程约束并执行全量验证

**Files:**
- Modify: `D:\efficiency-platform\efficiency-platform-agent\AGENTS.md`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\standards\01-工程与目录规范.md`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\standards\03-Python编码与注释规范.md`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\config\test_llm_configuration_template.py`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\governance\test_documentation_contract.py`
- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\plans\2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`

**Interfaces:**
- Consumes: Task 1/2 的结构验证和已批准设计。
- Produces: 可执行的中文注释/配置说明规范、通过的全量测试和已完成状态的实施记录。

- [ ] **Step 1: 收紧工程与编码规范**

在 `AGENTS.md` 的开发工作流章节增加项目级约束：本项目永久不是 Git 仓库，MUST NOT 要求、执行或声称 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程；变更审查使用文件快照、文件级差异包和项目内进度账本。

在 `01-工程与目录规范.md` 的配置章节写入以下等价条款：

```markdown
- 每个项目自维护且支持注释语法的有效配置项 MUST 具有紧邻上方的中文说明；说明 MUST 覆盖用途，必要时覆盖格式、单位、敏感性、默认值、启用条件或缺失行为。注释 MUST NOT 包含真实 Secret。
- 不支持注释语法或由工具自动生成的配置文件 MUST NOT 人工插入注释；其配置项说明 MUST 写入紧邻的人工维护配置、Schema 或说明文档。
```

在 `03-Python编码与注释规范.md` 将“中文 Docstring 和注释 MAY”收紧为“项目自行编写的 Python Docstring 和注释 MUST 使用中文”，并保留英文标识符和标准技术术语的例外说明。

- [ ] **Step 2: 扩展规范测试的稳定断言**

如果 `tests/governance/test_documentation_contract.py` 已存在规范文本断言，则添加以下所需短语的断言：

```python
"每个项目自维护且支持注释语法的有效配置项 MUST 具有紧邻上方的中文说明",
"项目自行编写的 Python Docstring 和注释 MUST 使用中文",
```

若该测试不以短语白名单方式断言，保持其现有测试结构，并仅加入能验证这两条新约束的最小测试。

- [ ] **Step 3: 执行全量测试**

执行：

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

预期：所有测试通过，且不发起外部连接、不输出 Secret。

- [ ] **Step 4: 更新实施计划状态并做静态复核**

将本计划每个已完成复选框改为 `[x]`，并在文档末尾记录：实际修改文件、失败测试证据、通过测试命令与结果、未执行的外部调用。扫描计划和设计文档中是否存在未完成占位标记或无证据的完成声明；发现后在同一轮修正。

## 计划自检

- 设计中的中文注释规则、逐项配置说明、DeepSeek 映射、API Key 保持为空、无外部调用和纯 Agent 侧边界均有对应任务。
- 每一项代码/配置行为都先由 Task 1 的失败测试覆盖，Task 2 通过最小修改转绿，Task 3 完成全量回归。
- 文件路径、环境变量名与已批准设计一致；不存在未定义接口、占位步骤或 Git 提交指令。
