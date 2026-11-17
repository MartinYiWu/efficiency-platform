# Agent记忆数据库迁移审阅

> 状态：脚本/隔离验证通过，共享迁移受1419阻断；任务未complete。适用aiep-biz-aihub；更新时间2026-11-14。
> 依据：总设计§9/§19/§21、D10 brief、D01 ADR。迁移号在写入前核对当前最大V1.2.15，本次新建V1.2.16，不修改历史迁移。

## DBA执行入口

当前用户已批准数据库操作；待具备技术权限的管理会话完成以下顺序。实际应用连接报1419，共享库目前memory对象仍为0。先核对目标业务库及预检，满足触发器创建条件后执行一次up，最后verify；应用账号继续使用业务DML权限。

| 顺序 | 已审文件 | 当前SHA256 |
| --- | --- | --- |
| 只读预检 | [V1.2.16__precheck_agent_memory.sql](../../ai-efficiency-platform/sql/verification/V1.2.16__precheck_agent_memory.sql) | `6386cd7edb68cf4d27ac6163e1a9aaa7f27d13c33dff1620263d4d7a15994dcf` |
| 新增12表及12触发器 | [V1.2.16__agent_memory_core.sql](../../ai-efficiency-platform/sql/migration/V1.2.16__agent_memory_core.sql) | `9d13daf70e91edae1ca3e5b8654a643dfe83dc16174b1661aebdbd6ac5e69de1` |
| 执行后核验 | [V1.2.16__verify_agent_memory.sql](../../ai-efficiency-platform/sql/verification/V1.2.16__verify_agent_memory.sql) | `26d13f182a057b83372bbe2070743c1435a6a881b79b1539061db322fc54943d` |

本任务没有更改共享服务器全局参数或应用账号权限。本机隔离验证不代表共享迁移已执行；D11及后续功能尚未开始。以下过程记录以文末最新实际结果为准。

## 范围

Java sql/是唯一SQL入口。本次12表为session_binding、policy、policy_version、item、version、source、dependency、decision、suppression、outbox、deletion_job、tombstone，统一ai_memory_前缀；无proposal、summary、vector、第二套消息或任务框架。默认policy.enabled=false，不自动启用功能/模型/索引或创建费用授权。

session_binding只保存已由服务端验证的运营/客服原会话引用及归属代次，唯一tenant/user/session防同会话改绑顶层Agent；HR TASK_ONLY不插会话binding。原会话/Run/HR execution仍在已有业务表，不能用binding获得原对象权限。

## 精确身份与键

tenant/subject/user等身份VARBINARY(512)，Java校验128 Unicode code point与512 UTF8字节，保留尾空格/大小写，不trim不截断。USER_PRIVATE scope_id采用`up1:`+4字节大端user字节长度+user原始UTF8+受控origin_agent；VARBINARY(1024)容纳128emoji，DB CHECK重新计算规范值。subject与owner独立。

item唯一键完整包含tenant/subject_type/subject/domain/scope_type/scope/purpose/field；purpose64、field128为受控ASCII机器字段。最坏索引2336字节，小于InnoDB16K页/DYNAMIC常见3072限制，无前缀索引。正式环境仍须预检真实版本/page size/row format。

## 数据库约束路线

同item唯一ACTIVE由条件STORED active_marker+完整唯一索引保证。current复合FK保证tenant/item/version一致；item插入/更新触发器要求current存在且ACTIVE，version离开ACTIVE前触发器锁原item并拒绝仍被指向；非ACTIVE不能再激活，只能建立新版本。立即约束要求事务先清指针、退役旧ACTIVE、插新ACTIVE、设置新指针和revision。无需未批准DRAFT状态。

version正文/加密标识/AAD/事实时间/来源关联不可覆盖，物理DELETE拒绝。合法scrub仅允许DELETED+匹配同tenant/item/deletion_epoch且全部目标已确认的SUCCEEDED deletion_job，将cipher/nonce/tag/content_hmac清空并写scrubbed_at；不能换值、重活或改key版本。policy_version更新/删除拒绝；source、item、suppression、tombstone代次不可回退，抑制/tombstone不可物理删除。Outbox有事件ID与逻辑事件双唯一键，重复投递不能产生第二事件；SOURCE suppression按tenant/source/version唯一，FIELD按完整subject/scope/field唯一。

source/dependency保持完整安全来源反向索引，包含既有execution/root/child thread/namespace元数据，不以展示引用裁剪依赖。多态target引用由后续拥有模块复验，不伪造跨业务FK或复制原文。

## 加密与事务边界

版本存ciphertext、nonce、tag、key_version、payload_schema、tenant分离HMAC及AAD格式/tenant/item/version/key_version元数据；CHECK与触发器绑定且不可修改。Mapper.aad使用版本化长度前缀编码，集成用临时测试密钥证明改变任一绑定字段导致AEAD失败。D10未实现生产密钥加载/业务加密服务，临时密钥只在隔离测试，不得作为生产随机密钥fallback。

CAS SQL只更新匹配expected_revision的行；低层Mapper不替代授权。item/version/decision/dependency/outbox应由下一阶段同一短事务调用；本次集成检验SQL及MyBatis事务回滚，不在事务中联网。

## 脚本与授权

- sql/verification/V1.2.16__precheck_agent_memory.sql：只读版本/page size、同名对象冲突，不输出连接或凭据。
- sql/migration/V1.2.16__agent_memory_core.sql：12表、2次显式循环FK、11触发器；标准DELIMITER $$，执行器必须尊重触发器内部分号，禁止直接split(';')。
- sql/verification/V1.2.16__verify_agent_memory.sql：只读结构与状态违例计数，预期12表11触发器、无前缀、状态/AAD违例0。
- sql/rollback/R__V1.2.16__agent_memory_core.sql：手工先移除触发器/两个循环FK，再按依赖逆序删除本次对象；只供本次专属隔离库破坏性演练，不可用于已含真实记忆的业务库。

MySQL DDL不参与业务事务回滚。root将仅在aiep_memory_it_日期_随机空库执行正向/反向演练，检查0残留。共享库须先完成只读预检、展示独立审阅后的精确脚本/hash/影响/回滚边界并核实本模块明确授权，才可执行该脚本一次；本文件与D09放行不是共享DDL授权。

## 当前证据门禁

真实空库红已由root确认expected12/actual0，不是环境红；编译/ArchUnit通过且集成默认skip不算成功。正式绿与rollback结果待root审阅脚本后在专属真MySQL执行；未据注释声称数据库约束已验证。证据和限制归本地reports/D10.md；共享真实迁移尚未执行。


## D10目录PAD SPACE复审修复

独立review Important指出VARCHAR ascii_bin目录会接受尾空格，但scope保留原字节。root真实只读表达式probe已重现。新候选将本次目录列改为VARBINARY同字节上界，并为item/suppression scope_type增加总设计§8与D02 MemoryPolicy共同批准六值的精确CHECK。不会trim或截断别名，合法domain/agent值不变；不触历史迁移。

新增JDBC绕过Javahelper直接写raw scope，验证目录尾空格/大小写/规范scope匹配拒绝；原128emoji/真实身份尾空格正向仍保留。该修复待独立复审及专属真MySQL实际约束验证，不能用probe或默认skip冒称候选DDL已通过。


## 已审SQL实际up与测试事务装配

root专属本机MySQL8.0.26已实际执行25条up成功；共享服务器独立schema原尝试仅因1419权限/binlog限制停止，未改服务器配置。该次本机完整green在Mapper回滚测试装配处失败，尚不构成绿测。

修复仅将测试裸SqlSession改为同DataSource的Spring事务管理器/TransactionTemplate/SqlSessionTemplate，不改Schema、断言或清数据。四SQL与已审SHA256保持一致；完整green、反序current/retire并发与逆向残留0待root受控重验，不以静态或前序断言替代。


## 同anchor显式重新授权窄例外（2026-11-14候选）

旧DELETED anchor永久不可LIVE已由真实--reauth-red确证与§9.1/§10.4冲突。修复仅追加Decision.expected_suppression_revision及严格item trigger分支；不恢复旧版本、不改逻辑键、不让模型/普通SAVE/System决策解锁。

明确USER REAUTHORIZE需绑定原owner、同item的新ACTIVE version、原/新revision与严格grant推进及单调epoch；正数绑定已解除规则的旧epoch，0代表完整逻辑FIELD规则不存在，二者都不能替代用户决策。旧DELETED body保持NULL；SOURCE只检查新版本实际依赖，旧源规则保留，不作全局解除。

新增suppression BEFORE INSERT与既有UPDATE共用item/source锚点锁，配合item更新内FOR UPDATE current read，使0=absent不依赖RR gap lock。当前12表/12trigger/up26，rollback新增trigger DROP；新SQL/hash须重新review/专属cycle。root仅补precheck只读binlog/trust权限检查，未修改共享服务器配置或执行共享业务DDL。


## 实际最终结果与共享阻断（2026-11-14）

root已在任务独占本机MySQL8.0.26临时loopback/binlogoff实例完成当前hash脚本up26、真实Schema green（1项、0失败/错误/跳过）、verify7、rollback26及rollback green（1项、0失败/错误/跳过）。最后memory表0/trigger0、schema已删；专属服务器已停、临时目录已清理，既有两个mysqld未触。证据green/D10-schema-cycle.json、D10-schema-green.log、D10-schema-rollback.log、D10-local-mysql-runtime.json。

双连接item/version反序锁强制竞争为1commit+1拒绝（1213死锁回滚），current invariant保留。目录/身份、ACTIVE/current、不可覆盖/scrub、真实Spring Mapper事务、AAD及显式同anchor重新授权/0=absent/拒绝路径已实际执行；默认skip的静态日志不能替代此证据。以上不是D12/D15业务闭环已上线。

共享只读预检另实测MySQL8.0.36-28、16K页、binlog1/trust0，应用账户没有SUPER及active/granted角色；现有memory表/trigger0，1419未解除。用户已批准DB操作，无需重复请求授权。剩余动作是由DBA已有管理会话对已审hash执行precheck/up/verify并留证；不自动给应用账号提权或改共享全局配置，不对共享真实数据执行破坏性rollback。

当前准确结论：“脚本/隔离验证通过，共享迁移受1419阻断”。未标D10 task complete；本次仅补结果文档，不改变SQL/source。
