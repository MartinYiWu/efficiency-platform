package com.aiep.aihub.web.customer;

import com.aiep.platformcore.api.ApiResponse;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice(assignableTypes = CustomerServiceController.class)
public class CustomerServiceExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiResponse<Void> invalid(IllegalArgumentException error) {
        return new ApiResponse<>(error.getMessage(), "请求不符合智能客服契约", null, null);
    }
    @ExceptionHandler(IllegalStateException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    public ApiResponse<Void> conflict(IllegalStateException error) {
        return new ApiResponse<>(error.getMessage(), "智能客服当前状态不允许该操作", null, null);
    }
}
