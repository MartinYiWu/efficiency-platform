package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.ObjectCodec;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;
import java.io.IOException;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.*;

/** 仅内部查询的原等待引用；所有字段显式出现，空值仅用于尚未准备或无图的等待。 */
@JsonDeserialize(using = MemoryContextWait.Deserializer.class)
public record MemoryContextWait(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("wait_event_id") String waitEventId,
        @JsonProperty("runtime_id") String runtimeId,
        @JsonProperty("task_id") String taskId,
        @JsonProperty("execution_id") String executionId,
        MemoryContextEnvelope.Scope scope,
        @JsonProperty("expected_packet_revision") long expectedPacketRevision,
        @JsonProperty("expected_execution_revision") long expectedExecutionRevision,
        @JsonProperty("expected_current_context_fingerprint") String expectedCurrentContextFingerprint,
        @JsonProperty("operation_hash") String operationHash,
        @JsonProperty("logical_operation_id") String logicalOperationId,
        @JsonProperty("semantic_input_hash") String semanticInputHash,
        @JsonProperty("canonical_request_hmac") String canonicalRequestHmac,
        long attempt,
        @JsonProperty("stage_id") String stageId,
        @JsonProperty("stage_slot") Long stageSlot,
        @JsonProperty("checkpoint_mode") CheckpointMode checkpointMode,
        @JsonProperty("checkpoint_ns") String checkpointNs,
        @JsonProperty("checkpoint_id") String checkpointId,
        @JsonProperty("wait_phase") WaitPhase waitPhase,
        @JsonProperty("original_deadline") long originalDeadline,
        @JsonProperty("refresh_count") long refreshCount) {
    public enum WaitPhase { BEFORE_PREPARE, PREPARED, RESERVED }
    public enum CheckpointMode { GRAPH, NONE }
    public enum RecordKind { WAIT, REFRESH, RESULT }
    public enum ResultPhase { CAPTURED }
    public MemoryContextWait {
        if (!"memory-context-wait/1".equals(contractVersion) || scope == null || checkpointMode == null || waitPhase == null)
            throw new IllegalArgumentException("MEMORY_WAIT_INVALID");
        for (String id : new String[]{waitEventId, runtimeId, taskId, executionId, logicalOperationId}) Wire.id(id);
        for (long count : new long[]{expectedPacketRevision, expectedExecutionRevision, attempt, originalDeadline, refreshCount}) Wire.count(count);
        if(expectedPacketRevision<1||expectedExecutionRevision<1||originalDeadline<1||attempt<1||attempt>3)
            throw new IllegalArgumentException("MEMORY_WAIT_ANCHOR_INVALID");
        if (refreshCount > 3) throw new IllegalArgumentException("CONTEXT_REFRESH_LIMIT");
        Wire.digest(operationHash); Wire.digest(semanticInputHash); Wire.digest(expectedCurrentContextFingerprint);
        if (waitPhase == WaitPhase.BEFORE_PREPARE) {
            if (canonicalRequestHmac != null) throw new IllegalArgumentException("MEMORY_WAIT_HMAC_INVALID");
        } else Wire.digest(canonicalRequestHmac);
        if ((stageId == null) != (stageSlot == null)) throw new IllegalArgumentException("MEMORY_STAGE_INVALID");
        if (stageId != null) {
            Wire.id(stageId); Wire.count(stageSlot);
            if(stageSlot<1||stageSlot>3) throw new IllegalArgumentException("MEMORY_STAGE_INVALID");
        }
        if (checkpointMode == CheckpointMode.GRAPH) {
            if(!"".equals(checkpointNs)) Wire.id(checkpointNs);
            Wire.id(checkpointId);
        }
        else if (checkpointNs != null || checkpointId != null) throw new IllegalArgumentException("MEMORY_CHECKPOINT_INVALID");
    }
    public static final class Deserializer extends StdDeserializer<MemoryContextWait> {
        public Deserializer() { super(MemoryContextWait.class); }
        @Override public MemoryContextWait deserialize(JsonParser parser, DeserializationContext context) throws IOException {
            JsonNode node = parser.getCodec().readTree(parser);
            Wire.exact(node, MemoryContextWait.class);
            return new MemoryContextWait(Wire.text(node,"contract_version"), Wire.text(node,"wait_event_id"), Wire.text(node,"runtime_id"),
                    Wire.text(node,"task_id"), Wire.text(node,"execution_id"), parser.getCodec().treeToValue(node.get("scope"),MemoryContextEnvelope.Scope.class),
                    Wire.number(node,"expected_packet_revision"), Wire.number(node,"expected_execution_revision"), Wire.text(node,"expected_current_context_fingerprint"), Wire.text(node,"operation_hash"),
                    Wire.text(node,"logical_operation_id"), Wire.text(node,"semantic_input_hash"), Wire.text(node,"canonical_request_hmac"), Wire.number(node,"attempt"),
                    Wire.text(node,"stage_id"), node.get("stage_slot").isNull()?null:Wire.number(node,"stage_slot"),
                    CheckpointMode.valueOf(Wire.text(node,"checkpoint_mode")), Wire.text(node,"checkpoint_ns"), Wire.text(node,"checkpoint_id"),
                    WaitPhase.valueOf(Wire.text(node,"wait_phase")), Wire.number(node,"original_deadline"), Wire.number(node,"refresh_count"));
        }
    }
    /** 三个刷新DTO共享严格JSON形状检查，不依赖应用ObjectMapper的宽松选项。 */
    static final class Wire {
        static void id(String value) { MemoryContextPacket.requireId(value); }
        static void count(long value) { if(value<0) throw new IllegalArgumentException("COUNT_INVALID"); }
        static void digest(String value) { if(value==null || !value.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("MEMORY_DIGEST_INVALID"); }
        static String text(JsonNode node,String name) { JsonNode value=node.get(name); if(value==null) throw new IllegalArgumentException("MEMORY_FIELD_REQUIRED"); return value.isNull()?null:value.textValue(); }
        static long number(JsonNode node,String name) { JsonNode value=node.get(name); if(value==null||!value.isIntegralNumber()||!value.canConvertToLong()) throw new IllegalArgumentException("COUNT_INVALID"); return value.longValue(); }
        static boolean bool(JsonNode node,String name) { JsonNode value=node.get(name); if(value==null||!value.isBoolean()) throw new IllegalArgumentException("BOOLEAN_INVALID"); return value.booleanValue(); }
        static void exact(JsonNode node,Class<?> type) {
            check(node,type);
            if(node.size()!=type.getRecordComponents().length) throw new IllegalArgumentException("MEMORY_FIELD_REQUIRED");
        }
        static void check(JsonNode node,Type type) {
            if(node==null||node.isNull()) {
                if(type instanceof Class<?> cls && cls.isPrimitive()) throw new IllegalArgumentException("MEMORY_FIELD_REQUIRED");
                return;
            }
            if(type instanceof ParameterizedType generic) {
                if(!node.isArray()) throw new IllegalArgumentException("MEMORY_TYPE_INVALID");
                for(JsonNode child:node) check(child,generic.getActualTypeArguments()[0]);
                return;
            }
            Class<?> cls=(Class<?>)type;
            if(cls==String.class||cls.isEnum()) {
                if(!node.isTextual()) throw new IllegalArgumentException("MEMORY_TYPE_INVALID");
            } else if(cls==boolean.class||cls==Boolean.class) {
                if(!node.isBoolean()) throw new IllegalArgumentException("BOOLEAN_INVALID");
            } else if(cls==long.class||cls==Long.class||cls==int.class) {
                if(!node.isIntegralNumber()||!node.canConvertToLong()||(cls==int.class&&!node.canConvertToInt())) throw new IllegalArgumentException("COUNT_INVALID");
            } else if(cls.isRecord()) {
                if(!node.isObject()) throw new IllegalArgumentException("MEMORY_TYPE_INVALID");
                Map<String,Type> fields=new HashMap<>();
                for(var field:cls.getRecordComponents()) {
                    JsonProperty annotation=field.getAnnotation(JsonProperty.class);
                    // JsonProperty也可能仅传播到访问器。
                    if(annotation==null) annotation=field.getAccessor().getAnnotation(JsonProperty.class);
                    fields.put(annotation==null?field.getName():annotation.value(),field.getGenericType());
                }
                var names=node.fieldNames();
                while(names.hasNext()) {
                    String name=names.next();
                    if(!fields.containsKey(name)) throw new IllegalArgumentException("MEMORY_UNKNOWN_FIELD");
                    check(node.get(name),fields.get(name));
                }
            }
        }
        static Object canonical(JsonNode node,String path) {
            if(node.isObject()) {
                Map<String,Object> map=new TreeMap<>();
                node.fields().forEachRemaining(entry->map.put(entry.getKey(),canonical(entry.getValue(),path+"/"+entry.getKey())));
                return map;
            }
            if(node.isArray()) {
                List<Object> values=new ArrayList<>();
                for(JsonNode child:node) values.add(canonical(child,path));
                if(path.startsWith("/refreshed_context/authorization/policy/")) {
                    values=new ArrayList<>(new HashSet<>(values));
                    values.sort((a,b)->Arrays.compareUnsigned(a.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8),b.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)));
                }
                return values;
            }
            if(node.isNull()) return null;
            if(node.isTextual()) return node.textValue();
            if(node.isBoolean()) return node.booleanValue();
            return node.longValue();
        }
    }
}
