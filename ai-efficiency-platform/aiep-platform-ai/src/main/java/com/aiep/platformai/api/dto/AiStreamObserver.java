package com.aiep.platformai.api.dto;

public interface AiStreamObserver {
    void onCitation(String citation);
    void onDelta(String delta);
    void onMeta(String metadata);
    void onError(String errorCode, String message);
}
