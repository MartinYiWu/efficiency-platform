package com.aiep.platformcore.domain;

/** Request-scoped trace identifier holder for synchronous Java call paths. */
public final class TraceIdHolder {
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    private TraceIdHolder() {
    }

    public static void set(String traceId) {
        TRACE_ID.set(traceId);
    }

    public static String current() {
        return TRACE_ID.get();
    }

    public static void clear() {
        TRACE_ID.remove();
    }
}
