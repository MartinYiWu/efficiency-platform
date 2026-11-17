package com.aiep.aihub.application.hr;

/** 招聘业务错误只公开稳定错误码和安全文案，避免日志输出简历正文。 */
public class HrBusinessException extends RuntimeException {
  private final String code;
  private final int status;

  public HrBusinessException(String code, String message, int status) {
    super(message);
    this.code = code;
    this.status = status;
  }

  public String code() {
    return code;
  }

  public int status() {
    return status;
  }
}
