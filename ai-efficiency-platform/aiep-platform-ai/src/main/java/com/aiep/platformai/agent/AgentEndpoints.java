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
    public static final String CONVERSATION_MESSAGES = "/v1/conversations/{conversation_id}/messages";
    public static final String RUN_EVENTS = "/v1/runs/{run_id}/events";
    public static final String RUN_CANCEL = "/v1/runs/{run_id}/cancel";
    public static final String CUSTOMER_SERVICE_RELEASE =
            "/internal/v1/customer-service/releases/{release_id}";
    public static final String CUSTOMER_SERVICE_INGEST_JOBS =
            "/internal/v1/customer-service/ingest-jobs";
    public static final String CUSTOMER_SERVICE_INGEST_JOB =
            "/internal/v1/customer-service/ingest-jobs/{task_id}";
    public static final String CUSTOMER_SERVICE_INDEX_VERIFY =
            "/internal/v1/customer-service/index-releases/{release_id}/verify";
    public static final String CUSTOMER_SERVICE_MESSAGES =
            "/v1/customer-service/conversations/{conversation_id}/messages";
    public static final String CUSTOMER_SERVICE_RUN_EVENTS =
            "/v1/customer-service/runs/{run_id}/events";
    public static final String CUSTOMER_SERVICE_RUN_CANCEL =
            "/v1/customer-service/runs/{run_id}/cancel";
    public static final String CUSTOMER_SERVICE_RAG_DEBUG =
            "/internal/v1/customer-service/rag-debug-runs";

    private AgentEndpoints() {
    }
}
