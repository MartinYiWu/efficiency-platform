import { expect, type Page } from '@playwright/test';
import type {
  KnowledgeBase,
  KnowledgeDirectory,
  KnowledgeDocument,
  IndexRelease,
  IngestBatch,
} from '../src/entities/knowledge/model';

export const fileName = '知识中心完整事务验收-超长文件名称-产品使用说明与冻结证据模式.md';
export const fileText = '# 产品说明\n\n这是需要保持原文的验收证据。\n';
export async function installKnowledgeJourney(page: Page) {
  const requests: string[] = [];
  const unexpected: string[] = [];
  let base: KnowledgeBase | undefined;
  const directories: KnowledgeDirectory[] = [];
  let document: KnowledgeDocument | undefined;
  let batch: IngestBatch | undefined;
  const releases: IndexRelease[] = [];
  let batchReads = 0;
  let failDirectory = true;
  let uploadCount = 0;
  const now = '2026-11-03T10:00:00';
  const release = (id: string, no: number): IndexRelease => ({
    id,
    knowledgeBaseId: 'journey',
    releaseNo: no,
    status: 'PUBLISHED',
    documentCount: 1,
    chunkCount: 2,
    embeddingModel: 'offline-fixture',
    embeddingDimension: 8,
    checksum: 'offline-checksum',
    previousReleaseId: no === 2 ? 'release-1' : null,
    createdAt: now,
    publishedAt: now,
  });
  await page.route('**/api/knowledge/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const key = `${method} ${path}`;
    requests.push(key);
    const ok = (data: unknown) => route.fulfill({ json: { code: 'SUCCESS', data } });
    if (key === 'GET /api/knowledge/bases')
      return ok({ items: base ? [base] : [], total: base ? 1 : 0, page: 1, pageSize: 10 });
    if (key === 'POST /api/knowledge/bases') {
      expect(request.postDataJSON()).toEqual({
        name: '事务验收产品库',
        code: 'journey',
        knowledgeType: 'PRODUCT_DOCUMENTATION',
        description: '完整业务事务离线验收',
      });
      expect(base).toBeUndefined();
      base = {
        id: 'journey',
        ...request.postDataJSON(),
        status: 'DRAFT',
        visibilityScope: 'COMPANY_WIDE',
        currentIndexReleaseId: null,
        createdAt: now,
        updatedAt: now,
      };
      return ok(base);
    }
    if (key === 'GET /api/knowledge/bases/journey') {
      expect(base).toBeDefined();
      return ok(base);
    }
    if (key === 'PUT /api/knowledge/bases/journey') {
      expect(base?.status).toBe('DRAFT');
      expect(request.postDataJSON()).toEqual({
        name: base?.name,
        description: base?.description,
        knowledgeType: 'PRODUCT_DOCUMENTATION',
        status: 'ACTIVE',
      });
      base!.status = 'ACTIVE';
      return ok(base);
    }
    if (key === 'GET /api/knowledge/bases/journey/directories') return ok(directories);
    if (key === 'POST /api/knowledge/bases/journey/directories') {
      expect(base?.status).toBe('ACTIVE');
      expect(request.postDataJSON()).toEqual({ name: '产品说明', parentId: null, sortNo: 1 });
      if (failDirectory) {
        failDirectory = false;
        return route.fulfill({
          status: 409,
          json: { code: 'DIRECTORY_CONFLICT', message: '目录冲突，请确认后重试' },
        });
      }
      directories.push({
        id: 'dir-1',
        knowledgeBaseId: 'journey',
        parentId: null,
        name: '产品说明',
        path: '/产品说明',
        sortNo: 1,
        status: 'ACTIVE',
      });
      return ok(directories[0]);
    }
    if (key === 'GET /api/knowledge/bases/journey/documents') {
      expect(url.searchParams.get('page')).toBe('1');
      const items =
        document &&
        (!url.searchParams.get('directoryId') ||
          url.searchParams.get('directoryId') === document.directoryId)
          ? [document]
          : [];
      return ok({ items, total: items.length, page: 1, pageSize: 10 });
    }
    if (key === 'GET /api/knowledge/bases/journey/index-releases') return ok(releases);
    if (key === 'POST /api/knowledge/bases/journey/documents/upload') {
      expect(base?.status).toBe('ACTIVE');
      expect(directories).toHaveLength(1);
      expect(uploadCount++).toBe(0);
      const form = await new Response(new Uint8Array(request.postDataBuffer()!), {
        headers: { 'Content-Type': request.headers()['content-type']! },
      }).formData();
      expect([...form.keys()].sort()).toEqual(['directoryId', 'evidenceMode', 'file']);
      expect(form.get('directoryId')).toBe('dir-1');
      expect(form.get('evidenceMode')).toBe('EXTRACTIVE_NARRATIVE');
      const file = form.get('file') as File;
      expect(file.name).toBe(fileName);
      expect(await file.text()).toBe(fileText);
      document = {
        id: 'doc-1',
        knowledgeBaseId: 'journey',
        directoryId: 'dir-1',
        title: fileName,
        documentCode: 'DOC-001',
        sourceType: 'UPLOAD',
        status: 'PROCESSING',
        currentPublishedVersionId: null,
        versions: [
          {
            id: 'version-1',
            documentId: 'doc-1',
            versionNo: 1,
            fileId: fileName,
            fileSha256: 'offline-sha256',
            contentType: 'text/markdown',
            evidenceMode: 'EXTRACTIVE_NARRATIVE',
            changeSummary: '初始上传',
            effectiveDate: null,
            status: 'PROCESSING',
            errorCode: null,
            errorMessage: null,
            createdAt: now,
            processingTasks: [
              {
                id: 'task-1',
                documentVersionId: 'version-1',
                agentTaskId: null,
                stage: 'INDEX',
                status: 'RUNNING',
                attemptNo: 1,
                progressPercent: 30,
                errorCode: null,
                errorMessage: null,
                startedAt: now,
                finishedAt: null,
              },
            ],
          },
        ],
      };
      batch = {
        id: 'batch-1',
        knowledgeBaseId: 'journey',
        importMode: 'SINGLE',
        totalCount: 1,
        succeededCount: 0,
        failedCount: 0,
        status: 'RUNNING',
        createdAt: now,
        finishedAt: null,
        items: [
          {
            id: 'item-1',
            batchId: 'batch-1',
            fileId: fileName,
            documentId: 'doc-1',
            documentVersionId: 'version-1',
            status: 'RUNNING',
            errorCode: null,
            errorMessage: null,
            retryOfItemId: null,
          },
        ],
      };
      return ok(batch);
    }
    if (key === 'GET /api/knowledge/imports/batch-1') {
      expect(batch).toBeDefined();
      if (++batchReads >= 2) {
        batch!.status = 'SUCCEEDED';
        batch!.succeededCount = 1;
        batch!.finishedAt = now;
        batch!.items[0]!.status = 'SUCCEEDED';
        document!.status = 'READY';
        const version = document!.versions[0]!;
        version.status = 'READY';
        Object.assign(version.processingTasks[0]!, {
          status: 'SUCCEEDED',
          progressPercent: 100,
          finishedAt: now,
        });
      }
      return ok(batch);
    }
    if (key === 'GET /api/knowledge/documents/doc-1') {
      expect(document).toBeDefined();
      return ok(document);
    }
    if (key === 'GET /api/knowledge/processing-tasks/task-1')
      return ok(document!.versions[0]!.processingTasks[0]);
    if (key === 'POST /api/knowledge/document-versions/version-1/publish') {
      expect(request.postData()).toBeNull();
      expect(document!.versions[0]!.status).toBe('READY');
      document!.status = 'PUBLISHED';
      document!.versions[0]!.status = 'PUBLISHED';
      document!.currentPublishedVersionId = 'version-1';
      releases.push(release('release-1', 1), release('release-2', 2));
      base!.currentIndexReleaseId = 'release-2';
      return ok(releases[1]);
    }
    if (key === 'POST /api/knowledge/index-releases/release-1/rollback') {
      expect(request.postData()).toBeNull();
      expect(base!.currentIndexReleaseId).toBe('release-2');
      base!.currentIndexReleaseId = 'release-1';
      return ok(releases[0]);
    }
    unexpected.push(key);
    await route.abort('blockedbyclient');
  });
  return { requests, unexpected, getBase: () => base, getDocument: () => document };
}
