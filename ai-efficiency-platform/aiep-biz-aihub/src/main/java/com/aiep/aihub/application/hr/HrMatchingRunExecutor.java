package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import java.util.concurrent.*;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class HrMatchingRunExecutor implements DisposableBean {
  private final ExecutorService executor =
      Executors.newThreadPerTaskExecutor(Thread.ofVirtual().name("hr-match-", 0).factory());
  private final ConcurrentHashMap<String, Future<?>> running = new ConcurrentHashMap<>();
  private final HrMatchingService service;

  public HrMatchingRunExecutor(HrMatchingService service) {
    this.service = service;
  }

  public void submit(HrActor actor, MatchRequest request, Run run) {
    FutureTask<Void> task =
        new FutureTask<>(
            () -> {
              try {
                service.execute(actor, request, run.id());
              } catch (RuntimeException ignored) {
              }
              return null;
            }) {
          @Override
          protected void done() {
            running.remove(run.id(), this);
          }
        };
    if (running.putIfAbsent(run.id(), task) != null) return;
    try {
      executor.execute(task);
    } catch (RejectedExecutionException error) {
      running.remove(run.id(), task);
      service.failQueued(actor, run.id());
    }
  }

  public Run cancel(HrActor actor, String id) {
    Run run = service.cancel(actor, id);
    Future<?> future = running.remove(id);
    if (future != null) future.cancel(true);
    service.cancelAgent(actor, id);
    return service.run(actor, id);
  }

  public void destroy() {
    executor.shutdownNow();
  }
}
