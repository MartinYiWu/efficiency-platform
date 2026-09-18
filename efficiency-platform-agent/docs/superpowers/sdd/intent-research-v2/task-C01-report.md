# C01 任务报告：范围冻结、兼容性基线和依赖准入

| 属性 | 内容 |
|---|---|
| 状态 | 实施完成，待控制器规格与质量审查；账本仍为进行中 |
| 负责人 | Agent 端维护负责人 |
| 适用范围 | Agent 项目 C01 离线依赖、文档治理与测试 |
| 更新时间 | 2026-09-16 |
| 关联决策 | [ADR-0002](../../../adr/ADR-0002-语义意图与多源研究闭环.md)、[实施进度账本](实施进度账本.md)、[依赖与开源准入记录](依赖与开源准入记录.md) |

## 实际改动与范围

- 更新 ADR-0002、三份 2026-09-16 设计和三份实施计划为“已批准 Agent 侧分阶段实施”，写明 2026-09-16 项目负责人“根据这3份实施计划以及实施顺序进行逐个阶段的开发”的证据、批准范围与历史。原文的此前文档交付记录保留为历史，不把离线准入扩大为数据库/真实来源/模型费用/生产权限。
- 旧组件/P4 技术选型仅追加 ADR-0002 局部替代说明，保留 2026-09-02 历史批准和旧正文。引入依赖范围，HTTPX 从 dev 移至直接运行依赖，tzdata 即使由 Windows 的 tzlocal 间接提供仍明确直接声明，锁文件由 `uv lock` 生成。
- 建立 25 任务账本、开源许可/依赖准入记录和纯内存准入测试。没有修改 Java/UI、真实配置、共享数据库；没有调用真实来源/模型；未作任何 Git 操作。

## 精确版本与许可

Python 3.13.15，uv 0.12.9；直接运行依赖精确锁定为 feedparser 6.0.14（BSD-2-Clause）、Trafilatura 2.2.0（Apache-2.0）、dateparser 1.4.3（BSD-3-Clause）、HTTPX 0.28.1（BSD-3-Clause）、tzdata 2026.3（Apache-2.0）。许可结论来自已安装分发包 `importlib.metadata` 的 License/License-Expression 字段；直接/新增传递关系及固定开源提交详见 [准入记录](依赖与开源准入记录.md)。`uv lock` 只新增 babel、courlan、dateparser、feedparser、feedparser-sgmllib、htmldate、justext、lxml-html-clean、pytz、tld、trafilatura、tzlocal 12 个包，没有报告无关包升级。`uv sync --frozen` 完成安装；未手改锁文件。

## RED/GREEN 与验证

- RED：新建准入测试后，运行 `.venv/Scripts/python.exe -m pytest tests/governance/test_research_v2_dependency_admission.py -q`，退出码 1，收集时 `ModuleNotFoundError: No module named 'dateparser'`。这是依赖准入的缺包红灯，不是运行行为失败；纯文档与机械锁更新不伪称 TDD。
- GREEN：`uv lock` 退出 0，Resolved 229 packages / Added 12；`uv sync --frozen` 退出 0；相同准入测试 4 passed in 3.65s，退出 0；Ruff 单文件检查 All checks passed，退出 0。覆盖内存 RSS/Atom 字节、HTML 字符串正文、中文“昨天”显式基准时钟/时区、ZoneInfo 和 HTTPX 导入；0 外网请求。
- `uv lock --check`：Resolved 229 packages in 1ms，退出 0。
- 既有回归命令 `.venv/Scripts/python.exe -m pytest tests/orchestration tests/conversation tests/contracts tests/unit/capabilities/test_research_provider.py tests/unit/capabilities/test_research_contracts.py tests/architecture -q`：172 passed、133 subtests passed in 6.92s，退出 0。C01 前置基线同命令为 172 passed、133 subtests passed、18.05s、退出 0。
- `.venv/Scripts/python.exe -m pytest tests/governance/test_documentation_contract.py -q`：首次执行 1 failed、18 passed、117 subtests passed；仅因报告尚未生成时两份治理记录引用其路径。补齐报告后重跑：19 passed、117 subtests passed in 2.09s，退出 0。
- `.venv/Scripts/python.exe -m compileall -q src tests`：退出 0。
- `uv audit --frozen`：命令可用，但退出 1，228 包内原有 accelerate 1.14.0 的 CVE-2026-69112 两个通告（PYSEC-2026-3804、GHSA-4j2p-28q2-5m79），工具显示暂无修复版本；不声称安全扫描通过。

## 文件清单与自检

本次修改：`pyproject.toml`、`uv.lock`、`docs/adr/ADR-0002-语义意图与多源研究闭环.md`、`docs/architecture/Agent侧技术组件选型.md`、`docs/superpowers/specs/2026-09-02-P4-公共研究与数据分析-技术选型.md`、三份 `docs/superpowers/specs/2026-09-16-*-设计.md`、三份 `docs/superpowers/plans/2026-09-16-*-实施计划.md`；新增 `tests/governance/test_research_v2_dependency_admission.py`、`docs/superpowers/sdd/intent-research-v2/实施进度账本.md`、`依赖与开源准入记录.md` 和本报告。文件均在 Agent 项目内；未读取 .env 值，未作 Git 操作。账本 C01 保持进行中，控制器规格审查/质量审查后才能标记离线通过。

## 未验证项与 concerns

- 离线最小样例不覆盖不同 RSS/HTML/日期格式、许可证分发义务、真实源条款/可用性或 SSRF 防护；R01/R02/X04 后续逐项验收。Graphon/Coze/Rasa/Open Deep Research/TrendRadar/Daybreak 的许可/提交沿用设计固定证据，本轮没有重新联网审查其上游文件，不作为复制授权。
- 原有 accelerate 安全告警无现成修复版本，需现有依赖所有者评估不可信 checkpoint 的输入暴露面；C01 不擅自升级/移除无关包。
- 未执行真实模型、共享 DDL、生产灰度、Java/UI、部署或自动发布；未声称这些验收通过。

## 控制器审查修复

控制器文件级审查发现 ADR、两份旧选型、总览/研究设计和总体计划仍有“待批准”或“实施冻结”的旧时点表述，会与 2026-09-16 的分阶段开发批准和 C01 已安装离线解析依赖的事实冲突。已将这些句子改为带日期的历史记录，并明确只有 Agent 侧离线依赖和分阶段实现解冻；真实来源/API、模型新增费用、数据库/DDL、部署和生产切换仍保持独立闸门。修复未扩大运行权限，也未修改测试规则。

修复后的新鲜验证：文档治理与准入测试合并执行为 23 passed、117 subtests passed；既有意图/会话/研究/架构回归为 172 passed、133 subtests passed；`uv lock --check`、`compileall` 和准入测试 Ruff 均退出 0。最终审查结论见 [C01 规格与质量审查](task-C01-review.md)。
