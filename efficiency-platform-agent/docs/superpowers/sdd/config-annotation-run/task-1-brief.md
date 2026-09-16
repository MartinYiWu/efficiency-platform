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

