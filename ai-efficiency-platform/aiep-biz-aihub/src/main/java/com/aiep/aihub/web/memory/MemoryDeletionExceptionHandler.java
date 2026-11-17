package com.aiep.aihub.web.memory;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.platformcore.api.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.dao.DataAccessException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

/** 与D12相同安全错误契约，独立限定新增Controller，避免扩大其他HTTP异常处理范围。 */
@RestControllerAdvice(assignableTypes=MemoryDeletionController.class)
public class MemoryDeletionExceptionHandler {
 @ExceptionHandler(MemoryException.class) public ResponseEntity<ApiResponse<Void>> memory(MemoryException error){String code=error.code();int status=switch(code){case "MEMORY_IDENTITY_REQUIRED"->401;case "MEMORY_SCOPE_DENIED"->403;case "MEMORY_NOT_FOUND"->404;case "MEMORY_REVISION_CONFLICT","MEMORY_IDEMPOTENCY_CONFLICT","MEMORY_SESSION_BINDING_CONFLICT"->409;case "FEATURE_DISABLED","MEMORY_VALUE_INVALID"->422;case "MEMORY_KEY_UNAVAILABLE","MEMORY_STORAGE_UNAVAILABLE"->503;default->400;};return response(status,code);}
 @ExceptionHandler(ResponseStatusException.class) public ResponseEntity<ApiResponse<Void>> identity(ResponseStatusException error){return response(error.getStatusCode().value(),"MEMORY_IDENTITY_REQUIRED");}
 @ExceptionHandler({IllegalArgumentException.class,HttpMessageNotReadableException.class,MissingServletRequestParameterException.class,MethodArgumentTypeMismatchException.class}) public ResponseEntity<ApiResponse<Void>> invalid(Exception error){return response(400,"MEMORY_REQUEST_INVALID");}
 @ExceptionHandler(DataAccessException.class) public ResponseEntity<ApiResponse<Void>> storage(DataAccessException error){return response(503,"MEMORY_STORAGE_UNAVAILABLE");}
 private ResponseEntity<ApiResponse<Void>> response(int status,String code){String trace=MemoryExceptionHandler.trace();return ResponseEntity.status(status).header("X-Trace-Id",trace).body(new ApiResponse<>(code,code,null,trace));}
}
