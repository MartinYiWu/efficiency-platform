ALTER TABLE ai_agent_release_snapshot
    DROP INDEX uk_ai_agent_release_snapshot_checksum,
    ADD KEY idx_ai_agent_release_snapshot_checksum (checksum);
