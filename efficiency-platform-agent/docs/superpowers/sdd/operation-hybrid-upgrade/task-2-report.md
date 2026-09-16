# Task 2：快速通道接入与研究标志实施报告

## 状态

DONE

## 实施内容

- `ConversationService` 在意图模型前接入确定性快速路径；命中后不重复调用意图模型，也不产生意图模型用量。
- 研究标志由 `IntentEnvelopeV1.needs_research` 传入 `OperationTaskSpec.requires_research`，供 Supervisor 决定是否启动在线研究阶段。
- 明确“不需要联网”的多平台文案仍进入受控多 Agent 编排，但跳过 Research Provider。
- 增加会话上下文修改快速路径：用户说“把上一版文案改得更专业”时，仅复用可见历史中已经确认的平台和主题，不猜测新的业务事实、不暴露内部 Prompt。
- 为兼容历史测试夹具，策略适配器对缺失新字段的旧对象保持安全默认值。

## TDD 证据

### RED

快速通道接入测试在接入前失败，原因是会话服务没有调用快速检测器；研究标志测试在字段加入前因 `OperationTaskSpec` 不接受 `requires_research` 失败。

### GREEN

```text
uv run pytest tests/orchestration/test_intent_fast_path.py tests/api/test_conversation_routes.py -q
通过
```

当前快速意图测试覆盖研究、多平台、否定联网约束、缺少主题以及上下文修改请求。

## 变更范围

- `src/efficiency_platform_agent/orchestration/intent_fast_path.py`
- `src/efficiency_platform_agent/conversation/service.py`
- `src/efficiency_platform_agent/agents/operation/contracts/task.py`
- `src/efficiency_platform_agent/strategies/multi_agent/nodes.py`
- 对应单元和 API 契约测试

## 注意事项

快速路径只处理可由用户原文和可见上下文确定的字段；复杂品牌、活动、日历等请求仍交由 LLM 意图解释和澄清流程，不把关键词规则扩展成业务逻辑。
