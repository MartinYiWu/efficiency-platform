package com.aiep.aihub.web.memory;
import com.aiep.aihub.application.memory.MemoryActorProvider;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.identity.api.IdentityFacade;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
/** 默认关闭；开发身份仅显式开关加本机请求，失败凭据不能降级到开发身份。 */
@Component
public class MemoryActorResolver implements MemoryActorProvider {
 private final IdentityFacade identity;
 private final OperationActor developmentActor;
 public MemoryActorResolver(IdentityFacade identity,
  @Value("${aiep.memory.development-actor.enabled:false}") boolean enabled,
  @Value("${aiep.memory.development-actor.tenant:}") String tenant,
  @Value("${aiep.memory.development-actor.user:}") String user) {
  this.identity=identity;this.developmentActor=enabled?new OperationActor(tenant,user):null;
 }
 public OperationActor current() {
  if(RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attributes)
   return resolve(attributes.getRequest());
  throw denied();
 }
 public OperationActor resolve(HttpServletRequest request) {
  String credential=request.getHeader("Authorization");
  if(credential!=null) {
   if(!credential.startsWith("Bearer "))throw denied();
   var subject=identity.authenticate(credential.substring(7)).orElseThrow(MemoryActorResolver::denied);
   if(subject.sessionRef()==null||subject.sessionRef().isBlank())throw denied();
   return new OperationActor(subject.tenantId(),subject.userId(),subject.sessionRef());
  }
  if(developmentActor!=null&&java.util.Set.of("127.0.0.1","::1","0:0:0:0:0:0:0:1").contains(request.getRemoteAddr()))return developmentActor;
  throw denied();
 }
 public OperationActor revalidate(OperationActor actor) {
  if(actor.sessionRef()==null) {
   if(developmentActor!=null&&developmentActor.equals(actor))return actor;
   throw denied();
  }
  var subject=identity.refresh(actor.tenantId(),actor.userId(),actor.sessionRef()).orElseThrow(MemoryActorResolver::denied);
  if(!actor.tenantId().equals(subject.tenantId())||!actor.userId().equals(subject.userId())||!actor.sessionRef().equals(subject.sessionRef()))throw denied();
  return actor;
 }
 private static ResponseStatusException denied() {return new ResponseStatusException(HttpStatus.UNAUTHORIZED,"MEMORY_IDENTITY_REQUIRED");}
}
