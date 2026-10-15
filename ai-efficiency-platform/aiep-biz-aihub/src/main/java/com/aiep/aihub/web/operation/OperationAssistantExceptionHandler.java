package com.aiep.aihub.web.operation;

import com.aiep.aihub.application.operation.OperationAssistantException;
import com.aiep.platformai.agent.AgentTransportException;
import com.aiep.platformcore.api.ApiResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice(assignableTypes = OperationAssistantController.class)
public class OperationAssistantExceptionHandler {

    @ExceptionHandler(OperationAssistantException.class)
    public ResponseEntity<ApiResponse<Void>> handleBusiness(OperationAssistantException exception) {
        HttpStatus status = exception.getCode().endsWith("_NOT_FOUND") ? HttpStatus.NOT_FOUND : HttpStatus.BAD_REQUEST;
        return ResponseEntity.status(status)
                .body(new ApiResponse<>(exception.getCode(), exception.getMessage(), null, null));
    }

    @ExceptionHandler(AgentTransportException.class)
    public ResponseEntity<ApiResponse<Void>> handleAgent(AgentTransportException exception) {
        HttpStatus status = HttpStatus.resolve(exception.getStatusCode());
        if (status == null || !status.isError()) {
            status = HttpStatus.BAD_GATEWAY;
        }
        return ResponseEntity.status(status)
                .body(new ApiResponse<>(exception.getErrorCode(), exception.getMessage(), null, null));
    }
}
