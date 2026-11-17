package com.aiep.aihub.memory;

import com.aiep.aihub.application.customer.CustomerServiceApplicationService;
import com.aiep.aihub.application.customer.CustomerServiceEventProjector;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.aihub.web.customer.CustomerServiceController;
import com.aiep.aihub.web.memory.MemoryActorResolver;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class MemoryCustomerStreamThreadTest {
    @Test void orderedProjectionLeavesNonBlockingPublisherThreadBeforeSynchronousManifestGate() throws Exception {
        var service=mock(CustomerServiceApplicationService.class);var projector=mock(CustomerServiceEventProjector.class);
        var actors=mock(MemoryActorResolver.class);var actor=new OperationActor("t","u","original-session");
        var run=mock(RunPO.class);when(run.status()).thenReturn("PENDING");
        when(actors.current()).thenReturn(actor);when(service.getRun("t","u","run")).thenReturn(run);
        var first=mock(CustomerServiceRunEvent.class);when(first.sequence()).thenReturn(1L);
        var second=mock(CustomerServiceRunEvent.class);when(second.sequence()).thenReturn(2L);
        when(service.stream("t","u","run",0)).thenReturn(Flux.just(first,second).publishOn(Schedulers.parallel()));
        var done=new CountDownLatch(2);var failures=new ConcurrentLinkedQueue<String>();var order=new CopyOnWriteArrayList<Long>();
        when(projector.project(eq("run"),eq("t"),any())).thenAnswer(call->{
            try {
                if(Schedulers.isInNonBlockingThread())failures.add("nonblocking-projection");
                Mono.delay(Duration.ofMillis(1)).block(Duration.ofSeconds(1));
                order.add(((CustomerServiceRunEvent)call.getArgument(2)).sequence());
            }catch(IllegalStateException blocked){failures.add("blocking-manifest-rejected");}
            finally{done.countDown();}
            return null;
        });
        new CustomerServiceController(service,projector,actors).events("run",null,0);
        assertTrue(done.await(3,TimeUnit.SECONDS));
        assertTrue(failures.isEmpty(),failures.toString());assertEquals(List.of(1L,2L),order);
        verify(actors,times(2)).revalidate(actor);
    }
}
