# 本机付费预算管理

## 只读真实验收准备

`readiness.py`只读取本地计划和1～3题代表案例，不打开总账、不授权、不加载密钥、不发HTTP或执行模型。账户侧消费上限确认默认false；计划仍复用`manage.load_plan`严格校验价格已核实、未来期限、金额、次数与token字段。报告只含计划SHA256、安全上限/价格版本/案例标识，不保存问题正文。`READY_FOR_REVIEW`仅表示静态审阅材料齐全，绝不是可执行授权。

```powershell
efficiency-platform-agent/.venv/Scripts/python.exe scripts/acceptance/paid-budget/readiness.py --plan scripts/acceptance/paid-budget/budget-plan.example.json --cases scripts/acceptance/paid-budget/representative-cases.example.json --out .local-acceptance/business-budget-20261103/readiness.json
```

输出目录须已存在，输出文件必须是`.local-acceptance`内的新文件，拒绝覆盖。以上零预算模板保持`BLOCKED`；不要为消除阻塞而擅自填入真实预算。仅当用户确已核实账户消费上限时显式加`--account-limit-confirmed`。案例必须包含唯一非空`key`/`question`、`category`（公司/混合/通用）、非空`description`及正整数`expected_max_attempts`；key最多256字符，attempts不得超过64位有符号整数上限。示例使用0表示调用上界尚未确认，会被预检拒绝；必须人工核算全部生成/Embedding/rerank/重试尝试后填写正整数，不能假设一次问答只有一次模型调用。检查总/单题尝试、固定费用上界是否覆盖冻结价格最坏成本、以及价格输入/输出/推理上界能否容纳；DeepSeek推理保守按全部输出计入推理上界（不会重复计费），其他Provider按0。价格真实性、实际调用上界及真实执行需另外人工审阅与明确授权。

状态：Token 预算与结算实现及离线验证完成；更新：2026-11-03。适用于本机 Agent 外部付费 HTTP 调用，与根目录 `docs/superpowers/specs/2026-11-03-问答Token硬预算与费用结算-设计.md` 配套。

默认零付费。示例计划所有上限为 0、价格为空且未核实，不能授权。本轮不得为真实服务授权非零预算。CLI 只管理 SQLite，不发 HTTP、不加载密钥、不启动模型。

## 查看与停止

在项目根目录运行：

```powershell
efficiency-platform-agent/.venv/Scripts/python.exe scripts/acceptance/paid-budget/manage.py status
efficiency-platform-agent/.venv/Scripts/python.exe scripts/acceptance/paid-budget/manage.py details --budget-id YOUR_EXISTING_ID
efficiency-platform-agent/.venv/Scripts/python.exe scripts/acceptance/paid-budget/manage.py stop --budget-id YOUR_EXISTING_ID --confirm-write
```

`status` 和 `details` 只读，不创建授权；不存在账本时不创建文件，不迁移已有数据库。`details` 可省略 `--budget-id` 查看当前批次，指定 ID 可查看历史批次。`stop` 持久停止指定预算。不存在 reset/refill/autorenew 命令；重复预算 ID 不得清零或复用。

## 用户明确授权后的手工开通

只有用户确认允许真实费用后，由操作者自行准备计划文件，核实每种 Provider/模型的最新价格和单次最坏费用，填入唯一预算 ID、总调用/费用上限、绝对截止时间、单问题上限/时限、并发及 429 累计阈值。调用、金额、期限、并发、429 阈值及输入 token 的总量/单问题上限必须为正整数；输出/推理 token 的总量/单问题上限可为 0，表示禁止该类 token，绝不表示无限。推理上限不得大于对应输出上限。截止时间是未来 Unix 毫秒。所有整数不得超过 SQLite 有符号 64 位上限。金额统一为 **CNY 微元，1 元 = 1000000 微元**。

计划必须恰好包含 `budget`、`prices`、`pricing_verified`；预算完整字段见零授权示例，缺少六项 token 字段的旧计划在打开账本前拒绝。`prices` 每项必须完整包含：

- 身份与来源：`provider`、`model`、`pricing_source`、`pricing_version`，均为非空字符串。
- 单次边界：`max_request_bytes`、`max_input_tokens`、`max_output_tokens`、`max_cost_microunits_per_attempt`。
- CNY 微元/百万 token 整数费率：`input_microunits_per_million`、`cached_input_microunits_per_million`、`output_microunits_per_million`。

输入费率、请求体/输入上限与固定单次金额上限必须为正；缓存费率可为 0；deepseek 输出费率必须为正，embedding/rerank 可为 0。`pricing_source` 记录人工核验来源与日期，`pricing_version` 唯一标识核验版本。只有核实真实费率和全部边界后才手工设 `pricing_verified: true`。每次预留还会检查固定金额上限足以覆盖该授权价格与请求最坏 token 成本；不足时在发送前拒绝。未知/重复字段、重复模型价格、空价格、未核实价格、布尔/负数/溢出整数均拒绝。不要把密钥或提示词放入计划。

```powershell
efficiency-platform-agent/.venv/Scripts/python.exe scripts/acceptance/paid-budget/manage.py authorize --plan PATH_TO_USER_VERIFIED_PLAN.json --confirm-write
```

每次实际 HTTP 尝试预留已核实的单次最坏费用和输入/输出/推理 token；合法完整 usage 可按实际消耗结算。失败、超时、取消及 usage 缺失标记为 unknown，保留预留，不当作零消耗或退款；SDK 重试不能形成免费尝试。402 立即熔断，429 累计达到阈值后熔断；熔断跨进程/重启保留。新的授权必须另经用户明确决定，不能自动循环授权。

价格项的 `provider` 分别为 `deepseek`、`embedding`、`rerank`，`model` 必须与实际请求一致；生成请求必须显式包含允许范围内的输出 token 上限。按 usage×授权费率计算的金额是本地结算估算，并非供应商实际账单。缓存 token 是输入子集，推理 token 是输出子集，不能分别再次加总；成本使用 `(输入−缓存)×输入费率 + 缓存×缓存费率 + 输出×输出费率`，合计除以一百万后向上取整到微元。

纯数学示例（合成费率，不是授权配置）：输入 100、其中缓存 20、输出 10、其中推理 4；合成费率分别为 1000000、500000、2000000 微元/百万 token，计算得 80+10+20=110 微元。推理 4 已包含在输出 10 中，不额外计费。该示例不能用于真实价格核验或开通预算。

服务启动时固定使用当时生效的预算；手工授权新计划会停止旧计划，旧进程不能继续花旧额度，随后需重启Agent加载新预算。没有授权时服务健康接口仍可用，付费业务返回 `NO_BUDGET`。`status` 保留累计调用、保守占用金额、剩余上限、绝对截止和停止原因，新增总量及单问题 token/金额汇总；`details` 按批次列出每调用与单问题 scope：预留 token/金额、reported usage/计算金额（未知为 null）、unknown/settled/anomaly 等状态及价格版本。unknown 不可从预留占用中减掉。进程崩溃留下的在途预留不会自动回收，可能保守阻断新请求；必须人工核对，不提供清零或退款命令。

只有正常完整读完且usage可验证时，结算才释放“预留减实际”的已证实未使用额度；取消、连接中断、缺终态、字段冲突等均保留全部预留。若厂商实际上报超过预留，持久熔断且记录实际异常；金额超SQLite整数范围时以精确十进制保存、标记`cost_overflow`并显示剩余额度0，不能把异常当作便宜请求继续发。旧账字段缺失时不自动迁移真实授权为新额度；需明确人工新授权。

旧Intent/研究/S7生成与付费搜索脚本已在联网前以 `PAID_LEGACY_ENTRY_DISABLED` 拒绝；请改用受保护的Java/Agent入口。仅免费 `models.list` 只读探针保留。显式测试模式也必须注入Fake Provider或无其他路由的MockTransport，不能用“测试”名义创建无守卫真实客户端。

## 固定共享总账与验收

Windows 默认 `%LOCALAPPDATA%/efficiency-platform/paid-budget.sqlite3`，缺失变量时取当前用户 `AppData/Local`；其他系统使用 `$XDG_DATA_HOME/efficiency-platform/paid-budget.sqlite3` 或 `~/.local/share/efficiency-platform/paid-budget.sqlite3`。同用户跨工作树和代理共用，文件不进项目版本管理。

全局 `--ledger PATH` 仅用于临时离线测试或显式管理员配置，必须放在子命令前。**不得为真实验收另开账本，绕过固定服务预算**。业务 HTTP 不接受账本或预算参数。账户其他程序的扣费和 Codex 服务自身 token 不受此账本约束，用户仍需配置供应商账户消费上限。

离线测试：

```powershell
efficiency-platform-agent/.venv/Scripts/python.exe -m unittest discover -s scripts/acceptance/paid-budget -p test_manage.py
```

测试只在临时目录授权有限 Fake 预算并阻断 socket 连接；不得将测试计划复制为真实服务授权。
