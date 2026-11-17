# 组件测试查询性能复核

本轮全量覆盖率中先后出现客服标题一条、人事弹层两条超时。已有浏览器完整事务通过，测试失败为超时而非业务断言失败。未据此修改产品逻辑或调高超时。

- 客服标题：仅将导航/输入区/重命名弹窗查询限定到实际区域并复用按钮；原断言、真实Antd、重名409和流信号不取消语义全部保留。独立coverage9/9通过，目标10.135s，文件测试耗时45.45→35.44s，覆盖率不变。
- 人事放行：同样限定弹窗并复用确认按钮；19.601→5.389s，原disabled→填理由→enabled门禁保留。
- 人事权重：弹窗预计变化/总计/历史说明/确认按钮查询局部化；26.607→14.439s，原35s超时不变。
- 两个人事用例独立coverage前后2/2通过，32个文件coverage-final.json完全一致。该定向测试的19个非目标用例未执行，不冒充完整文件全部通过。

独立优化证据位于本机root .local-acceptance/hr-query-before*、hr-query-after*及UI .local-acceptance/customer-title-before、customer-title-after。最终完整门禁串行执行，避免与浏览器/构建抢资源；结果以final-verification.md为准。
