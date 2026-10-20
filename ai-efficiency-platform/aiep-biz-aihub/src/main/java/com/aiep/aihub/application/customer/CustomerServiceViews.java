package com.aiep.aihub.application.customer;

import com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.FeedbackPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunStepPO;
import java.util.List;

public final class CustomerServiceViews {
    private CustomerServiceViews() { }

    public record PageView<T>(List<T> items, int page, int pageSize, long total) { }
    public record SubmitView(String conversationId, String runId, String status, String agentReleaseId) { }
    public record MessageView(MessagePO message, List<CitationPO> citations) { }
    public record ReplayView(
            RunPO run, MessagePO question, MessagePO answer, List<RunStepPO> stages,
            List<CitationPO> citations, FeedbackPO feedback) { }
}
