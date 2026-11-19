package com.aiep.aihub.api.memory;

import java.time.Instant;
import java.util.List;
import java.util.Set;

/** 经验只保存可观察依据，不接模型自报可信/分享/发布权限或隐藏推理。 */
public final class MemoryEpisodeContracts {
    private MemoryEpisodeContracts() { }
    public record Content(String category,String scenario,List<String> preconditions,List<String> actions,
            String observedResults,Long denominator,Instant observedFrom,Instant observedUntil,List<String> evidenceRefs,
            String applicableVersion,List<String> disallowedConditions) {
        public Content {
            if(category==null||!Set.of("USER_PREFERENCE","MEASURED_RESULT","TECHNICAL_EXPERIENCE").contains(category))invalid();
            text(scenario,2048);text(observedResults,4096);text(applicableVersion,128);
            preconditions=list(preconditions,16,512);actions=list(actions,16,512);evidenceRefs=list(evidenceRefs,128,128);disallowedConditions=list(disallowedConditions,16,512);
            if(actions.isEmpty()||evidenceRefs.isEmpty())invalid();
            if("MEASURED_RESULT".equals(category)&&(denominator==null||denominator<1||observedFrom==null||observedUntil==null||observedUntil.isBefore(observedFrom)))invalid();
            if(denominator!=null&&denominator<1||observedFrom!=null&&observedUntil==null||observedUntil!=null&&observedFrom==null)invalid();
        }
        @Override public String toString(){return "MemoryEpisodeContent[redacted]";}
    }
    public record CreateCommand(MemoryScopeDTO scope,String executionId,Content content,String idempotencyKey) { }
    public record EpisodeView(String id,String topAgent,String sessionId,Content content,String status,long revision,
            @com.fasterxml.jackson.annotation.JsonFormat(shape=com.fasterxml.jackson.annotation.JsonFormat.Shape.STRING) Instant expiresAt,long feedbackLikes) {
        @Override public String toString(){return "MemoryEpisodeView[redacted]";}
    }
    public record PromotionCommand(String episodeId,MemoryScopeDTO scope,long expectedEpisodeRevision,String targetType,
            String targetDefinitionId,String semanticVersion,String changeSummary,String graphKey,String graphVersion,String idempotencyKey) { }
    public record RegressionCommand(long expectedRevision,String suiteId,String suiteVersion,String candidateDigest,
            String reportSha256,int totalCases,int passedCases,String idempotencyKey) { }
    public record PromotionView(String id,String episodeId,String targetType,String targetDefinitionId,String targetVersionId,
            String candidateDigest,String status,long revision,String regressionReportSha256) { }
    public static void text(String value,int max){if(value==null||value.isBlank()||value.codePointCount(0,value.length())>max||value.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff))invalid();}
    private static List<String> list(List<String> values,int max,int length){if(values==null||values.size()>max)invalid();values=List.copyOf(values);values.forEach(value->text(value,length));return values;}
    private static void invalid(){throw new MemoryContracts.MemoryException("MEMORY_EPISODE_INVALID");}
}
