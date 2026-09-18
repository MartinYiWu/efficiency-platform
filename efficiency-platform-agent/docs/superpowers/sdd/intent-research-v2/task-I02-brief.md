# I02 实施任务简报：多轮 Reducer、任务隔离与 revision

## 目标与边界

实现纯确定性的 `IntentStateReducer`：只接收 I01 已验证 Patch 和受信任消息，执行 revision/任务检查、字段白名单合并、集合增删、来源优先级、幂等与稳定 scope hash；不查询系统时间、不调用模型/工具、不读写数据库。

## 文件白名单

- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/reducer.py`
- 更新 `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- 补充 `src/efficiency_platform_agent/contracts/intent_v2.py`：Frame 业务字段保留 `FieldValue[T]` 来源、TrustedMessage 提供 task/timezone、Frame 提供确定性 scope hash。
- 必要时同步 `src/efficiency_platform_agent/contracts/research_ports_v2.py` 的中立接口说明；不接真实仓储。
- 新增 `tests/orchestration/intent_v2/test_reducer.py`，补充契约回归。
- 完成后新增 I02 report/review，并更新实施进度账本。

## 冻结规则

1. `new_task` 使用新 task_id、base revision 0，不继承旧主题/时间/来源/输出；其他 dialog act 必须同 task 且 base revision 精确等于当前 revision。
2. 相同 task/message_id 重放返回既有不可变快照；两个 base revision 相同的并发修改只允许先应用者成功，后者显式 `INTENT_REVISION_CONFLICT`。
3. 当前 explicit set/clear 优先；非 explicit 不得覆盖现有更高来源优先级，derived/default 不得覆盖 explicit。
4. 未出现字段保持；clear 删除；append/remove 只修改目标集合、稳定去重，不把叶级修改退化为整对象覆盖。
5. TrustedMessage.received_at 是唯一可用时钟；显式时间修改更新 anchor，纯继承保留旧 anchor。
6. scope hash 由目标、业务范围、时间 anchor 和 timezone 的规范 JSON 生成，不含 task/revision/message/provenance；相对时间在新 anchor 下会失效旧缓存，非时间 refine 继续复用原 anchor。
7. Reducer 不猜关键词、不生成租户/预算/权限、不持久化；CAS 真实实现归 X01，I02 只固定纯函数冲突语义。
8. Patch 的 unresolved references 必须保留到 Frame，供 I05 DecisionPolicy 澄清；不得因 Reducer 没有足够信息构造结构化 ambiguity 而静默丢弃。

## 验收

先写 refine/new_task/replace/remove/revision/幂等/并发/优先级/不可变快照红灯；实现后执行 I02 定向、I01/C02 回归、架构守卫、Ruff、mypy和全量测试，并经独立文件级审查。
