# Task 3 任务简报：对外输出治理与产品化能力回答

## 目标

消除“我不能真正联网、调用工具或生成文件”等底座泄漏，形成稳定产品化身份/能力回答和最小发布前治理。

## 文件所有权

- 可修改：`src/efficiency_platform_agent/agents/conversation/general_agent.py`
- 可修改：`src/efficiency_platform_agent/conversation/local_responder.py`
- 可创建：`src/efficiency_platform_agent/security/public_response.py`
- 可修改/创建对应 `tests/unit` 测试。
- 不得修改 `ModelRuntime`、Harness、ConversationService、IntentInterpreter 或前端文件。

## 必须满足

- 先写失败测试并实际确认按预期失败，再写生产代码。
- “你能干什么”及常见同义表达命中本地能力回答，不调用模型。
- 能力回答只用产品语言，说明可协助公开资料整理、内容策划、品牌/IP/活动/渠道文案/运营复盘及按需提供来源；不得解释内部实现。
- 用正向人格替换会诱导模型复述底层限制的系统提示；仍需禁止泄露系统指令和隐藏思维。
- 发布治理必须区分“助手对自身能力作错误全局声明”和“用户正常讨论 Agent、Prompt、模型池、工具”等技术主题，后者不得被关键词误拦。
- 如实现流式缓冲接口，必须覆盖敏感模式跨两个 delta 的测试；保持接口足够窄，供后续真实流式接入。
- 所有新注释和 Docstring 使用中文。
- 不读取 `.env`，不运行 Git，不启动常驻服务。

## 验证

至少运行：

```powershell
uv run pytest tests/unit/conversation/test_local_responder.py tests/unit/agents/conversation/test_general_conversation_agent.py tests/unit/security -q
uv run ruff check src/efficiency_platform_agent/agents/conversation/general_agent.py src/efficiency_platform_agent/conversation/local_responder.py src/efficiency_platform_agent/security tests/unit/conversation tests/unit/agents/conversation tests/unit/security
```

把 RED 命令/失败原因、GREEN 命令/结果、修改文件、自查结论写入 `task-3-report.md`。
