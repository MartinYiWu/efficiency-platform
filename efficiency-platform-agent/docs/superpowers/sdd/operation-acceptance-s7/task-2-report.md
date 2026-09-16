# S7 Task 2 实施报告：真实集成依赖离线准入

## 实施范围

新增 S7 依赖准入测试，核验 Python 3.13、项目版本约束、禁止依赖清单和已批准真实集成组件的声明/锁定状态。本次不安装依赖、不执行真实导入、不访问网络，不修改 `.env`、`pyproject.toml` 或 `uv.lock`。

## RED/GREEN 证据

命令：`uv run pytest tests/admission/test_s7_dependencies.py -q`

结果：2 项通过，1 项失败。失败明确指出 24 个已批准 S7 包尚未在 `pyproject.toml` 和 `uv.lock` 同时声明/锁定。该结果是依赖缺失的真实阻断，不以盲目安装替代兼容性评估。

随后按计划补齐已批准依赖并生成锁文件。GREEN 命令：

`$env:PYTHONPATH='src'; uv run pytest tests/admission/test_s7_dependencies.py -q`

结果：3 项通过；24 个包已在 `pyproject.toml` 声明并由 `uv.lock` 锁定。依赖安装仅作用于本地虚拟环境，未执行真实服务连接或模型调用。

## 已落盘文件

- `tests/admission/__init__.py`
- `tests/admission/test_s7_dependencies.py`
- 本报告

静态检查：测试 Ruff、format、compileall 通过。

## 依赖安全审计

在 G0 复核中曾发现锁定的 `pypdf 5.9.0` 存在已知安全公告；负责人授权后已将约束升级为 `pypdf>=6.16.1,<7` 并锁定 6.17.0。升级后的 `uv audit --frozen` 无已知漏洞，仍需结合完整回归确认解析兼容性。

## 未验证边界

尚未执行真实第三方服务连接、模型调用、数据库/Redis/COS 写入或生产场景验收；Docling/PaddleOCR/PaddlePaddle 仅完成依赖解析与本地环境安装，不代表全部真实文件格式和 OCR 质量已验证。
