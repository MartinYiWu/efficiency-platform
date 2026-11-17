package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import org.springframework.stereotype.Component;

/** 批次只在显式start之后执行；同批提交去重，服务退出取消本进程持有的任务。 */
@Component
public class HrBatchExecutor {
  private final HrBatchService service;
  private final ExecutorService executor =
      Executors.newSingleThreadExecutor(Thread.ofVirtual().name("hr-batch-", 0).factory());
  private final ConcurrentHashMap<String, FutureTask<Void>> tasks = new ConcurrentHashMap<>();

  public HrBatchExecutor(HrBatchService service) {
    this.service = service;
  }

  public void submit(HrActor actor, String id) {
    String key = actor.tenantId() + ":" + id;
    FutureTask<Void> task =
        new FutureTask<>(
            () -> {
              try {
                service.process(actor, id);
              } finally {
                tasks.remove(key);
              }
              return null;
            });
    if (tasks.putIfAbsent(key, task) == null) {
      try {
        executor.execute(task);
      } catch (RuntimeException error) {
        tasks.remove(key);
        service.cancel(actor, id);
        throw error;
      }
    }
  }

  public void cancel(HrActor actor, String id) {
    service.cancel(actor, id);
    FutureTask<Void> task = tasks.get(actor.tenantId() + ":" + id);
    if (task != null) task.cancel(true);
  }

  @PreDestroy
  public void close() {
    for (var task : tasks.values()) task.cancel(true);
    executor.shutdownNow();
  }
}
