# Agent记忆与上下文需求追踪矩阵

状态：保留历史M1-A证据；D30已补真实发送边界的分域policy与专家传递血缘接合，后续完整发布/真实供应商仍未验。负责人：Codex；更新时间：2026-11-19；范围：总设计I/T隔离与跨模块合同、上下文协议C场景。历史阶段不因D30代码自动升级；文档自查不等于验收通过。

## 隔离需求

| 编号 | 需求 | 任务 | 关联T/C | 预期证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| I01 | 同用户不同session原文/摘要隔离 | D02/D08/D09 | T04/C15 | scope拒绝/允许用例与HTTP隔离回执 | M1-A通过：真实运营8scope隔离；长期摘要/记忆待D17 |
| I02 | 同用户不同顶层Agent默认拒绝 | D02/D08/D11/D17 | T06/C17 | scope拒绝/允许用例与HTTP隔离回执 | M1-A默认跨Agent拒绝通过；共享成功待D28 |
| I03 | 不同用户拒绝 | D02/D08/D09/D11 | T06/C05 | scope拒绝/允许用例与HTTP隔离回执 | M1-A通过：真实Identity/业务HTTP跨user404及Python受控边界 |
| I04 | 不同tenant拒绝 | D02/D08/D09/D11 | T06/C05 | scope拒绝/允许用例与HTTP隔离回执 | M1-A通过：真实跨tenant404/403及二进制存储隔离 |
| I05 | 11专家仅父任务受权切片 | D05/D07/D09/D30 | T03/C13 | scope拒绝/允许用例与HTTP隔离回执 | D30最终发送Fake矩阵已验：typed父plan/request hash＋实际task切片；不发父history正文，继承父plan真实输入闭包与上游最终Manifest。外部Tool/research/profile可信映射未接仍拒绝 |
| I06 | HR等TASK_ONLY不读取历史 | D02/D07/D08/D09 | T15/C17 | scope拒绝/允许用例与HTTP隔离回执 | M1-A真实HR TASK_ONLY/历史字段拒绝通过；恢复待D16 |
| I07 | 同Agent跨会话仅已确认私有偏好 | D11/D12/D13/D17 | T07/C15 | scope拒绝/允许用例与HTTP隔离回执 | 未运行 |
| I08 | 跨Agent仅显式授权偏好白名单 | D28/D30/D31 | T06/C05 | scope拒绝/允许用例与HTTP隔离回执 | 未运行 |

## T场景完整追踪

| 编号/阶段 | 场景 | 必须证明 | 实施/验收任务 | 证据计划 | 状态 |
| --- | --- | --- | --- | --- | --- |
| T01 M1 | 第8分钟等审批，第二天批准 | 旧run EXPIRED且零外发；无续授权链支持则明确拒绝；后继执行需人工有效授权且历史累计/未知预留不清零 | D16/D24/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T02 M1 | 第一次发送失败后packet过期 | 刷新保持operationId/语义hash/attempt；过期包不外发，重复resume不重复计次或执行 | D13/D16/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T03 M1 | 注入A/B，模型只引用B，A随后撤销 | 输出仍依赖A；不能仅凭展示引用B发布或恢复 | D13/D15/D17 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T04 M1 | 忘记A但保留曾受A影响的回答R | 下一轮历史/摘要/候选不含R及其传递派生物；存档展示不等于模型可读 | D13/D15/D17 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T05 M1 | 换策略、提炼器或新item ID重新处理旧消息 | 字段/源抑制仍生效；只有用户指定范围显式重新授权可解除 | D12/D15/D17 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T06 M1 | 用户退出项目 | 只失效该principal包/缓存/历史/执行，其他成员合法共享记忆保持可用 | D11/D15/D28/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T07 M1 | 同字段首次并发保存相反值 | 数据库逻辑唯一键仅一个item/当前ACTIVE；另一个409或待解决候选，不分裂两个有效值 | D10/D12/D17 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T08 M1 | A/B混合checkpoint，含子图pending writes，A撤销 | 先禁恢复，再清整thread组；清理未确认不标DELETED；新状态不复制旧正文 | D16/D17/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T09 任何实际付费前 | 两Worker争最后一份额度及reserve后进程崩溃 | 同机账本只一个成功外发，未知预留不释放；Provider为唯一保守计账者 | D06/D19/D24/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T10 M1 | 流式输出中撤权 | 敏感正文先缓冲；低风险流停止后续delta、标失效、禁用历史重放；不承诺撤回已显示内容 | D13/D15/D17/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T11 M2 | 摘要输入可读但不允许长期画像 | 不允许BOTH输入模式；仅summary或proposals之一，最多一次生成 | D18/D19/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T12 M2 | 老摘要超过1000 token、新区间持续增长 | 不重叠分段有界选择，遗漏历史明确说明；旧段不偷偷滚动压缩/付费；删源整段禁用 | D18/D20/D21/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T13 M3 | 第二天确认候选、原额度过期 | 保存即精确可用且零付费；索引NOT_REQUESTED，明确申请才启授权流程 | D25/D26/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T14 M3 | 很小授权集合与ANN强过滤 | 精确ground truth对照Recall@8及权限分别验收，scope不放宽；不足8条合法少返回 | D27/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| T15 M1 | 刷新事件重放、乱序revision、Direct/HR入口重发 | 幂等回执或409；非Graph也不重复POST新run；刷新最多3次后确定终止 | D07/D13/D16/D31 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |

## C场景完整追踪

| 编号/阶段 | 场景 | 必须证明 | 实施/验收任务 | 证据计划 | 状态 |
| --- | --- | --- | --- | --- | --- |
| C01 | 中文/代码/JSON/URL/emoji混合及大量工具Schema | 计完整序列化而非字符/4，包含适配器确认占窗的输出Schema | D03/D04/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A模块通过：D03完整序列化保守计数；真实HTTP逐请求清单对照 |
| C02 | T恰等H_ctx、超过1 token、F单独超限 | 前者可进入剩余门禁，后两者正确阻断；不静默裁剪必需内容 | D04/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A模块通过：D02/D03/D04窗口及未知容量拒绝 |
| C03 | output/reasoning、缓存命中及小模型切换 | 正确留O、缓存不减窗口、换模型重新计数，无重复扣除 | D03/D04/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A模块通过：T/H/F边界及真实ALLOW清单核对 |
| C04 | 工具大量结果/分页，未知总数 | 投影有completeness/count/cursor/snapshot；未知为null，前20不冒称总20 | D05/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A模块通过：ToolRuntime owner投影字段/完整性 |
| C05 | 数据聚合及权限缩小 | 分母/total只来自合法范围，不用LLM猜全量，不泄漏无权数量 | D05/D08/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A模块通过：scope/query/快照绑定及授权total拒绝 |
| C06 | 工具调用成功后裁剪/压缩/恢复 | 工具组完整，回执保存且不重复执行，UNKNOWN不变成功 | D04/D05/D16/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A模块通过：未知total/分页/UNKNOWN不升级完整 |
| C07 | 摘要前否决A，曾建议B但未确认 | rejected_options及原因保留，B仍MODEL_SUGGESTION/PROPOSED，不能升级确认 | D18/D20/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C08 | 摘要期间用户更正/源撤销 | CAS拒绝旧候选，禁止回退失效旧段 | D20/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C09 | 无压缩预算、额度已用、截止或402/429 | derive零新增请求；原业务继续也需其有效授权，次数/费用不清零 | D19/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C10 | 候选正文短但完整包装更长 | 用同模型/序列化的T_before/T_after比较，不采用负收益摘要 | D20/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C11 | 已知工具输出上界与未知G | 可验证G才提前压力处理；不伪造预测，结果返回仍重计，无额外derive机会 | D21/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C12 | 源区间自身超摘要窗口 | 有界缩小原始完整组或停止，不把超长原文交同样装不下的摘要模型 | D18/D19/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C13 | 11专家输入输出汇总 | 专家不接父全历史，输出部分完成元数据；父聚合重新计窗且继承安全依赖 | D05/D07/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A定向通过：切片/Decoder/Aggregator保守覆盖及实际专家发送计数 |
| C14 | 长期多Run增长和分段积累 | 总历史/摘要始终有界；省略明确，不滚动摘要的摘要 | D18/D21/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C15 | A影响摘要/R但模型只引B，A被忘记 | 摘要/R/历史/胶囊/Checkpoint不再带回A，展示引用不缩小依赖 | D13/D15/D16/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C16 | 当前价格/HR评分/制度条款占大窗口 | 不有损改写权威字段，已授权业务分段或阻断 | D04/D07/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A通过：必保权威输入超窗阻断，HR实际发送受控；权威字段必保为模块证据 |
| C17 | 多入口与每次重试/恢复 | Direct、HR、客服、Supervisor、专家及摘要都执行同一最终窗口合同 | D06/D07/D09/D21 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A通过：全现有发送入口动态/AST及真实Direct/CSR/HR；摘要待D21 |
| C18 | 前置压缩已用derive，后续想再提炼 | 后续零新增生成；用途不兼容也不拆成两次 | D19/D21/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | 未运行 |
| C19 | 远程计数未准入、未知价格/数据用途 | 无外发；本地无可信上界时明确拒绝，不裸调计数服务 | D03/D09 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A通过：本地未知profile拒绝、无预算零外发；真实价目仍未授权 |
| C20 | Provider计数漂移/context_length | 当前操作停止并留安全诊断，不自动换更贵模型或新ID重发 | D06/D07/D09/D23 | 对应任务定向测试、协议HTTP/Fake与阶段验收报告 | M1-A模块通过：全请求漂移/UNKNOWN/非重试拒绝；真实供应商漂移待D32 |

## 执行记录规则

任务映射表示实现责任与验收阶段，不表示任务已完成；T09等并发账本场景必须在任何真实付费前先离线验证。D09为M1-A、D17为M1-B、D23为M2、D31为全套演练；D32真实供应商验收只有核实价格与有限预算授权后方可运行。范围内Fake测试可用临时账本，不为真实服务另开额度。未来更新每条实际命令、退出码、证据路径与限制；未执行条目不得改为通过。I项不以相邻T/C通过自动代替独立隔离用例。

## M1-A已执行证据索引

- `.local-acceptance/agent-memory-implementation/reports/D02.md`至`D08J.md`、`D07J.md`及各独立reviews：模块红绿与跨端合同。
- `reports/D09O.md`、`green/D09-operation-java-http.json`：真实身份/MyBatis/业务HTTP/SSE→Python及16份完整安全计数，工具数明确为0。
- `reports/D09B.md`：真实客服GENERAL_QUERY、HR发布Prompt/快照、固定3槽修复与UNKNOWN零重发；不代表RAG质量或真实LLM。
- `green/D09-agent-phase.json`：1669通过/124子测试，56生产文件静态通过。`green/D09-java-full.json`：393通过/2默认显式集成跳过，实际集成另行1/0/0/0通过。
- `green/D06-real-mysql.json`与`D07S-real-mysql.json`：真实MySQL隔离仓储/并发/回滚。

这些是分层验收：模块层不冒称真实供应商或后续M1-B/M2/M3成功。生产context_enabled仍需显式发布真实已核实模型容量/Schema/策略资产及持久库；Fake容量不用于正式启用。

D09矩阵补齐最终证据：CSR四actor/八session/18发送；HR四actor/八成功TASK_ONLY加一UNKNOWN/11发送，共29安全清单，25stage、9快照。跨actor同run/op真实红测经D09P持久归属修复后拒绝，原缓存/截止/次数不转移。D09HJ确保实际Java HR也签发可信TASK_ONLY包。最终证据在green/D09-business-http.json和各独立review。

## D30分域实现与能力覆盖（2026-11-19）

以下区分代码接线、默认开关、Fake发送边界与尚不支持项；不把该表当生产开启或全入口业务HTTP已验。

| 入口 | 已接真实代码路径 | 记忆/事实边界 | 默认与当前验收 | 剩余边界 |
| --- | --- | --- | --- | --- |
| OPS Direct/intent | OperationAssistantService→MemoryAgentPolicyService→原PacketService→ServerDispatchAuthority | intent完整原请求继承真实input_dependencies，不读未选偏好；Direct只注入已确认白名单偏好，原摘要/候选沿已有原task机会 | packet/summary/proposals全局默认off；新agent-policy-binding默认false保原兼容，启用后须context.agentModes.operations=PRIVATE_MEMORY；Fake发送矩阵通过 | 真实供应商未验；M2完整真实闭环由独立D23报告决定 |
| OPS Supervisor与11专家 | ScenarioSupervisorAdapter/_ScenarioDispatch→server-owned Slice registry→ModelBackedOperationSpecialist→Authority/Controller→原Provider | 子payload只含goal/条件/所需上游，不发父history/checkpoint；可信父requestDigest+typed TaskSpec/OperationPlan digest绑定实际task input；父plan已读原请求所以传递继承context.input_dependencies，不使用全packet授权集合；最终prepared Manifest所选偏好回填上游结果闭包 | Python ContextPublication.specialist_lineage_enabled默认false，Java原发布context.specialistLineageEnabled也须真bool；25项最终发送矩阵包含11专家＋多轮传递源及未知授权源排除 | 实际研究/Tool/profile/外部制品缺source receipt映射时发送前明确拒绝，不以parent包有sources放过；专家摘要/派生不另开机会 |
| CSR GENERAL_QUERY | CustomerServiceApplicationService/EventProjector→分域policy→原packet/Authority | 当前问题/合法历史/已确认白名单偏好；JSON请求完整必保，不substring裁剪 | context.agentModes.customer-service=PRIVATE_MEMORY才按新分域gate读记忆；Fake发送边界通过 | 无history时摘要NOT_APPLICABLE；有history的CSR自动摘要尚缺带messageID完整组的结构化JSON投影/原frame模板接合，不宣称自动摘要已支持 |
| CSR正式知识/混合知识 | 原CSR检索/证据完整性路径保留；新增KnowledgeFacade.currentSourceSnapshot | 知识模块当前Identity.refresh原ref、knowledge:read权限、真实tenant/KB可见部门、当前发布release成员目录、docVersion/fileSHA逐项校验；新Facade只元数据，不输出正文 | 新metadata权威默认off；PRIVATE_MEMORY知识模型阶段仍MEMORY_KNOWLEDGE_LINEAGE_ADAPTER_REQUIRED且Fake证实0 Provider | 当前KB元数据目录已具体实现；还需将该当前目录签入原packet的逐文档授权源、检索owner对实际每段Evidence/ToolProjection绑定其doc/version/hash并回写完整Manifest。releaseID不能代替全目录授权；未接前可显式CURRENT_FACTS_ONLY沿原正式知识流程，不伪造长期记忆 |
| HR 6101—6110 | HrSemanticGateway→当前业务HrActorAuthority/SourceAuthorization→已发布事实/规则/asOfDate→原Skill/受控Provider | 永远TASK_ONLY、session=null、memory_mode=DISABLED；仅当前任务事实，不读聊天history、不提炼长期候选、不把界面语言/详略偏好用于评分 | 新分域gate开启须context.agentModes.hr=CURRENT_FACTS_ONLY和显式hrSkillIds数组；10个synthetic事实阶段最终发送矩阵通过，既有真实HR历史证据仍独立保留 | 不声称HR长记忆/技术经验自动端口已完成；HR群体/候选人长期印象禁止 |
| 跨Agent偏好/共享案例 | 已有D28 projection/grant/member与D29人工案例 | 仅已授权白名单偏好；专家安全源来自实际选到的manifest而非授权packet全量。案例必须原owner人工重写/独立审批与来源用途 | 全部默认off，代码/组件证据见D28JAVA/D29JAVA | 不能据此把source授权扩成源业务正文权限或生产已部署 |
| 行政 | 无运行入口 | NOT_IMPLEMENTED，只登记未来统一scope/policy/权限准入 | 未实现/未启用 | 不列为已覆盖业务Agent |

11专家固定登记为research.insight、channel.content、ip.strategy、quality.review、campaign.plan、user_growth.plan、brand.strategy、product.plan、analytics.review、community.plan、content.create（实际ID均以operation.前缀）。`tests/unit/context/test_memory_agent_policy_matrix.py`最终25通过：实际ServerDispatchAuthority→ContextController→ControlledModelProvider→FakeProvider，技术授权/Manifest为明确Fake边界，无DB/网络/付费；不是11专家各自全业务Graph/研究质量/真实供应商矩阵。

D30共享树AST定向曾报5个非D30文件依赖越界，已告对应owner；不放宽架构矩阵。当前最终全树门禁应以root后续统一冻结结果为准。精确代码/命令/限制见`.local-acceptance/agent-memory-implementation/reports/D30.md`。
