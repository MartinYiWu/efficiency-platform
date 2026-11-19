# Agent记忆安全性能与删除演练

状态：阶段证据汇总，未达到全系统发布验收；负责人Codex；更新时间2026-11-19（北京时间）。

## 已执行范围

M1历史阶段真实MySQL/PG、运行中停止、流退出后ACK、实例重启、旧备份删除清单、防复活、八范围十六会话矩阵及共享模型边界已有证据，索引见`.local-acceptance/agent-memory-implementation/progress.md`和对应runs。旧全量3585 passed/105 skipped/280 subtests和Java520 passed/17默认集成跳过是M2/M3后续新增源码之前的基线，不能沿用为当前源码全绿。

本阶段按用户“功能优先、减少重复测试”要求保留预算、权限、删除和关键接口定向验证，未反复运行宽套。D24有独立进程抢最后一次额度、CLI未确认只读、UNKNOWN不退款和后继额度累计；D26/D27有原受控Embedding MockTransport单发、跨重启去重/UNKNOWN、删除先后顺序、同epoch不同generation和retention独立截止；D28有共享偏好完整grant闭包/无grant及聊天源拒绝；D29有测量/HR画像拒绝与独立人工批准门禁。实际命令与输出分别见reports/D24、D26、D26WIRE、D26RETENTION、D27QUERY、D25PYTHON、D28JAVA、D29JAVA。组件通过不是实际共享库部署或真实模型效果通过。

## 仍须完成

新V20—V23及PG索引Schema隔离正逆/真实MyBatis业务链，M2自动主链最终收口，D30实际入口矩阵、300题与1000 scope确定性评估、故障注入、当前冻结版本最终集中检查及独立代码审查。未运行的项目不标绿。

Recall@8、压缩后错误新增事实、p95和并发吞吐需要实际数据与机器/规模说明，目前无结果，不写估计达标值。无真实有限供应商授权时保持真实语义验收未运行。

## 删除语义

Java先禁读并发布完整反向依赖；索引有持久Job时必须取得精确DELETED回执才确认INDEX，不可沿旧policy的NOT_PROVISIONED假ACK。关闭新索引/生成开关不应取消CPU删除补偿；未知结果不释放费用机会。共享撤回只撤对应投影，原私有值保留；任一原源遗忘仍使其派生历史/摘要/候选/案例失效。

2026-11-19追加实际结果：D31SQL扩大至V24共12新表，原生MySQL安装/逆序unusedrollback/重装verify退出0；D31BUSINESS真实MVC/DatabaseIdentity/MyBatis/MySQL 1passed12.47s（BUILD30.727s），原packet4秒自然过期后CPU确认有效候选，新索引未请求且Agent调用0；真实HTTP跨Agentgrant撤回后原private保留。D31INDEX原生PG17.6到期擦除修后同单case1passed3.44s。集中评审原1C/4I已由原独立评审者静态复核关闭，未放宽NOT_PROVISIONED清理证明。UI当前3文件21targeted全过，最新72生产Python源Ruff/mypy/compile全0；此static发生在后续CSRsummary新改之前，不能用于后改全绿声明。
