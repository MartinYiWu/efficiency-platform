# R09 有界补采 Planner 与研究子图任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R09 |
| 状态 | 进行中 |
| 依赖 | R08、C03 离线通过 |
| 范围 | Agent 侧缺口动作提案/验证、LangGraph 研究子图、无增益与停止优先级 |

## 不变量

1. 模型只提出 query、既有 gap/requirement/source 与受控 action_kind；程序验证来源准入、免费状态、角色、历史能力、原时间窗、预算和稳定指纹。
2. 任何动作不得扩大 Brief 时间、来源、requirement 或权限；SOURCE_COST_UNVERIFIED 只能切换到已准入免费源，OUTPUT_FORMAT_INVALID 只能内部重渲染。
3. action_id 是 intent revision + gap + source + 规范 query + cursor 的指纹；完成动作不重复，暂态 retry 属于同动作的 attempt，不创建新预算。
4. 模型输出 ResearchComplete/QUALITY_MET 不能绕过 QualityReport；没有 gap 时由程序直接 QUALITY_MET。
5. 唯一 LangGraph 子图包含 validate/plan/discover/acquire/normalize/filter/deduplicate/cluster/claims/quality/compose/verify/render/finalize，不创建第二 Runtime。
6. GraphState 只保存 Brief/Policy/Budget 版本、动作/文档/事件/Claim/Evidence/Artifact ID、质量摘要和控制计数，不保存正文、HTML、Prompt 或模型自由文本。
7. 初采不计 refill_round；补采最多两轮，连续两轮没有新增合格事件、Claim 或关闭 hard gap 时以 NO_GAIN 停止，已有证据 ID 不丢失。
8. 停止优先级固定为取消/致命/硬截止、输出质量达标、软截止/预算、NO_GAIN、ROUND_LIMIT、PLAN_EXHAUSTED。
9. COMPLETE 必须经过 compose→verify→render 且 output_verified；模型或 quality 节点不能直接宣布完成。
