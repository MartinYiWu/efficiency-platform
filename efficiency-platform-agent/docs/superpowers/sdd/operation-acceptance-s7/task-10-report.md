# S7 Task 10 实施报告

## 完成内容

- 新增 `scripts/s7_verify.py`：未传 Gate、未提供授权或未开启离线模式时返回 `NOT_EXECUTED`，不创建任何外部客户端；显式 `offline` 仅运行固定 Stub 接线并标记 `external_io=false`。
- `s7_verify.py` 已严格校验授权文件版本、记录列表和 `GateAuthorization` 字段；文件缺失、格式错误或空授权均失败关闭，不进入真实执行路径。
- 固定覆盖行业动态、三平台独立内容、上传文件复盘、部分失败四类场景；分别保留来源证据、差异化成品、Document 引用以及完成/缺失范围。
- 新增 `scripts/s7_cleanup.py`：严格校验 `local_paths` 为字符串列表且每个路径非空，仅删除 manifest 声明且位于 manifest 目录内的本地文件，跳过 manifest 自身；不执行数据库、Redis、COS 全局清理。
- 补充外部清理目标校验：PostgreSQL 只接受 `s7_acceptance_[a-f0-9]{8}`，Redis 只接受 `s7:{run_stamp}:`，COS 只接受 `s7/{run_stamp}/`；拒绝 `FLUSHDB`、`FLUSHALL`、通配符和全局目标。该校验仍不主动连接外部服务。
- `s7_verify.py` 入口已自举注入项目 `src` 路径，脱离 `PYTHONPATH` 直接执行仍保持默认关闭；新增脚本入口治理回归。
- 新增 `scripts/s7_preflight.py` 的 `preflight_end_to_end`：零网络核对所选子 Gate 的配置、授权有效期、脱敏成功证据、清理清单和固定预算；任一条件不满足返回 `BLOCKED`，不创建客户端、不触发外部 I/O。

## 验证证据

```text
uv run pytest tests/acceptance/s7 -q -m "not real_external"
10 passed
uv run pytest tests/governance/test_s7_script_entrypoints.py -q
1 passed
uv run pytest tests/governance/test_s7_end_to_end_preflight.py -q
5 passed
uv run ruff check scripts/s7_verify.py scripts/s7_cleanup.py tests/acceptance/s7
All checks passed
uv run mypy scripts/s7_verify.py scripts/s7_cleanup.py
Success: no issues found in 2 source files
```

RED 证据：首次运行四组验收测试因 `scripts.s7_verify` 不存在而出现 `ModuleNotFoundError`；实现脚本及 Stub 后转为 GREEN。

## 未执行范围

G7 端到端真实场景仍未执行；新增的零网络预检在当前配置下明确返回 `BLOCKED`，原因包括独立 Runtime DSN 缺失、G7 动作授权缺失/过期和清理清单不完整。离线结果以及 G1/G3/G5 的局部真实证据均不代表端到端真实业务验收或生产可用。
