# C01 任务简报：范围冻结、兼容性基线和依赖准入记录

## 当前授权

项目负责人在 2026-09-16 明确要求：“根据这3份实施计划以及实施顺序进行逐个阶段的开发。”这构成对三份实施计划及 ADR-0002 所述 Agent 侧实现范围的开发授权，可据此将相关设计、ADR、计划的状态与批准证据更新为“已批准”。授权不包含共享数据库 DDL 执行、生产配置切换、真实来源启用、真实模型新增费用、部署、Java/UI 修改、自动发布或付费服务。

## 任务目标

完成 M0 的 C01：冻结本次允许范围和既有测试基线；完成 feedparser、Trafilatura、dateparser、HTTPX/tzdata 的 Python 3.13 依赖准入；把已批准的局部替代关系写回权威文档；建立实施进度账本和依赖/开源准入记录。

## 约束

- 工作目录：`D:/软件目录/efficiency-platform/efficiency-platform-agent`。
- 只能修改 Agent 项目；保护父目录其他已有变更。
- 项目规范禁止 Git 操作：不得 commit、add、diff、stash、checkout、branch、push。使用任务报告、文件清单和测试证据交接。
- Python >=3.13,<3.14；不改变 LangGraph 唯一 Runtime、中央 Supervisor、ContextBuilder、Tool Runtime 或 Provider 边界。
- 仅为后续离线实现引入开源解析依赖；本任务不启用外网采集、不调用真实模型、不执行 DDL、不读取 `.env` 值。
- 项目自行编写的注释、Docstring、配置说明使用中文。
- 所有内容写入通过 `apply_patch`；`uv lock` 等依赖管理器可机械更新锁文件。
- 遵循 TDD：若新增治理行为/测试，先创建失败测试并记录 RED，再实现并记录 GREEN；纯文档/依赖锁变更记录现有基线与准入命令，不伪造 TDD。

## 必须完成的工作

1. 记录基线：当前已执行并通过以下命令，作为 C01 前置事实：

```powershell
.venv/Scripts/python.exe -m pytest tests/orchestration tests/conversation tests/contracts tests/unit/capabilities/test_research_provider.py tests/unit/capabilities/test_research_contracts.py tests/architecture -q
```

结果：172 passed、133 subtests passed，退出码 0，耗时 18.05 秒。实施者须在最终改动后至少重跑相同命令，并记录新结果。

2. 更新治理状态：
   - `docs/adr/ADR-0002-语义意图与多源研究闭环.md`
   - 三份 2026-09-16 设计文档
   - 三份 2026-09-16 实施计划
   将状态、批准人、批准日期、批准范围、证据和版本历史改为与当前用户明确开发指令一致。不得扩大为数据库/真实来源/模型费用/生产切换授权。
   - 给 `docs/architecture/Agent侧技术组件选型.md` 和 `docs/superpowers/specs/2026-09-02-P4-公共研究与数据分析-技术选型.md` 增加 ADR-0002 已批准局部替代说明；保留原批准正文和历史事实，不静默删除。

3. 建立实施账本：
   - `docs/superpowers/sdd/intent-research-v2/实施进度账本.md`
   - 含 25 个任务 C01—C03、I01—I07、R01—R10、X01—X05 的状态表。
   - C01 开始时可标进行中，只有规格审查与质量审查通过后由控制器改为离线通过；其他任务未开始。
   - 记录禁止 Git 的项目例外、文件白名单、基线测试、后续真实验收边界。

4. 建立依赖与开源准入记录：
   - `docs/superpowers/sdd/intent-research-v2/依赖与开源准入记录.md`
   - 对 feedparser、Trafilatura、dateparser、HTTPX、tzdata 记录精确锁定版本、许可证、Python 3.13 导入/最小解析结果、直接/传递依赖、用途和限制。
   - 对 Graphon/Coze/Rasa/Open Deep Research 保留设计文档已有固定提交映射。
   - TrendRadar GPL-3.0 与 Daybreak 缺独立 LICENSE 的部分仅允许机制参考，不复制代码。
   - 许可证结论必须来自已安装包元数据/上游许可文件或锁定来源，不凭印象。

5. 依赖改动：
   - `httpx` 从仅 dev 直接依赖调整为运行直接依赖，dev 不重复声明。
   - 引入经 Python 3.13 实测通过的 feedparser、Trafilatura、dateparser 兼容版本范围。
   - Windows IANA 时区依赖若已由传递依赖提供，仍需决定是否作为直接运行依赖；若 TemporalResolver 必须稳定依赖它，应明确直接声明。
   - 使用项目 uv 生成 `uv.lock`，不得手工编辑锁文件。
   - 不升级与本任务无关的大量依赖；若解析器导致大范围升级，停止并报告 concern。

6. 准入验证：至少创建或扩展一个依赖准入测试，例如 `tests/governance/test_research_v2_dependency_admission.py`，直接导入三个解析库并执行：
   - RSS/Atom 内存字节最小解析；
   - HTML 字符串正文提取，不允许联网；
   - 中文相对日期在显式 RELATIVE_BASE/时区设置下解析；
   - ZoneInfo("Asia/Shanghai") 可用；
   - HTTPX 可从运行环境导入。
   测试不得发起网络请求，也不得读取真实配置。

7. 验证命令及预期：

```powershell
uv lock --check
.venv/Scripts/python.exe -m pytest tests/governance/test_research_v2_dependency_admission.py -q
.venv/Scripts/python.exe -m pytest tests/orchestration tests/conversation tests/contracts tests/unit/capabilities/test_research_provider.py tests/unit/capabilities/test_research_contracts.py tests/architecture -q
.venv/Scripts/python.exe -m pytest tests/governance/test_documentation_contract.py -q
.venv/Scripts/python.exe -m compileall -q src tests
.venv/Scripts/python.exe -m ruff check tests/governance/test_research_v2_dependency_admission.py
```

全部退出码应为 0。若 `uv audit --frozen` 在当前 uv 中不可用，必须记录为工具不可用，不得声称已执行；可使用当前项目实际支持的只读依赖审查命令，但不得安装另一个审计平台。

## 交付报告

将完整报告写入：
`docs/superpowers/sdd/intent-research-v2/task-C01-report.md`

报告必须包含：实际改动、精确版本和许可证、测试命令/输出、RED/GREEN 证据、文件清单、自检、未验证项和 concerns。最终消息只返回状态、测试摘要、concerns 和报告路径；不得声称创建 Git commit。
