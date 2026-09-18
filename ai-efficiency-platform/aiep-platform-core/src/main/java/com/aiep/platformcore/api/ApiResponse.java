package com.aiep.platformcore.api;

/** Standard HTTP response envelope for platform APIs. */
public record ApiResponse<T>(String code, String message, T data, String traceId) {

    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>("SUCCESS", "success", data, null);
    }

    public ApiResponse<T> withTraceId(String traceId) {
        return new ApiResponse<>(code, message, data, traceId);
    }
}
