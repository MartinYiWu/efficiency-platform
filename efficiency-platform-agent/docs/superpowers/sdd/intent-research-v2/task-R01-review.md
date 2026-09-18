# R01 规格与质量审查

## 审查过程

1. 费用/准入轮：paid、unknown、disabled、UNVERIFIED、过期证据与准入记录漂移均失败关闭。
2. 运行时轮：用途、adapter、用户范围、primary、语言/地区、历史与 max lookback 先过滤后返回。
3. 凭据/额度轮：需要认证但无可信 credential、quota 未知/耗尽均拒绝；静态额度不能冒充实时余额。
4. 原子预留轮：发现“有剩余额度快照”仍不等于调用前预留，新增 `SourceQuotaLedger`；free_quota 无账本/预留失败不可调用。
5. 配置轮：三个候选全部关闭且未核验，未知字段/模块路径/未知 adapter 被严格 Schema 拒绝。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 免费与 VERIFIED 是程序门禁 | 通过 |
| 费用/准入双 TTL 与未来时间拒绝 | 通过 |
| adapter 显式注册、无动态模块加载 | 通过 |
| Token 不入配置，凭据仅可信 ID | 通过 |
| free_quota 快照与调用前原子预留分离 | 通过 |
| 用户来源限制和历史能力硬过滤 | 通过 |
| 默认配置零真实可用来源、零网络 | 通过 |
| contracts/architecture/全量回归 | 通过 |

## 结论

**PASS。** R01 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 问题；该结论不代表 R02 网络安全边界或任何真实来源已通过准入。
