package com.aiep.aihub.application.operation;

public record OperationActor(String tenantId, String userId) {
    public static OperationActor developmentActor() {
        return new OperationActor("dev", "1");
    }
}
