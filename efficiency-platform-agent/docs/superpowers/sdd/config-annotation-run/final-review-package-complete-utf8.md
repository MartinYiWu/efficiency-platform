# 完整 UTF-8 最终审查包
生成时间：2026-09-02T17:44:50

## 安全边界

- 本工件未读取本机 `.env` 原始文件。
- `.env` 仅使用 Task 2 已存在的脱敏快照和 Task 4 已存在的公开状态证据。
- 差异生成使用 Python 标准库 `difflib`；项目不是 Git 仓库，本流程未依赖 Git。

## 覆盖范围

- Task 1：配置测试基线到当前配置测试，含 Task 5 新增占位注释拒绝用例。
- Task 2：`.env.example`、路由 TOML、`pyproject.toml` 和 `.env` 脱敏结构差异。
- Task 3：`AGENTS.md`、工程规范、Python 规范、治理测试和实施计划。
- Task 4：`.gitignore` 精确白名单与本机 DeepSeek 公开状态证据。

## Task 1 配置测试基线 -> 当前配置测试

```diff
--- docs\superpowers\sdd\config-annotation-run\task-1-before.py+++ tests\config\test_llm_configuration_template.py@@ -9,6 +9,103 @@ 
 
 class LlmConfigurationTemplateTest(unittest.TestCase):
+    @staticmethod
+    def has_meaningful_chinese_comment(line: str) -> bool:
+        chinese_character_count = sum("\u4e00" <= character <= "\u9fff" for character in line)
+        return (
+            line.startswith("#")
+            and chinese_character_count >= 8
+            and any(punctuation in line for punctuation in ("。", "；"))
+        )
+
+    @staticmethod
+    def assert_assignments_have_chinese_comments(lines: list[str]) -> None:
+        for index, line in enumerate(lines):
+            stripped = line.strip()
+            if not stripped or stripped.startswith("#") or "=" not in stripped:
+                continue
+
+            previous = lines[index - 1].strip() if index else ""
+            if not LlmConfigurationTemplateTest.has_meaningful_chinese_comment(previous):
+                raise AssertionError(f"配置项缺少紧邻的中文说明：{stripped.split('=', 1)[0]}")
+
+    @staticmethod
+    def read_env_values(path: Path) -> dict[str, str]:
+        return {
+            key: value
+            for line in path.read_text(encoding="utf-8").splitlines()
+            if line and not line.startswith("#") and "=" in line
+            for key, value in [line.split("=", maxsplit=1)]
+        }
+
+    @staticmethod
+    def assert_rules_have_chinese_comments(lines: list[str]) -> None:
+        for index, line in enumerate(lines):
+            stripped = line.strip()
+            if not stripped or stripped.startswith("#"):
+                continue
+
+            previous = lines[index - 1].strip() if index else ""
+            if not LlmConfigurationTemplateTest.has_meaningful_chinese_comment(previous):
+                raise AssertionError(f"忽略规则缺少紧邻的中文说明：{stripped}")
+
+    def test_shared_configuration_assignments_have_chinese_comments(self) -> None:
+        self.assert_assignments_have_chinese_comments(
+            (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
+        )
+        self.assert_assignments_have_chinese_comments(
+            (PROJECT_ROOT / "config" / "llm-routing.toml").read_text(encoding="utf-8").splitlines()
+        )
+
+    def test_rejects_placeholder_chinese_comment_for_assignment(self) -> None:
+        with self.assertRaises(AssertionError) as context:
+            self.assert_assignments_have_chinese_comments(
+                [
+                    "# 中文",
+                    "AGENT_LLM_DEEPSEEK_API_KEY=should-not-appear",
+                ]
+            )
+
+        message = str(context.exception)
+        self.assertIn("AGENT_LLM_DEEPSEEK_API_KEY", message)
+        self.assertNotIn("should-not-appear", message)
+
+    def test_local_env_assignments_have_chinese_comments_when_present(self) -> None:
+        local_env = PROJECT_ROOT / ".env"
+        if local_env.exists():
+            self.assert_assignments_have_chinese_comments(
+                local_env.read_text(encoding="utf-8").splitlines()
+            )
+
+    def test_local_env_deepseek_public_state_matches_when_present(self) -> None:
+        local_env = PROJECT_ROOT / ".env"
+        if not local_env.exists():
+            return
+
+        expected_local_deepseek_values = {
+            "AGENT_LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
+            "AGENT_LLM_DEEPSEEK_FAST_MODEL": "deepseek-v4-flash",
+            "AGENT_LLM_DEEPSEEK_BALANCED_MODEL": "deepseek-v4-flash",
+            "AGENT_LLM_DEEPSEEK_STRONG_MODEL": "deepseek-v4-pro",
+            "AGENT_LLM_DEEPSEEK_API_KEY": "",
+            "AGENT_LLM_MODEL_POOL_BASE_URL": "",
+            "AGENT_LLM_MODEL_POOL_API_KEY": "",
+        }
+        values = self.read_env_values(local_env)
+
+        for key, expected_value in expected_local_deepseek_values.items():
+            if values.get(key) != expected_value:
+                self.fail("本机 .env DeepSeek 公开状态不匹配")
+
+    def test_deepseek_default_mapping_uses_current_official_model_ids(self) -> None:
+        values = self.read_env_values(PROJECT_ROOT / ".env.example")
+
+        self.assertEqual(values["AGENT_LLM_DEEPSEEK_BASE_URL"], "https://api.deepseek.com")
+        self.assertEqual(values["AGENT_LLM_DEEPSEEK_API_KEY"], "")
+        self.assertEqual(values["AGENT_LLM_DEEPSEEK_FAST_MODEL"], "deepseek-v4-flash")
+        self.assertEqual(values["AGENT_LLM_DEEPSEEK_BALANCED_MODEL"], "deepseek-v4-flash")
+        self.assertEqual(values["AGENT_LLM_DEEPSEEK_STRONG_MODEL"], "deepseek-v4-pro")
+
     def test_routing_template_declares_dynamic_deepseek_default(self) -> None:
         document = tomllib.loads(
             (PROJECT_ROOT / "config/llm-routing.toml").read_text(encoding="utf-8")
@@ -44,13 +141,7 @@         self.assertEqual(pool["api_key_env"], "AGENT_LLM_MODEL_POOL_API_KEY")
 
     def test_env_template_contains_only_empty_runtime_values(self) -> None:
-        lines = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
-        values = {
-            key: value
-            for line in lines
-            if line and not line.startswith("#") and "=" in line
-            for key, value in [line.split("=", maxsplit=1)]
-        }
+        values = self.read_env_values(PROJECT_ROOT / ".env.example")
 
         for key in (
             "AGENT_VECTOR_DATABASE_URL",
@@ -66,11 +157,7 @@             "AGENT_COS_REGION",
             "AGENT_COS_BUCKET",
             "AGENT_COS_BASE_URL",
-            "AGENT_LLM_DEEPSEEK_BASE_URL",
             "AGENT_LLM_DEEPSEEK_API_KEY",
-            "AGENT_LLM_DEEPSEEK_FAST_MODEL",
-            "AGENT_LLM_DEEPSEEK_BALANCED_MODEL",
-            "AGENT_LLM_DEEPSEEK_STRONG_MODEL",
             "AGENT_LLM_MODEL_POOL_BASE_URL",
             "AGENT_LLM_MODEL_POOL_API_KEY",
         ):
@@ -83,3 +170,8 @@         self.assertIn(".env", content)
         self.assertIn(".env.*", content)
         self.assertIn("!.env.example", content)
+
+    def test_gitignore_rules_have_adjacent_chinese_comments(self) -> None:
+        self.assert_rules_have_chinese_comments(
+            (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
+        )
```

## Task 2 .env.example 基线 -> 当前 .env.example

```diff
--- docs\superpowers\sdd\config-annotation-run\task-2-before.env.example+++ .env.example@@ -1,25 +1,59 @@-# Legacy Java configuration domains, intentionally empty in the tracked template.
+# 向量数据库连接地址；模板中保持为空，运行时由本机 .env 或受信任 Secret 注入。
 AGENT_VECTOR_DATABASE_URL=
+
+# 任务代理连接地址；模板中保持为空，避免提交真实中间件地址。
 AGENT_TASK_BROKER_URL=
+
+# 运行事件 Redis 连接地址；模板中保持为空，运行时按环境单独配置。
 AGENT_RUN_EVENT_REDIS_URL=
+
+# 向量嵌入服务基础地址；模板中保持为空，避免误写真实供应商地址。
 AGENT_EMBEDDING_DASHSCOPE_BASE_URL=
+
+# 向量嵌入服务 API Key；敏感值必须为空，由本机 .env 或 Secret 注入。
 AGENT_EMBEDDING_DASHSCOPE_API_KEY=
+
+# 向量嵌入模型标识；模板中保持为空，待具体供应商与模型策略确定。
 AGENT_EMBEDDING_MODEL=
+
+# 向量维度；模板中保持为空，运行时与所选嵌入模型保持一致。
 AGENT_EMBEDDING_DIMENSIONS=
+
+# 重排服务 API Key；敏感值必须为空，由本机 .env 或 Secret 注入。
 AGENT_RERANK_DASHSCOPE_API_KEY=
+
+# 对象存储访问标识；敏感值必须为空，由本机 .env 或 Secret 注入。
 AGENT_COS_SECRET_ID=
+
+# 对象存储访问密钥；敏感值必须为空，由本机 .env 或 Secret 注入。
 AGENT_COS_SECRET_KEY=
+
+# 对象存储地域标识；模板中保持为空，按实际部署地域填写。
 AGENT_COS_REGION=
+
+# 对象存储桶名称；模板中保持为空，按实际桶配置填写。
 AGENT_COS_BUCKET=
+
+# 对象存储外部访问基础地址；模板中保持为空，按网关或 CDN 配置填写。
 AGENT_COS_BASE_URL=
 
-# DeepSeek direct provider. Fill only in the ignored local .env file.
-AGENT_LLM_DEEPSEEK_BASE_URL=
+# DeepSeek 官方 OpenAI 兼容服务地址；当前默认使用官方域名，不包含密钥。
+AGENT_LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com
+
+# DeepSeek API Key；敏感值必须为空，由本机 .env 或 Secret 注入。
 AGENT_LLM_DEEPSEEK_API_KEY=
-AGENT_LLM_DEEPSEEK_FAST_MODEL=
-AGENT_LLM_DEEPSEEK_BALANCED_MODEL=
-AGENT_LLM_DEEPSEEK_STRONG_MODEL=
 
-# Future model pool. Keep empty until its provider contract is approved.
+# 快模型的官方模型标识；用于低复杂度任务。
+AGENT_LLM_DEEPSEEK_FAST_MODEL=deepseek-v4-flash
+
+# 平衡模型的官方模型标识；当前复用快模型，保留独立配置位以支持后续替换。
+AGENT_LLM_DEEPSEEK_BALANCED_MODEL=deepseek-v4-flash
+
+# 强模型的官方模型标识；用于高复杂度任务。
+AGENT_LLM_DEEPSEEK_STRONG_MODEL=deepseek-v4-pro
+
+# 未来模型池的基础地址；当前保留为空，待供应商契约确认后启用。
 AGENT_LLM_MODEL_POOL_BASE_URL=
+
+# 未来模型池的 API Key；敏感值必须为空，待供应商契约确认后注入。
 AGENT_LLM_MODEL_POOL_API_KEY=
```

## Task 2 路由 TOML 基线 -> 当前路由 TOML

```diff
--- docs\superpowers\sdd\config-annotation-run\task-2-before.llm-routing.toml+++ config\llm-routing.toml@@ -1,35 +1,72 @@ [router]
+# 选择模式：由 Agent 提议能力层，再由 Harness 施加硬性约束。
 selection_mode = "agent_proposed_with_harness_guardrails"
+
+# 默认聊天路由名称；当前指向自适应的通用对话路由。
 default_route = "chat_default"
+
+# 是否允许在可重试失败后向较低能力层降级，以提升可用性。
 allow_lower_tier_degrade_on_retry = true
 
 [providers.deepseek_direct]
+# 是否启用 DeepSeek 直连提供方；当前默认启用。
 enabled = true
+
+# 提供方适配器类型；使用 OpenAI 兼容协议访问 DeepSeek。
 adapter_kind = "openai_compatible"
+
+# DeepSeek 基础地址所读取的环境变量名称。
 base_url_env = "AGENT_LLM_DEEPSEEK_BASE_URL"
+
+# DeepSeek API Key 所读取的环境变量名称。
 api_key_env = "AGENT_LLM_DEEPSEEK_API_KEY"
 
 [providers.model_pool]
+# 是否启用未来模型池；当前保留关闭状态。
 enabled = false
+
+# 模型池适配器类型；未接入前保持未配置标识。
 adapter_kind = "unconfigured"
+
+# 未来模型池基础地址所读取的环境变量名称。
 base_url_env = "AGENT_LLM_MODEL_POOL_BASE_URL"
+
+# 未来模型池 API Key 所读取的环境变量名称。
 api_key_env = "AGENT_LLM_MODEL_POOL_API_KEY"
 
 [routes.chat_default]
+# 路由候选选择顺序；自适应模式会按任务复杂度在能力层间选择。
 selection_order = "adaptive"
+
+# 该路由允许使用的能力层列表；按 fast、balanced、strong 逐层开放。
 allowed_tiers = ["fast", "balanced", "strong"]
 
 [[routes.chat_default.candidates]]
+# 候选提供方名称；当前快层使用 DeepSeek 直连。
 provider = "deepseek_direct"
+
+# 候选能力层；用于低复杂度任务。
 tier = "fast"
+
+# 快层模型标识所读取的环境变量名称。
 model_env = "AGENT_LLM_DEEPSEEK_FAST_MODEL"
 
 [[routes.chat_default.candidates]]
+# 候选提供方名称；当前平衡层使用 DeepSeek 直连。
 provider = "deepseek_direct"
+
+# 候选能力层；用于中等复杂度任务。
 tier = "balanced"
+
+# 平衡层模型标识所读取的环境变量名称。
 model_env = "AGENT_LLM_DEEPSEEK_BALANCED_MODEL"
 
 [[routes.chat_default.candidates]]
+# 候选提供方名称；当前强层使用 DeepSeek 直连。
 provider = "deepseek_direct"
+
+# 候选能力层；用于高复杂度任务。
 tier = "strong"
+
+# 强层模型标识所读取的环境变量名称。
 model_env = "AGENT_LLM_DEEPSEEK_STRONG_MODEL"
```

## Task 2 pyproject.toml 基线 -> 当前 pyproject.toml

```diff
--- docs\superpowers\sdd\config-annotation-run\task-2-before.pyproject.toml+++ pyproject.toml@@ -1,9 +1,19 @@ [project]
+# 项目名称；用于标识当前 Agent 运行时包。
 name = "efficiency-platform-agent"
+
+# 项目版本；当前为初始基线版本号。
 version = "0.1.0"
+
+# 项目简介；描述当前包的职责边界。
 description = "Framework-neutral foundation for the efficiency platform Agent runtime."
+
+# Python 版本范围；保持现有解释器约束，不改变运行语义。
 requires-python = ">=3.13,<3.14"
+
+# 运行时依赖列表；当前为空，表示基线阶段不声明额外依赖。
 dependencies = []
 
 [tool.unittest]
+# 单元测试起始目录；保持 unittest 从 tests 目录发现用例。
 start-directory = "tests"
```

## Task 2 .env 脱敏前快照 -> .env 脱敏后快照

```diff
--- docs\superpowers\sdd\config-annotation-run\task-2-before.env.redacted+++ docs\superpowers\sdd\config-annotation-run\task-2-after.env.redacted@@ -1,32 +1,59 @@-# User-authorized local configuration. This file is ignored and must never be committed.
+# 向量数据库连接地址；保留现有值不变，仅补充说明。
+AGENT_VECTOR_DATABASE_URL=<已脱敏>
 
-# Migrated legacy PostgreSQL Vector and Redis connections.
-AGENT_VECTOR_DATABASE_URL=<已脱敏>
+# 任务代理连接地址；保留现有值不变，仅补充说明。
 AGENT_TASK_BROKER_URL=<已脱敏>
+
+# 运行事件 Redis 连接地址；保留现有值不变，仅补充说明。
 AGENT_RUN_EVENT_REDIS_URL=<已脱敏>
 
-# Migrated legacy DashScope embedding configuration. Rerank reuses the same credential only.
+# 向量嵌入服务基础地址；保留现有值不变，仅补充说明。
 AGENT_EMBEDDING_DASHSCOPE_BASE_URL=<已脱敏>
+
+# 向量嵌入服务 API Key；敏感值不在输出中展示。
 AGENT_EMBEDDING_DASHSCOPE_API_KEY=<已脱敏>
+
+# 向量嵌入模型标识；保留现有值不变，仅补充说明。
 AGENT_EMBEDDING_MODEL=<已脱敏>
+
+# 向量维度；保留现有值不变，仅补充说明。
 AGENT_EMBEDDING_DIMENSIONS=<已脱敏>
+
+# 重排服务 API Key；敏感值不在输出中展示。
 AGENT_RERANK_DASHSCOPE_API_KEY=<已脱敏>
 
-# Migrated legacy Tencent COS configuration.
+# 对象存储访问标识；敏感值不在输出中展示。
 AGENT_COS_SECRET_ID=<已脱敏>
+
+# 对象存储访问密钥；敏感值不在输出中展示。
 AGENT_COS_SECRET_KEY=<已脱敏>
+
+# 对象存储地域标识；保留现有值不变，仅补充说明。
 AGENT_COS_REGION=<已脱敏>
+
+# 对象存储桶名称；保留现有值不变，仅补充说明。
 AGENT_COS_BUCKET=<已脱敏>
+
+# 对象存储外部访问基础地址；保留现有值不变，仅补充说明。
 AGENT_COS_BASE_URL=<已脱敏>
 
-# DeepSeek direct provider. Fill these locally when the API Key and actual model IDs are ready.
+# DeepSeek 官方 OpenAI 兼容服务地址；不含密钥，当前使用官方域名。
 AGENT_LLM_DEEPSEEK_BASE_URL=<已脱敏>
+
+# DeepSeek API Key；必须由使用者后续填写，当前保持为空。
 AGENT_LLM_DEEPSEEK_API_KEY=<已脱敏>
+
+# 快模型的官方模型标识；用于低复杂度任务。
 AGENT_LLM_DEEPSEEK_FAST_MODEL=<已脱敏>
+
+# 平衡模型的官方模型标识；当前复用快模型，保留独立配置位。
 AGENT_LLM_DEEPSEEK_BALANCED_MODEL=<已脱敏>
+
+# 强模型的官方模型标识；用于高复杂度任务。
 AGENT_LLM_DEEPSEEK_STRONG_MODEL=<已脱敏>
 
-# Future model pool. Keep empty until its provider contract is approved.
+# 未来模型池基础地址；保留现有值不变或为空，当前不启用。
 AGENT_LLM_MODEL_POOL_BASE_URL=<已脱敏>
+
+# 未来模型池 API Key；当前保持为空，待后续供应商接入。
 AGENT_LLM_MODEL_POOL_API_KEY=<已脱敏>
-
```

## Task 3 AGENTS.md 基线 -> 当前 AGENTS.md

```diff
--- docs\superpowers\sdd\config-annotation-run\task-3-before-AGENTS.md+++ AGENTS.md@@ -18,7 +18,7 @@ 
 ## 开发工作流
 
-变更 MUST 遵循：确认范围 → 阅读规范/实现 → 设计或 ADR → 实施计划 → 测试先行 → 最小实现 → 验证 → 文档同步 → 评审交付。新增扩展 SHOULD 走端口与注册机制，不修改 Harness 或 Graph Runtime 的公共生命周期；跨层依赖或架构裁决变更 MUST 先形成 ADR。
+变更 MUST 遵循：确认范围 → 阅读规范/实现 → 设计或 ADR → 实施计划 → 测试先行 → 最小实现 → 验证 → 文档同步 → 评审交付。新增扩展 SHOULD 走端口与注册机制，不修改 Harness 或 Graph Runtime 的公共生命周期；跨层依赖或架构裁决变更 MUST 先形成 ADR。本项目永久不是 Git 仓库，MUST NOT 要求、执行或声称 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程；变更审查 MUST 使用文件快照、文件级差异包和项目内进度账本。项目自行编写的注释、Docstring、SQL 注释和配置注释 MUST 使用中文；标识符、环境变量名、Provider 名称、模型 ID 和标准技术术语 MAY 保留英文。
 
 ## 测试与完成证据
 
```

## Task 3 工程规范基线 -> 当前工程规范

```diff
--- docs\superpowers\sdd\config-annotation-run\task-3-before-docs__standards__01-工程与目录规范.md+++ docs\standards\01-工程与目录规范.md@@ -6,7 +6,7 @@ | 状态 | 评审中 |
 | 作者/负责人 | Agent 平台维护者 |
 | 创建日期 | 2026-09-01 |
-| 最后更新日期 | 2026-09-01 |
+| 最后更新日期 | 2026-09-02 |
 | 评审人/批准人 | 评审人：尚未指定；批准人：尚未批准 |
 | 关联 ADR/设计/计划 | [纯 Agent 侧总体架构](../architecture/纯Agent侧总体架构.md)、[Agent 侧技术组件选型](../architecture/Agent侧技术组件选型.md)、[Agent 侧工程规范体系实施计划](../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md) |
 | 替代关系 | 无 |
@@ -129,6 +129,8 @@ - 项目元数据、依赖声明和工具静态配置 MUST 位于 `pyproject.toml`；MUST NOT 在多个互相冲突的配置文件中重复维护同一设置。
 - 运行期可变值和 Secret MUST 通过环境变量或受信任的 Secret 注入进入配置对象；业务模块 MUST 依赖类型化配置对象，MUST NOT 到处直接读取环境变量。
 - 配置对象 MUST 在应用组合根完成解析和校验，MUST 对缺失、非法范围和冲突配置快速失败。
+- 每个项目自维护且支持注释语法的有效配置项 MUST 具有紧邻上方的中文说明；说明 MUST 覆盖用途，必要时覆盖格式、单位、敏感性、默认值、启用条件或缺失行为。注释 MUST NOT 包含真实 Secret。
+- 不支持注释语法或由工具自动生成的配置文件 MUST NOT 人工插入注释；其配置项说明 MUST 写入紧邻的人工维护配置、Schema 或说明文档。
 - 密钥、令牌、连接串、真实账户、个人信息和生产数据 MUST NOT 写入源码、测试样本、Prompt、日志、数据库配置表或仓库文档。
 - 非敏感示例值 MAY 写入示例配置，但 MUST 使用明显无效的占位值并说明注入方式。
 - 配置键属于 Provider 实现细节时 MUST 在 Provider 内映射，上层 MUST NOT 感知厂商专有键。
```

## Task 3 Python 规范基线 -> 当前 Python 规范

```diff
--- docs\superpowers\sdd\config-annotation-run\task-3-before-docs__standards__03-Python编码与注释规范.md+++ docs\standards\03-Python编码与注释规范.md@@ -6,7 +6,7 @@ | 状态 | 评审中 |
 | 作者/负责人 | Agent 平台维护者 |
 | 创建日期 | 2026-09-01 |
-| 最后更新日期 | 2026-09-01 |
+| 最后更新日期 | 2026-09-02 |
 | 评审人/批准人 | 评审人：尚未指定；批准人：尚未批准 |
 | 关联 ADR/设计/计划 | [Agent 侧技术组件选型](../architecture/Agent侧技术组件选型.md)、[架构与依赖规范](02-架构与依赖规范.md)、[Agent 侧工程规范体系实施计划](../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md) |
 | 替代关系 | 无 |
@@ -23,7 +23,7 @@ 
 ## 2. 命名
 
-代码标识符 MUST 使用英文；中文 Docstring 和注释 MAY 保留 Graph、Checkpoint、Provider、Tool、Prompt、Schema 等标准英文技术术语。同一模块 MUST 保持一致的语言和术语风格。
+代码标识符 MUST 使用英文；项目自行编写的 Python Docstring 和注释 MUST 使用中文，并 MAY 保留 Graph、Checkpoint、Provider、Tool、Prompt、Schema 等标准英文技术术语。同一模块 MUST 保持一致的语言和术语风格。
 
 | 对象 | 规则 | 示例 |
 |---|---|---|
@@ -164,26 +164,26 @@ 
 ```python
 async def request_tool_approval(state: RunState) -> StateUpdate:
-    """Build a governed approval request for the pending tool call.
-
-    Input state:
-        Requires ``run_id``, tenant-scoped identity, and one validated
-        ``pending_tool_call``. The call has not executed yet.
-    Output update:
-        Sets ``status`` to ``WAITING_APPROVAL`` and appends an approval event;
-        it does not replace unrelated state fields.
-    Side effects:
-        Persists the approval event through the injected checkpoint port. It
-        does not invoke the tool or any provider.
-    Pause point:
-        Interrupts after the checkpoint is durable and resumes with the same
-        ``run_id`` and checkpoint when an approval decision arrives.
-    Idempotency:
-        Replaying the same ``run_id`` and tool-call id reuses the existing
-        approval event and MUST NOT create a second external request.
-    Raises:
-        InvalidRunStateError: Required state is missing or inconsistent.
-        CheckpointError: The pause state cannot be persisted.
+    """为待审批 Tool 调用构建受治理的审批请求。
+
+    输入状态：
+        必须包含 ``run_id``、租户作用域身份和一个已经校验的
+        ``pending_tool_call``；该调用尚未执行。
+    输出更新：
+        将 ``status`` 设置为 ``WAITING_APPROVAL`` 并追加审批事件；
+        不替换无关状态字段。
+    副作用：
+        通过注入的 checkpoint port 持久化审批事件；
+        不调用 Tool，也不调用任何 Provider。
+    暂停点：
+        checkpoint 持久化后中断；审批决策到达后使用相同的
+        ``run_id`` 和 checkpoint 恢复。
+    幂等性：
+        使用相同 ``run_id`` 和 Tool 调用 ID 重放时复用已有审批事件，
+        MUST NOT 创建第二个外部请求。
+    异常：
+        InvalidRunStateError: 必需状态缺失或不一致。
+        CheckpointError: 暂停状态无法持久化。
     """
 ```
 
@@ -195,28 +195,28 @@ 
 ```python
 async def fetch_public_page(request: FetchPageRequest) -> FetchPageResult:
-    """Fetch one policy-approved public HTTP page.
-
-    Args:
-        request: Validated URL, tenant context, maximum bytes, and deadline.
-    Permissions:
-        Requires the ``public_web.read`` capability. The Tool Runtime applies
-        DNS/IP SSRF policy and tenant-scoped rate limits before invocation.
-    Side effects:
-        Performs a read-only external HTTP request and emits an audit event; it
-        does not write to the target site.
-    Timeout:
-        Uses the smaller of the request deadline and runtime policy limit.
-    Retry:
-        Retries only classified transient connection failures within the total
-        deadline. DNS-policy denials and 4xx responses are not retried.
-    Returns:
-        A normalized result containing final URL, status, safe headers,
-        bounded content, content hash, and provenance metadata.
-    Raises:
-        ToolPermissionError: URL or caller is not allowed.
-        ToolTimeoutError: The governed deadline expires.
-        ToolResultLimitError: The response exceeds the configured byte limit.
+    """抓取一个已通过策略审批的公开 HTTP 页面。
+
+    参数：
+        request: 已校验 URL、租户上下文、最大字节数和截止时间。
+    权限：
+        需要 ``public_web.read`` 能力。Tool Runtime 在调用前应用
+        DNS/IP SSRF 策略和租户作用域限流。
+    副作用：
+        执行只读外部 HTTP 请求并发出审计事件；
+        不向目标站点写入内容。
+    超时：
+        使用请求截止时间与运行时策略上限中的较小值。
+    重试：
+        仅在总截止时间内重试已分类的临时连接失败；
+        DNS 策略拒绝和 4xx 响应不重试。
+    返回：
+        归一化结果，包含最终 URL、状态、安全响应头、
+        有界内容、内容哈希和来源元数据。
+    异常：
+        ToolPermissionError: URL 或调用方不被允许。
+        ToolTimeoutError: 受治理的截止时间已到期。
+        ToolResultLimitError: 响应超过配置的字节上限。
     """
 ```
 
```

## Task 3 治理测试基线 -> 当前治理测试

```diff
--- docs\superpowers\sdd\config-annotation-run\task-3-before-tests__governance__test_documentation_contract.py+++ tests\governance\test_documentation_contract.py@@ -71,6 +71,66 @@             "docs/superpowers/sdd/task-3-brief.md",
             "../templates/架构设计文档模板.md",
         ): "示例描述将写入 docs/standards/00-规范索引.md 的模板链接",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-AGENTS.md",
+            "docs/architecture/纯Agent侧总体架构.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-AGENTS.md",
+            "docs/architecture/Agent侧技术组件选型.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-AGENTS.md",
+            "docs/architecture/扩展开发约定.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-AGENTS.md",
+            "docs/standards/00-规范索引.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__01-工程与目录规范.md",
+            "../architecture/纯Agent侧总体架构.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__01-工程与目录规范.md",
+            "../architecture/Agent侧技术组件选型.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__01-工程与目录规范.md",
+            "../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__01-工程与目录规范.md",
+            "04-测试与质量门禁.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__01-工程与目录规范.md",
+            "05-数据库与SQL规范.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__03-Python编码与注释规范.md",
+            "../architecture/Agent侧技术组件选型.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__03-Python编码与注释规范.md",
+            "02-架构与依赖规范.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-3-before-docs__standards__03-Python编码与注释规范.md",
+            "../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-4-before-docs__standards__03-Python编码与注释规范.md",
+            "../architecture/Agent侧技术组件选型.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-4-before-docs__standards__03-Python编码与注释规范.md",
+            "02-架构与依赖规范.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
+        (
+            "docs/superpowers/sdd/config-annotation-run/task-4-before-docs__standards__03-Python编码与注释规范.md",
+            "../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md",
+        ): "历史快照保留原始相对链接，供文件级差异审查使用",
     }
 
     def test_required_governance_documents_exist(self) -> None:
@@ -88,6 +148,7 @@             "测试与完成证据",
             "数据库与 SQL",
             "安全红线",
+            "本项目永久不是 Git 仓库",
             "](docs/standards/00-规范索引.md)",
         )
         for marker in required_markers:
@@ -231,6 +292,21 @@                 errors.append(str(path.relative_to(PROJECT_ROOT)))
         self.assertEqual(errors, [])
 
+    def test_annotation_and_configuration_comment_rules_are_documented(self) -> None:
+        required_markers = {
+            PROJECT_ROOT / "docs/standards/01-工程与目录规范.md": (
+                "每个项目自维护且支持注释语法的有效配置项 MUST 具有紧邻上方的中文说明",
+            ),
+            PROJECT_ROOT / "docs/standards/03-Python编码与注释规范.md": (
+                "项目自行编写的 Python Docstring 和注释 MUST 使用中文",
+            ),
+        }
+        for path, markers in required_markers.items():
+            content = path.read_text(encoding="utf-8")
+            for marker in markers:
+                with self.subTest(path=path.name, marker=marker):
+                    self.assertIn(marker, content)
+
     def test_document_naming_status_sections_and_exception_rules_are_complete(self) -> None:
         content = (
             PROJECT_ROOT / "docs/standards/09-文档命名与变更治理规范.md"
```

## Task 3 计划基线 -> 当前实施计划

```diff
--- docs\superpowers\sdd\config-annotation-run\task-3-before-docs__superpowers__plans__2026-09-02-中文注释与DeepSeek默认配置-实施计划.md+++ docs\superpowers\plans\2026-09-02-中文注释与DeepSeek默认配置-实施计划.md@@ -29,7 +29,7 @@ - Consumes: 项目根目录 `.env.example`、可选的本机 `.env`、`config/llm-routing.toml`。
 - Produces: `assert_assignments_have_chinese_comments(lines: list[str]) -> None`，用于断言每个 `KEY=value` 或 `key = value` 配置项具有紧邻中文注释。
 
-- [ ] **Step 1: 写入失败测试**
+- [x] **Step 1: 写入失败测试**
 
 在 `LlmConfigurationTemplateTest` 中新增下列测试和辅助方法；注释与断言文本均使用中文：
 
@@ -88,7 +88,7 @@         }
 ```
 
-- [ ] **Step 2: 运行测试并确认失败**
+- [x] **Step 2: 运行测试并确认失败**
 
 执行：
 
@@ -110,7 +110,7 @@ - Consumes: Task 1 的结构性配置测试和 `AGENT_LLM_DEEPSEEK_*` 环境变量名称。
 - Produces: 具有逐项中文说明的共享模板、模型路由配置和本机配置；本机 API Key 继续为空。
 
-- [ ] **Step 1: 为 `.env.example` 的每个变量添加紧邻中文说明**
+- [x] **Step 1: 为 `.env.example` 的每个变量添加紧邻中文说明**
 
 将每个变量拆为“说明行 + 变量行”。例如：
 
@@ -130,7 +130,7 @@ 
 所有遗留基础设施变量和未来模型池变量也必须各自具有说明，且仅 DeepSeek 的非敏感地址/模型 ID 写入值。
 
-- [ ] **Step 2: 为 `.env` 添加说明且只填充 DeepSeek 非敏感值**
+- [x] **Step 2: 为 `.env` 添加说明且只填充 DeepSeek 非敏感值**
 
 对已存在的每个环境变量插入紧邻中文说明，保持现有基础设施值逐字不变。仅设置下列 DeepSeek 值：
 
@@ -153,7 +153,7 @@ 
 不得打印、复制、改写或移动 `.env` 中已有敏感值；未来模型池变量保持空值。
 
-- [ ] **Step 3: 为 `config/llm-routing.toml` 和 `pyproject.toml` 的每个配置项添加说明**
+- [x] **Step 3: 为 `config/llm-routing.toml` 和 `pyproject.toml` 的每个配置项添加说明**
 
 TOML 中每个配置项必须有紧邻中文注释。例如：
 
@@ -167,7 +167,7 @@ 
 `pyproject.toml` 的每个 `[project]` 与 `[tool.unittest]` 配置项也必须有紧邻中文说明。不得修改依赖、Python 版本范围或工具语义。
 
-- [ ] **Step 4: 运行新增测试并确认通过**
+- [x] **Step 4: 运行新增测试并确认通过**
 
 执行：
 
@@ -191,7 +191,7 @@ - Consumes: Task 1/2 的结构验证和已批准设计。
 - Produces: 可执行的中文注释/配置说明规范、通过的全量测试和已完成状态的实施记录。
 
-- [ ] **Step 1: 收紧工程与编码规范**
+- [x] **Step 1: 收紧工程与编码规范**
 
 在 `AGENTS.md` 的开发工作流章节增加项目级约束：本项目永久不是 Git 仓库，MUST NOT 要求、执行或声称 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程；变更审查使用文件快照、文件级差异包和项目内进度账本。
 
@@ -204,7 +204,7 @@ 
 在 `03-Python编码与注释规范.md` 将“中文 Docstring 和注释 MAY”收紧为“项目自行编写的 Python Docstring 和注释 MUST 使用中文”，并保留英文标识符和标准技术术语的例外说明。
 
-- [ ] **Step 2: 扩展规范测试的稳定断言**
+- [x] **Step 2: 扩展规范测试的稳定断言**
 
 如果 `tests/governance/test_documentation_contract.py` 已存在规范文本断言，则添加以下所需短语的断言：
 
@@ -215,7 +215,7 @@ 
 若该测试不以短语白名单方式断言，保持其现有测试结构，并仅加入能验证这两条新约束的最小测试。
 
-- [ ] **Step 3: 执行全量测试**
+- [x] **Step 3: 执行全量测试**
 
 执行：
 
@@ -225,7 +225,7 @@ 
 预期：所有测试通过，且不发起外部连接、不输出 Secret。
 
-- [ ] **Step 4: 更新实施计划状态并做静态复核**
+- [x] **Step 4: 更新实施计划状态并做静态复核**
 
 将本计划每个已完成复选框改为 `[x]`，并在文档末尾记录：实际修改文件、失败测试证据、通过测试命令与结果、未执行的外部调用。扫描计划和设计文档中是否存在未完成占位标记或无证据的完成声明；发现后在同一轮修正。
 
@@ -234,3 +234,122 @@ - 设计中的中文注释规则、逐项配置说明、DeepSeek 映射、API Key 保持为空、无外部调用和纯 Agent 侧边界均有对应任务。
 - 每一项代码/配置行为都先由 Task 1 的失败测试覆盖，Task 2 通过最小修改转绿，Task 3 完成全量回归。
 - 文件路径、环境变量名与已批准设计一致；不存在未定义接口、占位步骤或 Git 提交指令。
+
+### Task 4: 关闭最终审查发现并重新验证
+
+**Files:**
+- Modify: `D:\efficiency-platform\efficiency-platform-agent\.gitignore`
+- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\standards\03-Python编码与注释规范.md`
+- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\config\test_llm_configuration_template.py`
+- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\governance\test_documentation_contract.py`
+- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\plans\2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`
+- Create: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\sdd\config-annotation-run\task-4-local-deepseek-public-state.md`
+- Create: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\sdd\config-annotation-run\final-review-package-utf8.md`
+
+**Interfaces:**
+- Consumes: Task 1–3 的配置结构、最终审查发现和本机 `.env` 的受控读取。
+- Produces: 覆盖 `.gitignore` 的中文紧邻说明校验、本机非敏感 DeepSeek 映射/空值的安全证据，以及不产生中文乱码的最终审查工件。
+
+- [x] **Step 1: 先添加会失败的覆盖范围测试**
+
+在 `tests/config/test_llm_configuration_template.py` 新增 `.gitignore` 有效规则的紧邻中文说明校验；有效规则定义为非空且不以 `#` 开头的行。还要新增一个条件式本机 `.env` 校验：文件存在时，断言下列非敏感字段精确匹配；任何 API Key 或模型池字段都不得写入断言失败消息：
+
+```python
+expected_local_deepseek_values = {
+    "AGENT_LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
+    "AGENT_LLM_DEEPSEEK_FAST_MODEL": "deepseek-v4-flash",
+    "AGENT_LLM_DEEPSEEK_BALANCED_MODEL": "deepseek-v4-flash",
+    "AGENT_LLM_DEEPSEEK_STRONG_MODEL": "deepseek-v4-pro",
+    "AGENT_LLM_DEEPSEEK_API_KEY": "",
+    "AGENT_LLM_MODEL_POOL_BASE_URL": "",
+    "AGENT_LLM_MODEL_POOL_API_KEY": "",
+}
+```
+
+执行聚焦测试，预期 `.gitignore` 规则缺少中文说明而失败。
+
+- [x] **Step 2: 补齐 `.gitignore` 与规范示例**
+
+为 `.gitignore` 每一条有效规则添加紧邻上方的中文说明；不得改变忽略规则本身、顺序或匹配语义。将 `03-Python编码与注释规范.md` 中标记为“合规示例”的 Graph Node 和 Tool 英文 Docstring 改为中文说明，保留代码标识符、Schema 字段和标准技术术语英文形式。
+
+- [x] **Step 3: 生成本机 DeepSeek 非敏感状态证据**
+
+用受控读取 `.env` 的方式生成 `task-4-local-deepseek-public-state.md`：文件只允许出现七个变量名、固定期望值是否匹配和整体退出状态；MUST NOT 出现 `.env` 的原始行、API Key、模型池值或其他基础设施值。任何一项不匹配必须以非零状态失败。
+
+- [x] **Step 4: 修正执行记录并生成 UTF-8 差异工件**
+
+更新本计划的执行记录，明确其覆盖 Task 1–4：Task 2 修改了本机 `.env` 的注释和 DeepSeek 非敏感默认值，但未输出 Secret；Task 3 未读取或改动 `.env`。不得再以“未改动 `.env`”概括整个计划。用 UTF-8 输出生成最终审查工件；可使用标准库 `difflib` 比较 Task 1–3 快照与当前文件，但不得把 `.env` 原始值写入工件，`.env` 仅能使用既有脱敏结构与状态证据。
+
+- [x] **Step 5: 聚焦与全量验证**
+
+如 Task 4 的 `task-4-before-*` 历史快照触发既有文档链接治理测试，仅可在 `tests/governance/test_documentation_contract.py` 的历史快照精确白名单增加该快照的原始相对链接；MUST NOT 放宽现行文档的链接、元数据、占位或状态门禁。
+
+执行：
+
+```powershell
+& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v
+& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
+```
+
+预期：聚焦测试和全量测试均通过；不执行 Git 或外部服务调用。
+
+## 执行记录
+
+- 实际修改文件覆盖 Task 1–4：`.env.example`、`.env`、`.gitignore`、`config/llm-routing.toml`、`pyproject.toml`、`AGENTS.md`、`docs/standards/01-工程与目录规范.md`、`docs/standards/03-Python编码与注释规范.md`、`tests/config/test_llm_configuration_template.py`、`tests/governance/test_documentation_contract.py`、`docs/superpowers/plans/2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`，并新增 `docs/superpowers/sdd/config-annotation-run/task-4-local-deepseek-public-state.md`、`docs/superpowers/sdd/config-annotation-run/final-review-package-utf8.md` 和 `docs/superpowers/sdd/config-annotation-run/task-4-report.md`。
+- Task 2 的 `.env` 范围：受控修改本机 `.env` 的逐项中文说明和 DeepSeek 非敏感默认映射；保留既有基础设施值，不输出 Secret、API Key、连接串或模型池实际值。
+- Task 3 的 `.env` 范围：未读取、未改动 `.env`；Task 3 只固化工程约束、规范文本、治理测试和计划执行记录。
+- Task 4 的 `.env` 范围：只进行受控读取并生成公开状态证据；工件仅包含指定变量名和“匹配/不匹配”状态，不包含 `.env` 原始行或实际值。
+- Task 1 失败测试证据：`& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v` 首次执行新增测试后失败，结果来自配置说明和 DeepSeek 默认映射尚未补齐。
+- Task 2 通过测试证据：同一配置测试命令复跑后结果 `OK`。
+- Task 3 失败测试证据：`& '.\.venv\Scripts\python.exe' -m unittest tests.governance.test_documentation_contract -v` 首次执行 `Ran 15 tests in 0.466s`，结果 `FAILED (failures=4)`；失败点为 `AGENTS.md` 缺少“本项目永久不是 Git 仓库”，以及两份标准文档缺少新增中文规则断言，外加历史快照文档的相对链接校验未豁免。
+- Task 3 通过测试证据：同一治理测试命令复跑后 `Ran 15 tests in 0.329s`，结果 `OK`。
+- Task 4 RED 证据：`& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v` 在仅新增 `.gitignore` 覆盖测试后退出码 1，`Ran 9 tests in 0.024s`，结果 `FAILED (failures=1)`；失败点为忽略规则 `__pycache__/` 缺少紧邻中文说明。
+- Task 4 GREEN 证据：同一配置测试命令复跑后退出码 0，`Ran 9 tests in 0.009s`，结果 `OK`。
+- 全量测试证据：`& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v` 首次执行退出码 1，阻断点为历史快照 `docs/superpowers/sdd/config-annotation-run/task-4-before-docs__standards__03-Python编码与注释规范.md` 的 3 条原始相对链接缺少治理豁免；追加授权后仅在 `tests/governance/test_documentation_contract.py` 补充该 Task 4 历史快照的精确白名单，复跑退出码 0，`Ran 49 tests in 1.080s`，结果 `OK`。
+- 静态复核：已执行占位标记扫描命令检查计划与对应设计文档；设计文档未命中占位标记，计划中的任务复选框已全部勾选。
+
+### Task 5: 关闭最终审查工件与质量门禁遗留项
+
+**Files:**
+- Modify: `D:\efficiency-platform\efficiency-platform-agent\tests\config\test_llm_configuration_template.py`
+- Modify: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\plans\2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`
+- Create: `D:\efficiency-platform\efficiency-platform-agent\docs\superpowers\sdd\config-annotation-run\final-review-package-complete-utf8.md`
+
+**Interfaces:**
+- Consumes: Task 1–4 的执行前快照、当前非敏感配置与既有不泄密状态证据。
+- Produces: 覆盖 Task 1–4 最终状态的 UTF-8 文件级差异包，以及拒绝无意义中文占位注释的配置说明测试。
+
+- [x] **Step 1: 先添加会失败的无意义注释测试**
+
+在 `tests/config/test_llm_configuration_template.py` 增加最小测试，向现有配置注释辅助方法传入 `# 中文` 与一个配置项，断言必须失败。先运行聚焦测试，预期该测试因当前辅助方法只检查任意汉字而失败。
+
+- [x] **Step 2: 收紧配置说明辅助方法**
+
+配置说明校验必须同时要求：紧邻注释、至少八个中文字符，并且包含中文句号或分号。错误信息仅暴露配置项名称，不得显示配置值。现有 `.env.example`、TOML、`.gitignore` 和本机 `.env`（存在时）的有效说明均必须继续通过。
+
+- [x] **Step 3: 生成完整 UTF-8 最终审查包**
+
+使用标准库 `difflib` 将下列基线快照与当前文件比较并以 UTF-8 写入 `final-review-package-complete-utf8.md`：Task 1 的配置测试快照；Task 2 的 `.env.example`、路由 TOML、`pyproject.toml` 快照；Task 3 的 `AGENTS.md`、工程规范、Python 规范、治理测试和计划快照；Task 4 的 `.gitignore` 快照。`tests/config/test_llm_configuration_template.py` 必须使用 Task 1 基线，`tests/governance/test_documentation_contract.py` 使用 Task 3 基线，`03-Python编码与注释规范.md` 使用 Task 3 基线，计划使用 Task 3 基线，从而覆盖 Task 1–4 的最终状态和 Task 4 精确白名单。`.env` 只允许包含 Task 2 前后脱敏结构差异及既有公开状态证据，MUST NOT 出现原始值。
+
+- [x] **Step 4: 清理计划记录重复项并验证**
+
+删除 Task 3 文件清单中重复的 `tests/governance/test_documentation_contract.py` 项；将 Task 5 步骤如实勾选，并在执行记录中加入 RED/GREEN、完整审查包和最终全量测试证据。执行：
+
+```powershell
+& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v
+& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
+```
+
+预期：聚焦测试和全量测试均通过；不执行 Git 或外部服务调用。
+- 未执行的外部调用：未访问 DeepSeek、PostgreSQL、Redis、COS、DashScope 或其他外部服务；未运行 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程。
+
+## Task 5 执行记录
+
+- 实际修改文件：`tests/config/test_llm_configuration_template.py`、`docs/superpowers/plans/2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`。
+- 实际新增文件：`docs/superpowers/sdd/config-annotation-run/final-review-package-complete-utf8.md`、`docs/superpowers/sdd/config-annotation-run/task-5-report.md`。
+- Task 5 RED 证据：`& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v` 在只新增 `# 中文` 占位注释拒绝用例后退出码 1，`Ran 10 tests in 0.007s`，结果 `FAILED (failures=1)`；失败原因为 `AssertionError not raised`，证明旧辅助方法会接受无意义占位中文注释。
+- Task 5 GREEN 证据：收紧配置说明辅助方法后，同一聚焦命令退出码 0，`Ran 10 tests in 0.007s`，结果 `OK`；新增断言确认失败消息包含配置项键名且不包含赋值内容。
+- 完整 UTF-8 审查包：已使用 Python 标准库 `difflib` 生成 `docs/superpowers/sdd/config-annotation-run/final-review-package-complete-utf8.md`，覆盖 Task 1–4 指定基线到当前文件的差异，并仅使用 Task 2 `.env` 脱敏快照与 Task 4 公开状态证据。
+- 最终聚焦测试证据：`& '.\.venv\Scripts\python.exe' -m unittest tests.config.test_llm_configuration_template -v` 退出码 0，`Ran 10 tests in 0.025s`，结果 `OK`。
+- 最终全量测试证据：`& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v` 退出码 0，`Ran 50 tests in 1.124s`，结果 `OK`。
+- 安全检查：未读取或输出本机 `.env` 原始内容；未访问 DeepSeek、PostgreSQL、Redis、COS、DashScope 或其他外部服务；未运行 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程。
```

## Task 4 .gitignore 基线 -> 当前 .gitignore

```diff
--- docs\superpowers\sdd\config-annotation-run\task-4-before-.gitignore+++ .gitignore@@ -1,22 +1,40 @@+# Python 字节码缓存目录；由解释器运行时生成，不纳入项目文件。
 __pycache__/
+# Python 编译产物；由解释器运行时生成，不纳入项目文件。
 *.py[cod]
+# Python 特定虚拟机编译产物；由解释器运行时生成，不纳入项目文件。
 *$py.class
 
+# 本机虚拟环境目录；依赖应通过项目配置重建，不纳入版本治理。
 .venv/
+# uv 包管理缓存目录；属于本机工具缓存，不纳入版本治理。
 .uv-cache/
+# pytest 缓存目录；由测试运行生成，不纳入项目文件。
 .pytest_cache/
+# mypy 缓存目录；由类型检查生成，不纳入项目文件。
 .mypy_cache/
+# Ruff 缓存目录；由静态检查生成，不纳入项目文件。
 .ruff_cache/
+# 覆盖率数据文件；由测试覆盖率工具生成，不纳入项目文件。
 .coverage
+# HTML 覆盖率报告目录；由测试覆盖率工具生成，不纳入项目文件。
 htmlcov/
 
+# 本机环境配置；可能包含 Secret 或基础设施地址，必须留在本机。
 .env
+# 本机环境配置变体；可能包含 Secret 或基础设施地址，必须留在本机。
 .env.*
+# 共享环境变量模板；只包含空值或非敏感默认值，必须允许纳入版本治理。
 !.env.example
 
+# 构建分发目录；由打包流程生成，不纳入项目源文件。
 dist/
+# 构建输出目录；由打包流程生成，不纳入项目源文件。
 build/
+# Python 包元数据目录；由打包或安装流程生成，不纳入项目源文件。
 *.egg-info/
 
+# JetBrains IDE 本机配置目录；属于个人编辑器状态，不纳入项目文件。
 .idea/
+# VS Code 本机配置目录；属于个人编辑器状态，不纳入项目文件。
 .vscode/
```

## Task 4 本机 DeepSeek 公开状态证据

# Task 4 本机 DeepSeek 公开状态

| 变量名 | 期望状态 |
|---|---|
| AGENT_LLM_DEEPSEEK_BASE_URL | 匹配 |
| AGENT_LLM_DEEPSEEK_FAST_MODEL | 匹配 |
| AGENT_LLM_DEEPSEEK_BALANCED_MODEL | 匹配 |
| AGENT_LLM_DEEPSEEK_STRONG_MODEL | 匹配 |
| AGENT_LLM_DEEPSEEK_API_KEY | 匹配 |
| AGENT_LLM_MODEL_POOL_BASE_URL | 匹配 |
| AGENT_LLM_MODEL_POOL_API_KEY | 匹配 |

整体退出状态：匹配
