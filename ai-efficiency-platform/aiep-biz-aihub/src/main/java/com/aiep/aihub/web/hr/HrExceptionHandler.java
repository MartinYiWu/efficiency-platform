package com.aiep.aihub.web.hr;

import com.aiep.aihub.application.hr.HrBusinessException;
import com.aiep.platformcore.api.ApiResponse;
import com.aiep.platformcore.domain.TraceIdHolder;
import java.util.UUID;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 招聘接口安全异常边界，数据库/模型错误正文不能回显候选人或配置秘密。 */
@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(basePackages = "com.aiep.aihub.web.hr")
public class HrExceptionHandler {
  @ExceptionHandler(HrBusinessException.class)
  public ResponseEntity<ApiResponse<Void>> business(HrBusinessException error) {
    return response(error.status(), error.code(), error.getMessage());
  }

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<ApiResponse<Void>> invalid(IllegalArgumentException error) {
    return response(422, "HR_INPUT_INVALID", "输入格式或业务规则不符合要求");
  }

  @ExceptionHandler(DataAccessException.class)
  public ResponseEntity<ApiResponse<Void>> database(DataAccessException error) {
    return response(503, "HR_DATABASE_NOT_READY", "人事数据服务未就绪，请联系管理员");
  }

  @ExceptionHandler(RuntimeException.class)
  public ResponseEntity<ApiResponse<Void>> failure(RuntimeException error) {
    return response(503, "HR_SERVICE_UNAVAILABLE", "人事服务当前不可用，请根据追踪编号排查");
  }

  private static ResponseEntity<ApiResponse<Void>> response(
      int status, String code, String message) {
    String trace = TraceIdHolder.current();
    if (trace == null) trace = UUID.randomUUID().toString();
    return ResponseEntity.status(status)
        .header("X-Trace-Id", trace)
        .body(new ApiResponse<>(code, message, null, trace));
  }
}
