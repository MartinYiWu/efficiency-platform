package com.aiep.aihub.facade.memory;

import com.aiep.aihub.api.memory.MemoryContracts;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryFacade;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.MemoryScopePolicy;
import com.aiep.aihub.application.memory.MemorySessionBindingService;
import com.aiep.aihub.application.memory.MemoryPreferenceService;
import com.aiep.identity.api.IdentityFacade;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;

/** 偏好开放确定性持久化；遗忘与包组装仍明确拒绝。 */
@Service
public class DefaultMemoryFacade implements MemoryFacade {
    private final MemoryScopePolicy policy;
    private final MemorySessionBindingService bindings;
    private final MemoryPreferenceService preferences;
    public DefaultMemoryFacade(MemoryScopePolicy policy) { this(policy,null,null); }
    @org.springframework.beans.factory.annotation.Autowired
    public DefaultMemoryFacade(MemoryScopePolicy policy,MemorySessionBindingService bindings,MemoryPreferenceService preferences) { this.policy=policy;this.bindings=bindings;this.preferences=preferences; }

    public List<MemoryContracts.Preference> listPreferences(IdentityFacade.Subject actor, MemoryScopeDTO scope, Set<String> fieldKeys) {
        policy.require(actor, scope, fieldKeys);
        if(preferences==null)throw new MemoryException("FEATURE_DISABLED");
        bindings.require(actor,scope);
        return preferences.list(actor,scope,fieldKeys);
    }
    public MemoryContracts.Preference savePreference(IdentityFacade.Subject actor, MemoryContracts.PreferenceCommand command) {
        policy.require(actor, command.scope(), Set.of(command.fieldKey()));
        if(preferences==null)throw new MemoryException("FEATURE_DISABLED");
        bindings.require(actor,command.scope());
        return preferences.save(actor,command);
    }
    public MemoryContracts.Preference correctPreference(IdentityFacade.Subject actor, String id, MemoryContracts.PreferenceCommand command) {
        policy.require(actor, command.scope(), Set.of(command.fieldKey()));
        if(preferences==null)throw new MemoryException("FEATURE_DISABLED");
        bindings.require(actor,command.scope());
        return preferences.correct(actor,id,command);
    }
    public String forget(IdentityFacade.Subject actor, String id, MemoryContracts.ForgetCommand command) {
        policy.require(actor, command.scope(), Set.of());
        throw new MemoryException("FEATURE_DISABLED");
    }
    public MemoryContracts.Packet assemblePacket(IdentityFacade.Subject actor, MemoryContracts.Execution execution) {
        policy.require(actor, execution.scope(), Set.of());
        throw new MemoryException("FEATURE_DISABLED");
    }
}
