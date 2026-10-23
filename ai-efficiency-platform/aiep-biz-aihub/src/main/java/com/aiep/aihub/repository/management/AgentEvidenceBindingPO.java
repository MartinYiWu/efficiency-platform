package com.aiep.aihub.repository.management;

/** 管理页只读绑定投影；Release 行从冻结快照读取，当前索引只供提示，不用于运行时切换。 */
public record AgentEvidenceBindingPO(
        String sourceType, String sourceId, String largeModelName, Integer maxInputTokens,
        String knowledgeBaseId, String boundIndexReleaseId, String currentIndexReleaseId) { }
