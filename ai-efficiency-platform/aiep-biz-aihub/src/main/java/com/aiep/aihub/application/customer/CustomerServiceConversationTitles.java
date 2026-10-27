package com.aiep.aihub.application.customer;

import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import java.util.Locale;
import org.springframework.dao.DuplicateKeyException;

/** 会话标题校验、唯一性冲突与首轮自动命名规则。 */
public final class CustomerServiceConversationTitles {
    private CustomerServiceConversationTitles() { }

    public static String normalize(String title, boolean allowEmpty) {
        String normalized = title == null ? "" : title.trim();
        if (!allowEmpty && normalized.isBlank())
            throw new TitleException("CUSTOMER_SERVICE_CONVERSATION_TITLE_EMPTY", "会话名称不能为空");
        if (normalized.codePointCount(0, normalized.length()) > 80)
            throw new TitleException("CUSTOMER_SERVICE_CONVERSATION_TITLE_TOO_LONG", "会话名称不能超过80个字符");
        return normalized;
    }

    public static void requireAvailable(CustomerServiceMappers repository, String tenantId, String userId,
            String title, String excludedId) {
        if (!title.isBlank() && repository.conversationTitleExists(tenantId, userId, title, excludedId))
            throw duplicate();
    }

    public static RuntimeException translate(DuplicateKeyException error) {
        return isTitleDuplicate(error) ? duplicate() : error;
    }

    public static void assignAutomatic(CustomerServiceMappers repository, RunPO run, String title) {
        if (title == null || title.isBlank()) return;
        var conversation = repository.findConversationForTitleUpdate(run.conversationId(), run.tenantId());
        if (conversation == null || (conversation.title() != null && !conversation.title().isBlank())) return;
        String base = title.trim();
        base = base.substring(0, base.offsetByCodePoints(0, Math.min(24, base.codePointCount(0, base.length()))));
        for (int suffix = 1; ; suffix++) {
            String candidate = suffix == 1 ? base : base + "（" + suffix + "）";
            if (repository.conversationTitleExists(run.tenantId(), conversation.userId(), candidate, conversation.id())) continue;
            try {
                repository.assignConversationTitle(conversation.id(), run.tenantId(), conversation.userId(), run.userMessageId(), candidate);
                return;
            } catch (DuplicateKeyException error) {
                // MySQL 的重复键只回滚本条语句；不经嵌套事务代理，外层事件事务仍可提交重试结果。
                if (!isTitleDuplicate(error)) throw error;
            }
        }
    }

    private static boolean isTitleDuplicate(DuplicateKeyException error) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause.getMessage() != null && cause.getMessage().toLowerCase(Locale.ROOT).contains("uk_ai_cs_conversation_title")) return true;
        }
        return false;
    }

    private static TitleException duplicate() {
        return new TitleException("CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE", "会话名称已存在，请使用其他标题");
    }

    public static final class TitleException extends RuntimeException {
        private final String code;
        private TitleException(String code, String message) { super(message); this.code = code; }
        public String code() { return code; }
    }
}
