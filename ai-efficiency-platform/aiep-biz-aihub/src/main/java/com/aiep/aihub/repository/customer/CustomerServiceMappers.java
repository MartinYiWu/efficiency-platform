package com.aiep.aihub.repository.customer;

import com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.FeedbackPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunStepPO;
import java.util.List;

public interface CustomerServiceMappers {
    void insertConversation(ConversationPO value);
    ConversationPO findConversation(String id, String tenantId, String userId);
    List<ConversationPO> listConversations(String tenantId, String userId, String keyword, int offset, int limit);
    long countConversations(String tenantId, String userId, String keyword);
    void updateConversation(String id, String tenantId, String userId, String title, String status);
    void touchConversation(String id, String title);

    void insertMessage(MessagePO value);
    MessagePO findMessage(String id, String tenantId);
    MessagePO findMessageByClientRequest(String tenantId, String clientRequestId);
    MessagePO findAssistantMessageByRun(String runId, String tenantId);
    List<MessagePO> listMessages(String conversationId, String tenantId, String beforeMessageId, int limit);
    List<MessagePO> listCompletedHistory(String conversationId, String tenantId, int limit);
    void completeAssistantMessage(String id, String content, String answerMode, String status);

    void insertRun(RunPO value);
    RunPO findRun(String id, String tenantId);
    RunPO findRunByUserMessage(String userMessageId, String tenantId);
    void bindAgentRun(String id, String agentRunId, String status);
    boolean advanceRun(String id, long expectedSequence, long nextSequence, String status,
                       String answerMode, String failureCode, String failureMessage);
    List<RunPO> listRuns(String agentKey, String status, String answerMode, int offset, int limit);
    long countRuns(String agentKey, String status, String answerMode);

    void insertRunStep(RunStepPO value);
    List<RunStepPO> listRunSteps(String runId);
    void insertCitation(CitationPO value);
    List<CitationPO> listCitationsByMessage(String messageId);
    CitationPO findCitationByRunAndNumber(String runId, int citationNo);
    CitationPO findCitation(String id, String tenantId);

    void upsertFeedback(FeedbackPO value);
    FeedbackPO findFeedback(String tenantId, String userId, String messageId);
    List<FeedbackPO> listFeedback(String rating, String reasonCode, int offset, int limit);
    long countFeedback(String rating, String reasonCode);
}
