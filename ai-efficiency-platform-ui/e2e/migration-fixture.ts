import { hrFixtureResponse } from './hr-empty-fixture';
import type { Page } from '@playwright/test';
const now = '2026-11-03T00:00:00Z';
const agent = {
  id: 'a',
  agentKey: 'customer-service',
  name: '证据客服',
  description: '公司知识问答',
  agentType: 'CUSTOMER_SERVICE',
  status: 'ACTIVE',
  createdBy: '1',
  createdAt: now,
  updatedBy: '1',
  updatedAt: now,
};
const agentVersion = {
  id: 'av',
  agentDefinitionId: 'a',
  semanticVersion: '1.0.0',
  graphKey: 'customer-service',
  graphVersion: '1',
  status: 'PUBLISHED',
  changeSummary: '正式版本',
  createdBy: '1',
  createdAt: now,
  publishedAt: now,
};
const release = {
  id: 'rel',
  agentDefinitionId: 'a',
  agentVersionId: 'av',
  environment: 'dev',
  releaseStatus: 'ACTIVE',
  releaseSnapshotId: 'snap',
  releasedBy: '1',
  releasedAt: now,
  rolledBackFromReleaseId: null,
  createdAt: now,
};
const base = {
  id: 'kb',
  code: 'company-policy',
  name: '公司制度知识库',
  description: '集中管理制度、流程与技术资料',
  knowledgeType: 'TECHNICAL_DOCUMENTATION',
  visibilityScope: 'COMPANY_WIDE',
  status: 'ACTIVE',
  currentIndexReleaseId: 'index',
  createdAt: now,
  updatedAt: now,
};
const task = {
  id: 'task',
  documentVersionId: 'v',
  agentTaskId: null,
  stage: 'PARSE',
  status: 'SUCCEEDED',
  attemptNo: 1,
  progressPercent: 100,
  errorCode: null,
  errorMessage: null,
  startedAt: now,
  finishedAt: now,
};
const version = {
  id: 'v',
  documentId: 'd',
  versionNo: 1,
  fileId: 'file',
  fileSha256: 'hash',
  contentType: 'text/plain',
  changeSummary: '首版制度',
  effectiveDate: '2026-11-03',
  status: 'READY',
  errorCode: null,
  errorMessage: null,
  createdAt: now,
  processingTasks: [task],
  evidenceMode: 'FULL_ONLY',
};
const document = {
  id: 'd',
  knowledgeBaseId: 'kb',
  directoryId: 'dir',
  title: '报销制度技术指南',
  documentCode: 'TECH-1',
  sourceType: 'UPLOAD',
  status: 'ACTIVE',
  currentPublishedVersionId: 'v',
  versions: [version],
};
const index = {
  id: 'index',
  knowledgeBaseId: 'kb',
  releaseNo: 1,
  status: 'PUBLISHED',
  documentCount: 1,
  chunkCount: 5,
  embeddingModel: 'offline-fixture',
  embeddingDimension: 3,
  checksum: null,
  previousReleaseId: null,
  createdAt: now,
  publishedAt: now,
};
const directory = {
  id: 'dir',
  knowledgeBaseId: 'kb',
  parentId: null,
  name: '公司资料',
  path: '/公司资料',
  sortNo: 1,
  status: 'ACTIVE',
};
const prompt = {
  id: 'prompt',
  promptKey: 'answer',
  scope: 'AGENT',
  ownerAgentDefinitionId: 'a',
  name: '正式回答模板',
  description: '受控指令模板',
  stageKey: 'answer',
  status: 'ACTIVE',
  createdBy: '1',
  createdAt: now,
  updatedBy: '1',
  updatedAt: now,
};
const modelPolicy = {
  id: 'mp',
  ownerAgentDefinitionId: 'a',
  policyKey: 'model-policy',
  semanticVersion: '1',
  provider: 'offline',
  modelName: 'fixture-model',
  temperature: 0.2,
  topP: 1,
  maxInputTokens: 64000,
  maxOutputTokens: 4000,
  connectTimeoutMs: 10000,
  readTimeoutMs: 60000,
  maxRetries: 0,
  status: 'PUBLISHED',
  checksum: null,
  createdBy: '1',
  createdAt: now,
  publishedAt: now,
};
const ragPolicy = {
  id: 'rp',
  ownerAgentDefinitionId: 'a',
  policyKey: 'evidence-policy',
  semanticVersion: '1',
  rewriteQueryLimit: 3,
  vectorTopK: 10,
  ftsTopK: 10,
  fusionTopK: 10,
  rerankTopK: 5,
  contextTokenLimit: 60000,
  citationLimit: 5,
  status: 'PUBLISHED',
  checksum: null,
  createdBy: '1',
  createdAt: now,
  publishedAt: now,
};
const run = {
  id: 'r',
  conversationId: 'c',
  tenantId: 't',
  userMessageId: 'q',
  agentRunId: 'ar',
  agentReleaseId: 'rel',
  status: 'SUCCEEDED',
  answerMode: 'COMPANY_KNOWLEDGE',
  lastEventSequence: 1,
  failureCode: null,
  failureMessage: null,
  startedAt: now,
  finishedAt: now,
  createdAt: now,
  updatedAt: now,
};
const message = {
  id: 'answer',
  conversationId: 'c',
  tenantId: 't',
  role: 'ASSISTANT',
  content: '依据制度提供准确回答。',
  status: 'COMPLETED',
  answerMode: 'COMPANY_KNOWLEDGE',
  runId: 'r',
  clientRequestId: null,
  createdAt: now,
};
const feedback = {
  id: 'f',
  conversationId: 'c',
  messageId: 'answer',
  runId: 'r',
  tenantId: 't',
  userId: '1',
  rating: 'POSITIVE',
  reasonCode: null,
  comment: '证据清晰',
  createdAt: now,
  updatedAt: now,
};
const dataset = {
  id: 'ds',
  name: '制度问答验收集',
  description: '离线契约数据',
  agentKey: 'customer-service',
  status: 'ACTIVE',
  caseCount: 1,
  createdAt: now,
  updatedAt: now,
};
const evaluationCase = {
  id: 'case',
  datasetId: 'ds',
  caseNo: 'C001',
  question: '如何办理报销？',
  expectedAnswerMode: 'COMPANY_KNOWLEDGE',
  expectedFacts: ['需提供票据'],
  prohibitedFacts: [],
  expectedDocumentTitles: ['制度指南'],
  expectedDocumentVersionIds: ['v'],
  minCitationCount: 1,
  tags: ['制度'],
  enabled: true,
};
const evaluationRun = {
  id: 'er',
  datasetId: 'ds',
  agentKey: 'customer-service',
  agentVersionId: 'av',
  ragPolicyVersionId: 'rp',
  knowledgeBindings: [{ knowledgeBaseId: 'kb', indexReleaseId: 'index' }],
  status: 'SUCCEEDED',
  totalCount: 1,
  passedCount: 1,
  failedCount: 0,
  metrics: {
    executionSuccessRate: 1,
    answerModeAccuracy: 1,
    expectedFactRecall: 1,
    prohibitedFactRate: 0,
    sourceRecallAtK: 1,
    citationComplianceRate: 1,
    versionAccuracy: 1,
    casePassRate: 1,
    latencyP50Ms: 100,
    latencyP95Ms: 100,
  },
  failureCode: null,
  failureMessage: null,
  createdAt: now,
  startedAt: now,
  finishedAt: now,
};
const pageOf = (items: unknown[]) => ({ items, page: 1, pageSize: 10, total: items.length });
export async function installMigrationFixture(page: Page, baseURL: string) {
  const origin = new URL(baseURL).origin;
  const unknown: string[] = [];
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (url.origin !== origin) {
      unknown.push(`EXTERNAL ${request.resourceType()} ${url.origin}${path}`);
      await route.abort('blockedbyclient');
      return;
    }
    if (!/^\/(api|v1)(\/|$)/.test(path) && !['fetch', 'xhr'].includes(request.resourceType())) {
      await route.continue();
      return;
    }
    if (path.startsWith('/api/hr/')) {
      const data = hrFixtureResponse(path);
      const authorizedMissing = new Set([
        '/api/hr/positions/position-1/config-versions',
        '/api/hr/candidates/candidate-1/facts',
        '/api/hr/candidates/candidate-1',
        '/api/hr/resume-batches/batch-1',
      ]);
      if (data === undefined && !authorizedMissing.has(path))
        unknown.push(`${request.method()} ${path}`);
      await route.fulfill(
        data === undefined
          ? {
              status: 404,
              json: {
                code: authorizedMissing.has(path) ? 'HR_NOT_FOUND' : 'OFFLINE_FIXTURE_MISSING',
                message: authorizedMissing.has(path)
                  ? '离线未创建授权业务对象'
                  : 'OFFLINE_FIXTURE_MISSING',
              },
            }
          : { json: { code: 'SUCCESS', data } },
      );
      return;
    }
    const responses: Record<string, unknown> = {
      '/api/aihub/agents': [agent],
      '/api/aihub/agents/a': {
        definition: agent,
        versions: [agentVersion],
        evidenceBindings: [
          {
            sourceType: 'RELEASE',
            sourceId: 'rel',
            largeModelName: 'fixture-model',
            maxInputTokens: 64000,
            knowledgeBaseId: 'kb',
            boundIndexReleaseId: 'index',
            currentIndexReleaseId: 'index',
          },
        ],
      },
      '/api/aihub/agents/customer-service/releases': [release],
      '/api/aihub/policies': { modelPolicies: [modelPolicy], ragPolicies: [ragPolicy] },
      '/api/aihub/prompts': [prompt],
      '/api/aihub/runs': pageOf([run]),
      '/api/aihub/runs/r/replay': {
        run,
        question: { ...message, id: 'q', role: 'USER', content: '报销流程是什么？' },
        answer: message,
        stages: [
          {
            id: 's',
            runId: 'r',
            sequenceNo: 1,
            stage: 'retrieval',
            status: 'SUCCEEDED',
            publicSummary: '已检索制度',
            internalPayload: null,
            startedAt: now,
            finishedAt: now,
          },
        ],
        citations: [],
        feedback,
      },
      '/api/aihub/feedback': pageOf([feedback]),
      '/api/aihub/rag-evaluations/datasets': [dataset],
      '/api/aihub/rag-evaluations/datasets/ds': {
        dataset,
        cases: [evaluationCase],
        runs: [evaluationRun],
      },
      '/api/aihub/rag-evaluations/runs': [evaluationRun],
      '/api/aihub/rag-evaluations/runs/er': {
        run: evaluationRun,
        cases: [evaluationCase],
        results: [],
      },
      '/api/knowledge/bases': pageOf([base]),
      '/api/knowledge/bases/kb': base,
      '/api/knowledge/bases/kb/directories': [directory],
      '/api/knowledge/bases/kb/documents': pageOf([document]),
      '/api/knowledge/bases/kb/index-releases': [index],
      '/api/knowledge/documents/d': document,
      '/api/customer-service/conversations': pageOf([
        {
          id: 'c',
          tenantId: 't',
          userId: '1',
          title: '制度咨询历史',
          status: 'ACTIVE',
          lastMessageAt: now,
          createdAt: now,
          updatedAt: now,
        },
      ]),
      '/api/customer-service/conversations/c/messages': [{ message, citations: [] }],
      '/api/customer-service/runs/r/timeline': {
        runId: 'r',
        status: 'SUCCEEDED',
        lastEventSequence: 1,
        assistant: { message, citations: [] },
        steps: [],
      },
      '/api/operations/conversations': {
        conversationId: 'oc',
        title: '运营规划',
        status: 'active',
        createdAt: now,
      },
      '/api/operations/conversations/oc/artifacts': { conversationId: 'oc', artifacts: [] },
    };
    if (!(path in responses)) {
      unknown.push(`${request.method()} ${path}`);
      await route.fulfill({
        status: 501,
        json: { code: 'OFFLINE_FIXTURE_MISSING', message: `离线验收未配置请求：${path}` },
      });
      return;
    }
    await route.fulfill({
      json: { code: 'SUCCESS', message: '离线验收数据', data: responses[path] },
    });
  });
  return unknown;
}
