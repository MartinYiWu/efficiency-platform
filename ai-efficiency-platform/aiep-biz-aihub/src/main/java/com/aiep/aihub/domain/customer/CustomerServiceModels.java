package com.aiep.aihub.domain.customer;

import java.util.Set;

public final class CustomerServiceModels {
    private CustomerServiceModels() { }

    public static final String AGENT_KEY = "customer-service";
    public static final Set<String> TERMINAL_STATUSES = Set.of(
            "SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED");
    public static final Set<String> RATINGS = Set.of("UP", "DOWN");
    public static final Set<String> DOWN_REASONS = Set.of(
            "INCORRECT", "OUTDATED", "IRRELEVANT", "MISSING_CITATION", "UNCLEAR", "OTHER");

    public static void requireRating(String rating, String reasonCode, String comment) {
        if (!RATINGS.contains(rating)) {
            throw new IllegalArgumentException("CUSTOMER_SERVICE_FEEDBACK_RATING_INVALID");
        }
        if ("UP".equals(rating) && (reasonCode != null || comment != null)) {
            throw new IllegalArgumentException("CUSTOMER_SERVICE_FEEDBACK_UP_FIELDS_INVALID");
        }
        if ("DOWN".equals(rating) && (reasonCode == null || !DOWN_REASONS.contains(reasonCode))) {
            throw new IllegalArgumentException("CUSTOMER_SERVICE_FEEDBACK_REASON_INVALID");
        }
        if ("OTHER".equals(reasonCode) && (comment == null || comment.isBlank() || comment.length() > 500)) {
            throw new IllegalArgumentException("CUSTOMER_SERVICE_FEEDBACK_COMMENT_REQUIRED");
        }
    }
}
