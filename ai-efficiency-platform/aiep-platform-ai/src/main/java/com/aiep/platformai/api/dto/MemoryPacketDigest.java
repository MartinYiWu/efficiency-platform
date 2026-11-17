package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.TreeMap;

/** 与 Python dataclass snake_case JSON 等值；保留数组顺序，仅来源集合排序去重。 */
public final class MemoryPacketDigest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private MemoryPacketDigest() { }
    private static int unicodeCompare(String a, String b) {
        var left = a.codePoints().iterator(); var right = b.codePoints().iterator();
        while (left.hasNext() && right.hasNext()) {
            int comparison = Integer.compare(left.nextInt(), right.nextInt());
            if (comparison != 0) return comparison;
        }
        return Boolean.compare(left.hasNext(), right.hasNext());
    }
    public static final Comparator<MemoryContextPacket.Dependency> DEPENDENCY_ORDER =
            Comparator.comparing(MemoryContextPacket.Dependency::sourceType, MemoryPacketDigest::unicodeCompare)
                    .thenComparing(MemoryContextPacket.Dependency::sourceId, MemoryPacketDigest::unicodeCompare)
                    .thenComparing(MemoryContextPacket.Dependency::sourceVersion, MemoryPacketDigest::unicodeCompare)
                    .thenComparingLong(MemoryContextPacket.Dependency::grantEpoch)
                    .thenComparingLong(MemoryContextPacket.Dependency::sourceEpoch)
                    .thenComparingLong(MemoryContextPacket.Dependency::deletionEpoch);
    public static List<MemoryContextPacket.Dependency> dependencies(List<MemoryContextPacket.Dependency> values) {
        return values.stream().distinct().sorted(DEPENDENCY_ORDER).toList();
    }
    public static String digest(MemoryContextPacket packet) { return digest(packet, false); }
    public static String semanticDigest(MemoryContextPacket packet) { return digest(packet, true); }
    private static String digest(MemoryContextPacket packet, boolean semantic) {
        ObjectNode value = JSON.valueToTree(packet);
        value.set("safety_dependencies", JSON.valueToTree(dependencies(packet.safetyDependencies())));
        for (int index = 0; index < packet.items().size(); index++)
            ((ObjectNode) value.path("items").get(index)).set("safety_dependencies",
                    JSON.valueToTree(dependencies(packet.items().get(index).safetyDependencies())));
        if (semantic) value.remove(List.of("packet_revision", "execution_revision", "issued_at", "expires_at"));
        return canonicalDigest(value);
    }
    public static String canonicalDigest(JsonNode value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(JSON.writeValueAsString(sorted(value)).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception failure) { throw new IllegalArgumentException("MEMORY_DIGEST_INVALID"); }
    }
    private static Object sorted(JsonNode value) {
        if (value.isObject()) {
            var result = new TreeMap<String, Object>(MemoryPacketDigest::unicodeCompare);
            value.fields().forEachRemaining(entry -> result.put(entry.getKey(), sorted(entry.getValue())));
            return result;
        }
        if (value.isArray()) {
            var result = new java.util.ArrayList<Object>(); value.forEach(child -> result.add(sorted(child))); return result;
        }
        return value;
    }
}
