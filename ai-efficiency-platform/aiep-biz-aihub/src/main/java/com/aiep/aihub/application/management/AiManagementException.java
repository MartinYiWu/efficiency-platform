package com.aiep.aihub.application.management;

public class AiManagementException extends RuntimeException {
    private final String code;

    public AiManagementException(String code, String message) {
        super(message);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
