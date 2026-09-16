### Task 2: 落地根目录强制规则与 Agent 总纲

**Files:**

- Create: `AGENTS.md`
- Create: `Agent.md`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`

**Interfaces:**

- Consumes: 已批准设计、`docs/architecture/纯Agent侧总体架构.md`、`docs/architecture/Agent侧技术组件选型.md`
- Produces: 后续所有详细规范必须服从的根规则、架构总纲、贡献流程和安全基线

#### Step 1: 编写 AGENTS.md

必须按以下顺序写入章节：

```markdown
# AGENTS.md
## 适用范围与优先级
## 必读文档
## 纯 Agent 侧边界
## 架构强制约束
## 开发工作流
## 测试与完成证据
## 数据库与 SQL
## 安全红线
## 文档与变更治理
## 详细规范入口
```

必须明确：不负责 Java 侧；不得新增第二 Graph Runtime；多 Agent 采用 Supervisor；厂商 SDK 必须经 Provider；Tool 必须经 Tool Runtime；共享 DDL 需预检和明确授权；不得提交密钥；完成声明需新鲜验证；使用 MUST/MUST NOT/SHOULD/MAY；详细入口必须是 Markdown 链接目标 `](docs/standards/00-规范索引.md)`。保持短而强，不复制详细规范全文。

#### Step 2: 编写 Agent.md

必须按以下顺序写入章节：

```markdown
# Agent 侧开发总纲
## 1. 使命与边界
## 2. 总体架构范式
## 3. 执行策略
## 4. 多 Agent 协作拓扑
## 5. 统一运行状态
## 6. 核心层职责
## 7. 扩展准入规则
## 8. 上下文、工具与记忆
## 9. Provider 与技术能力
## 10. 禁止事项
## 11. 必读规范
```

必须保留 `Harnessed Hybrid Multi-Agent Architecture`、Direct、Workflow、ReAct、Plan-and-Execute、Multi-Agent、Supervisor、Specialist Subgraph；解释 Strategy Router 与 Supervisor 区别；规定 Specialist Subgraph 不与用户或其他专家自由对话；链接总体架构、技术选型和扩展约定。

#### Step 3: 编写 CONTRIBUTING.md

必须覆盖：开始前检查、需求分类、设计/ADR 触发条件、实施计划、TDD、文件范围、验证矩阵、评审清单、交付状态、Git 与无 Git 两种场景。流程固定为：确认范围 → 阅读规范/实现 → 设计或 ADR → 实施计划 → 测试先行 → 最小实现 → 验证 → 文档同步 → 评审交付。

不得声称 Ruff、mypy、pytest 已安装；必须区分：

- 当前可执行：`python -m unittest discover -s tests -v`、源码编译、AST 架构守卫；
- 组件引入后目标：pytest、Ruff、mypy、依赖与安全扫描。

#### Step 4: 编写 SECURITY.md

必须覆盖：安全问题报告方式（联系项目负责人，不虚构邮箱）、Secret、租户上下文、Prompt Injection、Tool 权限、SSRF、文件、SQL、日志、模型输出、依赖和安全验收。明确内容审核暂不建设，但基础安全控制仍强制适用。

#### Step 5: 执行根文档聚焦测试

```powershell
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_agents_rules_link_to_detailed_standards tests.governance.test_documentation_contract.DocumentationContractTest.test_agent_handbook_preserves_selected_architecture -v
```

Expected: 2 tests PASS。完整文档治理测试仍因其余规范文件未创建而保持 RED。
