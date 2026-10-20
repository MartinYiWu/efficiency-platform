package com.aiep.platformfile.application;

public final class FileStorageException extends RuntimeException {
    private final String errorCode;

    public FileStorageException(String errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    public FileStorageException(String errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
