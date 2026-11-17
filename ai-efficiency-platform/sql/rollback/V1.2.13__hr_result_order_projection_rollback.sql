-- 回滚会移除已确定排序投影；执行前确认所有应用版本已回退。
ALTER TABLE ai_hr_matching_result DROP KEY ix_hr_result_rank,DROP COLUMN total_score,DROP COLUMN evidence_coverage,DROP COLUMN band;
