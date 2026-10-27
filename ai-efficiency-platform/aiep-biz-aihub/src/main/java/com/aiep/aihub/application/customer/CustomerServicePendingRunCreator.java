package com.aiep.aihub.application.customer;

import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerServicePendingRunCreator {
    private final CustomerServiceMappers repository;

    public CustomerServicePendingRunCreator(CustomerServiceMappers repository) { this.repository = repository; }

    @Transactional
    public Pending create(String conversationId, String tenantId, String message, String clientRequestId, String releaseId) {
        MessagePO existing = repository.findMessageByClientRequest(tenantId, clientRequestId);
        if (existing != null) {
            return new Pending(repository.findRunByUserMessage(existing.id(), tenantId), existing, null, false);
        }
        Instant now = Instant.now();
        String runId = UUID.randomUUID().toString();
        MessagePO user = new MessagePO(UUID.randomUUID().toString(), conversationId, tenantId, "USER", message,
                "COMPLETED", null, runId, clientRequestId, now);
        MessagePO assistant = new MessagePO(UUID.randomUUID().toString(), conversationId, tenantId, "ASSISTANT", "",
                "PENDING", null, runId, null, now);
        RunPO run = new RunPO(runId, conversationId, tenantId, user.id(), null, releaseId, "PENDING", null,
                0, null, null, null, null, now, now);
        repository.insertMessage(user);
        repository.insertMessage(assistant);
        repository.insertRun(run);
        repository.touchConversation(conversationId);
        return new Pending(run, user, assistant, true);
    }

    public record Pending(RunPO run, MessagePO userMessage, MessagePO assistantMessage, boolean created) { }
}
