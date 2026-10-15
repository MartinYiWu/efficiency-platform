package com.aiep.aihub.repository.operation;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface OperationMessageMapper extends BaseMapper<OperationMessagePO> {
    default List<OperationMessagePO> selectConversationMessages(String conversationId, String tenantId) {
        return selectList(new LambdaQueryWrapper<OperationMessagePO>()
                .eq(OperationMessagePO::getConversationId, conversationId)
                .eq(OperationMessagePO::getTenantId, tenantId)
                .orderByAsc(OperationMessagePO::getCreatedAt)
                .orderByAsc(OperationMessagePO::getId));
    }
}
