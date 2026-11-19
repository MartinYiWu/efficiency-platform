package com.aiep.aihub.web.memory;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.platformcore.api.ApiResponse;
import com.aiep.platformcore.domain.TraceIdHolder;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.dao.DataAccessException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
/** 错误仅回安全码与追踪ID，禁止正文/SQL/密钥异常进入HTTP。 */
@RestControllerAdvice(assignableTypes={MemoryController.class,MemoryContextUsageController.class,MemoryProposalController.class,MemorySharingController.class,MemoryEpisodeController.class,MemorySemanticController.class})
public class MemoryExceptionHandler {
 @ExceptionHandler(MemoryException.class) public ResponseEntity<ApiResponse<Void>> memory(MemoryException error){String code=error.code();int status=switch(code){case "MEMORY_IDENTITY_REQUIRED"->401;case "MEMORY_SCOPE_DENIED"->403;case "MEMORY_NOT_FOUND"->404;case "MEMORY_REVISION_CONFLICT","MEMORY_IDEMPOTENCY_CONFLICT","MEMORY_SESSION_BINDING_CONFLICT","MEMORY_PROPOSAL_REVISION_CONFLICT","MEMORY_SOURCE_CHANGED","MEMORY_PROPOSAL_STALE","MEMORY_PROPOSAL_SUPPRESSED","MEMORY_SHARING_REVISION_CONFLICT","MEMORY_EPISODE_REVISION_CONFLICT","MEMORY_PROMOTION_REVISION_CONFLICT","MEMORY_PROMOTION_ASSET_CHANGED","MEMORY_PROMOTION_SOURCE_REVOKED","MEMORY_EXECUTION_EXPIRED"->409;case "FEATURE_DISABLED","MEMORY_VALUE_INVALID","MEMORY_PROPOSAL_PURPOSE_DENIED","MEMORY_SHARING_SOURCE_DENIED","MEMORY_SHARING_FIELD_DENIED","MEMORY_SHARING_RETENTION_DENIED","MEMORY_QUERY_EMBEDDING_NOT_AUTHORIZED","MEMORY_INDEX_EXECUTION_UNSUPPORTED","MEMORY_PROMOTION_REGRESSION_REQUIRED","MEMORY_EPISODE_MEASUREMENT_AUTHORITY_REQUIRED","MEMORY_EPISODE_TECHNICAL_AUTHORITY_REQUIRED"->422;case "MEMORY_KEY_UNAVAILABLE","MEMORY_STORAGE_UNAVAILABLE"->503;default->400;};return response(status,code);}
 @ExceptionHandler(com.aiep.platformai.api.AiInvocationException.class) public ResponseEntity<ApiResponse<Void>> invocation(com.aiep.platformai.api.AiInvocationException error){String code=error.code();boolean safe=code!=null&&code.matches("(?:MEMORY_|DERIVE_|SUMMARY_|CONTEXT_|PAID_|PROVIDER_|AGENT_|BUDGET_|RUN_|WORKLOAD_|LEDGER_)[A-Z0-9_]{1,96}");int status=error.status();return response(status>=400&&status<=599?status:502,safe?code:"AGENT_REQUEST_FAILED");}
 @ExceptionHandler(com.aiep.aihub.application.management.AiManagementException.class) public ResponseEntity<ApiResponse<Void>> management(com.aiep.aihub.application.management.AiManagementException error){String code=error.getCode();boolean safe=code!=null&&code.matches("(?:AI_|MEMORY_)[A-Z0-9_]{1,96}");return response(422,safe?code:"MEMORY_ASSET_REQUEST_FAILED");}
 @ExceptionHandler(ResponseStatusException.class) public ResponseEntity<ApiResponse<Void>> identity(ResponseStatusException error){return response(error.getStatusCode().value(),"MEMORY_IDENTITY_REQUIRED");}
 @ExceptionHandler({IllegalArgumentException.class,HttpMessageNotReadableException.class,MissingServletRequestParameterException.class,MethodArgumentTypeMismatchException.class}) public ResponseEntity<ApiResponse<Void>> invalid(Exception error){return response(400,"MEMORY_REQUEST_INVALID");}
 @ExceptionHandler(DataAccessException.class) public ResponseEntity<ApiResponse<Void>> storage(DataAccessException error){return response(503,"MEMORY_STORAGE_UNAVAILABLE");}
 @ExceptionHandler(RuntimeException.class) public ResponseEntity<ApiResponse<Void>> unexpected(RuntimeException error){return response(500,"MEMORY_REQUEST_FAILED");}
 static String trace(){String value=TraceIdHolder.current();return value==null?java.util.UUID.randomUUID().toString():value;}
 private ResponseEntity<ApiResponse<Void>> response(int status,String code){String trace=trace();return ResponseEntity.status(status).header("X-Trace-Id",trace).body(new ApiResponse<>(code,code,null,trace));}
}
