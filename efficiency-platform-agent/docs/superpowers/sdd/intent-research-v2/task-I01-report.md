# I01 实施报告：字段来源、Patch 验证与严格边界

## 状态

**离线通过。**

本任务只实现 Agent 侧确定性 Patch 校验；未调用网络、真实模型、研究工具或数据库，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/patch_validation.py`
- `src/efficiency_platform_agent/contracts/intent_v2.py`（I01 边界收紧）
- `src/efficiency_platform_agent/contracts/temporal_v2.py`（I01 严格数值边界）
- `tests/orchestration/intent_v2/test_patch_validation.py`
- `tests/contracts/test_intent_v2.py`（I01 契约回归）
- `docs/superpowers/sdd/intent-research-v2/task-I01-brief.md`
- 本报告与完成后的独立审查记录

## 已实现边界

- raw mapping 必须先通过 `IntentPatchV2` 的 `extra="forbid"` Schema；租户、预算及任意额外字段不能进入校验后 Patch。
- `set/clear` 与 `append/remove` 使用固定字段集合，不接受 JSONPath；clear 不带 value，但必须携带操作级显式原文跨度。
- topic、时间表达、来源约束、输出要求、实体及布尔/集合叶字段按 IntentFrame 对应类型校验；`target_platforms remove` 可表达“不要公众号”，而错误的 bool/int/string 伪类型会被拒绝。
- Goal 通用参数名必须由服务端可信范围显式允许；模型不能把 `tenant_id`、预算等字段藏入合法的嵌套 parameters。
- 安全相关 revision/span/时间数字及布尔值拒绝字符串、bool/int 间的隐式转换；嵌套来源、输出和实体逐项检查长度、空白及重复值。
- 未提及、clear、空字符串和 set null 保持不同语义；空值、重复集合项、超长文本/集合/操作数组均拒绝。
- explicit 只可引用可信范围中的可见用户消息；网页/工具内容即使出现在 visible mapping 也不能伪装用户来源。
- source span 按原始 Python Unicode 字符索引精确验证，覆盖 emoji、中文标点、同字重复、空 quote、错位和越界。
- inherited revision、default policy、derived normalizer 均需由服务端可信范围授权；混合来源元数据拒绝。
- 结果只暴露稳定 `INTENT_SCHEMA_INVALID`，内部 reason code 用于诊断；成功 Patch 与错误结果强制互斥。

## 红灯证据

首次只加入行为测试后执行：

```text
.venv/Scripts/python.exe -m pytest tests/orchestration/intent_v2/test_patch_validation.py tests/contracts/test_intent_v2.py -q
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2'
```

实现后首轮 Unicode 回归暴露测试夹具偏移错误：字符串第二个“AI新闻”实际从索引 10 开始而非 9；实现正确返回 `SOURCE_SPAN_MISMATCH`，修正夹具后通过。

## 绿灯与回归证据

```text
.venv/Scripts/python.exe -m pytest tests/orchestration/intent_v2/test_patch_validation.py tests/contracts/test_intent_v2.py -q
69 passed

.venv/Scripts/python.exe -m pytest tests/orchestration/intent_v2/test_patch_validation.py tests/contracts/test_intent_v2.py tests/architecture -q
112 passed, 124 subtests passed

.venv/Scripts/python.exe -m ruff check src/efficiency_platform_agent/orchestration/intent_v2 src/efficiency_platform_agent/contracts/intent_v2.py tests/orchestration/intent_v2/test_patch_validation.py tests/contracts/test_intent_v2.py
All checks passed!

.venv/Scripts/python.exe -m mypy src/efficiency_platform_agent/orchestration/intent_v2/patch_validation.py src/efficiency_platform_agent/contracts/intent_v2.py src/efficiency_platform_agent/contracts/temporal_v2.py
Success: no issues found in 3 source files

.venv/Scripts/python.exe -m pytest -q
1088 passed, 275 subtests passed, 2 existing dependency warnings
```

## 未宣称事项

- 校验通过只说明结构、来源和可信边界成立，不代表模型语义判断正确。
- Reducer、CAS、任务隔离、多轮合并、目标平台的叶级修改及真实解释器仍归 I02 及后续任务；I01 不触发任何执行工具。
- Reducer/CAS、任务隔离、多轮合并和最终状态构造仍归 I02；`base_revision`
  是否等于当前 revision 由 I02 检查，I01 只保证其为严格非负整数。
