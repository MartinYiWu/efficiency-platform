# I01 实施任务简报：字段来源、Patch 验证与严格边界

## 目标与边界

实现纯确定性的 IntentPatchValidator：只校验结构、字段操作、可见用户消息引用、Unicode 原文跨度和可信来源元数据；不猜测语义、不调用模型/工具、不写库。

## 文件白名单

- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/patch_validation.py`
- 补充 `src/efficiency_platform_agent/contracts/intent_v2.py`：为无 value 的 clear
  增加操作级原文跨度，并收紧 Patch 文本/集合上限；不修改 V1 契约。
- 补充 `src/efficiency_platform_agent/contracts/temporal_v2.py`：Patch 可输入的时间
  数值使用严格整数，拒绝字符串/布尔隐式转换。
- 新增 `tests/orchestration/intent_v2/test_patch_validation.py`
- 补充 `tests/contracts/test_intent_v2.py`
- 完成后新增 I01 report/review，并由控制器更新进度账本。

## 冻结规则

1. raw mapping 先由 `IntentPatchV2` 以 extra-forbid 解析；租户、身份、预算及任意额外字段稳定失败。
2. explicit 只能引用 trusted scope 允许的可见用户消息；网页/工具内容即使在 visible mapping 中也不能作为用户原文。
3. span 使用原始 Python Unicode 字符索引 `[start,end)`，不得先 normalize；quote 必须逐字符精确匹配。
4. inherited revision 必须属于同任务可见 revision；default/derived 的 policy/version 必须由 trusted scope 允许。
5. set/clear 与 append/remove 按字段白名单约束；未出现、clear、set null、空字符串是不同语义。
6. 返回成功 patch 或稳定 `INTENT_SCHEMA_INVALID` 与内部 reason_code；不得抛出模型原文或执行任何工具。
7. Goal 通用参数名必须来自服务端显式白名单；字段值必须与 IntentFrame 类型同构，
   `target_platforms` 等集合叶字段使用固定标识，不开放任意 JSONPath。

## 验收

执行 I01 定向测试、意图契约、架构守卫、Ruff 和 mypy；独立文件级审查通过后才能更新账本。
