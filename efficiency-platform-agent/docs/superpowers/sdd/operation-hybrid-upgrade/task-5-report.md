# Task 5：八类真实验收与报告任务记录

## 状态

基础设施和真实执行均已完成；最终证据以真实 HTTP/SSE 运行文件为准。R01～R08 的逐项结果在正式验收报告中区分记录，不把降级成功、研究失败或未终态混写为普通成功。

## TDD 证据

1. 先新增 `tests/acceptance/real/test_operation_live_matrix.py`，首次运行因 `scripts.real_operation_acceptance` 尚不存在而红灯：`ModuleNotFoundError`。
2. 新增真实验收编排器和配置门禁后，目标测试通过：`10 passed`。
3. `uv run ruff check scripts/operation_chat_acceptance.py scripts/real_operation_acceptance.py tests/acceptance/real/test_operation_live_matrix.py` 通过。
4. `tests/governance/test_operation_chat_acceptance.py` 与新增测试联合回归：`35 passed`。

## 已实现内容

- 固定 R01～R08 八类真实输入，其中 R03 保留用户指定的“收集下周 AI 行业热点，整理成公众号、小红书和头条三种版本”。
- 真实模式只调用本地 FastAPI 的消息和 SSE 接口，不提供 Fake、Mock 或离线回退参数。
- DeepSeek Web Search Gate 或 Key 缺失时，研究用例返回 `BLOCKED_CONFIGURATION`，不伪造 PASS。
- 研究成功必须有引用；多平台任务检查独立成品数量。
- 通过 `include_details=True` 记录 Run ID 和 SSE 事件名称序列；不记录模型正文、Prompt、工具参数或密钥。
- 默认输出脱敏 JSON 证据，路径为 `docs/superpowers/acceptance/evidence/2026-09-09-运营Agent受控混合升级-真实验收.json`。

## 最终真实执行命令

```powershell
uv run python scripts/real_operation_acceptance.py --base-url http://127.0.0.1:8080 --cases R01,R02,R03,R04,R05,R06,R07,R08 --output docs/superpowers/acceptance/evidence/2026-09-09-运营Agent受控混合升级-真实验收.json
```

最终执行后，证据文件已覆盖原 `NOT_EXECUTED` 占位内容，并在真实验收报告中逐项区分 `PASS`、`FAIL-CLOSED`、`BLOCKED_CONFIGURATION` 与 `NOT_EXECUTED`。R02/R07 在渠道 Specialist 120 秒预算和 8000 输出预算修复后分别单独复验，均达到三平台 3/3；R08 在研究节点超时映射修复后定向复验为稳定 `RESEARCH_UNAVAILABLE`。
