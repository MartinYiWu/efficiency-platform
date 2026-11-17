# Agent记忆与上下文边界ADR

| 属性 | 内容 |
| --- | --- |
| 状态 | D01执行基线；规格/质量独立技术评审通过，非生产验收 |
| 负责人 | Codex执行；项目负责人负责业务裁决 |
| 更新时间 | 2026-11-13 |
| 适用范围 | 全项目Agent统一记忆与上下文，D01只读盘点及文档 |
| 执行依据 | 用户明确“按照实施计划开始执行”；此授权与独立技术review分开记账，不伪造外部审批 |
| 关联决策 | 总设计R4 §5/8.1/9/20/21、上下文协议R4、ADR-0005 |

## 裁决与边界

Java为身份权限、原消息、业务事实、长期MemoryItem/Version/Proposal、用户确认、更正、撤销、抑制和删除的权威；Agent只持受控输入与执行派生状态。PostgreSQL/pgvector是可重建召回投影，命中需Java重新hydrate及鉴权；Redis仅短期缓存。Agent独立MySQL保存Run/Event/幂等/运行恢复与后续Manifest，不搬迁为PG运行库。本文只增加记忆/上下文责任边界，不整体替换已接受ADR-0005；其Checkpoint另议条款由本文提出更具体合同，尚不声称已落地。

Java→Agent保持唯一业务调用方向。召回由Java签发受权MemoryContextPacket随请求传递；Python不回调Java数据库或搜索全用户历史。包过期返回结构化等待事件，Java对原来源集合重新授权，经原execution/operation幂等resume更新revision，最多3次；来源变化/撤权停止，不偷偷删来源继续。Direct/HR无Graph路径同样保存wait_event/manifest/回执，不伪造Checkpoint。当前未实现时拒绝动态续执行。

业务task、有限execution和付费authorization分别治理。重启、等待、刷新、新run不重置task累计金额/调用/未知预留；旧execution绝对截止不延长。跨授权续执行链未实现时默认拒绝，次日业务批准不等于新付费授权。真实生成/Embedding/rerank/远程计数均不得绕固定SQLite总账与统一Provider付费HTTP守卫。本文未核实任何真实价格或授予预算。

## agent-scope-catalog/1

版本化目录映射既有release/agent key，不改生产ID。规范顶层ID仅operations、customer-service、hr；domain分别为operations、customer-service、hr。release ID是发布版本引用，不能替代顶层归属。未来行政标记NOT_IMPLEMENTED，不预注册为可执行入口。

| 分支/既有键 | top_level_agent_id | execution_agent_id | session_kind |
| --- | --- | --- | --- |
| 运营会话general_chat/GeneralConversationAgent | operations | 通用Direct执行分支，保留现有实际键 | CONVERSATION |
| 运营Supervisor/既有运行release | operations | Supervisor既有键 | CONVERSATION |
| 客服release bundle/stage_key | customer-service | 既有stage_key | CONVERSATION |
| HR发布Skill编号 | hr | 下列hr.* Skill | TASK_ONLY |
| 未来行政 | NOT_IMPLEMENTED | 无 | 无 |
| operation.research.insight | operations | operation.research.insight | 继承父会话，仅子任务切片 |
| operation.quality.review | operations | operation.quality.review | 继承父会话，仅子任务切片 |
| operation.brand.strategy | operations | operation.brand.strategy | 继承父会话，仅子任务切片 |
| operation.ip.strategy | operations | operation.ip.strategy | 继承父会话，仅子任务切片 |
| operation.product.plan | operations | operation.product.plan | 继承父会话，仅子任务切片 |
| operation.content.create | operations | operation.content.create | 继承父会话，仅子任务切片 |
| operation.channel.content | operations | operation.channel.content | 继承父会话，仅子任务切片 |
| operation.campaign.plan | operations | operation.campaign.plan | 继承父会话，仅子任务切片 |
| operation.user_growth.plan | operations | operation.user_growth.plan | 继承父会话，仅子任务切片 |
| operation.community.plan | operations | operation.community.plan | 继承父会话，仅子任务切片 |
| operation.analytics.review | operations | operation.analytics.review | 继承父会话，仅子任务切片 |
| 6101 | hr | hr.resume.extract | TASK_ONLY，session_id=null |
| 6102 | hr | hr.resume.structure | TASK_ONLY，session_id=null |
| 6103 | hr | hr.requirements.evaluate | TASK_ONLY，session_id=null |
| 6104 | hr | hr.match.explain | TASK_ONLY，session_id=null |
| 6105 | hr | hr.interview.generate | TASK_ONLY，session_id=null |
| 6106 | hr | hr.jd.draft | TASK_ONLY，session_id=null |
| 6107 | hr | hr.run.cancel | TASK_ONLY，session_id=null |
| 6108 | hr | hr.readiness | TASK_ONLY，session_id=null |
| 6109 | hr | hr.workload.preflight | TASK_ONLY，session_id=null |
| 6110 | hr | hr.talent.search | TASK_ONLY，session_id=null |

## 冻结作用域合同

ConversationScope字段tenant_id/user_id/domain/top_level_agent_id/session_kind/session_id；ExecutionScope追加task_id/execution_id/subtask_id/purpose，execution_agent_id仅标执行能力。所有非可选ID非空且长度≤128，domain/顶层ID来自目录，HTTP不得伪造或扩大服务端身份。CONVERSATION历史键严格为(tenant,user,domain,top_agent,session_id)，改变任何一项不可读原历史；session_kind必须CONVERSATION且session_id非空。TASK_ONLY必须session_id=null，history_key=None，绝不查history；不可把null拼成共享会话。task/execution/subtask/purpose也参与授权与来源校验，不是可绕过会话隔离的替代键。

同用户不同会话原文/摘要不互读；同顶层Agent跨会话只允许已明确确认的私有偏好。USER_PRIVATE scope_id由服务端规范化user与origin_top_level_agent_id生成并参与逻辑唯一键；同字段不同origin不合并。跨Agent默认禁用；只有语言、回答长度、输出格式等显式白名单field_key，在用户确认origin/allowed_agent_ids/revision后才可读。授权不包含会话、摘要、客户/候选人材料或项目共享。撤回目标投影不误删origin值。11专家不各建私库，不接父全历史、其他专家轨迹或整个Checkpoint。

## 实际入口与发送边界盘点

路径均相对工作区；下表为源码事实与未来接合合同，不把已有预算保护当完整上下文治理。

| 入口 | 身份/会话来源 | 模型发送与Schema/工具追加 | Provider/预算 | Checkpoint/记忆现状 |
| --- | --- | --- | --- | --- |
| 运营conversation_routes→conversation/service.py | Java OperationAssistantService actor tenant/user；会话按tenant/user查询拥有关系，conversation_id传入 | general_agent.py:91追加system/visible_history/user，113—155流/非流model_runtime；通用Direct属于operations | local_real_factory真实DeepSeekStreamingProvider；ModelRuntime与BudgetGuard；固定SqlitePaidBudgetLedger | Direct不伪造图恢复；DirectConversationSubmission保留既有最多8条/12000字符更严格历史上限，不扩大为12条；尚无统一长期Memory实现 |
| 运营意图解释/修复 | 同运营请求及task | orchestration/intent_interpreter.py:181/211；intent_v2/interpreter.py:304/859；Prompt/patch输出Schema也须计窗 | 同ModelRuntime和父预算，不另领额度 | 意图revision/CAS是运行状态，不是长期事实 |
| 运营Supervisor→11专家 | 继承父task、operations session，subtask单独标识 | specialists/runtime.py调用model；model_backed.py:424/710/753/967含初稿、修订、补充发送；343/374及后续重试追加JSON Schema；scenario_model_executor.py:286另有发送 | 注入ModelRuntime；发布AgentSpec预算不是独立付费额度 | operation_runtime.py:82使用InMemorySaver、176 compile；声明operation-specialist-memory/1尚不等于策略实现 |
| 运营研究专家工具循环 | operation.research.insight父scope切片 | research_v2/tool_loop.py:285追加tools、291输出Schema、314 complete；研究Provider接入local_real_factory | ResearchV2ProviderAdapter/获准免费来源；模型仍同父付费守卫 | research_local_memory临时缓存不可当长期库；子图thread须登记 |
| 客服customer_service_routes.py:24 | Java CustomerServiceApplicationService先findConversation(id,tenant,user)；最多12条完成消息有界历史 | model_gateway.py:294 complete、377构造流request；256/274及387追加输出Schema；evidence_assembly负责证据输入 | 发布release按模型路由，工厂DeepSeek Provider；共享付费账本；RAG Embedding/rerank也受守卫 | 既有会话/Run持久化不证明官方PG Saver已接合；统一memory包待实现 |
| 客服内部rag-debug与ingest/index | 内部受控调用，不得获得用户会话记忆 | rag-debug是证据检索；ingest/index可能Embedding/rerank，不能遗漏计费边界 | local_real_factory的DashScopeEmbeddingProvider/DashScopeRerankProvider及受控HTTP | 无聊天history；不是新增共享记忆授权 |
| HR /skill/execute | Java HR受权Skill请求及冻结事实/配置/快照；无聊天session，TASK_ONLY | hr/service.py:_generate 377—404追加输出合同、421修复消息、444 provider.complete；批处理各次都需门禁 | hr_factory发布策略及HrPolicyModelProvider，RunControl调用/截止与固定付费总账共同限制；保留现有131072策略校验直至版本映射 | 非Graph；无会话历史/长期候选人印象库，评分事实不接受偏好覆盖 |
| 通用runs submit/resume API | 内部受权run/task，不得从用户自报session扩大范围 | harness与runtime调度的实际发送仍归上述Provider/节点；resume不另开操作 | 复用原operation/attempt/预留/截止 | 自有postgres_checkpoint与官方AsyncPostgresSaver工厂存在不表示全入口启用 |

HR逐Skill行为：6101 resume.extract为本地提取/可选OCR，不默认LLM；6102 structure、6103 evaluate（分批）、6104 explain、6105 interview、6106 jd及6110 talent.search经过_generate；6107取消、6108 readiness、6109 workload.preflight是控制/预检入口，不因存在Skill编号而虚构模型请求。每个控制入口仍执行TASK_ONLY与权限边界；若后续新增OCR外部能力另行准入，不在D01启动。

最终供应商序列化边界providers/llm/deepseek.py处理json_schema/response_format等参数，因此计窗必须覆盖最终messages/tools/output-schema及角色开销，不能仅对ContextBuilder正文字符/4估算。上述意图修复、内容修订、补充、scenario与研究循环同样必须登记到D07/D09，不能只覆盖首轮专家。

## 整thread删除与安全依赖

Java历史负责跨Run连续性；thread_id仅对应execution，服务端随机生成并以tenant/execution映射校验，不复用session/task作thread。子图同thread不同namespace或独立child thread均登记parent_execution。共享Saver不构成鉴权。

manifest记录全部实际输入传递safety_dependencies，不以display_citations缩小：看过A/B只引用B仍依赖A。A忘记/撤权后先禁execution恢复和外发，再清整个受影响root/child thread及namespace，包括checkpoints、blobs/channels和pending writes；不对混合A/B状态局部涂改后继续。清理未确认保持DELETE_PENDING/BLOCKED，不声称DELETED。历史回答、摘要、胶囊、缓存、派生候选同样禁回流；备份恢复先应用tombstone。官方Saver与自有适配均须锁版本验证删除接口和真实清理，当前InMemorySaver不能证明重启恢复或持久删除。

## 后续门禁与取舍

D01只冻结文档合同与入口目录。D02实施前应由独立技术review记录目录完整性、条款冲突和严重问题关闭情况；本次执行授权已存在，不再以计划旧“未批准”描述重复索要用户授权。本文没有外部评审结论，亦未启动D02。

先M1-A每次请求完整计窗/工具投影/专家切片/Manifest和权限费用最终门禁，再M1-B精确偏好与遗忘闭环；M2才允许有限摘要，后续才启向量/跨Agent白名单/共享案例。容量、tokenizer或价格上界不可信则发送前拒绝，不自动更贵模型、不新run绕限、不循环摘要。未来生产迁移另有预检、授权及回滚，D01无数据库连接或DDL。

## D01独立技术复审

2026-11-13：规格符合性与质量均通过，Critical=0/Important=0，可进入D02。证据`.local-acceptance/agent-memory-implementation/reviews/D01.md`；仅静态核对，不把本条作为运行验收或真实付费/共享DDL授权。
