package com.aiep.knowledge.web;

import com.aiep.knowledge.application.KnowledgeException;
import com.aiep.platformcore.api.ApiResponse;
import com.aiep.platformfile.application.FileStorageException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice(assignableTypes = {
        KnowledgeBaseController.class, KnowledgeDocumentController.class, KnowledgeImportController.class})
public class KnowledgeExceptionHandler {
    @ExceptionHandler(KnowledgeException.class)
    public ResponseEntity<ApiResponse<Void>> handle(KnowledgeException exception) {
        HttpStatus status = exception.getCode().endsWith("_NOT_FOUND")
                ? HttpStatus.NOT_FOUND : HttpStatus.BAD_REQUEST;
        return ResponseEntity.status(status)
                .body(new ApiResponse<>(exception.getCode(), exception.getMessage(), null, null));
    }

    @ExceptionHandler(FileStorageException.class)
    public ResponseEntity<ApiResponse<Void>> handleFile(FileStorageException exception) {
        return ResponseEntity.badRequest()
                .body(new ApiResponse<>(exception.getErrorCode(), exception.getMessage(), null, null));
    }
}
