# Agent记忆M1-A验收报告

2026-11-13。状态：D09整体规格/质量复审通过；第一阶段验收完成。范围D01—D09，仅上下文治理、隔离及当前来源门禁；长期偏好/遗忘/摘要/向量尚未交付。

## 实际结果

- Agent受影响完整回归：1669 passed、124 subtests。56个生产文件Ruff/mypy/compileall通过。首次全量发现HR未发布资产input_schema漏同步，仅生成该草稿字段后定向7项通过，再按原范围最终全量通过；未改发布状态或输出资产。
- Java所属工程全量：393 passed、0failure、0error；2项显式集成默认skip。两项集成均已另行开启、真实执行通过，不能将skip当成功。
- 真实运营业务链：DatabaseIdentityFacade与真实登录表→MemoryActorResolver→MVC/MyBatis/事务→AiInvokeFacade→生产HTTP Client→Python factory/LangGraph→Fake Provider→真实MySQL Manifest/Stage→SSE→Java业务run终态。两tenant×两user×两会话共8scope、16发送、16清单；跨tenant/user不可读，原session撤销不借同账号另一session。
- 真实客服/HR链：实际发布配置、客服GENERAL_QUERY生产Graph/Gateway；HR MySqlPromptRepository/PromptAssembler/快照及持久原运行控制。真实HTTP/专属MySQL，两tenant×两user各两CSR session及HR独立TASK_ONLY成功任务，另注入1个UNKNOWN；总29次Fake发送/29清单/25stage/9实际PromptSnapshot，schema修复共享固定3槽，UNKNOWN后重复请求零新发送。未验证RAG检索质量，也未冒称Java客服/HR业务Controller完整链。
- D06真实MySQL仓储7项、阶段账本8项，含二进制身份、512UTF8字节键、并发CAS、UNKNOWN/三槽、迁移回滚。所有专属schema已清理；共享业务库写入0。

## 计数与权限

真实运营16份逐发送安全诊断位于`.local-acceptance/agent-memory-implementation/green/D09-operation-java-http.json`的contextMeasurements。只含合成scope/执行引用/数值，不含正文、Prompt、凭据。完整ProviderRequest实际独立上界5211—8055；该合成发布策略H_ctx=120000，全部verified/ALLOW，T等于清单上界，F不超T，输出预留与安全余量按发布版本核对。此路径工具数明确为0。工具查询总数/前20条/未知total和专家部分覆盖通过D05模块定向验证，不把Direct无工具样本当作工具查询业务全栈。

运营、客服、HR及专家/意图/场景/研究等现有逻辑阶段在实际Provider请求形成后统一计窗；工具/Schema/options/role均进入最终序列化计数。缺可信scope、容量、内部认证或固定发布配置时失败关闭。付费预留后再次最终门禁；所有门禁I/O返回后重查原截止与停止状态，不延长相对timeout。已SENT或结果未知不因换进程/slot重发。

## 真实调用及启用边界

所有模型均Fake或HTTP MockTransport，真实供应商/Embedding/rerank调用0。当前用户固定SQLite总账与基线一致：5 budgets、78 calls、3418262 costMicrounits、0 active；未重置或另开真实额度。Fake临时账本仅用于明确合成边界。

没有核实真实模型总窗口/输入限制/推理输出口径的发布资产，不得拿合成容量启用生产。正式context_enabled仍默认关闭；开启要求显式密钥、持久仓储、可信Java内部通道与已核实发布资产。真实LLM质量、价格与有限预算验收属于D32授权门禁。

## 问题闭环

已关闭：MySQL PAD SPACE身份混淆；Java硬编码身份/幂等串scope；新内部认证漏头及128字符合同冲突；运营并发pending跨用户结果；合法schema发布变体/输出下调；debug真实actor/TASK_ONLY/原session撤销；意图缺显式max_tokens；最终CAS/账本I/O跨deadline仍发送；HR未发布Schema草稿漂移；HR跨actor同run/op缓存/取消及Java HR中央信封缺失。

每项红绿、代码差异、SHA256、独立review与实际HTTP/SQL层次在`.local-acceptance/agent-memory-implementation/`。D07A/B/S/J及D08J已独立通过；D09O/R两项Important已修复复审通过。D09整体review指出的CSR/HR多主体矩阵已补全并实际通过；补测复现的HR跨actor缓存缺陷由D09P持久scope修复、71定向与review通过，真实矩阵红→绿。Java HR中央网关可信包D09HJ亦已22定向及review通过。D09整体复审Important/Minor全部关闭，下一阶段D10仍需完成专属库演练和本记忆模块共享库迁移授权，不能沿用旧HR授权。

## 未验价目与发布绑定清单

| 用途 | Provider / 可追踪模型绑定 | 未验项 | 继续门禁 |
| --- | --- | --- | --- |
| 意图/运营快速候选 | DeepSeek / AGENT_LLM_DEEPSEEK_FAST_MODEL | 本轮未解析/冻结部署模型名，未核实当前价目、上下文/推理口径 | D03发布资产校验＋D32有限真实预算；未知即拒发 |
| Direct/运营平衡候选 | DeepSeek / AGENT_LLM_DEEPSEEK_BALANCED_MODEL | 同上；不得把synthetic-balanced当正式模型 | 同上 |
| 运营高能力候选 | DeepSeek / AGENT_LLM_DEEPSEEK_STRONG_MODEL | 同上；不得通过候选切换扩大额度 | 同上 |
| 客服各stage/大上下文策略 | 发布Release的model_policy.model_name | 正式release/策略版本、本次价格证明、输入/输出上界尚未冻结 | 明确策略变体＋同一固定账本有效授权；D32 |
| HR发布Prompt | agent_model_policy的provider/model_name及Prompt发布快照 | 正式发布快照对应模型当前价目未验；合成DB seed不算正式证明 | Prompt/容量/价目/预算全部核实才真实调用；D32 |
| 记忆摘要/候选derive | D19显式发布模型绑定（尚未启用） | 当前无正式derive模型价目/用途授权 | D19/D24同task累计＋D32有限真实验收 |
| 记忆Embedding | DashScope / embedding_model，代码默认text-embedding-v4 | 代码默认不等于部署配置；当前真实价目、批大小与保守上界未验 | D26专属投影/用途授权及统一付费守卫 |
| 记忆rerank（若显式策略启用） | DashScope / rerank_model，代码默认qwen3-rerank | 当前真实价目/请求计价上界未验；未启用记忆rerank | D27策略/价格/预算先准入，不自动新增请求 |

本清单不读取或展示API凭据、供应商账户余额或.env，不把历史价格记录作为当前授权。现有固定账本0 active，任何真实调用仍须在发送前由本机管理流程核实具体provider/model、金额/次数/截止；业务HTTP不能补开额度。
