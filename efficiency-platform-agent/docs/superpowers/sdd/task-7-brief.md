# Task 7 实施简报：首页导航与全量验证

## 1. 目标

让工程规范从项目首页可发现，清理前序审查记录的两条 Minor，并对纯 Agent 侧工程骨架、治理文档和源码执行完整、可复现的验证。

## 2. 唯一允许修改的文件

- `README.md`
- `docs/standards/04-测试与质量门禁.md`
- `docs/superpowers/sdd/task-6-report.md`
- `docs/superpowers/sdd/task-7-report.md`（新建）

不得修改任何 Python 源码、测试、其他规范、模板或架构文档。

## 3. README 导航

在 README 的“当前验证”章节之前增加：

```markdown
## 开发规范

- [仓库强制规则](AGENTS.md)
- [Agent 侧开发总纲](Agent.md)
- [贡献与交付流程](CONTRIBUTING.md)
- [安全基线](SECURITY.md)
- [工程规范索引](docs/standards/00-规范索引.md)
- [文档模板](docs/templates/)
- [SQL 变更规范](sql/README.md)
```

可以添加一句简短说明，但不得改写现有架构结论、组件选型或验证声明。检查所有新增链接真实存在。

## 4. Minor 清理

1. 将 `docs/standards/04-测试与质量门禁.md` 中的 `MUST NOT覆盖` 修正为 `MUST NOT 覆盖`，不得借机修改该规范其他内容。
2. 在 `docs/superpowers/sdd/task-6-report.md` 中追加审查补充说明，记录原扫描只覆盖 ASCII `...`，独立审查已使用同时覆盖 ASCII 和 Unicode 省略号的表达式补扫且无命中；给出实际表达式和结果，不重写历史证据。

## 5. 验证

必须执行并把实际输出统计写入报告：

### 5.1 Python 与测试

```powershell
python --version
python -m unittest discover -s tests -v
```

预期：15/15 PASS，0 failures，0 errors，0 skipped。

### 5.2 无字节码源码编译

递归读取 `efficiency_platform_agent/**/*.py`，使用内置 `compile(source, path, 'exec')` 编译，不写入 `__pycache__`。必须报告扫描和成功编译的文件数。

### 5.3 架构约束验证

运行项目已有架构约束检查或对应测试，确认：

- 违规数为 0；
- 只存在一个 Graph Runtime；
- 核心层没有反向依赖具体 Agent/Provider；
- Tool 与 Provider 边界测试通过。

不得只凭目录肉眼判断。

### 5.4 范围边界

扫描并报告：

- `*.java` 文件数必须为 0；
- `efficiency_platform_agent/agents/` 下不得存在 `hr`、`administration`、`operation`、`data_assistant`、`customer_service` 等具体业务 Agent 目录；
- 不执行部署、数据库或外部服务操作。

### 5.5 文档链接与占位内容

验证 README 和所有治理 Markdown 中的相对链接目标存在。忽略 fenced code block 内作为示例展示的路径语法，但不得忽略正文真实链接。

对以下范围扫描 ASCII/Unicode 省略号和常见未完成标记：

- `AGENTS.md`
- `Agent.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `sql/README.md`
- `docs/standards/*.md`
- `docs/templates/*.md`

扫描词至少包含拼接后等价于：ASCII 三点、Unicode 省略号、TBD、FIXME、待补充、待完善、未确定、XXX。报告必须写实际表达式和命中数；如有命中，区分合法示例与无解释占位，不能直接删除规范示例。

### 5.6 Git 状态

先只读检查当前目录是否为 Git 仓库。若不是，如实记录“非 Git 仓库，未执行 diff/commit”；不得初始化 Git。

## 6. 实施报告

`task-7-report.md` 必须包含：

- 精确修改文件列表；
- README 链接清单与有效性；
- 两条 Minor 的关闭证据；
- Python 版本和测试 ran/passed/failures/errors/skipped；
- 编译文件数、架构违规数、Java 文件数、具体业务 Agent 目录数；
- Markdown 链接检查和占位扫描结果；
- Git 检查结果；
- 未执行部署、数据库、Java 或外部写操作的事实。
