package com.aiep.aihub.api.memory;

import com.aiep.identity.api.IdentityFacade;
import java.util.List;
import java.util.Set;

/** 同模块及跨模块记忆入口；actor仅由服务端身份解析，所有操作重新核验原登录。 */
public interface MemoryFacade {
    List<MemoryContracts.Preference> listPreferences(IdentityFacade.Subject actor, MemoryScopeDTO scope, Set<String> fieldKeys);
    MemoryContracts.Preference savePreference(IdentityFacade.Subject actor, MemoryContracts.PreferenceCommand command);
    MemoryContracts.Preference correctPreference(IdentityFacade.Subject actor, String id, MemoryContracts.PreferenceCommand command);
    String forget(IdentityFacade.Subject actor, String id, MemoryContracts.ForgetCommand command);
    MemoryContracts.Packet assemblePacket(IdentityFacade.Subject actor, MemoryContracts.Execution execution);
}
