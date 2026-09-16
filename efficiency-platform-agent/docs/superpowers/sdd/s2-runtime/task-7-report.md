# S2 任务 7：模型策略路由、有限降级和 Fake Provider 实施报告

## 交付范围

- `core/model.py`：版本化 `ModelDemand`、`ModelTier`、候选/选择/执行结果与 `ModelCandidateSelector`、取消信号端口。
- `routing/model_router.py`：显式合成候选 `fake_fast`、`fake_balanced`、`fake_strong`，按硬能力、上下文、剩余额度、禁用/不健康集合过滤并按层级向下排序。
- `providers/llm/registry.py`：显式 Provider 注册表，重复 ID 失败关闭、未知 ID 拒绝。
- `providers/llm/fake.py`：内存脚本 Fake Provider，脚本耗尽稳定返回 `FAKE_SCRIPT_EXHAUSTED`，无环境/文件/网络访问。
- `capabilities/model/runtime.py`：每步最多两次尝试，受控写入 `logical_model`，仅临时 Provider 错误允许降级，预算/取消/有界超时治理，Usage 只来自 Provider 返回值。

## RED 证据

按实施计划先运行：

```powershell
uv run pytest tests/unit/routing/test_model_router.py tests/unit/capabilities/test_model_runtime.py tests/contract/runtime/test_model_provider_contract.py -q
```

实现前收集阶段因目标模块缺失返回 `ModuleNotFoundError`，退出码 2。

## GREEN 与质量门禁

同一聚焦命令实现后结果为 `6 passed`。配置/ADR 回归：`uv run python -m unittest tests.config.test_llm_configuration_template -v`，结果 `12 passed`。本次新增生产文件 Ruff、mypy 和 `python -m compileall -q src tests` 均通过。任务6 Tool 聚焦回归 12 passed。

全量 pytest 仍受历史 docs 快照测试模块导入冲突及尚未实现的 acceptance fixture 影响，未将其归因于任务7。

## 未验证边界

本任务未调用 DeepSeek 或其他真实 Provider，未验证真实模型质量、价格/费用、网络健康、生产预算持久化、跨进程恢复或线上部署。
