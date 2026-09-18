# Task 3 Run 事实与预算绑定文件级差异包

状态：实现及聚焦离线验证完成，待独立规格/代码复核。
负责人：Agent 端维护负责人；更新时间：2026-09-17。
适用范围：ADR-0004 本地内存研究 Task 3；关联：[实施计划](../../superpowers/plans/2026-09-17-免费公开源本地实时V2研究闭环-实施计划.md)。

## 白名单和基线

原文件逐字快照位于同目录 `task3-before/`，未包含 `.env` 或任何连接配置。
只修改以下两个既有源码；新增三个源码与两个测试。进度账本在追加前另存快照。

| 既有文件 | 变更前 SHA-256 | 变更后 SHA-256 |
|---|---|---|
| `harness/intent_v2_delegate.py` | `280FFA3CEA474A8C2837C0B9539049EDE73B1748B2B41554FB025C08997DC0AD` | `C28D0B162116BB8C00CC0A0C157AECFFF8EF0D8D0A80DB0DABE5C44A81D66F8F` |
| `harness/research_v2_adapter.py` | `AB1DEC14C5337BC67322E4A3B026663E1440E376F69581DA7B87AF84AF47CCE3` | `DC804D57C3923FE0BC7E4ABD3B242D3AAB4E3FE9FD0EA7F4CA3B5D1646B7CC27` |

以上源码相对 `src/efficiency_platform_agent/`。新增文件与验证后 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `contracts/research_local_runtime_v2.py` | `2E74F9D6C60B063156CEC71F89684ED70E037A3BE26F76D72B2894F6A339761F` |
| `persistence/research_local_memory.py` | `A9583700E59292381000656B7E3909E3E8AEDEDC882A538A2B6715A8CDEE0975` |
| `harness/research_local_runtime.py` | `EEF246CC4DE4810F907B152FCC8ED7B05018176BE5C0DCB46E97BE41F03E5263` |
| `tests/unit/harness/test_research_local_runtime.py` | `D3C605950C141890D104425621D788F3D49AB80AFE8D5B5475F2001769BE417D` |
| `tests/integration/research_v2/test_local_memory_isolation.py` | `C821E5967E27B54900EA6D724ADB81A47CF737BB438CDCD60464F9FC6BFABA27` |

## 文件级变化

- 中立契约：完整 tenant/user/conversation/run/task/revision 身份键；候选、提取文档、归一文档、事件、claim、evidence、quality、delivery、plan、attempt、draft、output decision 均复用 V2 类型。保存版本、阶段 ID、资源计数、期限、终态和 outcome。
- 内存事实库：四个 async 接口 create/get/put/expire；锁内 CAS、幂等创建、重新验证全部嵌套值、深拷贝读写。默认 TTL 30 分钟、最多 100 Run、每 Run 20 MiB，仅允许调严。容量不足拒绝；活动引用保护过期对象；终态清除正文、候选和草稿，结果保留至 TTL。
- Run 组合层：可信注册绑定完整 key 与原 BudgetExecutionBinding；每 Run factory 只创建一次正式 LangGraphResearchServiceV2；同 Run 并发重试共享执行与结果。独立取消和硬截止信号；不合作的迟到调用不阻塞取消交付，持有引用直到自己退出，结果永不重新发布。
- 预算辅助函数只在 Run 首次创建时初始化既有 InMemoryBudgetLeaseRepository，收紧为 Harness 剩余预算与 180 秒/60 调用/20 MiB；保留 35 秒及至少 25% 输出 Token。所有阶段共用原租约；终态同时冻结 research 和 output usage_key；未知费用仍按既有保守结算。
- Brief adapter：索引扩为 tenant/task/run。旧两参数读取仅在唯一候选时返回，多个 Run 安全拒绝。显式绑定 Run 的 Provider 调用使用三参数。
- Intent delegate：增加结构化可选注册端口，先把可信用户/会话/Run 注册给本地服务再交接 Brief；不支持该端口的旧实现保持既有流程。

## TDD 与新鲜验证

1. 首轮两新增测试文件：`17 failed in 2.64s`。真实旧 Brief 双 Run 冲突，其余断言新增模块不存在。
2. 首轮实现后：17 passed；随后补充真实两个 LangGraph Run、父预算未知费用、可信身份改绑、硬截止与准备阶段接线。
3. 次轮 RED：output 阶段取消后仍可预约、delegate 未执行身份注册，共 `2 failed, 10 passed`。修复仅在组合层，不修改 core 预算账本。
4. 第三轮 RED：本地服务缺少有 TTL 的 Brief 投影；不合作调用拖延取消交付，共 `2 failed, 12 passed`。加入事实库 Brief 适配、后台活动引用和迟到异常回收。
5. 最终聚焦命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/harness/test_research_local_runtime.py tests/integration/research_v2/test_local_memory_isolation.py tests/unit/harness/test_research_v2_provider_adapter.py tests/orchestration/research_v2/test_service.py tests/unit/harness/test_intent_v2_delegate.py tests/architecture -q
```

结果：`83 passed, 124 subtests passed in 8.93s`，退出码 0，无警告。

5 个变更源码的 `mypy --follow-imports=silent`：`Success: no issues found in 5 source files`。
7 个源码/测试的 Ruff check：`All checks passed!`。
6 个新建/重排文件的 Ruff format check：`6 files already formatted`。
5 个源码 compileall：退出码 0。delegate 不扩展格式化范围。
文档治理最终为 `20 passed, 122 subtests passed in 2.19s`。首轮发现账本快照的相对链接按新目录解析失败；
原样快照仅改名为 `进度账本.md.snapshot`，不改变正文或放宽治理测试。

扩展回归（factory、closed_loop、conversation intent、budget adapter）：28 passed / 1 failed。
失败是既有 `local_real_factory.py:270` 将 test_mode 的 memory V2 送入 production 门禁，抛出
`RESEARCH_V2_PERSISTENCE_NOT_READY`；属于 Task 7 组合根接线范围，本任务未改该文件。

## 后续组合约束和保留边界

- Task 7 首次建 Run 时使用 `build_local_research_binding`，并在 Intent 和研究全过程传播同一 binding；不得在研究开始时换账本。
- 本地 `research_state_store` 传 `RunScopedResearchServiceV2` 本身，以让 Brief 读取复用有 TTL 的事实库；不要在 local_live 继续使用无限期旧 Brief 副本。
- `service_factory(execution)` 接收完整 LocalResearchExecutionV2，由后续 Task 4～6 注入正式 runner/materializer；Task 3 没有实现另一套 Graph 循环。
- max_body_requests=30、max_concurrency=4、max_host_concurrency=1、max_collection_rounds=3 为显式执行配置，实际网络计数/并发门和阶段消费由 Task 4/5 落实，不能据此宣称网络已接线。
- 取消后不合作 Provider 仍可能耗用已经发生的外部请求；原租约只允许迟到记账，事实引用保持至退出，不交付迟到结果。
- 没有执行服务重启、真实网络、模型、数据库、Git、Java/UI 操作，没有读取 `.env`。Task 3 的完成证据仅为离线范围，不表示生产或真实会话验收。
