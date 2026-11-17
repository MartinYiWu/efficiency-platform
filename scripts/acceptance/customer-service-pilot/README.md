# 智能客服小范围试用证据工具

当前实际员工人数未确认，已确认参与人数为 **0**。开发验收只标记 `developer`，不证明员工试用完成。未经授权不联系员工、不提交员工反馈、不收集未知个人数据。

在仓库根目录执行，使用 Agent 项目已有 Python/httpx 环境。工具不调用模型，不执行 SSE，不修改生产代码或 DDL。默认采集只 GET；只有 `import --confirm-write` 可以写 API，并且只创建 `pilot-` 前缀的新独立评测集。任何输出都拒绝覆盖。

## 1. 约定范围并采集

由负责人明确授权试用人员、问题范围与 Run/反馈 ID；不按日期抓取全部 Run。页面反馈 API 没有 Run 过滤器，因此指定反馈时逐页读取，在内存丢弃未指定记录，落盘只含精确范围。未指定反馈 ID 时不抓反馈，也剔除 replay 内嵌反馈。指定反馈缺失或 Run 归属不符会失败。

```powershell
uv run --project efficiency-platform-agent python scripts/acceptance/customer-service-pilot/pilot.py collect --run-id RUN_ID --feedback-id FEEDBACK_ID --cohort developer --out .local-acceptance/stability-pilot-20261030/pilot-raw.json
uv run --project efficiency-platform-agent python scripts/acceptance/customer-service-pilot/pilot.py review --input .local-acceptance/stability-pilot-20261030/pilot-raw.json --out .local-acceptance/stability-pilot-20261030/pilot-review.json
```

重复 `--run-id` / `--feedback-id` 可选多个，自动去重。真实员工获得授权并实际参与后才使用 `--cohort employee --confirmed-employee-count N`；人数由负责人确认，工具不能验证人员身份。可用全局 `--base-url` 指定 Java 服务；可选 `PILOT_AUTHORIZATION` 环境变量，不在命令中填凭据。

原始问题、答案、引用、反馈可能含个人信息，全部文件只允许写入被 Git 忽略的 `.local-acceptance`。review 输出采用字段白名单，排除正文、评论、用户/租户/会话身份与内部 payload；仍含内部 Run/版本标识，仅供内部审阅。原始文件不得提交、转发或直接粘贴报告；按团队既有保留制度人工管理。

冻结来源含 agentReleaseId、documentVersionId、indexReleaseId、chunkId、contentHash。历史 Run 开始/结束时间仅代表已持久化总耗时；`ttftMs=null`，不能用历史回放事件间隔补造首正文耗时。若需首正文指标，由获授权的实时 SSE 验收另行记录并注明测量来源。

## 2. 人工审阅与导出

审阅人核对原文与冻结引用，将每个 Run 的问题分为事实错误、引用错误、遗漏、延迟；同一 Run 的多个问题合并标注，不能直接根据差评自动断定错误。`review` 生成四类待审清单，不做自动事实裁判。

手工在忽略目录创建 `pilot-annotations.json`，数组元素示例（所有文字须人工脱敏；reviewer 使用内部代号）：

```json
[
  {
    "runId": "RUN_ID",
    "category": "事实错误",
    "reviewer": "reviewer-01",
    "approved": true,
    "question": "人工脱敏且可独立复现的问题",
    "expectedAnswerMode": "COMPANY_KNOWLEDGE",
    "expectedFacts": ["经原始文档核对的期望事实"],
    "prohibitedFacts": [],
    "expectedDocumentVersionIds": ["FROZEN_DOCUMENT_VERSION_ID"],
    "minCitationCount": 1
  }
]
```

```powershell
uv run --project efficiency-platform-agent python scripts/acceptance/customer-service-pilot/pilot.py export --input .local-acceptance/stability-pilot-20261030/pilot-raw.json --annotations .local-acceptance/stability-pilot-20261030/pilot-annotations.json --out .local-acceptance/stability-pilot-20261030/pilot-export.json
```

export 要求人工批准、有效分类、冻结来源、非空期望事实；保留 Run/反馈 ID、审阅代号、来源哈希和冻结版本。仅导出人工提供的脱敏问题和事实，不自动把原文当评测题。期望版本必须来自采集证据；目标为通用建议或其他无需引用的回答时，可留空版本列表并设置 minCitationCount=0。若原运行遗漏引用，但目标是有公司依据的回答，仍应要求至少1条引用；不能因原运行无引用而降低目标标准，也不能假造原运行的文档版本。模式仅支持当前服务契约的 COMPANY_KNOWLEDGE、MIXED、GENERAL_ADVICE、INSUFFICIENT_EVIDENCE。

可选 `reviewNote` 记录人工裁定理由，`sourceDocuments` 记录另外人工核验原文的名称和 SHA256；它们随导出来源保留，不冒充该 Run 已返回引用。export 与 import 都校验非空白问题/事实、字符串数组及非负整数引用数，损坏包在任何写入前拒绝。

## 3. 显式写入新独立集

先审阅导出文件，并获取业务负责人写入授权后再执行；本流程准备本身不代表已获得任意外部写入授权。

```powershell
uv run --project efficiency-platform-agent python scripts/acceptance/customer-service-pilot/pilot.py import --input .local-acceptance/stability-pilot-20261030/pilot-export.json --dataset-name pilot-approved-batch-001 --confirm-write --out .local-acceptance/stability-pilot-20261030/pilot-import.json
```

不接受已有 dataset ID，不修改现有集、不自动启动模型评测。导入是“创建新集→导入题目”两次调用；若第二步失败，新集会保留待人工检查，工具不会删除或自动重试。执行前应保证输出目录可写并避免重复命令。评测集 description 保存来源哈希，case tags 保存 Run/发布版本，完整来源保留在本地导出包。

## 验证

```powershell
uv run --project efficiency-platform-agent python -m unittest discover -s scripts/acceptance/customer-service-pilot -p test_pilot.py
```

覆盖分页、精确 ID 与去重、反馈归属、白名单脱敏、历史 TTFT 缺失、人工批准及冻结来源、忽略目录边界、显式写入及新独立集。真实 API 验收须另外保存精确 Run/反馈、命令和结果；本地单元测试不是员工反馈。
