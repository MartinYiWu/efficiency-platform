package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptMessageTemplatePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVariablePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ConditionalOnBean(JdbcTemplate.class)
public class AiPromptManagementService {
    private static final String USER_ID = "1";
    private static final Pattern VARIABLE = Pattern.compile("\\{\\{([a-zA-Z][a-zA-Z0-9_]*)}}");
    private static final Set<String> ROLES = Set.of("SYSTEM", "DEVELOPER", "USER", "ASSISTANT");
    private final AiManagementMappers repository;

    public AiPromptManagementService(AiManagementMappers repository) {
        this.repository = repository;
    }

    public List<PromptDefinitionPO> list(String scope, String ownerAgentId) {
        return repository.listPrompts(scope, ownerAgentId);
    }

    public AiManagementViews.PromptDetail getVersion(String versionId) {
        PromptVersionPO version = requiredVersion(versionId);
        return new AiManagementViews.PromptDetail(
                requiredDefinition(version.promptDefinitionId()), version,
                repository.listPromptMessages(versionId), repository.listPromptVariables(versionId));
    }

    @Transactional
    public PromptDefinitionPO createDefinition(
            String promptKey, String scope, String ownerAgentId,
            String name, String description, String stageKey) {
        String normalizedScope = AiAgentManagementService.required(scope, "Prompt 范围").toUpperCase();
        if (!Set.of("SHARED", "PRIVATE").contains(normalizedScope)
                || ("SHARED".equals(normalizedScope) && ownerAgentId != null)
                || ("PRIVATE".equals(normalizedScope) && (ownerAgentId == null || ownerAgentId.isBlank()))) {
            throw new AiManagementException("AI_PROMPT_SCOPE_INVALID", "共享 Prompt 不得设置 owner，私有 Prompt 必须设置 owner");
        }
        LocalDateTime now = LocalDateTime.now();
        PromptDefinitionPO value = new PromptDefinitionPO(
                UUID.randomUUID().toString(), AiAgentManagementService.required(promptKey, "Prompt 编码"),
                normalizedScope, ownerAgentId, AiAgentManagementService.required(name, "Prompt 名称"),
                description, AiAgentManagementService.required(stageKey, "阶段编码"),
                "ACTIVE", USER_ID, now, USER_ID, now);
        repository.insertPromptDefinition(value);
        return value;
    }

    @Transactional
    public PromptVersionPO createVersion(String promptId, String semanticVersion, String changeSummary) {
        requiredDefinition(promptId);
        PromptVersionPO value = new PromptVersionPO(
                UUID.randomUUID().toString(), promptId,
                AiAgentManagementService.required(semanticVersion, "版本号"), "DRAFT",
                "0".repeat(64), AiAgentManagementService.required(changeSummary, "变更说明"),
                USER_ID, LocalDateTime.now(), null);
        repository.insertPromptVersion(value);
        return value;
    }

    @Transactional
    public PromptVersionPO replaceDraft(
            String versionId, List<MessageInput> messageInputs, List<VariableInput> variableInputs) {
        PromptVersionPO current = requiredVersion(versionId);
        AiAgentManagementService.mutable(current.status());
        if (messageInputs == null || messageInputs.isEmpty()) {
            throw new AiManagementException("AI_PROMPT_MESSAGES_REQUIRED", "Prompt 至少需要一条消息模板");
        }
        Set<Integer> ordinals = new HashSet<>();
        Set<String> messageKeys = new HashSet<>();
        List<PromptMessageTemplatePO> messages = messageInputs.stream().map(input -> {
            String role = AiAgentManagementService.required(input.role(), "消息角色").toUpperCase();
            if (!ROLES.contains(role) || !ordinals.add(input.ordinal())
                    || !messageKeys.add(AiAgentManagementService.required(input.messageKey(), "消息编码"))) {
                throw new AiManagementException("AI_PROMPT_MESSAGE_INVALID", "消息角色、顺序或编码无效");
            }
            String content = AiAgentManagementService.required(input.contentTemplate(), "消息模板");
            return new PromptMessageTemplatePO(
                    UUID.randomUUID().toString(), versionId, input.ordinal(), role,
                    input.messageKey().strip(), content, "TEXT", input.trustedInstruction(), sha256(content));
        }).sorted(java.util.Comparator.comparingInt(PromptMessageTemplatePO::ordinal)).toList();
        if (!Set.of("SYSTEM", "DEVELOPER").contains(messages.getFirst().role())) {
            throw new AiManagementException("AI_PROMPT_MESSAGE_INVALID", "首条消息必须是 SYSTEM 或 DEVELOPER 角色");
        }
        Set<String> declared = new HashSet<>();
        List<PromptVariablePO> variables = (variableInputs == null ? List.<VariableInput>of() : variableInputs)
                .stream().map(input -> {
                    PromptMessageTemplatePO message = messages.stream()
                            .filter(item -> item.messageKey().equals(input.messageKey())).findFirst()
                            .orElseThrow(() -> new AiManagementException(
                                    "AI_PROMPT_VARIABLE_INVALID", "变量引用的消息不存在"));
                    String name = AiAgentManagementService.required(input.variableName(), "变量名");
                    if (!declared.add(message.messageKey() + ":" + name)) {
                        throw new AiManagementException("AI_PROMPT_VARIABLE_INVALID", "变量声明重复");
                    }
                    return new PromptVariablePO(
                            UUID.randomUUID().toString(), message.id(), name,
                            AiAgentManagementService.required(input.valueType(), "变量类型").toUpperCase(),
                            AiAgentManagementService.required(input.valueSource(), "变量来源").toUpperCase(),
                            input.required(), input.sensitive(), input.maxLength(), input.allowUntrustedContent());
                }).toList();
        assertVariablesDeclared(messages, declared);
        String checksum = sha256(messages.stream()
                .map(value -> value.role() + "\n" + value.contentTemplate())
                .collect(java.util.stream.Collectors.joining("\n---\n")));
        PromptVersionPO updated = new PromptVersionPO(
                current.id(), current.promptDefinitionId(), current.semanticVersion(), current.status(),
                checksum, current.changeSummary(), current.createdBy(), current.createdAt(), current.publishedAt());
        repository.replacePromptMessages(versionId, messages, variables);
        repository.updatePromptVersion(updated);
        return updated;
    }

    @Transactional
    public PromptVersionPO transition(String versionId, String targetStatus) {
        PromptVersionPO current = requiredVersion(versionId);
        String target = AiAgentManagementService.required(targetStatus, "目标状态").toUpperCase();
        String expected = switch (current.status()) {
            case "DRAFT" -> "VALIDATED";
            case "VALIDATED" -> "PUBLISHED";
            case "PUBLISHED" -> "RETIRED";
            default -> null;
        };
        if (!target.equals(expected)) {
            throw new AiManagementException("AI_ASSET_STATE_INVALID", "Prompt 版本状态流转无效");
        }
        if ("VALIDATED".equals(target) && repository.listPromptMessages(versionId).isEmpty()) {
            throw new AiManagementException("AI_PROMPT_MESSAGES_REQUIRED", "Prompt 消息模板为空");
        }
        PromptVersionPO updated = new PromptVersionPO(
                current.id(), current.promptDefinitionId(), current.semanticVersion(), target,
                current.checksum(), current.changeSummary(), current.createdBy(), current.createdAt(),
                "PUBLISHED".equals(target) ? LocalDateTime.now() : current.publishedAt());
        repository.updatePromptVersion(updated);
        return updated;
    }

    @Transactional
    public void bind(
            String agentVersionId, String promptVersionId,
            String stageKey, int ordinal, boolean required) {
        AgentVersionPO agentVersion = repository.findAgentVersion(agentVersionId);
        PromptVersionPO promptVersion = requiredVersion(promptVersionId);
        if (agentVersion == null) {
            throw new AiManagementException("AI_AGENT_VERSION_NOT_FOUND", "Agent 版本不存在");
        }
        AiAgentManagementService.mutable(agentVersion.status());
        if (!"PUBLISHED".equals(promptVersion.status())) {
            throw new AiManagementException("AI_PROMPT_NOT_PUBLISHED", "只能绑定已发布 Prompt");
        }
        PromptDefinitionPO definition = requiredDefinition(promptVersion.promptDefinitionId());
        if ("PRIVATE".equals(definition.scope())
                && !agentVersion.agentDefinitionId().equals(definition.ownerAgentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "私有 Prompt 不属于该 Agent");
        }
        repository.insertPromptBinding(new PromptBindingPO(
                agentVersionId, AiAgentManagementService.required(stageKey, "阶段编码"), ordinal,
                definition.id(), promptVersionId, required));
    }

    private void assertVariablesDeclared(
            List<PromptMessageTemplatePO> messages, Set<String> declared) {
        for (PromptMessageTemplatePO message : messages) {
            Matcher matcher = VARIABLE.matcher(message.contentTemplate());
            while (matcher.find()) {
                if (!declared.contains(message.messageKey() + ":" + matcher.group(1))) {
                    throw new AiManagementException(
                            "AI_PROMPT_VARIABLE_UNDECLARED", "模板变量未声明：" + matcher.group(1));
                }
            }
        }
    }

    private PromptDefinitionPO requiredDefinition(String id) {
        PromptDefinitionPO value = repository.findPromptDefinition(id);
        if (value == null) {
            throw new AiManagementException("AI_PROMPT_NOT_FOUND", "Prompt 不存在");
        }
        return value;
    }

    private PromptVersionPO requiredVersion(String id) {
        PromptVersionPO value = repository.findPromptVersion(id);
        if (value == null) {
            throw new AiManagementException("AI_PROMPT_VERSION_NOT_FOUND", "Prompt 版本不存在");
        }
        return value;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    public record MessageInput(
            int ordinal, String role, String messageKey,
            String contentTemplate, boolean trustedInstruction) { }

    public record VariableInput(
            String messageKey, String variableName, String valueType, String valueSource,
            boolean required, boolean sensitive, Integer maxLength,
            boolean allowUntrustedContent) { }
}
