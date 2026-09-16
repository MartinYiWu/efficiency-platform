# Task 2 本机敏感配置安全校验证据

## 校验范围

- `AGENT_LLM_DEEPSEEK_API_KEY`
- `AGENT_LLM_MODEL_POOL_BASE_URL`
- `AGENT_LLM_MODEL_POOL_API_KEY`

## 校验结果

- `AGENT_LLM_DEEPSEEK_API_KEY`：空值
- `AGENT_LLM_MODEL_POOL_BASE_URL`：空值
- `AGENT_LLM_MODEL_POOL_API_KEY`：空值

## 校验说明

- 本证据仅记录“变量名 + 空值/已填写状态”，不记录任何变量值。
- 运行时若任一目标变量非空，校验命令应以非零状态退出。
