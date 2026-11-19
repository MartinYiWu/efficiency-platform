package com.aiep.knowledge.api;

/** 知识生命周期的refs-only撤销事件；不包含文档正文/凭据。 */
public record KnowledgeSourceEvent(String eventId,String tenantId,String knowledgeBaseId,String reason) { }
