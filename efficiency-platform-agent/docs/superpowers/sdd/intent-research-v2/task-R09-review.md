# R09 规格与质量审查

## 审查过程

1. 模型权限轮：确认模型只能提出动作，不能通过空计划或 stop_reason 宣布 `RESEARCH_COMPLETE`/`QUALITY_MET`。
2. 范围轮：反例覆盖扩大时间窗、未知 gap、错误 requirement 与未知 source，均失败关闭。
3. 来源轮：重验 admitted、verified_free、primary 角色和 history 能力；内部重渲染只能使用 `internal.renderer`。
4. 指纹轮：规范 query 的空白与大小写后生成稳定指纹；篡改 action_id 被拒绝，完成动作不重跑。
5. 预算轮：accepted 动作数不能超过剩余 call 预算；暂态 retry 不通过制造新 action 绕过历史。
6. 优先级轮：程序对事实/时间阻断、required facet、数量、热度和格式动作确定性排序，不信任模型顺序。
7. GraphState 轮：检查 TypedDict 字段，正文、HTML、Prompt 和模型输出未进入检查点。
8. 流程轮：完整路径必须依次经过 compose、verify、render 才能 `COMPLETE`。
9. 无增益轮：初采后两轮同一事件/Claim/gap 触发 `NO_GAIN`，refill 和 no_gain 计数正确，已有证据 ID 保留。
10. 终止轮：取消和硬截止在 validate 后立即 finalize；终态优先级与 COMPLETE/NO_MATCHES/PARTIAL/FAILED/NOT_EVALUATED 区分正确。
11. Prompt 轮：唯一 ContextBuilder、USER_UNTRUSTED、范围不扩张、免费来源、受控动作映射和模型不得宣布完成均在模板中冻结。
12. 回归轮：执行 19 项定向、1416 项全量、全仓 Ruff、262 源码 mypy、compileall 与 62 项治理/架构测试。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 缺口到允许动作映射 | 通过 |
| 时间/requirement/source 范围不扩张 | 通过 |
| 免费与来源角色门禁 | 通过 |
| 稳定 action 指纹与历史去重 | 通过 |
| 事实阻断优先级 | 通过 |
| 唯一 LangGraph Research 子图 | 通过 |
| GraphState 仅 ID/版本/计数 | 通过 |
| 两轮无增益停止并保留证据 | 通过 |
| 取消/截止/预算/轮次终态优先级 | 通过 |
| COMPLETE 必须输出核验 | 通过 |
| replan Prompt 治理 | 通过 |
| 全量离线回归与静态门禁 | 通过 |
| 真实组合根、模型与来源调用 | 未执行，按计划保持关闭 |

## 结论

**PASS。** R09 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 实现问题；历史全仓格式漂移和迁移后虚拟环境启动器已明确记录，不影响本阶段代码规则、类型、编译及离线行为结论。该结论不代表真实模型、来源、持久化或 Supervisor 集成已经验收。
