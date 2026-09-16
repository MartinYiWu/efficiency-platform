# 本机 `.env` 结构校验修复报告

- 状态：已完成
- 范围：S1 本机 `.env` 配置结构测试
- 负责人：Agent
- 更新时间：2026-09-03

## 问题

`test_local_env_values_are_not_compared` 之前始终使用测试内的合成字典。本机 `.env` 即使缺少必需配置键，也不会进入结构校验；本机 `.env` 的中文注释校验虽已存在，但键结构校验没有覆盖实际文件。

## TDD 证据

先新增临时目录测试，写入缺少 `AGENT_LLM_MODEL_POOL_API_KEY` 的 `.env`，并调用本机配置校验测试。修复前实测：测试失败，提示 `AssertionError: AssertionError not raised`，证明旧逻辑没有检查实际 `.env`。

随后完成最小实现：当 `.env` 存在时，读取现有解析结果的 `keys()` 交给结构 helper；不存在时保留原有合成键集合路径。结构 helper 改为只接收键集合并检查必需键。

## 数据安全边界

本次不比较本机 `.env` 的任何值，不在失败消息中输出值，也不写入真实配置值或 Key。模板 `.env.example` 与路由 TOML 的严格值测试保持不变；本机文件的中文注释校验保持不变。

## 验证

```text
python -m unittest tests.config.test_llm_configuration_template.LlmConfigurationTemplateTest.test_present_local_env_missing_required_key_is_rejected
Ran 1 test in 0.005s
OK

python -m unittest tests.config.test_llm_configuration_template
Ran 11 tests in 0.010s
OK
```

未执行真实 Provider、网络或生产环境验证；本变更仅涉及测试治理与报告。

## 复审收紧

复审指出本机结构路径不应先构造包含值的字典。已新增 `read_env_keys`，只解析每行 `=` 左侧的键名；本机结构测试改为仅使用该键集合。新增回归测试会在本机结构路径调用 `read_env_values` 时直接失败，确保真实 `.env` 值不会被读取、比较或输出。

追加验证：

```text
python -m unittest tests.config.test_llm_configuration_template.LlmConfigurationTemplateTest.test_local_env_structure_does_not_read_values
Ran 1 test in 0.002s
OK

python -m unittest tests.config.test_llm_configuration_template
Ran 12 tests in 0.010s
OK
```
