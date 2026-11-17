# HR Agent 离线资产候选

状态：草稿，未发布。负责人：当前实施执行者。更新时间：2026-11-11。范围：HR Agent生产装配、离线Prompt与输出契约候选。

`hr-prompt-contracts-draft.json` 包含当前输入Schema和五项模型能力的Prompt及输出Schema。抽取与取消属于CPU/控制动作，不需要模型Prompt。该文件不会被运行时扫描、导入或自动发布，也没有模型ID、价目授权、数据库ID或Release映射。发布前由管理员核对实际模型、上下文、价格上界与授权，通过现有Prompt治理流程发布；缺配置的实际请求会在模型HTTP前失败。

本机 `.env` 显式配置键：

```dotenv
AGENT_HR_ENABLED=false
AGENT_HR_INTERNAL_SECRET=
AGENT_HR_OCR_DETECTION_MODEL_DIR=
AGENT_HR_OCR_RECOGNITION_MODEL_DIR=
```

默认关闭。启用时内部服务凭证至少32字符，且仅以SecretStr持有，不记录正文。OCR两个目录成对配置，必须已有本地推理权重与已安装依赖；缺依赖保持格式不可用，不下载、不安装。已有DeepSeek模型配置形成精确逻辑模型映射；发布策略中的模型未在映射中登记时拒绝，不自动降级或换模型。启用配置不构成付费预算授权，所有实际HTTP仍经当前用户固定SQLite总账。

生产组合根把PromptAssembler、受守卫Provider映射、固定总账和离线OCR装入HR端点；Fake默认不开启HR，且不能以缺失已发布Prompt存储的Fake组合根冒充真实HR装配。未执行真实模型、真实数据库发布或真实OCR质量验收。
