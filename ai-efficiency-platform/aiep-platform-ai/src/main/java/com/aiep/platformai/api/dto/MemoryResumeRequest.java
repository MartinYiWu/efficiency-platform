package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.util.List;
import static com.aiep.platformai.api.dto.MemoryContextWait.Wire;

/** 原等待的严格内部恢复命令；七字段构造器仅保留旧安全拒绝协议。 */
@JsonDeserialize(using = MemoryResumeRequest.Deserializer.class)
@JsonSerialize(using = MemoryResumeRequest.Serializer.class)
public record MemoryResumeRequest(
        @JsonProperty("wait_event_id") String waitEventId,
        @JsonProperty("packet_revision") long packetRevision,
        @JsonProperty("expected_execution_revision") long expectedExecutionRevision,
        @JsonProperty("resume_request_id") String resumeRequestId,
        @JsonProperty("operation_hash") String operationHash,
        @JsonProperty("mode") Mode resumeMode,
        @JsonProperty("new_content") boolean newContent,
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("logical_operation_id") String logicalOperationId,
        @JsonProperty("canonical_request_hmac") String canonicalRequestHmac,
        Long attempt,
        @JsonProperty("expected_current_context_fingerprint") String expectedCurrentContextFingerprint,
        @JsonProperty("refreshed_context") MemoryContextEnvelope refreshedContext) {
    public enum Mode { cpu, paid, refresh }
    public MemoryResumeRequest(String waitEventId,long packetRevision,long expectedExecutionRevision,String resumeRequestId,String operationHash,String mode,boolean newContent) {
        this(waitEventId,packetRevision,expectedExecutionRevision,resumeRequestId,operationHash,mode==null?null:Mode.valueOf(mode),newContent,null,null,null,null,null,null);
    }
    public MemoryResumeRequest {
        if(contractVersion==null) {
            if(logicalOperationId!=null||canonicalRequestHmac!=null||attempt!=null||expectedCurrentContextFingerprint!=null||refreshedContext!=null)
                throw new IllegalArgumentException("MEMORY_RESUME_INVALID");
        } else {
            if(!"memory-context-resume/2".equals(contractVersion)||newContent||resumeMode==null||attempt==null)
                throw new IllegalArgumentException("MEMORY_RESUME_INVALID");
            Wire.id(waitEventId); Wire.id(resumeRequestId); Wire.id(logicalOperationId);
            Wire.count(packetRevision); Wire.count(expectedExecutionRevision); Wire.count(attempt);
            if(packetRevision<1||expectedExecutionRevision<1||attempt<1||attempt>3)
                throw new IllegalArgumentException("MEMORY_RESUME_ANCHOR_INVALID");
            Wire.digest(operationHash); Wire.digest(expectedCurrentContextFingerprint);
            if(canonicalRequestHmac!=null) Wire.digest(canonicalRequestHmac);
            if(resumeMode==Mode.refresh) {
                if(refreshedContext==null||!"EXACT_ONLY".equals(refreshedContext.memoryMode())||refreshedContext.packet()==null)
                    throw new IllegalArgumentException("MEMORY_AUTHORIZATION_REQUIRED");
                if(refreshedContext.packet().packetRevision()<=packetRevision||refreshedContext.packet().executionRevision()!=expectedExecutionRevision)
                    throw new IllegalArgumentException("MEMORY_REVISION_CONFLICT");
            } else if(refreshedContext!=null) throw new IllegalArgumentException("MEMORY_RESUME_CONTEXT_INVALID");
        }
    }
    public String mode() { return resumeMode==null?null:resumeMode.name(); }
    @JsonIgnore public boolean isV2() { return "memory-context-resume/2".equals(contractVersion); }
    public void requireV2() { if(!isV2()) throw new IllegalStateException("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED"); }
    public String canonicalFingerprint() {
        requireV2();
        var mapper=new ObjectMapper();
        return MemoryPacketDigest.canonicalDigest(mapper.valueToTree(Wire.canonical(mapper.valueToTree(this),"")));
    }
    /** 只比较原授权身份；当前源权限、实际TTL及发送许可仍由受信服务逐次核验。 */
    public void validateBinding(MemoryContextWait wait,MemoryContextEnvelope.Scope routeScope,String executionId,String currentFingerprint,MemoryContextEnvelope original) {
        requireV2();
        if(!wait.scope().equals(routeScope)||!wait.executionId().equals(executionId)) throw new IllegalArgumentException("CONTEXT_SCOPE_MISMATCH");
        if(!wait.waitEventId().equals(waitEventId)||wait.expectedPacketRevision()!=packetRevision||wait.expectedExecutionRevision()!=expectedExecutionRevision
                ||!wait.operationHash().equals(operationHash)||!wait.logicalOperationId().equals(logicalOperationId)
                ||!java.util.Objects.equals(wait.canonicalRequestHmac(),canonicalRequestHmac)||wait.attempt()!=attempt
                ||!expectedCurrentContextFingerprint.equals(currentFingerprint)||!expectedCurrentContextFingerprint.equals(wait.expectedCurrentContextFingerprint())) throw new IllegalArgumentException("MEMORY_RESUME_CONFLICT");
        if(refreshedContext==null) return;
        if(original==null||original.packet()==null) throw new IllegalArgumentException("MEMORY_AUTHORITY_UNAVAILABLE");
        var old=original.packet(); var target=refreshedContext.packet();
        if(!old.scope().equals(wait.scope())||!old.taskId().equals(wait.taskId())||!old.executionId().equals(wait.executionId())
                ||old.packetRevision()!=packetRevision||old.executionRevision()!=expectedExecutionRevision||!old.semanticInputHash().equals(wait.semanticInputHash())
                ||target.expiresAt()>wait.originalDeadline()) throw new IllegalArgumentException("MEMORY_RESUME_CONFLICT");
        var mapper=new ObjectMapper();
        ObjectNode previous=mapper.valueToTree(original), next=mapper.valueToTree(refreshedContext);
        for(ObjectNode envelope:List.of(previous,next)) {
            ((ObjectNode)envelope.get("packet")).remove(List.of("packet_revision","execution_revision","issued_at","expires_at"));
            ((ObjectNode)envelope.get("authorization")).remove("packet_digest");
        }
        if(!Wire.canonical(previous,"/refreshed_context").equals(Wire.canonical(next,"/refreshed_context")))
            throw new IllegalArgumentException("SOURCE_CHANGED");
    }
    public static final class Deserializer extends StdDeserializer<MemoryResumeRequest> {
        public Deserializer() { super(MemoryResumeRequest.class); }
        @Override public MemoryResumeRequest deserialize(JsonParser parser,DeserializationContext context) throws IOException {
            JsonNode node=parser.getCodec().readTree(parser);
            if(!node.has("contract_version")) {
                if(!node.isObject()||node.size()!=7) throw new IllegalArgumentException("MEMORY_RESUME_INVALID");
                Wire.check(node,MemoryResumeRequest.class);
                return new MemoryResumeRequest(Wire.text(node,"wait_event_id"),Wire.number(node,"packet_revision"),Wire.number(node,"expected_execution_revision"),Wire.text(node,"resume_request_id"),Wire.text(node,"operation_hash"),Wire.text(node,"mode"),Wire.bool(node,"new_content"));
            }
            Wire.exact(node,MemoryResumeRequest.class);
            return new MemoryResumeRequest(Wire.text(node,"wait_event_id"),Wire.number(node,"packet_revision"),Wire.number(node,"expected_execution_revision"),Wire.text(node,"resume_request_id"),Wire.text(node,"operation_hash"),Mode.valueOf(Wire.text(node,"mode")),Wire.bool(node,"new_content"),Wire.text(node,"contract_version"),Wire.text(node,"logical_operation_id"),Wire.text(node,"canonical_request_hmac"),Wire.number(node,"attempt"),Wire.text(node,"expected_current_context_fingerprint"),node.get("refreshed_context").isNull()?null:parser.getCodec().treeToValue(node.get("refreshed_context"),MemoryContextEnvelope.class));
        }
    }
    public static final class Serializer extends StdSerializer<MemoryResumeRequest> {
        public Serializer() { super(MemoryResumeRequest.class); }
        @Override public void serialize(MemoryResumeRequest value,JsonGenerator gen,SerializerProvider provider) throws IOException {
            gen.writeStartObject();
            gen.writeStringField("wait_event_id",value.waitEventId); gen.writeNumberField("packet_revision",value.packetRevision);
            gen.writeNumberField("expected_execution_revision",value.expectedExecutionRevision); gen.writeStringField("resume_request_id",value.resumeRequestId);
            gen.writeStringField("operation_hash",value.operationHash); gen.writeStringField("mode",value.mode()); gen.writeBooleanField("new_content",value.newContent);
            if(value.isV2()) {
                gen.writeStringField("contract_version",value.contractVersion); gen.writeStringField("logical_operation_id",value.logicalOperationId);
                gen.writeStringField("canonical_request_hmac",value.canonicalRequestHmac); gen.writeNumberField("attempt",value.attempt);
                gen.writeStringField("expected_current_context_fingerprint",value.expectedCurrentContextFingerprint); gen.writeObjectField("refreshed_context",value.refreshedContext);
            }
            gen.writeEndObject();
        }
    }
}
