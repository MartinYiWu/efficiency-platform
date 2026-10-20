package com.aiep.aihub.application.management;

import com.aiep.aihub.application.customer.CustomerServiceApplicationService;
import com.aiep.aihub.application.customer.CustomerServiceViews.PageView;
import com.aiep.aihub.application.customer.CustomerServiceViews.ReplayView;
import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.customer.CustomerServicePOs.FeedbackPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class AiRunManagementService {
    private final CustomerServiceMappers repository;
    private final CustomerServiceApplicationService customerService;
    public AiRunManagementService(CustomerServiceMappers repository, CustomerServiceApplicationService customerService) {
        this.repository = repository; this.customerService = customerService;
    }
    public PageView<RunPO> runs(String agentKey, String status, String answerMode, int page, int pageSize) {
        int offset = Math.max(0, page - 1) * pageSize;
        return new PageView<>(repository.listRuns(agentKey, status, answerMode, offset, pageSize), page, pageSize,
                repository.countRuns(agentKey, status, answerMode));
    }
    public ReplayView replay(String id) { return customerService.replay("dev", id); }
    public PageView<FeedbackPO> feedback(String rating, String reasonCode, int page, int pageSize) {
        int offset = Math.max(0, page - 1) * pageSize;
        return new PageView<>(repository.listFeedback(rating, reasonCode, offset, pageSize), page, pageSize,
                repository.countFeedback(rating, reasonCode));
    }
}
