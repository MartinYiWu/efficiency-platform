package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryPacketMapper;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 仅接受由运行时实际输入manifest给出的闭包；调用者必须先核对签发包及业务归属。 */
@Service
public class MemoryDependencyService {
    private final MemoryPacketMapper mapper;
    private final Clock clock;
    @Autowired public MemoryDependencyService(MemoryPacketMapper mapper) { this(mapper, Clock.systemUTC()); }
    public MemoryDependencyService(MemoryPacketMapper mapper, Clock clock) { this.mapper = mapper; this.clock = clock; }

    public Instant requireCurrent(MemoryScopeDTO scope, List<Dependency> dependencies) {
        Instant earliest = Instant.MAX;
        for (var dependency : dependencies.stream().sorted((left,right) -> Arrays.compareUnsigned(MemoryMapper.identity(left.sourceId()),MemoryMapper.identity(right.sourceId()))).toList()) {
            var source = mapper.findSource(MemoryMapper.identity(scope.tenantId()), MemoryMapper.identity(dependency.sourceId()));
            if (source == null || source.blocked() || source.retentionDeadline() == null
                    || !source.retentionDeadline().isAfter(clock.instant())
                    || !source.sourceType().equals(dependency.sourceType())
                    || !Arrays.equals(source.id(), MemoryMapper.identity(dependency.sourceId()))
                    || !Arrays.equals(source.sourceVersion(), MemoryMapper.identity(dependency.sourceVersion()))
                    || source.grantEpoch() != dependency.grantEpoch()
                    || source.sourceEpoch() != dependency.sourceEpoch()
                    || source.deletionEpoch() != dependency.deletionEpoch())
                throw new MemoryException("MEMORY_SOURCE_CHANGED");
            if (source.retentionDeadline().isBefore(earliest)) earliest = source.retentionDeadline();
        }
        return earliest;
    }

    public List<Dependency> dependencies(MemoryScopeDTO scope, String type, String target, String version) {
        return MemoryPacketDigest.dependencies(mapper.findDependencies(MemoryMapper.identity(scope.tenantId()),
                type, MemoryMapper.identity(target), MemoryMapper.identity(version)));
    }

    @Transactional
    public List<Dependency> record(MemoryScopeDTO scope, String type, String target, String version,
            String execution, List<Dependency> authorized, List<List<Dependency>> actualInputs,
            List<Dependency> displayCitations) {
        if (!Set.of("MESSAGE", "SUMMARY", "TASK_CAPSULE", "EXECUTION").contains(type))
            throw new MemoryException("MEMORY_TARGET_INVALID");
        var all = new ArrayList<Dependency>(); actualInputs.forEach(all::addAll);
        var closure = MemoryPacketDigest.dependencies(all);
        if (!authorized.containsAll(closure)) throw new MemoryException("MEMORY_MANIFEST_SOURCE_DENIED");
        requireCurrent(scope, closure);
        var existing = dependencies(scope, type, target, version);
        if (!existing.isEmpty()) {
            if (!existing.equals(closure)) throw new MemoryException("MEMORY_MANIFEST_CONFLICT");
            return existing;
        }
        for (var dependency : closure) {
            int changed = mapper.insertDependency(MemoryMapper.identity(scope.tenantId()),
                    MemoryMapper.identity(dependency.sourceId()), type, MemoryMapper.identity(target),
                    MemoryMapper.identity(version), MemoryMapper.identity(execution), dependency.grantEpoch(),
                    dependency.sourceEpoch(), dependency.deletionEpoch());
            if (changed != 1) throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");
        }
        return closure;
    }
}
