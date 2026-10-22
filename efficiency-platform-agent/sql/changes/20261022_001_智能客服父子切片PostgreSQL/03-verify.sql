-- 只读验证：零行代表没有孤儿父子关系。
SELECT c.chunk_id, c.document_version_id
FROM customer_service.document_chunk c
LEFT JOIN customer_service.document_parent p ON p.parent_id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND (p.parent_id IS NULL OR p.document_version_id <> c.document_version_id);

SELECT p.document_version_id, COUNT(*) AS parent_count
FROM customer_service.document_parent p
GROUP BY p.document_version_id
ORDER BY p.document_version_id;

SELECT c.document_version_id,
       COUNT(*) AS child_count,
       COUNT(*) FILTER (WHERE c.parent_id IS NULL) AS legacy_child_count,
       COUNT(*) FILTER (WHERE c.parent_id IS NOT NULL
           AND (c.child_no IS NULL OR c.start_offset IS NULL OR c.end_offset IS NULL))
           AS invalid_position_count
FROM customer_service.document_chunk c
GROUP BY c.document_version_id
ORDER BY c.document_version_id;

-- 零行代表已关联子片段的原文位置、租户与文档归属一致。
SELECT c.chunk_id, c.parent_id, c.document_version_id,
       c.start_offset, c.end_offset
FROM customer_service.document_chunk c
JOIN customer_service.document_parent p ON p.parent_id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND (
      c.tenant_id <> p.tenant_id
      OR c.knowledge_base_id <> p.knowledge_base_id
      OR c.document_id <> p.document_id
      OR c.start_offset IS NULL
      OR c.end_offset IS NULL
      OR c.end_offset > length(p.content)
      OR substring(p.content FROM c.start_offset + 1
                   FOR c.end_offset - c.start_offset) <> c.content
  );
