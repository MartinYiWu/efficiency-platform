# 运营交付展示迁移对照

仅修改 operation-delivery、operation-artifact、operation-next-action；Chat/API/SSE由主代理负责。

| 模块 | Vue 文件 | 保留内容 |
| --- | --- | --- |
| 聚合交付 | OperationDelivery.vue | mapDeliverableSet；v1/v2/v3分支；summary、degraded、全局/交付warning；按kind+platform最高version匹配artifact；复制成功/失败；v2后续动作 |
| 旧版 | OperationDelivery.vue | 标题、平台、Markdown正文、标签、格式说明、默认折叠来源、安全HTTPS链接、warning |
| V3 | OperationDelivery.vue | 标题、场景/平台、copy_text Markdown、精确复制copy_text、warning、artifact；与原版同样不把V3 content结构作为额外展示 |
| 热点榜 | RankedDigestView.vue | 连续编号、无重复列表标记、时间、来源数、可信度、核验、摘要、运营价值、角度、指标、只复制copyText |
| 平台稿 | PlatformContentView.vue | 正文、标签、格式说明、只复制copyText |
| 行动计划 | StructuredOperationView.vue | 目标、受众、阶段行动/指标、整体指标、前提、空数组未提供 |
| 诊断 | StructuredOperationView.vue | high/medium/low排序、标题、优先级、证据、建议、数据缺口 |
| 复盘 | StructuredOperationView.vue | 目标/结果/差距/原因/下一步五区块 |
| 证据 | SourceEvidencePanel.vue | 默认折叠、受控/非受控展开；采集窗、排序、候选/合并/保留/淘汰、已核验/冲突计数、来源名称与时间；仅无凭据HTTPS外链 |
| 成稿 | OperationArtifactActions.vue | API复制、微信预览noopener/noreferrer、Markdown下载、编码artifactId、失败提示 |
| 下一步 | OperationNextActions.vue | 六类白名单、来源只展开不提交；其余只提交label，不暴露intent_patch；无来源回调禁用 |

原CSS module保留布局，React Antd专有变量替换为全局--ui-*，适配Ant Design Vue主题；390像素区块缩排/单列规则保留。

验证：缺组件RED后实现。2文件11项测试通过，涵盖五类展示、v1/v2/v3、来源默认折叠与安全外链、copy_text、最高成稿版本、后续动作和复制失败。与知识联合复验6文件24项通过，知识轮询另2项通过。领域eslint与Prettier通过，vue-tsc领域无诊断。主代理负责全量门禁与三宽视觉验收。

共享MarkdownContent使用html:false，保证原始HTML不执行；当前会把原HTML转义为文本，而原React skipHtml会跳过HTML标记，此细节已通知主代理统一决定。
