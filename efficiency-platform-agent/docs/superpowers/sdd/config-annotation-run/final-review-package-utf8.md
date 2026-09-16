# Task 4 UTF-8 最终审查包

范围：仅比较 Task 4 前快照与当前允许修改文件。
安全说明：本工件不读取、不写入、不比较 .env 原始内容；.env 仅由公开状态工件表达匹配状态。

## .gitignore

```diff
--- before/.gitignore
+++ after/.gitignore
@@ -1,22 +1,40 @@
+# Python 字节码缓存目录；由解释器运行时生成，不纳入项目文件。
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

## docs/standards/03-Python编码与注释规范.md

```diff
--- before/docs/standards/03-Python编码与注释规范.md
+++ after/docs/standards/03-Python编码与注释规范.md
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

## tests/config/test_llm_configuration_template.py

```diff
--- before/tests/config/test_llm_configuration_template.py
+++ after/tests/config/test_llm_configuration_template.py
@@ -32,6 +32,20 @@
             for key, value in [line.split("=", maxsplit=1)]
         }
 
+    @staticmethod
+    def assert_rules_have_chinese_comments(lines: list[str]) -> None:
+        for index, line in enumerate(lines):
+            stripped = line.strip()
+            if not stripped or stripped.startswith("#"):
+                continue
+
+            previous = lines[index - 1].strip() if index else ""
+            has_chinese_comment = previous.startswith("#") and any(
+                "\u4e00" <= character <= "\u9fff" for character in previous
+            )
+            if not has_chinese_comment:
+                raise AssertionError(f"忽略规则缺少紧邻的中文说明：{stripped}")
+
     def test_shared_configuration_assignments_have_chinese_comments(self) -> None:
         self.assert_assignments_have_chinese_comments(
             (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
@@ -46,6 +60,26 @@
             self.assert_assignments_have_chinese_comments(
                 local_env.read_text(encoding="utf-8").splitlines()
             )
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
 
     def test_deepseek_default_mapping_uses_current_official_model_ids(self) -> None:
         values = self.read_env_values(PROJECT_ROOT / ".env.example")
@@ -120,3 +154,8 @@
         self.assertIn(".env", content)
         self.assertIn(".env.*", content)
         self.assertIn("!.env.example", content)
+
+    def test_gitignore_rules_have_adjacent_chinese_comments(self) -> None:
+        self.assert_rules_have_chinese_comments(
+            (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
+        )
```

## docs/superpowers/plans/2026-09-02-中文注释与DeepSeek默认配置-实施计划.md

```diff
--- before/docs/superpowers/plans/2026-09-02-中文注释与DeepSeek默认配置-实施计划.md
+++ after/docs/superpowers/plans/2026-09-02-中文注释与DeepSeek默认配置-实施计划.md
@@ -249,7 +249,7 @@
 - Consumes: Task 1–3 的配置结构、最终审查发现和本机 `.env` 的受控读取。
 - Produces: 覆盖 `.gitignore` 的中文紧邻说明校验、本机非敏感 DeepSeek 映射/空值的安全证据，以及不产生中文乱码的最终审查工件。
 
-- [ ] **Step 1: 先添加会失败的覆盖范围测试**
+- [x] **Step 1: 先添加会失败的覆盖范围测试**
 
 在 `tests/config/test_llm_configuration_template.py` 新增 `.gitignore` 有效规则的紧邻中文说明校验；有效规则定义为非空且不以 `#` 开头的行。还要新增一个条件式本机 `.env` 校验：文件存在时，断言下列非敏感字段精确匹配；任何 API Key 或模型池字段都不得写入断言失败消息：
 
@@ -267,15 +267,15 @@
 
 执行聚焦测试，预期 `.gitignore` 规则缺少中文说明而失败。
 
-- [ ] **Step 2: 补齐 `.gitignore` 与规范示例**
+- [x] **Step 2: 补齐 `.gitignore` 与规范示例**
 
 为 `.gitignore` 每一条有效规则添加紧邻上方的中文说明；不得改变忽略规则本身、顺序或匹配语义。将 `03-Python编码与注释规范.md` 中标记为“合规示例”的 Graph Node 和 Tool 英文 Docstring 改为中文说明，保留代码标识符、Schema 字段和标准技术术语英文形式。
 
-- [ ] **Step 3: 生成本机 DeepSeek 非敏感状态证据**
+- [x] **Step 3: 生成本机 DeepSeek 非敏感状态证据**
 
 用受控读取 `.env` 的方式生成 `task-4-local-deepseek-public-state.md`：文件只允许出现七个变量名、固定期望值是否匹配和整体退出状态；MUST NOT 出现 `.env` 的原始行、API Key、模型池值或其他基础设施值。任何一项不匹配必须以非零状态失败。
 
-- [ ] **Step 4: 修正执行记录并生成 UTF-8 差异工件**
+- [x] **Step 4: 修正执行记录并生成 UTF-8 差异工件**
 
 更新本计划的执行记录，明确其覆盖 Task 1–4：Task 2 修改了本机 `.env` 的注释和 DeepSeek 非敏感默认值，但未输出 Secret；Task 3 未读取或改动 `.env`。不得再以“未改动 `.env`”概括整个计划。用 UTF-8 输出生成最终审查工件；可使用标准库 `difflib` 比较 Task 1–3 快照与当前文件，但不得把 `.env` 原始值写入工件，`.env` 仅能使用既有脱敏结构与状态证据。
 
@@ -292,9 +292,16 @@
 
 ## 执行记录
 
-- 实际修改文件：`AGENTS.md`、`docs/standards/01-工程与目录规范.md`、`docs/standards/03-Python编码与注释规范.md`、`tests/governance/test_documentation_contract.py`、`docs/superpowers/plans/2026-09-02-中文注释与DeepSeek默认配置-实施计划.md`。
-- 失败测试证据：`& '.\.venv\Scripts\python.exe' -m unittest tests.governance.test_documentation_contract -v` 首次执行 `Ran 15 tests in 0.466s`，结果 `FAILED (failures=4)`；失败点为 `AGENTS.md` 缺少“本项目永久不是 Git 仓库”，以及两份标准文档缺少新增中文规则断言，外加历史快照文档的相对链接校验未豁免。
-- 通过测试证据：同一治理测试命令复跑后 `Ran 15 tests in 0.329s`，结果 `OK`。
-- 全量测试证据：`& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v` 最终执行 `Ran 47 tests in 2.703s`，结果 `OK`。
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
+- 全量测试证据：`& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v` 当前退出码 1，阻断点为范围外历史快照 `docs/superpowers/sdd/config-annotation-run/task-4-before-docs__standards__03-Python编码与注释规范.md` 的相对链接缺少治理豁免；可修复位置不在 Task 4 允许修改清单内，详见 Task 4 报告。
 - 静态复核：已执行占位标记扫描命令检查计划与对应设计文档；设计文档未命中占位标记，计划中的任务复选框已全部勾选。
-- 未执行的外部调用：未访问 DeepSeek、PostgreSQL、Redis、COS、DashScope 或其他外部服务；未读取、输出或改动 `.env`。
+- 未执行的外部调用：未访问 DeepSeek、PostgreSQL、Redis、COS、DashScope 或其他外部服务；未运行 Git 初始化、提交、分支、推送、Git diff 或基于 Git 的审查流程。
```

## 本机 DeepSeek 公开状态

```text
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
```
