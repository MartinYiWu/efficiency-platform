package com.aiep.aihub.application.memory;
import com.aiep.aihub.application.operation.OperationActor;
/** 当前请求认证及异步原会话复核；实现不得借用同账号其他登录。 */
public interface MemoryActorProvider {
 OperationActor current();
 OperationActor revalidate(OperationActor actor);
}
