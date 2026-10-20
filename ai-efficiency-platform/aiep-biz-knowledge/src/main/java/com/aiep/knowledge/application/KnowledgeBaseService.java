package com.aiep.knowledge.application;

import com.aiep.knowledge.domain.KnowledgeEnums.BaseStatus;
import com.aiep.knowledge.domain.KnowledgeEnums.DirectoryStatus;
import com.aiep.knowledge.domain.KnowledgeEnums.KnowledgeType;
import com.aiep.knowledge.repository.KnowledgeBasePO;
import com.aiep.knowledge.repository.KnowledgeDirectoryPO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class KnowledgeBaseService {
    public static final String TENANT_ID = "dev";
    public static final String USER_ID = "1";
    private final KnowledgeMappers repository;

    public KnowledgeBaseService(KnowledgeMappers repository) {
        this.repository = repository;
    }

    @Transactional
    public KnowledgeViews.KnowledgeBaseView create(String code, String name, String description, String knowledgeType) {
        String normalizedCode = required(code, "知识库编码").toUpperCase();
        if (!normalizedCode.matches("[A-Z][A-Z0-9_-]{1,127}")) {
            throw new KnowledgeException("KB_CODE_INVALID", "知识库编码格式无效");
        }
        if (repository.findBaseByCode(TENANT_ID, normalizedCode) != null) {
            throw new KnowledgeException("KB_CODE_DUPLICATE", "知识库编码已存在");
        }
        String type = enumValue(KnowledgeType.class, knowledgeType, "KB_TYPE_INVALID");
        LocalDateTime now = LocalDateTime.now();
        KnowledgeBasePO value = new KnowledgeBasePO(
                UUID.randomUUID().toString(), TENANT_ID, normalizedCode, required(name, "知识库名称"),
                optional(description, 2000), type, "COMPANY_WIDE", null, BaseStatus.DRAFT.name(),
                null, USER_ID, now, USER_ID, now);
        repository.insertBase(value);
        return toView(value);
    }

    @Transactional
    public KnowledgeViews.KnowledgeBaseView update(
            String id, String name, String description, String knowledgeType, String status) {
        KnowledgeBasePO current = requiredBase(id);
        KnowledgeBasePO updated = new KnowledgeBasePO(
                current.id(), current.tenantId(), current.code(), required(name, "知识库名称"),
                optional(description, 2000), enumValue(KnowledgeType.class, knowledgeType, "KB_TYPE_INVALID"),
                "COMPANY_WIDE", current.ownerDepartmentId(),
                enumValue(BaseStatus.class, status, "KB_STATUS_INVALID"), current.currentIndexReleaseId(),
                current.createdBy(), current.createdAt(), USER_ID, LocalDateTime.now());
        repository.updateBase(updated);
        return toView(updated);
    }

    public KnowledgeViews.KnowledgeBaseView get(String id) {
        return toView(requiredBase(id));
    }

    public KnowledgeViews.PageView<KnowledgeViews.KnowledgeBaseView> list(
            String keyword, String type, String status, int page, int pageSize) {
        Page pageValue = page(page, pageSize);
        List<KnowledgeViews.KnowledgeBaseView> items = repository.listBases(
                        TENANT_ID, keyword, type, status, pageValue.offset(), pageValue.pageSize())
                .stream().map(KnowledgeBaseService::toView).toList();
        return new KnowledgeViews.PageView<>(items, pageValue.page(), pageValue.pageSize(),
                repository.countBases(TENANT_ID, keyword, type, status));
    }

    @Transactional
    public KnowledgeViews.DirectoryView createDirectory(
            String baseId, String parentId, String name, int sortNo) {
        requiredBase(baseId);
        repository.lockBase(baseId);
        String normalizedName = required(name, "目录名称");
        if (repository.findDirectoryByName(baseId, parentId, normalizedName) != null) {
            throw new KnowledgeException("KB_DIRECTORY_DUPLICATE", "同级目录名称已存在");
        }
        KnowledgeDirectoryPO parent = parentId == null ? null : requiredDirectory(baseId, parentId);
        if (parent != null && !DirectoryStatus.ACTIVE.name().equals(parent.status())) {
            throw new KnowledgeException("KB_DIRECTORY_DISABLED", "父目录已停用");
        }
        LocalDateTime now = LocalDateTime.now();
        String id = UUID.randomUUID().toString();
        String path = parent == null ? "/" + id : parent.path() + "/" + id;
        KnowledgeDirectoryPO value = new KnowledgeDirectoryPO(
                id, baseId, parentId, normalizedName, path, sortNo, DirectoryStatus.ACTIVE.name(),
                USER_ID, now, USER_ID, now);
        repository.insertDirectory(value);
        return toView(value);
    }

    @Transactional
    public KnowledgeViews.DirectoryView updateDirectory(String id, String name, int sortNo, String status) {
        KnowledgeDirectoryPO current = findDirectory(id);
        repository.lockBase(current.knowledgeBaseId());
        String normalizedName = required(name, "目录名称");
        KnowledgeDirectoryPO duplicate = repository.findDirectoryByName(
                current.knowledgeBaseId(), current.parentId(), normalizedName);
        if (duplicate != null && !duplicate.id().equals(id)) {
            throw new KnowledgeException("KB_DIRECTORY_DUPLICATE", "同级目录名称已存在");
        }
        KnowledgeDirectoryPO value = new KnowledgeDirectoryPO(
                current.id(), current.knowledgeBaseId(), current.parentId(), normalizedName,
                current.path(), sortNo, enumValue(DirectoryStatus.class, status, "KB_DIRECTORY_STATUS_INVALID"),
                current.createdBy(), current.createdAt(), USER_ID, LocalDateTime.now());
        repository.updateDirectory(value);
        return toView(value);
    }

    public List<KnowledgeViews.DirectoryView> listDirectories(String baseId) {
        requiredBase(baseId);
        return repository.listDirectories(baseId).stream().map(KnowledgeBaseService::toView).toList();
    }

    public KnowledgeBasePO requiredActiveBase(String id) {
        KnowledgeBasePO value = requiredBase(id);
        if (!BaseStatus.ACTIVE.name().equals(value.status())) {
            throw new KnowledgeException("KB_BASE_NOT_ACTIVE", "知识库未启用");
        }
        return value;
    }

    public void requireActiveDirectory(String baseId, String directoryId) {
        if (directoryId == null || directoryId.isBlank()) return;
        KnowledgeDirectoryPO value = requiredDirectory(baseId, directoryId);
        if (!DirectoryStatus.ACTIVE.name().equals(value.status())) {
            throw new KnowledgeException("KB_DIRECTORY_DISABLED", "目录已停用");
        }
    }

    private KnowledgeBasePO requiredBase(String id) {
        KnowledgeBasePO value = repository.findBase(TENANT_ID, id);
        if (value == null) throw new KnowledgeException("KB_BASE_NOT_FOUND", "知识库不存在");
        return value;
    }
    private KnowledgeDirectoryPO requiredDirectory(String baseId, String id) {
        KnowledgeDirectoryPO value = repository.findDirectory(baseId, id);
        if (value == null) throw new KnowledgeException("KB_DIRECTORY_NOT_FOUND", "目录不存在");
        return value;
    }
    private KnowledgeDirectoryPO findDirectory(String id) {
        KnowledgeDirectoryPO found = repository.findDirectoryById(id);
        if (found != null) return found;
        throw new KnowledgeException("KB_DIRECTORY_NOT_FOUND", "目录不存在");
    }

    static KnowledgeViews.KnowledgeBaseView toView(KnowledgeBasePO v) {
        return new KnowledgeViews.KnowledgeBaseView(v.id(), v.code(), v.name(), v.description(),
                v.knowledgeType(), v.visibilityScope(), v.status(), v.currentIndexReleaseId(),
                v.createdAt(), v.updatedAt());
    }
    static KnowledgeViews.DirectoryView toView(KnowledgeDirectoryPO v) {
        return new KnowledgeViews.DirectoryView(v.id(), v.knowledgeBaseId(), v.parentId(),
                v.name(), v.path(), v.sortNo(), v.status());
    }
    static String required(String value, String field) {
        if (value == null || value.isBlank()) throw new KnowledgeException("KB_VALIDATION_FAILED", field + "不能为空");
        return value.strip();
    }
    static String optional(String value, int maxLength) {
        if (value == null || value.isBlank()) return null;
        String result = value.strip();
        if (result.length() > maxLength) throw new KnowledgeException("KB_VALIDATION_FAILED", "字段长度超限");
        return result;
    }
    static <E extends Enum<E>> String enumValue(Class<E> type, String value, String code) {
        try { return Enum.valueOf(type, required(value, "枚举字段").toUpperCase()).name(); }
        catch (IllegalArgumentException exception) { throw new KnowledgeException(code, "枚举值无效"); }
    }
    static Page page(int page, int pageSize) {
        int normalizedPage = Math.max(page, 1);
        int normalizedSize = Math.min(Math.max(pageSize, 1), 100);
        return new Page(normalizedPage, normalizedSize, (normalizedPage - 1) * normalizedSize);
    }
    record Page(int page, int pageSize, int offset) { }
}
