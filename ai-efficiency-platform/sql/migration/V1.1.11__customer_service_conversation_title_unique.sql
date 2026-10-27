-- 范围：开发库 ai_efficiency_platform 的智能客服会话标题唯一约束。
-- 前置：执行对应只读预检；备份并为已授权的历史重名追加序号，确认重名组数为零。
-- 空标题允许多个；已删除会话释放名称；未删除归档会话仍参与唯一约束。
ALTER TABLE ai_customer_service_conversation
    ADD COLUMN title_unique_key VARCHAR(255)
        GENERATED ALWAYS AS (
            CASE
                WHEN status <> 'DELETED' AND CHAR_LENGTH(TRIM(COALESCE(title, ''))) > 0
                THEN LOWER(TRIM(title))
                ELSE NULL
            END
        ) VIRTUAL,
    ADD UNIQUE INDEX uk_ai_cs_conversation_title (tenant_id, user_id, title_unique_key);
