# I04 实施任务简报：受控语义解释与 Prompt 注册

## 目标与边界

实现 `ControlledIntentInterpreterV2`：模型只提出 `IntentPatchV2`，格式错误最多修复一次，确定性策略要求时最多复核一次，总模型调用不超过 3 次。所有调用复用现有 ModelRuntime、PromptRuntime、ContextBuilder 和 RemainingBudget；不调用研究工具、不写库、不决定 READY。

## 冻结端口与适配

C02 的 `interpret(text, context, previous, catalog, lease)` 签名保持不变。由于 `IntentContextV2` 和 `BudgetLeaseReferenceV2` 仅是版本化引用，解释器注入两个只读适配器：

- Context scope resolver 将受信任 `context_version` 解析为 `RunRequest / RunContext / ExecutionBudget`，解释器再强制调用唯一 `ContextBuilder`；不由模型生成身份。
- Budget resolver 将受信任 lease 引用解析为 `RemainingBudget`；每次模型调用前重新读取并与本地已消费额度取严格下界。

真实会话历史、租约仓储和组合根接线归 I07；I04 只用 Fake 验证边界，不创建第二套上下文、模型或预算运行时。

## 文件白名单

- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/interpreter.py`
- 更新 `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- 更新 `src/efficiency_platform_agent/prompts/registry.py`，增加显式注册函数
- 新增 `src/efficiency_platform_agent/prompts/resources/intent/interpret_v2.j2`
- 新增 `src/efficiency_platform_agent/prompts/resources/intent/repair_v2.j2`
- 新增 `src/efficiency_platform_agent/prompts/resources/intent/review_v2.j2`
- 新增 `tests/orchestration/intent_v2/test_interpreter.py`
- 新增 `tests/unit/prompts/test_intent_v2_templates.py`
- 完成后新增 I04 report/review，并更新实施进度账本

## 冻结规则

1. 首次合法只调用一次；Schema/基准 revision 错误最多修复一次；再次无效返回 `INTENT_SCHEMA_INVALID`，不循环。
2. 语义复核只由注入的确定性策略触发，不使用模型自报 confidence；与修复合计最多 3 次。
3. Provider 超时/失败返回 `INTENT_PROVIDER_UNAVAILABLE`，取消返回 `INTENT_CANCELLED`，预算不足返回 `INTENT_BUDGET_EXHAUSTED`；技术失败不得伪装为澄清。
4. 每次模型调用前检查取消、重新读取租约额度和剩余绝对截止；费用、输入/输出 token、模型尝试、Prompt 版本、目录版本、Context 版本与 lease 版本进入执行事实。
5. Prompt 只注册显式 ID；系统消息分区提供可信能力目录、字段 Schema 与 Context manifest，用户/历史数据以不可信 user 数据消息发送。
6. 修复 Prompt 只接收稳定校验错误和最多 20,000 字符的安全裁剪输出；不回显 Provider 异常或隐藏思维。
7. 模型不能生成 tenant、user、权限、预算、成功终态；未知能力由 I05 Binder 拒绝，Patch 来源跨度由 I01 校验，解释器不得越权代替。
8. 身份聊天、按钮说明、否定研究等仍经过语义解释，但 I04 永远不调用研究/业务工具。

## 验收

先写合法、一次修复、修复仍失败、Provider 失败、预算不足、取消、一次复核、三次上限、ContextBuilder 强制使用、Prompt 分区与约束红灯；实现后执行 I04 定向、旧 V1 解释器回归、意图/契约/架构组合、Ruff、mypy 和全量测试，再完成文件级反例审查。
