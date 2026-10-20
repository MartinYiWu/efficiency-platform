package com.aiep.aihub.web.management;

import com.aiep.aihub.application.management.AiManagementException;
import com.aiep.platformcore.api.ApiResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice(basePackages = "com.aiep.aihub.web.management")
public class AiManagementExceptionHandler {
    @ExceptionHandler(AiManagementException.class)
    public ResponseEntity<ApiResponse<Void>> handle(AiManagementException exception) {
        HttpStatus status = exception.getCode().endsWith("NOT_FOUND")
                ? HttpStatus.NOT_FOUND : HttpStatus.BAD_REQUEST;
        return ResponseEntity.status(status)
                .body(new ApiResponse<>(exception.getCode(), exception.getMessage(), null, null));
    }
}
