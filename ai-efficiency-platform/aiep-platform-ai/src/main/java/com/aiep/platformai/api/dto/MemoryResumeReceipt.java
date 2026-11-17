package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;
import com.fasterxml.jackson.databind.ser.std.StdSerializer;
import java.io.IOException;
import java.util.Set;
import static com.aiep.platformai.api.dto.MemoryContextWait.Wire;

/** 提交时不可变回执；dispatchAllowed只描述提交结果，绝不是后续发送许可。 */
@JsonDeserialize(using = MemoryResumeReceipt.Deserializer.class)
@JsonSerialize(using = MemoryResumeReceipt.Serializer.class)
public record MemoryResumeReceipt(
        @JsonProperty("code") Code resultCode,
        @JsonProperty("receipt_ref") String receiptRef,
        @JsonProperty("wait_event_id") String waitEventId,
        @JsonProperty("packet_revision") Long packetRevision,
        @JsonProperty("execution_revision") Long executionRevision,
        @JsonProperty("current_packet_revision") Long currentPacketRevision,
        @JsonProperty("current_context_fingerprint") String currentContextFingerprint,
        @JsonProperty("refresh_count") Long refreshCount,
        State state,
        @JsonProperty("candidate_phase") CandidatePhase candidatePhase,
        @JsonProperty("next_wait_event_id") String nextWaitEventId,
        @JsonProperty("dispatch_allowed") Boolean dispatchAllowed) {
    public enum CandidatePhase { PENDING, ACKED, EXPIRED_UNAPPLIED, APPLIED_EXPIRED, ABORTED }
    public enum State { ACTIVE, WAITING_CONTEXT, REFRESH_PENDING, BLOCKED, EXPIRED, REVOKED, SCRUBBED, DELETED }
    public enum Code {
        CONTEXT_REFRESHED, CPU_CONFIRMED, MEMORY_REFRESH_PENDING, MEMORY_RESUME_CONFLICT, MEMORY_WAIT_CONSUMED,
        MEMORY_REVISION_CONFLICT, MEMORY_REFRESH_PACKET_EXPIRED, CONTEXT_REFRESH_LIMIT, EXECUTION_EXPIRED,
        SOURCE_CHANGED, SOURCE_REVOKED, ACCESS_REVOKED, CONTINUATION_AUTH_UNSUPPORTED, MEMORY_REFRESH_CAPABILITY_UNSUPPORTED,
        MEMORY_REFRESH_SCHEMA_REQUIRED, MEMORY_AUTHORITY_UNAVAILABLE, CONTEXT_INTERNAL_AUTH_REQUIRED, CONTEXT_SCOPE_MISMATCH,
        MEMORY_RESULT_UNAVAILABLE,
        // 仅旧两字段响应保留原码，不进入新版授权或错误白名单。
        MEMORY_THREAD_FENCED, MEMORY_REFRESH_AUTH_UNSUPPORTED, MEMORY_AUTHORITY_REFRESH_REQUIRED;
        private boolean legacyOnly() {
            return this==MEMORY_THREAD_FENCED||this==MEMORY_REFRESH_AUTH_UNSUPPORTED||this==MEMORY_AUTHORITY_REFRESH_REQUIRED;
        }
        public int httpStatus() {
            return switch(this) {
                case CONTEXT_REFRESHED, CPU_CONFIRMED -> 200;
                case MEMORY_REFRESH_PENDING -> 202;
                case MEMORY_REFRESH_SCHEMA_REQUIRED, MEMORY_AUTHORITY_UNAVAILABLE -> 503;
                case CONTEXT_INTERNAL_AUTH_REQUIRED -> 401;
                case CONTEXT_SCOPE_MISMATCH -> 403;
                default -> 409;
            };
        }
        static Code legacy(String value) {
            return Code.valueOf(switch(value) { case "MEMORY_REFRESH_LIMIT" -> "CONTEXT_REFRESH_LIMIT"; case "EXPIRED" -> "EXECUTION_EXPIRED"; default -> value; });
        }
    }
    public MemoryResumeReceipt(String code,String receiptRef) {
        this(Code.legacy(code),receiptRef,null,null,null,null,null,null,null,null,null,null);
    }
    public String code() { return resultCode.name(); }
    public MemoryResumeReceipt {
        if(resultCode==null) throw new IllegalArgumentException("MEMORY_RECEIPT_INVALID");
        if(state==null) {
            if(waitEventId!=null||packetRevision!=null||executionRevision!=null||currentPacketRevision!=null||currentContextFingerprint!=null||refreshCount!=null||candidatePhase!=null||nextWaitEventId!=null||dispatchAllowed!=null)
                throw new IllegalArgumentException("MEMORY_RECEIPT_INVALID");
        } else {
            if(resultCode.legacyOnly()) throw new IllegalArgumentException("MEMORY_RECEIPT_LEGACY_CODE_INVALID");
            if(refreshCount==null||dispatchAllowed==null) throw new IllegalArgumentException("MEMORY_RECEIPT_INVALID");
            for(String value:new String[]{receiptRef,waitEventId,nextWaitEventId}) if(value!=null) Wire.id(value);
            for(Long value:new Long[]{packetRevision,executionRevision,currentPacketRevision}) if(value!=null) {
                Wire.count(value);
                if(value<1) throw new IllegalArgumentException("MEMORY_RECEIPT_BINDING_INVALID");
            }
            Wire.count(refreshCount);
            if(refreshCount>3) throw new IllegalArgumentException("CONTEXT_REFRESH_LIMIT");
            if(candidatePhase!=null&&refreshCount<1) throw new IllegalArgumentException("MEMORY_RECEIPT_BINDING_INVALID");
            if(currentContextFingerprint!=null) Wire.digest(currentContextFingerprint);
            if(candidatePhase!=null&&(receiptRef==null||waitEventId==null||packetRevision==null||executionRevision==null||currentPacketRevision==null||currentContextFingerprint==null))
                throw new IllegalArgumentException("MEMORY_RECEIPT_BINDING_INVALID");
            if(resultCode==Code.CONTEXT_REFRESHED&&(candidatePhase!=CandidatePhase.ACKED||state!=State.ACTIVE||!java.util.Objects.equals(packetRevision,currentPacketRevision)))
                throw new IllegalArgumentException("MEMORY_RECEIPT_SUCCESS_INVALID");
            if(dispatchAllowed&&(resultCode!=Code.CONTEXT_REFRESHED||candidatePhase!=CandidatePhase.ACKED||state!=State.ACTIVE))
                throw new IllegalArgumentException("MEMORY_RECEIPT_DISPATCH_INVALID");
            if(candidatePhase==CandidatePhase.PENDING&&(resultCode!=Code.MEMORY_REFRESH_PENDING||state!=State.REFRESH_PENDING))
                throw new IllegalArgumentException("MEMORY_RECEIPT_PENDING_INVALID");
            if(resultCode==Code.MEMORY_REFRESH_PENDING&&candidatePhase!=CandidatePhase.PENDING)
                throw new IllegalArgumentException("MEMORY_RECEIPT_PENDING_INVALID");
            if(candidatePhase==CandidatePhase.ACKED&&resultCode!=Code.CONTEXT_REFRESHED)
                throw new IllegalArgumentException("MEMORY_RECEIPT_SUCCESS_INVALID");
            if((candidatePhase==CandidatePhase.EXPIRED_UNAPPLIED||candidatePhase==CandidatePhase.APPLIED_EXPIRED)&&resultCode!=Code.MEMORY_REFRESH_PACKET_EXPIRED)
                throw new IllegalArgumentException("MEMORY_RECEIPT_EXPIRY_INVALID");
            if(resultCode==Code.MEMORY_REFRESH_PACKET_EXPIRED) {
                if(candidatePhase!=CandidatePhase.EXPIRED_UNAPPLIED&&candidatePhase!=CandidatePhase.APPLIED_EXPIRED||dispatchAllowed||!Set.of(State.WAITING_CONTEXT,State.BLOCKED).contains(state))
                    throw new IllegalArgumentException("MEMORY_RECEIPT_EXPIRY_INVALID");
                if(candidatePhase==CandidatePhase.EXPIRED_UNAPPLIED&&(currentPacketRevision>=packetRevision||nextWaitEventId!=null)) throw new IllegalArgumentException("MEMORY_RECEIPT_EXPIRY_INVALID");
                if(candidatePhase==CandidatePhase.APPLIED_EXPIRED&&!currentPacketRevision.equals(packetRevision)) throw new IllegalArgumentException("MEMORY_RECEIPT_EXPIRY_INVALID");
                if(candidatePhase==CandidatePhase.EXPIRED_UNAPPLIED&&refreshCount<3&&state!=State.WAITING_CONTEXT)
                    throw new IllegalArgumentException("MEMORY_RECEIPT_EXPIRY_INVALID");
                if(candidatePhase==CandidatePhase.APPLIED_EXPIRED&&(state==State.WAITING_CONTEXT)!=(nextWaitEventId!=null))
                    throw new IllegalArgumentException("MEMORY_RECEIPT_NEXT_WAIT_INVALID");
                if(refreshCount==3&&(state!=State.BLOCKED||nextWaitEventId!=null)) throw new IllegalArgumentException("MEMORY_RECEIPT_LIMIT_INVALID");
            }
            if(nextWaitEventId!=null&&(nextWaitEventId.equals(waitEventId)||candidatePhase!=CandidatePhase.APPLIED_EXPIRED||state!=State.WAITING_CONTEXT||refreshCount>=3||dispatchAllowed))
                throw new IllegalArgumentException("MEMORY_RECEIPT_NEXT_WAIT_INVALID");
            if((resultCode==Code.CPU_CONFIRMED||resultCode==Code.CONTINUATION_AUTH_UNSUPPORTED)&&(candidatePhase!=null||packetRevision!=null))
                throw new IllegalArgumentException("MEMORY_RECEIPT_MODE_INVALID");
        }
    }
    public static final class Deserializer extends StdDeserializer<MemoryResumeReceipt> {
        public Deserializer() { super(MemoryResumeReceipt.class); }
        @Override public MemoryResumeReceipt deserialize(JsonParser parser,DeserializationContext context) throws IOException {
            JsonNode node=parser.getCodec().readTree(parser);
            if(node.isObject()&&node.size()==2&&node.has("code")&&node.has("receipt_ref")) {
                Wire.check(node,MemoryResumeReceipt.class);
                return new MemoryResumeReceipt(Wire.text(node,"code"),Wire.text(node,"receipt_ref"));
            }
            Wire.exact(node,MemoryResumeReceipt.class);
            return new MemoryResumeReceipt(Code.valueOf(Wire.text(node,"code")),Wire.text(node,"receipt_ref"),Wire.text(node,"wait_event_id"),nullableLong(node,"packet_revision"),nullableLong(node,"execution_revision"),nullableLong(node,"current_packet_revision"),Wire.text(node,"current_context_fingerprint"),Wire.number(node,"refresh_count"),State.valueOf(Wire.text(node,"state")),node.get("candidate_phase").isNull()?null:CandidatePhase.valueOf(Wire.text(node,"candidate_phase")),Wire.text(node,"next_wait_event_id"),Wire.bool(node,"dispatch_allowed"));
        }
        private Long nullableLong(JsonNode node,String key) { return node.get(key).isNull()?null:Wire.number(node,key); }
    }
    public static final class Serializer extends StdSerializer<MemoryResumeReceipt> {
        public Serializer() { super(MemoryResumeReceipt.class); }
        @Override public void serialize(MemoryResumeReceipt value,JsonGenerator gen,SerializerProvider provider) throws IOException {
            gen.writeStartObject(); gen.writeStringField("code",value.code()); gen.writeStringField("receipt_ref",value.receiptRef);
            if(value.state!=null) {
                gen.writeStringField("wait_event_id",value.waitEventId); gen.writeObjectField("packet_revision",value.packetRevision); gen.writeObjectField("execution_revision",value.executionRevision);
                gen.writeObjectField("current_packet_revision",value.currentPacketRevision); gen.writeStringField("current_context_fingerprint",value.currentContextFingerprint);
                gen.writeNumberField("refresh_count",value.refreshCount); gen.writeStringField("state",value.state.name()); gen.writeObjectField("candidate_phase",value.candidatePhase);
                gen.writeStringField("next_wait_event_id",value.nextWaitEventId); gen.writeBooleanField("dispatch_allowed",value.dispatchAllowed);
            }
            gen.writeEndObject();
        }
    }
}
