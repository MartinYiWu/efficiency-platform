package com.aiep.knowledge.application;

public final class KnowledgeException extends RuntimeException {
    private final String code;

    public KnowledgeException(String code, String message) {
        super(message);
        this.code = code;
    }

    public KnowledgeException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
