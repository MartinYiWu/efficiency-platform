package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemorySharingContracts.*;
import com.aiep.identity.api.IdentityFacade;
import java.util.List;
import org.springframework.stereotype.Service;

/** 同用户跨Agent授权入口，统一复用共享的来源/投影/撤销判定。 */
@Service
public class MemoryAgentGrantService {
    private final MemorySharingService sharing;
    public MemoryAgentGrantService(MemorySharingService sharing){this.sharing=sharing;}
    public GrantView grant(IdentityFacade.Subject actor,GrantCommand command){return sharing.grantAgent(actor,command);}
    public List<GrantView> list(IdentityFacade.Subject actor,String origin){return sharing.listAgentGrants(actor,origin);}
    public GrantView withdraw(IdentityFacade.Subject actor,String id,RevisionCommand command){return sharing.withdrawAgent(actor,id,command);}
}
