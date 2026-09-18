# I04 实施报告：受控语义解释与 Prompt 注册

## 状态

**离线通过。**

本任务只实现 Agent 侧受控 Intent V2 解释器、Prompt 与 Fake 验收；未调用真实模型、网络、研究工具或数据库，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。真实会话 Context 与预算租约仓储接线仍归 I07。

## 交付文件

- `src/efficiency_platform_agent/orchestration/intent_v2/interpreter.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- `src/efficiency_platform_agent/contracts/intent_v2.py`（当前消息 ID 与可见范围绑定）
- `src/efficiency_platform_agent/prompts/registry.py`
- `src/efficiency_platform_agent/prompts/resources/intent/interpret_v2.j2`
- `src/efficiency_platform_agent/prompts/resources/intent/repair_v2.j2`
- `src/efficiency_platform_agent/prompts/resources/intent/review_v2.j2`
- `tests/orchestration/intent_v2/test_interpreter.py`
- `tests/unit/prompts/test_intent_v2_templates.py`
- `docs/superpowers/sdd/intent-research-v2/task-I04-brief.md`
- 本报告与规格/质量审查记录

## 已实现边界

- 保持 C02 冻结 `interpret(text, context, previous, catalog, lease)` 端口；通过只读 resolver 将 context/lease 引用解析为可信构建作用域和 `RemainingBudget`。
- 解释器强制复用唯一 `ContextBuilder`、现有 `PromptRuntime` 和 `IntentModelRuntime.complete(...)`；不创建模型旁路或业务工具快路径。
- `IntentContextV2.current_message_id` 必须属于唯一可见消息集合，当前正文与可信消息 ID 可进入 Prompt 数据区并供 I01 span 校验衔接。
- 首次合法只调用一次；Schema 或 base revision 错误最多修复一次；再次无效稳定返回 `INTENT_SCHEMA_INVALID`。
- 语义复核只由注入的确定性策略触发，不读取模型自报 confidence；修复加复核总调用上限为 3。
- 无效复核保留最后合法 Patch；复核不能增加 `unresolved_references`，不能以更差状态覆盖候选。
- 每次调用前检查取消、重新读取 lease 剩余额度，并与本地实际 attempts/usage 后的余额取严格下界；低但正数的输出预算会收紧请求上限。
- Provider 失败/超时、取消、预算、Context、Prompt 和复核策略故障均以技术错误结束，不伪装成用户澄清。
- 执行事实记录可信 usage、模型尝试、降级、模型调用数、Prompt ID/版本、catalog/context/lease 版本；错误路径也保留可用审计事实。
- 三份 Prompt 通过显式注册函数加入现有注册表；可信目录/Schema/manifest 在 system 区，当前/历史语义数据与候选输出在不可信 user 区。
- 修复只接收稳定错误和安全裁剪至 20,000 字符的待修输出；不向模型传 tenant/user、权限、预算、成功终态或网页正文。
- 身份聊天、按钮说明和否定研究均走语义解释，但该组件的 ModelDemand 固定 `requires_tools=False`，不调用研究工具。

## 红灯证据

首次只加入行为和 Prompt 测试后执行：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2.interpreter'
ImportError: cannot import name 'register_intent_v2_prompts'
```

首轮实现后静态检查暴露 7 项 Ruff 问题和 3 项 mypy 类型问题，均修复后转绿。反例审查随后补齐 revision 可信修复、无效/恶化复核、20,000 字符裁剪、Prompt 未注册失败关闭、错误审计版本与正数小预算。

第二轮契约审查发现 `IntentContextV2` 无法指出当前正文对应哪个可见消息 ID；已新增 `current_message_id` 且强制属于去重后的可见集合，并增加回归。

## 绿灯与回归证据

```text
I04 解释器 + Prompt 定向：21 passed

旧 V1 解释器 + PromptRuntime + ContextBuilder：61 passed

意图 V2 + contracts + architecture：
234 passed, 124 subtests passed

Ruff：All checks passed

mypy：Success: no issues found in 4 source files

全量回归：
1176 passed, 275 subtests passed, 2 existing dependency warnings in 36.36s
```

两条全量警告来自既有 Starlette `BlockingPortal` 弃用提示和 Polars `read_excel` 未来返回类型变化，不由 I04 引入。

## 未宣称事项

- Fake 合法 Patch 只证明调用边界、预算、Prompt、修复和审计行为；不代表真实模型意图准确率已经验收。真实模型标注集评测属于 X04。
- I04 不决定 READY；Patch 仍必须经过 I01 Validator、I02 Reducer、I03 TemporalResolver 和 I05 Binder/DecisionPolicy。
- Context scope resolver 与 Budget resolver 的真实会话仓储/租约仓储实现、历史正文装配、组合根接线和并发生命周期属于 I07；I04 未用伪身份或本地默认预算冒充真实接线。
- Prompt 引用的能力目录只提供候选语义；未知能力、权限和参数合法性仍由 I05 确定性拒绝。
