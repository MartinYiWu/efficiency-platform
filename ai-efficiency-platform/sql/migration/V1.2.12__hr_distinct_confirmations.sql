-- 不同人确认绑定对称来源与双方事实版本，不得影响授权或自动合并。
CREATE TABLE ai_hr_distinct_confirmation (
 tenant_id VARCHAR(64) NOT NULL,left_candidate_id CHAR(36) NOT NULL,right_candidate_id CHAR(36) NOT NULL,
 left_fact_version BIGINT NOT NULL,right_fact_version BIGINT NOT NULL,
 actor_id VARCHAR(64) NOT NULL,reason_json LONGTEXT NOT NULL,created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(tenant_id,left_candidate_id,right_candidate_id,left_fact_version,right_fact_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
