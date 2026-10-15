package com.aiep.platformai.agent;

public final class AgentTransportException extends RuntimeException {
    private final int statusCode;
    private final String errorCode;

    public AgentTransportException(int statusCode, String errorCode, String message) {
        super(message);
        this.statusCode = statusCode;
        this.errorCode = errorCode;
    }

    public int getStatusCode() {
        return statusCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
