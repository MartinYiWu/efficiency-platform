# S2 任务 7 复核：模型策略路由、有限降级和 Fake Provider

## 复核范围

依据 S2 实施计划第 2.4 节及任务 7 的验收项，复核 `core/model.py`、`routing/model_router.py`、`providers/llm/{registry,fake}.py`、`capabilities/model/runtime.py`，三组模型测试、配置回归和静态检查。仅做只读复核；未修改生产实现。

## 可复现验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 模型三组聚焦测试 | `uv run pytest tests/unit/routing/test_model_router.py tests/unit/capabilities/test_model_runtime.py tests/contract/runtime/test_model_provider_contract.py -q` | 通过，6 passed |
| LLM 配置回归 | `uv run python -m unittest tests.config.test_llm_configuration_template -v` | 通过，12 passed |
| Ruff | `uv run ruff check`（任务7相关 5 个源码文件及 3 个测试文件） | 通过 |
| mypy | `uv run mypy`（任务7相关 5 个源码文件） | 通过 |
| 编译 | `uv run python -m compileall -q src tests` | 通过 |

## 规范符合项

- Router 以 `strong → balanced → fast` 向下排序，硬能力、上下文、剩余 input/output token、迭代额度、禁用和不可用候选均在调用前过滤；候选是显式 `fake_fast`、`fake_balanced`、`fake_strong`，未引入真实模型 ID 或 Secret。
- Runtime 固定最多两次尝试，只有 `retryable=True` 且属于 timeout/connection/rate_limit/server_error 的 ProviderError 才进入下一候选；认证错误的聚焦测试确认不会降级。成功模型内容在后置预算检查失败时不会返回。
- `logical_model` 由 Runtime 通过复制后的 options 受控写入；Usage 从 ProviderResult 累加，并按候选 `usage_is_estimated` 标记；Fake Provider 只消费不可变内存脚本，耗尽错误稳定。
- Registry 显式注册、拒绝重复和未知 ID；Provider 文件未反向依赖 routing、capabilities 或 Harness。配置回归未发现 Fake 覆盖配置或写入真实模型配置。

## 发现与风险

### [P1] 任意 Provider 异常被当作可降级临时错误

`capabilities/model/runtime.py:111-112` 使用宽泛 `except Exception`，统一生成 `ProviderError(category="connection", retryable=True)`。因此 Provider 抛出 `ValueError`、契约实现错误或其他非临时异常时也会切换候选；这超出第 2.4 节“仅 retryable 的临时 ProviderError 可切换”的边界。建议只捕获并归一化明确允许的 Provider/传输异常，未知异常归一化为不可重试安全错误，并增加回归测试。

### [P1] 无 BudgetGuard 路径没有执行次数治理，且候选筛选使用旧预算快照

`runtime.py:79-82` 每次 selector 调用都传入同一个 `remaining_budget`；`runtime.py:182-193` 在无 Guard 时不更新或校验 iterations。若调用方传入 `iterations=1` 且首个候选返回可降级临时错误，Router 仍可为第二次尝试返回候选，违反“每次调用前后最新 RemainingBudget”和预算维度治理。建议让 Runtime 持有/更新受控预算状态，或在无 Guard 时显式递减并在重试前阻止 `iterations` 耗尽；增加 `iterations=1` 的两次尝试测试。

## 结论

**质量结论：实现级聚焦门禁通过，但任务 7 不能判定为无条件 `REAL_ACCEPTANCE_COMPLETE`。** 结构、Fake Provider、候选硬过滤、有限降级和静态质量证据充分，当前可标记 `IMPLEMENTATION_READY`（在纯 Fake/单进程测试边界内）。上述两个 P1 风险需要修复并补测后，才能认为第 2.4 节关于“仅临时错误降级”和“最新预算/尝试治理”的规范完整闭合。

真实模型调用、模型质量/价格、网络健康、生产预算持久化、跨进程恢复和线上部署均未验证；不能据此宣称生产就绪。
