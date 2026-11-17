# 最小生成结算与剩余两类业务验收记录

状态：最小生成及混合/通用业务 API 验收通过；本轮浏览器刷新核验未完成。负责人：本轮执行代理。更新时间：2026-11-04（北京时间）。适用范围：现有 Agent Provider、已发布客服业务及费用治理。

## 本轮结果

| 验收项 | 结果 | 耗时 | 付费 HTTP | 本地费率估算 |
|---|---|---:|---:|---:|
| 最小 Flash 生成与结算 | 成功；完整 EOF、gzip、推理用量可证实，settled | 744ms | 1 | 0.000140元 |
| 混合题 | SUCCEEDED、MIXED、617字符、6条引用，SSE完成、消息读回一致 | 37257ms | 18 | 0.106888元 |
| 通用题 | SUCCEEDED、GENERAL_ADVICE、498字符、无公司引用，SSE完成、消息读回一致 | 5185ms | 2 | 0.007490元 |

本轮共 **21 次付费 HTTP，全部 settled，新增 unknown=0，费率估算 0.114518 元**。最小验证预留上限仅 0.02 元；业务上限为 20 元/60 次，没有为了触达额度增加请求。

混合题沿用昨日公司知识用例组合通用建议要求，通用题沿用昨日方案中的固定通用输入；各只提交一次，没有为了凑通过率替换问题重测。混合题同时检测到公司事实与通用建议标签；此项是模式、引用及标签验证，不等于人工逐句事实审核。

昨日公司知识题的业务成功记录继续有效，未额外付费重测公司题。本轮不能称“修复后三类问题全部重新执行通过”，也未执行18题全量回归。

## 授权与费用控制

用户在收到“先一次真实生成结算验证，再条件执行混合/通用两题，原累计30元/90次不清零”方案后，明确要求制定计划并实施。本轮使用新的有限授权记录，不恢复旧停止授权。

执行前重新 GET 核实官方公开价格并保存页面：

- https://api-docs.deepseek.com/zh-cn/quick_start/pricing ：旧 `deepseek-v4-flash` 仍可调用并按 Flash 计费；高峰每百万输入2元、缓存输入0.04元、输出8元。
- https://help.aliyun.com/zh/model-studio/model-pricing ：北京 `text-embedding-v4` 与 `qwen3-rerank` 文本输入0.5元/百万；配置的 Embedding 主机为 `dashscope.aliyuncs.com`，模型及1024维未变。

最小验证输入上界8192、输出/推理上界256，最坏0.018432元，因此授权/预留仅0.02元、1次HTTP，10分钟绝对期限；Provider及HTTP底层均关闭重试，单次最多120秒。真实请求仅经既有 DeepSeekStreamingProvider → PaidHttpTransport → 固定用户 SQLite 总账，未绕过守卫。此项为 Provider 验证，不冒充前端业务验收。

最小验证通过且持久停止后，再根据历史22次/3.106392元有效占用，为两题授权最多60次/20元、30分钟，每题30次/10元/10分钟，单并发；Token总额也扣历史有效占用。只允许Flash、Embedding、rerank；原累计30元/90次仍是总上限。

两个执行脚本都有执行一次锁；业务脚本监测 unknown、金额溢出、429及停止状态，立即停止预算并取消尚在执行的本次Run。每题提交前、题后和最终再次检查；最终必须全部settled、在途0才通过。402/429/额度耗尽等边界仅通过离线 Mock 验证，未真实触达消费上限。

## 真实业务与服务

当前活跃 release 仍是 `d73e7639-69b0-400b-a6fa-0d8c892e4d87`。没有修改前端、Java、业务 Prompt、发布策略、模型配置或共享数据库Schema。业务阶段直接使用已运行的Java8080客服接口→Agent8090→统一费用守卫，未直接请求模型厂商。

Agent 的守卫在创建时固定预算ID，因此仅重启本会话Agent加载新的业务授权：launcher199468、监听239672，父子关系已核对。用户Java仍为PID241736，未重启。结束后Java健康UP、Agent readiness为ok。

两题都验证了模式、非空回答、引用要求、公开SSE终态及递增序号、持久消息读回；结束后再独立GET两次，消息完全一致。没有重发问题，没有保存问题、Prompt或回答正文。

本轮20次业务HTTP为Flash16次、Embedding1次、rerank3次，全部HTTP200并settled；加最小验证Flash1次，本轮21次全部结算。本轮真实证明当前生成链路能够正确结算，但不据此追溯推断昨日14次未知用量的唯一原因。

## 本轮离线验证与审查

- 实际执行前，诊断/HTTP守卫/队列定向预检49项通过。
- 默认离线执行器使用Fake账本与MockTransport验证完整/缺失用量、最多一次HTTP；不读取真实凭据或请求模型。
- 执行器完整控制流程2项、业务监视/题间竞态5项，最终合并新鲜执行：`7 passed in 1.60s`。
- 相关验收脚本Ruff及compileall通过；本轮无生产源码变更，不重复上一轮234项回归。
- 独立只读审查发现题间停止结果可能被忽略的P2，已在真实发题前修复；竞态测试确认只提交mixed、不提交general，复审无新增重要问题。审查没有真实服务访问。

最终离线命令：

```powershell
efficiency-platform-agent/.venv/Scripts/python.exe -m pytest .local-acceptance/guarded-single-smoke-20261104/test_executor.py .local-acceptance/mixed-general-live-20261104/test_watchdog.py -q
```

## 累计总账与停止

当前固定总账共4个授权记录，均为 `operator_stop`，在途0：

- 累计42次付费HTTP；累计保守计账 **3.220770元**。
- 已结算费率估算 **0.120770元**；历史未知保留 **3.100000元**。
- 本轮没有新增未知保留；历史unknown未退款、未清零、未回填结算。

以上为本地已核实费率的估算与未知预留，不是已经核对的供应商实际账单。当前没有可用付费授权，不自动续额。

## 尚未完成的浏览器项

原前端5192预览已不运行。启动本地dist预览的操作被自动审批拒绝，工具仅返回 `blocked by policy`，没有更详细原因；没有换方式绕过启动。已运行Java的根路径也不提供前端页面。

因此本轮完成的是业务API/SSE/消息读回验收，**未完成两题在Vue页面中的真实浏览器刷新核验**，不能将消息API读回等同于浏览器验收。此前Vue离线/浏览器/UI风格验收记录保留，不以本轮替代。此剩余项可在本地预览恢复后只读GET验证，无需再次生成或付费调用。

## 证据

- [最小验证](smoke-result.json)
- [两题汇总](two-case-summary.json)
- [累计总账与健康](final-audit.json)
- [独立消息只读复验](readonly-message-verification.json)
- [业务结算脱敏诊断](business-settlement-diagnostics.log)
- [执行器离线测试](offline-executor-tests.log)
- [进程核对](process-verification.json)
- [最小验证授权来源](smoke-authorization.json)
- [两题有限授权来源](business-authorization.json)
- [实施计划](../../superpowers/plans/2026-11-04-最小真实结算验证与剩余业务验收-实施计划.md)

本地完整治理证据分别位于 `.local-acceptance/guarded-single-smoke-20261104/` 和 `.local-acceptance/mixed-general-live-20261104/`，原始账本未复制；未发布服务原始日志或业务正文。
