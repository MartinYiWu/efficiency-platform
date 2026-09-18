# R08 规格与质量审查

## 审查过程

1. H1 轮：检查所有事件成员必须来自过滤 accepted 集合，缺失或 uncertain 不能默认通过。
2. H2 轮：发现“事件内任意 full 文档”不足，收紧为每个 Claim 的实际支持引用至少落在 full/platform_text 文档。
3. H3 轮：重验 Ref/正文、独立来源最小值和 required facet 的 primary 策略，不信任上游布尔结论。
4. H4/H5 轮：覆盖跨事件重复成员、objective unresolved 冲突与 attributed dispute，冲突不冒充确定事实。
5. H6 轮：来源策略缺失和显式禁止均失败关闭；来源 URL 可访问不等于允许使用/保存。
6. 集合数量轮：验证 exact 不足、best_effort 少于 target、minimum 和 required facets，不用凑数或固定三家来源。
7. 空结果轮：覆盖完整成功空、全失败空、分页截断和历史 unknown，只有第一种可 NO_MATCHES。
8. 致命错误轮：补充 critical integrity failure 优先级，已有合格事件也不能覆盖成 COMPLETE。
9. arXiv 轮：验证显式 submittedDate、category、offset、totalResults、submitted/updated、landing URL 和 abstract_only；畸形 200 失败。
10. GDELT 轮：验证显式 start/end、first_seen 语义、URL-only 线索、历史前置拒绝和畸形 200；无总量证明保持 unknown。
11. 来源治理轮：确认新增 adapter 只进入显式允许枚举，TOML 中继续 disabled/UNVERIFIED/unknown cost。
12. 回放轮：程序展开 manifest，确认 100 个连续唯一文档、30 个事件和 H1–H6 正反例矩阵。
13. 回归轮：执行 R08 定向、全仓 Ruff、全 src mypy 和全量 pytest，未发现新增回归。

## 最终确认

| 检查项 | 结果 |
|---|---|
| H1–H6 逐事件程序门禁 | 通过 |
| exact/at_most/best_effort 数量语义 | 通过 |
| required facets 覆盖与 gap | 通过 |
| COMPLETE/PARTIAL/NO_MATCHES/FAILED 区分 | 通过 |
| fatal integrity failure 优先级 | 通过 |
| arXiv 摘要范围与时间/分页契约 | 通过 |
| GDELT 显式窗口、历史与 URL 线索契约 | 通过 |
| 无总量证明不伪造 complete coverage | 通过 |
| 两来源保持 disabled/UNVERIFIED | 通过 |
| 100 文档/30 事件 manifest | 通过 |
| 全仓静态检查与全量回归 | 通过 |
| 真实免费性、条款、限额和公网可用性 | 未执行，按计划保持关闭 |

## 结论

**PASS。** R08 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 实现问题；本结论只覆盖离线质量裁决、Provider 契约和固定回放治理，不代表真实来源、模型质量或公网历史覆盖已经验收。
