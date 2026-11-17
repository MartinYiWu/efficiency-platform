-- 仅保存服务端已确定的排序投影；详情仍取不可变加密结果，不重新调用模型。
ALTER TABLE ai_hr_matching_result
 ADD COLUMN total_score DECIMAL(5,1) NULL,
 ADD COLUMN evidence_coverage DECIMAL(5,1) NULL,
 ADD COLUMN band VARCHAR(32) NULL,
 ADD KEY ix_hr_result_rank(tenant_id,position_id,config_version,status,total_score,evidence_coverage,created_at);
