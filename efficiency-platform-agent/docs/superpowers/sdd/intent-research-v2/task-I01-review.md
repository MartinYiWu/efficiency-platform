# I01 规格与质量审查

## 审查范围

独立审查覆盖 I01 计划、任务简报、Patch/时间契约变化、Validator、测试与报告。项目规范禁止 Git，因此以当前文件、反例和新鲜测试输出进行只读审查；未调用网络、模型、工具执行或数据库。

## 审查过程

审查采用四轮反例驱动：

1. 首轮发现 tenant/budget 可藏入 Goal parameters，以及 Patch 值与 Frame 类型不同构、`target_platforms remove` 不可表达。
2. 第二轮发现嵌套来源/输出 item 无界，以及 bool/int/string 可被 Pydantic 宽松转换。
3. 第三轮发现叶级字段上限宽于聚合 Frame，可能使 Reducer 无法构造合法状态。
4. 修复后重新逐字段攻击来源授权、Unicode span、类型、长度、集合基数、嵌套参数和 coercion，未再发现问题。

以上问题均在本任务内修复并增加回归，不作为遗留项降级处理。

## 最终确认

| 检查项 | 结果 |
|---|---|
| raw extra、嵌套 tenant/budget 参数注入 | 通过；参数名只接受服务端白名单 |
| set/clear、append/remove 固定字段判别 | 通过；无任意 JSONPath |
| Patch 与 Frame 类型/长度/集合基数同构 | 通过 |
| `target_platforms remove` 表达“不要公众号” | 通过 |
| strict revision/span/时间数字及布尔 | 通过 |
| 网页/不可见消息、伪造 span、不可见 inherited revision | 通过 |
| Unicode、clear/null/未提及、混合 provenance | 通过 |
| 成功/错误结果与稳定外部错误码互斥 | 通过 |
| I01 范围记录包含 `temporal_v2.py` | 通过 |

`base_revision` 与当前状态冲突按计划由 I02 Reducer/CAS 处理，不是 I01 遗漏。

## 新鲜验证

```text
I01 定向 + 契约 + 架构：112 passed, 124 subtests passed
全量回归：1088 passed, 275 subtests passed, 2 existing dependency warnings
Ruff：All checks passed
mypy：Success, 3 source files
```

## 结论

**PASS。** 未发现 Critical、Important 或 Minor 问题。I01 可标记为“离线通过”；该结论不代表 I02 Reducer、真实模型、数据库或端到端接口已完成。
