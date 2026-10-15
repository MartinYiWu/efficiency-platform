package com.aiep.aihub.application.operation;

public final class OperationAssistantException extends RuntimeException {
    private final String code;

    public OperationAssistantException(String code, String message) {
        super(message);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
