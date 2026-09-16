# S7 Task 4 实施报告：DeepSeek 服务端搜索 Provider

## 实施范围

新增 `DeepSeekWebSearchProvider`，精确复用 S5 `ResearchProviderPort`、`ResearchRequest`、`ResearchResult`、`ResearchObservation`。Provider 只调用注入的 Responses client 的服务端 `web_search` Tool，仅读取响应中的来源字段，不根据任何 URL 发起 HTTP 请求，也不返回网页正文。

适配器完成来源 HTTPS 规范化、重复 URL 去重、来源字段质量校验、最大来源数限制和 `RESEARCH_UNAVAILABLE` / `RESEARCH_INSUFFICIENT` / `EVIDENCE_INVALID` 错误关闭；取消时关闭注入客户端并继续传播取消信号。

## RED/GREEN 证据

RED：Task 4 Provider 与测试文件不存在时，目标模块无法导入。

GREEN：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.capabilities.test_research_provider -v
```

结果：退出码 0，3 项测试通过，覆盖普通来源、HTTPS 规范化、重复来源、非法来源、超时和取消关闭。测试使用拒绝网络的 Responses Stub，代码未触发网络。

## 文件清单

- `src/efficiency_platform_agent/capabilities/research/deepseek_web_search.py`
- `tests/unit/capabilities/test_research_provider.py`
- `scripts/s7_verify.py` 中的 `probe_deepseek_web_search` 与 `run_deepseek_web_search_acceptance` 受控入口
- `tests/acceptance/s7/test_real_gate_probe_safety.py` 中的默认关闭守卫

## 未验证边界

- 真实 `web_search` Gate 仍默认关闭，未执行真实搜索调用；本次只补齐授权、预算和脱敏证据入口。
- 当前仅证明 Transport Stub 和 S5 契约形状；来源网页正文真实性、搜索穷尽性、费用和配额未验证。
