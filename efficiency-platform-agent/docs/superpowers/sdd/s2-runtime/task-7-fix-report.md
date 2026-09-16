# S2 任务 7 复核问题修复报告

## 修复范围

针对 `task-7-review.md` 的两项 P1 复核问题，仅修改 `capabilities/model/runtime.py` 与模型 Runtime 回归测试：

- Provider 异常归一化为安全的不可重试 `PROVIDER_FAILURE/provider`；仅显式白名单的 `ProviderError(code, category, retryable)` 组合允许候选降级。未知 code、认证/授权、非法请求、Schema、取消和 `BUDGET_EXHAUSTED` 均不降级。
- ModelRuntime 在每次候选选择前刷新最新预算；有 `BudgetGuard` 时使用同一 guard 的前置检查和后置记账。无 guard 时也在本地递减每次尝试的 iteration，并更新 token/cost 剩余量，额度耗尽后不启动下一候选。

未修改实施计划，未实现任务 8+，未调用真实 Provider 或网络，未进行 Git 工作流。

## TDD RED

先新增三项回归测试并运行：

```powershell
uv run pytest tests/unit/capabilities/test_model_runtime.py -q
```

结果：`2 passed, 3 failed`。失败分别复现了未知异常被降级、未知可重试 ProviderError code 被降级，以及 `iterations=1` 时无 BudgetGuard 仍启动第二候选。

## GREEN 与质量门禁

```text
uv run pytest tests/unit/capabilities/test_model_runtime.py -q                         5 passed
uv run pytest tests/unit/routing/test_model_router.py tests/unit/capabilities/test_model_runtime.py tests/contract/runtime/test_model_provider_contract.py -q
                                                                                         9 passed
uv run python -m unittest tests.config.test_llm_configuration_template -v                12 passed
uv run ruff check src/efficiency_platform_agent/core/model.py src/efficiency_platform_agent/routing/model_router.py src/efficiency_platform_agent/providers/llm/registry.py src/efficiency_platform_agent/providers/llm/fake.py src/efficiency_platform_agent/capabilities/model/runtime.py tests/unit/routing/test_model_router.py tests/unit/capabilities/test_model_runtime.py tests/contract/runtime/test_model_provider_contract.py
                                                                                         All checks passed
uv run mypy src/efficiency_platform_agent/core/model.py src/efficiency_platform_agent/routing/model_router.py src/efficiency_platform_agent/providers/llm/registry.py src/efficiency_platform_agent/providers/llm/fake.py src/efficiency_platform_agent/capabilities/model/runtime.py
                                                                                         Success: no issues found in 5 source files
uv run python -m compileall -q src tests                                                    通过
```

## 验收边界

本修复闭合了复核指出的 Provider 降级白名单和候选 iteration 治理问题；上述证据仍仅覆盖 Fake Provider/进程内离线边界。真实模型质量、价格、网络健康、生产预算持久化、跨进程恢复、部署与真实 Provider 均未验证。
