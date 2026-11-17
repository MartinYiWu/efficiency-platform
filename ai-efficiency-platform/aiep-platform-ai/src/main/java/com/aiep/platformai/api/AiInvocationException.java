package com.aiep.platformai.api;

/** 跨模块安全AI错误，只有稳定错误码/状态和安全文案，不携带厂商异常正文。 */
public final class AiInvocationException extends RuntimeException {
    private final int status;private final String code;
    public AiInvocationException(int status,String code,String message){super(message);this.status=status;this.code=code;}
    public int status(){return status;}
    public String code(){return code;}
}
