# Task 1：联网请求快速意图预判实施报告

## 状态

DONE

## 实施范围

本任务实现明确联网研究请求和上下文修改请求的无外部 I/O 确定性预判；会话服务接线由 Task 2 负责。

实现内容如下：

- 识别有限词表中的搜索、热点、动态、新闻、来源和联网等研究标记；
- 提取下周、最近 7 天、本周等受控时间窗口；
- 提取公众号、小红书、今日头条等平台，并转换为稳定的平台标识；
- 对“收集下周 AI 行业热点，整理成公众号、小红书和头条三种版本”生成多平台内容意图；
- 对缺少明确主题的研究请求返回 `missing_fields=("topic",)`，不虚构主题；
- 普通对话和品牌发布计划等复杂非明确联网请求返回 `None`，交由后续模型意图解析；
- “把上一版文案改得更专业”等请求仅在可见历史已明确平台和主题时复用历史约束，避免无依据追问；
- 仅使用用户消息和可见会话上下文，不调用网络、模型或外部工具。

## TDD 证据

### RED

命令：

```powershell
uv run pytest tests/orchestration/test_intent_fast_path.py -q
```

结果：未创建生产模块时测试收集失败，错误为：

```text
ModuleNotFoundError: No module named
'efficiency_platform_agent.orchestration.intent_fast_path'
```

该失败确认测试确实覆盖了尚不存在的功能。

### GREEN

命令：

```powershell
uv run pytest tests/orchestration/test_intent_fast_path.py -q
```

结果：

```text
5 passed in 0.30s
```

静态检查命令：

```powershell
uv run ruff check src/efficiency_platform_agent/orchestration/intent_fast_path.py tests/orchestration/test_intent_fast_path.py
```

结果：

```text
All checks passed!
```

## 文件清单

- 新增 `src/efficiency_platform_agent/orchestration/intent_fast_path.py`
- 新增 `tests/orchestration/test_intent_fast_path.py`
- 新增本报告 `docs/superpowers/sdd/operation-hybrid-upgrade/task-1-report.md`

## 未执行项

- 尚未接入 `ConversationService`，该内容属于 Task 2；
- 尚未进行真实 DeepSeek 或联网调用；
- 尚未执行完整运营 Agent 端到端验收。

## 疑问

无。当前 Task 1 已按计划完成，等待 Task 2 接入快速通道。
