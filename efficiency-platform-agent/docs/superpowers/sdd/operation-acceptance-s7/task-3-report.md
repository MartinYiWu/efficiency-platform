# S7 Task 3 实施报告：DeepSeek Provider 离线契约

## 实施范围

新增 `DeepSeekModelProvider`，精确实现 S2 `ModelProvider.complete(ProviderRequest) -> ProviderResult`。适配器由组合根注入 OpenAI 兼容客户端，不读取 `.env`、不创建 SDK 客户端、不访问网络，也不输出密钥或厂商异常原文。厂商响应统一为 S2 `ProviderMessage`、`ProviderUsage`、`ProviderError`；取消时关闭客户端并继续传播取消信号。

## RED/GREEN 证据

RED：适配器与契约测试不存在时，目标模块无法导入。

GREEN：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest tests.contract.providers.test_real_model_provider_contract -v
```

结果：退出码 0，6 项测试通过，覆盖签名复用、Responses/Chat Completions 两种 OpenAI 兼容响应、JSON Schema 选项、401/429/5xx、超时、截断/空响应、Usage 缺失、取消和关闭。

静态检查：`ruff check`、`ruff format --check` 和 `python -m compileall` 对本任务文件通过。

## 文件清单

- `src/efficiency_platform_agent/providers/llm/deepseek.py`
- `src/efficiency_platform_agent/providers/llm/__init__.py`
- `tests/contract/providers/test_real_model_provider_contract.py`

## 未验证边界

- S7 Task 2 的批准依赖已完成声明、锁定并通过本地导入检查；本适配器仍不在模块加载时构造 `openai.AsyncOpenAI`，真实 SDK 请求和版本兼容性需在独立 Gate 中验证。
- 当前仅使用拒绝网络的 SDK Transport Stub；没有执行真实 DeepSeek 请求、探测、计费调用或长期稳定性验证。
- Usage 缺失按零值归一化，表示未知而非伪造计数；价格、配额和模型池切换未在本任务实现。
- 流式 Provider 子能力未实现，基础非流式 S2 协议保持不变。
