# I07 实施任务简报：会话协调、CAS 生命周期与离线评测

## 目标与边界

把 I01— I06 组装为单一 IntentPipelineV2，使用 Fake/InMemory 仓储验证多轮、幂等、CAS、Run 生命周期和离线评测资产；为现有 ConversationService 增加可选 V2 协调器注入点。I07 不接真实 PostgreSQL、不执行真实模型/来源/Tool、不替换 V1 线上路径。

## 文件白名单

- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/pipeline.py`
- 新增 `src/efficiency_platform_agent/evaluation/intent_v2.py`
- 更新 `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- 更新 `src/efficiency_platform_agent/conversation/service.py`（仅可选协调器注入点与 V1 pending 保护）
- 新增 `tests/conversation/test_intent_v2_flow.py`
- 新增 `tests/evaluation/test_intent_v2_dataset.py`
- 新增 `tests/fixtures/intent_v2/development.jsonl`、`regression.jsonl`、`frozen.jsonl`、`manifest.json`
- 完成后新增 I07 report/review，并更新实施进度账本

## 冻结规则

1. 固定顺序：读取任务/幂等记录→解释→Patch 校验→Reducer→时间验证→Binder/Decision→Brief/场景投影→CAS commit→返回可提交结果。
2. 任何未 commit Frame、FAILED/UNSUPPORTED/CLARIFY、chat/cancel 或等待安全边界的 refine 均不得标记 dispatch_allowed。
3. 同 message_id+相同正文重放已有结果，不重复调用模型；同 ID 不同正文冲突。不同并发消息基于同 revision 时只允许一个 CAS 成功，另一方稳定失败，不自动覆盖或合并。
4. WAITING_INPUT 补齐条件复用同 Run；终态后的新任务使用新 Run；运行中 refine 只产生“在既有安全边界停止旧 revision”意图，不直接写终态或旁路取消入口。
5. 任务一旦选择 V1/V2 不降格；ConversationService 仅在没有 V1 pending 时调用可选 V2 coordinator，业务 fast_path 继续只属于 V1。
6. 澄清最多两轮；超过上限技术失败，不继续循环。
7. 240 例离线数据按单轮60、多轮60、日期40、复合30、攻击30、故障20分布，开发/回归/冻结为120/60/60；语义族不得跨集合，manifest 固定文件 hash、来源、标注人、时区和计数。
8. 离线评测输出字段正确数/总数、决策正确数/总数、能力正确数/总数及逐字段错误；Fake/静态预测不得称为真实模型精度。

## 验收

先写 WAITING_INPUT 同 Run、终态新 Run、运行中 refine、安全取消意图、幂等重放、并发 CAS、V1 固定和数据集完整性红灯；实现后执行 I07 定向、全部意图/会话/架构回归、Ruff、mypy 和全量测试，再完成文件级反例审查。
