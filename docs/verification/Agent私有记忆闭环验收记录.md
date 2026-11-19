# Agent私有记忆闭环验收记录

状态：M1-B隔离工程验收进行中，授权刷新真实接合已部分通过，尚未完成正式发布。负责人：当前执行者；更新时间：2026-11-18；适用：运营Direct和客服GENERAL_QUERY的当前受支持入口。依据：统一记忆实施计划D10—D17。

## 当前可核验结果

| 范围 | 实际证据 | 结论 |
| --- | --- | --- |
| 私有偏好保存/跨会话读取/更正/首次并发 | D12、D14API真实Identity/HTTP/MyBatis/MySQL；D17管理矩阵8个tenant/user/Agent范围、16会话 | 隔离工程通过；不共享其他会话原文 |
| 已运行记忆遗忘 | D17真实Java→Outbox worker→Agent→MySQL/PG，运营和客服各实际执行→停止/清理→DELETED→明确重新授权 | 真依赖通过，唯一Fake为模型边界 |
| 未执行记忆遗忘 | D17管理矩阵以已锁来源完整闭包证明无EXECUTION，实际worker清版本/抑制/墓碑 | 无执行证明通过；不冒称实际删除过thread |
| 旧历史与安全依赖 | D13实际多轮运营/客服历史、完整Manifest；来源撤销后旧回答不进入新输入 | 受支持入口通过，未知血缘拒绝 |
| Checkpoint全部正文加密及整组清理 | D16真实MySQL8.0.26+PG17.6：12 passed，官方Saver3.1.2与自有索引；primitive明文红→绿、typed容器、AAD篡改拒绝、root/child/ns/pending全清 | 组件通过，未知后端/不完整登记保持pending |
| 运行中/已开流遗忘 | D17INFLIGHT真实Java/Agent/MySQL/PG：取消信号后实际Provider退出被gate阻塞时无ACK，退出后DELETED；已开网络SSE不再回放故障注入marker | 通过；marker由真实publish入口合成注入，不冒称模型流式输出 |
| Agent进程重启 | D17INFLIGHT实际关闭/重启Agent，同MySQL原SCRUBBED执行稳定拒绝且新进程Provider调用0 | 当前范围通过；未知跨实例owner仍保持pending |
| 删除清单优先于旧备份 | D17RESTORE真实旧ACTIVE记录+更高item/source tombstone，旧16断言红→读写门禁绿；原D15再授权回归通过 | 最低读取/写入屏障通过，不代表完整备份恢复编排或旧原料物理擦除工具 |
| worker互斥和故障恢复 | D17真实两MySQL连接GET_LOCK竞争、持久lease过期恢复、原deadline不变 | 通过；没有自动续Provider预算 |
| 明确重授权 | 仅原owner新USER decision+当前suppression revision+新加密版本；旧DELETED正文保持NULL | 通过，不复活旧版本或旧来源 |
| 浏览器记忆管理 | D14API真实浏览器→Java身份/业务Mapper/MySQL；17 GET/10 POST，双用户、双Agent与撤登录 | 通过；验收宿主仅内存Bearer，生产登录壳未交付 |

上述成功分别绑定各自冻结代码和场景，不能合并描述成全部Agent、全部记忆层或生产部署已完成。HR当前TASK_ONLY，不建立候选人长期印象；专家/知识路径未完成的记忆入口仍失败关闭，统一覆盖留D30。

## 授权刷新实际接合增量

以下证据均位于 `.local-acceptance/agent-memory-implementation/` 的不可变运行目录；真实本机接口、MySQL与PostgreSQL参与，外部模型仅Fixed Fake或MockTransport。

| 场景 | 实际证据 | 已证实行为 |
| --- | --- | --- |
| Java→客服原回答栈的TTL刷新 | `runs/D16RF07/9c0c59afc5f59578/`，1/0/0/0，BUILD26.594s | 原运行、deadline与计数保留，Java复核原登录/来源后自动刷新；意图与回答各一次；原准备Manifest保持1/1，RESULT实际发送授权分别1/2；员工SSE不含等待引用，终态重连不再resume |
| 运营Direct真实CPU等待与结果保存 | `runs/D16RF04G/66ef02d0da4c8dad/`，2passed18.57s | 真实LangGraph interrupt、官方/自有同ID检查点及内部HTTP恢复；含响应跨TTL后保存加密结果、原Run再发布，模型与费用预留各一次 |
| 原Paid栈连续候选过期 | `runs/D16RF04P/63cf560058b75616/`，2passed12.17s | 两次安装后过期沿同原栈迁移继任等待，第三次有效ACKED后发送一次；refresh_count=3、当前版本4，原reservation、attempt与冻结请求不重建 |
| 跨库局部ACK过期 | `runs/D16RF03I1/d45cc8156de6e9ad/`与`5697b4f630afd0a8/`，1+5定向passed | MySQL先确认而PG未提交时，候选过期后安全落ABORTED/BLOCKED；保留MySQL不可变历史、原count/财务锚，无过期ACTIVE；独立复审C0/I0 |
| 启动结构门禁 | `runs/D16RF03/31c5b2fd5d0d3482/`，8passed7.43s | 完整结构可启动；真实缺表/缺列、未强制CHECK、缺失或禁用trigger、缺唯一索引分别拒启，无启动DDL |
| 内部HTTP拒绝与重放 | `runs/D16RF07N/12a39fd0b306af63/`，1passed2.35s | 错身份/作用域、操作锚与Schema变化不增加候选或计数；正确候选同ID多次回放保持同回执 |

新增验收暴露并记录了两个尚未关闭的组合缺口：运营Graph在reserve后才过期时，须绑定真实Dispatch检查点而非重跑Dispatch；客服在intent阶段刷新后，后续调用须同时使用原执行的最新绑定和经认证的原grant。后者已有精确离线ContextVar反例与修补，但真实intent链在更早的grant登记差异处被拒，仍在接合，不能用回答阶段通过代替。上述表格也不等于R01—R17完整验收或生产功能启用。

## 最新完整接口执行

命令（工作区根）：

```text
efficiency-platform-agent/.venv/Scripts/python.exe .local-acceptance/agent-memory-implementation/run_local_memory_postgres.py --task D17 --mysql-java-tests PrivateMemoryLifecycleIntegrationTest
```

最近一次包含8范围/16会话矩阵和恢复读取屏障的真实执行：1 test、0 failure、0 error、0 skipped，BUILD SUCCESS 38.392s。`logs/D17-real-java.log`和`green/D17-real-java.json`记录实际过程；真实MySQL8.0.26和PostgreSQL17.6，`green/D17-local-{mysql,postgres}-runtime.json`确认仅任务自建loopback实例、全部测试schema为0、进程停止、Temp移除。D17原两业务执行清理的较早1pass另存`green/D17-first-full-lifecycle-real-java.log/json`，未用后续新增测试冒充早期覆盖。

D17RESTORE独立真实用例：1/0/0/0、test7.486s，BUILD12.163s；随后MemoryForgetIntegrationTest原真实回归1/0/0/0、BUILD15.308s，保留RR锁等待后的新MESSAGE闭包、独立source epoch、旧job与重新授权等断言。

D17INFLIGHT独立真实用例：1/0/0/0、test24.00s，BUILD28.814s；日志`logs/D17I-real-java.log`，双库运行与清理见`green/D17I-*.json`。真实Provider取消/退出握手、未退出不能ACK、已开网络SSE、迟到publish拒绝、重复原request不新增Provider及Agent进程重启均有固定断言。

当前阶段全量检查：Vue49个文件/263测试通过，typecheck/lint/format退出0，`green/D17-final-ui.json`。Java全工程485测试中474通过、11个显式集成默认跳过，失败/错误0，命令和逐suite见`green/D17-final-java.json`；这些跳过不当实际绿，其中本阶段重点集成已另行真实启用。Agent原全套2051通过、124子测试通过、2失败：HR草稿Schema漂移与测试实际使用随真实日期过期的enabled来源。D17CHECKFIX只同步DRAFT_NOT_PUBLISHED资产input_schema和确定性合成测试，原2红→4定向绿，相关49绿，独立复审C0/I0；未改生产授权、时效校验或发布状态，不把两次输出拼成同一次全套全绿。98生产源Ruff/mypy/compile全部通过。

所有证据路径相对 `.local-acceptance/agent-memory-implementation/`。报告、before快照、difflib差异、SHA256及独立审查分别在reports、before、diffs、manifests、reviews；各增量不重置他人快照。

## 验证中发现的问题与处理

1. 官方Saver会直接把primitive channel和metadata写JSONB；真实marker检查失败后，改为所有内容位置绑定AES256-GCM封装，逐列无明文和解密读回均实际通过。
2. 原resume/erase回执键可碰撞、JsonObject往返变None、自有Checkpoint视图丢恢复binding；精确反例红→内部协议分域/受限typed序列化/认证binding重建后，12项真实双库通过，独立复审关闭三项Important。
3. Provider包装器虚报stream能力，使普通调用走流式失败；真实完整链失败及离线factory反例后，改为仅底层真实支持流式时声明stream，并验证提前关闭先关底流后释放门禁。
4. 只擦数据库仍留下OPS Hub、订阅队列、已复制SSE和会话/Graph缓存；补原worker退出后可信清理及每次yield撤销校验，独立复审关闭Important。
5. owned schema组合层比现有适配器允许范围更宽；实际启动失败后复用原校验器，连接前拒绝，不放宽数据库命名空间。
6. 新恢复读写屏障共享SQL片段跨namespace引用失败；追加真实MyBatis解析/BoundSql红测，修为全限定引用后实际MySQL通过，没有把XML格式正确当作Mapper可用。

详细失败原始输出和修复复验保留在对应任务报告；不以Mock Mapper、Fake ACK或接口200替代数据库事实。

## 尚未关闭的阶段门禁

- 正式共享MySQL迁移仍受1419限制。账户具备普通CREATE/ALTER/TRIGGER，但共享binlog条件要求额外受信配置/权限；本任务没有提升账号、改变全局配置或冒认已部署。
- 在途网络流及当前范围进程重启已通过；备份恢复完整操作编排与阶段Agent全套检查继续执行。Java/Vue本次结果不替代后续新增功能的必要验证。
- Java新包纯授权刷新与Agent持久更新已取得上述真实接口证据；运营reserve后过期组合、客服intent阶段刷新与最终R01—R17门禁仍需闭合。当前不支持的跨执行paid continuation/内容追加继续明确拒绝，原运行中的TTL刷新不生成新预算。
- 生产登录宿主、所有Agent业务启用和正式灰度发布另有门禁。自动提炼、向量、跨Agent/跨用户共享及案例晋升没有因本阶段通过而开放。
- M2摘要合同/唯一derive/压缩收益当前只有各自独立组件证据，Schema/权威来源投影/CAS/主流程和真实模型语义仍未全部接合，不声明M2完成。

## 费用及数据边界

本阶段仅合成授权身份和数据、真实本机接口/数据库、Fake Provider，不访问真实生成/Embedding/rerank。固定真实SQLite总账最近只读复核仍为5 budgets、78 calls、3418262 costMicrounits、0 active，和执行前一致。未创建真实预算、未续期、未清账；正式迁移、生产开启与有限真实供应商验收分别守原门禁。
