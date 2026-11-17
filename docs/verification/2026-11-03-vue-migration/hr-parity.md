# HR Vue 迁移功能等价核验

核验日期：2026-11-03。原工程只读；所有用例离线，无真实服务或付费调用。

## 原测试逐文件映射

下表所有原用例按原测试名保留于 `ai-efficiency-platform-ui-vue/src/pages/hr-assistant/hr.parity.test.ts`。仅替换 Vue 渲染/事件与 Vue Router 内存路由；完成态通过真实 `router.push("/?state=completed")` 进入，无 window 后门。Ant Design Vue 分页的页容量显示按其 DOM 断言。

| 原测试文件（原HR目录下） | 原用例 / 新文件行 |
| --- | --- |
| `interviews/InterviewGeneratePage.test.tsx` | `renders the interview question configuration and lets the user adjust its scope` → `hr.parity.test.ts:21` |
| `interviews/InterviewGuidePreviewPage.test.tsx` | `keeps AI score fields locked out of the interview guide and records sensitive exports` → `hr.parity.test.ts:43` |
| `interviews/InterviewQuestionSetPage.test.tsx` | `renders traceable interview questions and supports expanding a question` → `hr.parity.test.ts:54` |
| `matching/FilteredResumesPage.test.tsx` | `renders retained filtered resumes and an accountable manual-release entry` → `hr.parity.test.ts:67`<br>`requires a documented reason before an allowed hard condition can be released` → `hr.parity.test.ts:75` |
| `matching/MatchDetailPage.test.tsx` | `renders traceable evidence and a guarded contact reveal action` → `hr.parity.test.ts:94` |
| `matching/MatchResultsPage.test.tsx` | `renders match results and keeps AI guidance distinct from a hiring decision` → `hr.parity.test.ts:104`<br>`opens the weight recalculation dialog with a valid total and impact preview` → `hr.parity.test.ts:114`<br>`paginates matching rows instead of rendering static pagination text` → `hr.parity.test.ts:125` |
| `positions/PositionListPage.test.tsx` | `uses the native table pagination with the designed total and page size` → `hr.parity.test.ts:138` |
| `resumes/ResumeCorrectionPage.test.tsx` | `renders the low-confidence correction workspace with guarded continuation` → `hr.parity.test.ts:150` |
| `resumes/ResumeProgressPage.test.tsx` | `renders parsing progress with failure isolation and confirmation actions` → `hr.parity.test.ts:164`<br>`renders the specified completion state when the batch is complete` → `hr.parity.test.ts:174` |
| `resumes/ResumeUploadPage.test.tsx` | `keeps the upload workspace and its primary action as named landmarks` → `hr.parity.test.ts:185` |
| `settings/AuditPage.test.tsx` | `shows traceable sensitive actions and expands their details` → `hr.parity.test.ts:196`<br>`paginates audit rows with a distinct second page` → `hr.parity.test.ts:203` |
| `settings/SkillSynonymPage.test.tsx` | `opens a governed skill entry editor and keeps ambiguous aliases visible` → `hr.parity.test.ts:214` |
| `talent/CandidateProfilePage.test.tsx` | `renders the candidate profile with masked contacts and structured profile tab` → `hr.parity.test.ts:224` |
| `talent/TalentSearchPage.test.tsx` | `filters the talent library without exposing hiring decisions` → `hr.parity.test.ts:234`<br>`paginates candidate results with a distinct second page` → `hr.parity.test.ts:243` |
| `workbench/HrWorkbenchPage.test.tsx` | `renders the five HR workbench todo categories and direct action` → `hr.parity.test.ts:254` |

## 额外两组覆盖

`hr.pages.test.ts`：25个页面逐一真实挂载/卸载，模块入口传入title/description/nextPage。该组仅证明页面可装配，不当作交互等价证据。

`hr.behavior.test.ts`：

- `岗位查询在应用后筛选，重置恢复数据`（第29行）。
- `联系方式确认展示后30秒恢复脱敏`（第39行）。
- `基础信息缺失时禁止下一步`（第48行）。
- `权重合计不等于100时禁止预演`（第52行）。
- `硬性条件支持删除和添加`（第59行）。
- `HR对话发送后保留内容并清空输入`（第67行）。
- `软性要求可添加和删除核心技能`（第74行）。
- `人工放行必须填写理由`（第81行）。
- `上传移除文件更新数量`（第88行）。

## 实现独立复核

- 原HR页面没有Ant Form或Form.useForm；本模块未伪造表单实例，也不涉及React Form状态迁移。基础字段、条件与权重均由Vue ref维护，派生校验在render读取.value；原演示中未接线的按钮/筛选未擅自添加后台功能。
- 唯一原useEffect位于CandidateProfilePage。迁移为setup中watch(revealed)，onCleanup清除30秒计时器，卸载由Vue自动停止watch并清理；额外用例验证确认查看后30秒恢复脱敏。
- Input/TextArea change事件读取event.target.value；Checkbox/Radio读取target.checked/value；Select/InputNumber/Slider/Switch接收直接值；Tabs/Segmented/Pagination按Vue控件change事件更新ref。原生文件input由input事件接入，并保留ref、文件大小/格式校验、拖放及移除。
- 岗位查询保留draft/applied双阶段，查询应用后才筛选，重置恢复；人才与匹配分页、同义词搜索、审计展开/分页均保留。岗位列表额外用例验证输入不立即应用、查询生效、重置恢复。
- hrVnodes仅构建Vue VNode与Ant Design Vue slots，不含React状态/生命周期兼容运行时。Table render映射customRender；Tabs/Collapse/Descriptions items映射Vue子组件；Dropdown映射overlay；Alert title映射message；icon/footer等VNode转slot。纯两字中文Button显式aria-label避免Ant自动插空格改变可访问名。
- 静态限制：helper的input为object，Vue h同样允许宽泛VNode props；它不提供每种Ant组件props的完整泛型验证，业务回调/模型仍有明确类型且严格TS无any/ignore。本轮逐项核对时还发现Slider的React tooltip.open配置在Vue应为tooltipOpen，已直接修正岗位软性要求页，恢复关闭浮动提示的原行为。此边界依靠行为测试与浏览器流程补充验证，不能把strict通过解释为所有控件props都得到编译器完整验证。

## 已执行证据与边界

- 2026-11-03 12:12完整HR执行：3文件53用例全部通过，214.06秒；其中25挂载+21原用例+7新增行为。之后增补岗位查询、30秒脱敏两条定向行为（本轮单独执行2 passed / 7 skipped，33.93秒），当前清单合计55。
- HR生产严格类型检查无报错；ESLint 0 errors，55条one-component-per-file警告来自同页内聚的小型Vue展示组件，未关闭规则。
- 根代理集成浏览器验收负责最终1440/1024/390视觉与完整路由。独立读取.e2e-retest.log时所见失败均为客服证据弹窗，不属于HR；不能据此宣称HR整体浏览器全绿。

