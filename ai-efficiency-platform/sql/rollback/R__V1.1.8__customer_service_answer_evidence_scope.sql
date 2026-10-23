-- 人工受控回滚，未执行；日期：2026-10-23。需独立授权，停止相关编辑与发布并备份。
-- 仅删除本脚本创建且仍为未发布、未绑定的草稿。已发布或已绑定版本及旧版本均保留。
START TRANSACTION;
SELECT id,status FROM ai_prompt_version WHERE id IN ('30000000-0000-0000-0000-000000001009','30000000-0000-0000-0000-000000001010','30000000-0000-0000-0000-000000001014') FOR UPDATE;
DELETE p FROM ai_prompt_variable p JOIN ai_prompt_message_template m ON p.prompt_message_template_id=m.id JOIN ai_prompt_version v ON m.prompt_version_id=v.id WHERE v.id IN ('30000000-0000-0000-0000-000000001009','30000000-0000-0000-0000-000000001010','30000000-0000-0000-0000-000000001014') AND v.status='DRAFT' AND v.published_at IS NULL AND NOT EXISTS (SELECT 1 FROM ai_agent_version_prompt_binding b WHERE b.prompt_version_id=v.id);
DELETE m FROM ai_prompt_message_template m JOIN ai_prompt_version v ON m.prompt_version_id=v.id WHERE v.id IN ('30000000-0000-0000-0000-000000001009','30000000-0000-0000-0000-000000001010','30000000-0000-0000-0000-000000001014') AND v.status='DRAFT' AND v.published_at IS NULL AND NOT EXISTS (SELECT 1 FROM ai_agent_version_prompt_binding b WHERE b.prompt_version_id=v.id);
DELETE v FROM ai_prompt_version v WHERE v.id IN ('30000000-0000-0000-0000-000000001009','30000000-0000-0000-0000-000000001010','30000000-0000-0000-0000-000000001014') AND v.status='DRAFT' AND v.published_at IS NULL AND NOT EXISTS (SELECT 1 FROM ai_agent_version_prompt_binding b WHERE b.prompt_version_id=v.id);
COMMIT;
-- 再运行 verification；未发布未绑定草稿应消失，受保护版本应仍完整存在。
