package com.aiep.platformai.agent;

/** All business endpoints exposed by efficiency-platform-agent. */
public final class AgentEndpoints {
    public static final String TEXT_GENERATE = "/text/generate";
    public static final String CHAT_STREAM = "/chat/stream";
    public static final String SKILL_EXECUTE = "/skill/execute";
    public static final String KB_QA = "/kb/qa";
    public static final String KB_INGEST = "/kb/ingest";
    public static final String TASK_QUERY = "/task/{task_id}";
    public static final String KB_VECTORS = "/kb/vectors";

    private AgentEndpoints() {
    }
}
