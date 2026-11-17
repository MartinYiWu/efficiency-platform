package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

/** 展示档案与模型历史分开；未知旧血缘不会被重新推断为安全输入。 */
@Service
public class MemoryHistoryProjection {
    private final MemoryDependencyService dependencies;
    public MemoryHistoryProjection(MemoryDependencyService dependencies) { this.dependencies = dependencies; }
    public record Message(MemoryScopeDTO scope, String id, String version, String role, String content) {
        @Override public String toString() { return "HistoryMessage[redacted]"; }
    }
    public static Message message(MemoryScopeDTO scope,String id,String role,String content) {
        String normalized=role.toLowerCase(java.util.Locale.ROOT);
        String version="1";
        if("user".equals(normalized))try {
            version=java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                .digest(content.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        }catch(java.security.NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
        return new Message(scope,id,version,normalized,content);
    }
    public List<Message> selectBounded(MemoryScopeDTO scope,List<Message> messages,int maximumMessages,int maximumCharacters) {
        var authorized=select(scope,messages);
        var selected=new ArrayList<Message>();int characters=0;
        for(int index=authorized.size()-1;index>=0&&selected.size()<maximumMessages;index--) {
            var message=authorized.get(index);
            if(!java.util.Set.of("user","assistant").contains(message.role())||message.content()==null||message.content().isBlank()
                ||message.content().length()+characters>maximumCharacters)continue;
            selected.add(message);characters+=message.content().length();
        }
        java.util.Collections.reverse(selected);return List.copyOf(selected);
    }
    public List<Message> select(MemoryScopeDTO authorized, List<Message> messages) {
        if (authorized.historyKey() == null) return List.of();
        var result = new ArrayList<Message>();
        for (var message : messages) {
            if (!authorized.equals(message.scope())) continue;
            var closure = dependencies.dependencies(authorized, "MESSAGE", message.id(), message.version());
            if (closure.isEmpty()) continue;
            try { dependencies.requireCurrent(authorized, closure); }
            catch (MemoryException rejected) {
                if (!"MEMORY_SOURCE_CHANGED".equals(rejected.code())) throw rejected;
                continue;
            }
            result.add(message);
        }
        return List.copyOf(result);
    }
}
