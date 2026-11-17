import { expect, type Page } from '@playwright/test';
const now = '2026-11-03T00:00:00Z';
const audit = { createdBy: 'offline', createdAt: now, updatedBy: 'offline', updatedAt: now };
export const draftInput = {
  semanticVersion: '1.0.1',
  graphKey: 'customer-service',
  graphVersion: '2',
  changeSummary: '离线验收版本',
};
export const importedCase = {
  caseNo: '001',
  question: '报销期限？',
  expectedAnswerMode: 'COMPANY_KNOWLEDGE',
  expectedFacts: ['保留事实', '移除事实'],
  expectedFactAlternatives: { 保留事实: ['保留同义'], 移除事实: ['旧同义'] },
  prohibitedFacts: [],
  expectedDocumentTitles: ['报销制度'],
  expectedDocumentVersionIds: ['doc-v2'],
  minCitationCount: 1,
  tags: ['offline'],
  enabled: true,
};
export const frozenInput = {
  datasetId: 'dataset',
  agentKey: 'customer-service',
  agentVersionId: 'av',
  ragPolicyVersionId: 'rag',
  knowledgeBindings: [{ knowledgeBaseId: 'kb', indexReleaseId: 'index' }],
};
export async function managementFixture(page: Page) {
  const definition = {
    id: 'a',
    agentKey: 'customer-service',
    name: '离线客服 Agent',
    description: '事务验收',
    agentType: 'CUSTOMER_SERVICE',
    status: 'ACTIVE',
    ...audit,
  };
  const versions = [
    {
      id: 'av',
      agentDefinitionId: 'a',
      semanticVersion: '1.0.0',
      graphKey: 'customer-service',
      graphVersion: '1',
      status: 'PUBLISHED',
      changeSummary: null as string | null,
      createdBy: 'offline',
      createdAt: now,
      publishedAt: now as string | null,
    },
  ];
  const prompt = {
    id: 'p',
    promptKey: 'answer',
    scope: 'AGENT',
    ownerAgentDefinitionId: 'a',
    name: '离线回答模板',
    description: null,
    stageKey: 'answer',
    status: 'ACTIVE',
    ...audit,
  };
  const promptVersion = {
    id: 'pv',
    promptDefinitionId: 'p',
    semanticVersion: 'draft',
    status: 'DRAFT',
    checksum: null,
    changeSummary: null,
    createdBy: 'offline',
    createdAt: now,
    publishedAt: null,
  };
  const messages = ['SYSTEM', 'USER', 'ASSISTANT'].map((role, i) => ({
    id: `m${i}`,
    promptVersionId: 'pv',
    ordinal: i + 1,
    role,
    messageKey: role.toLowerCase(),
    contentTemplate: `${role} 原始 {{question}}`,
    contentFormat: 'TEXT',
    trustedInstruction: role === 'SYSTEM',
    checksum: 'offline',
  }));
  const variables = [
    {
      id: 'var',
      promptMessageTemplateId: 'm1',
      variableName: 'question',
      valueType: 'STRING',
      valueSource: 'INPUT',
      required: true,
      sensitive: false,
      maxLength: 1000,
      allowUntrustedContent: true,
    },
  ];
  type Dataset = {
    id: string;
    name: string;
    description: string;
    agentKey: string;
    status: string;
    caseCount: number;
    createdAt: string;
    updatedAt: string;
  };
  const state = {
    datasets: [] as Dataset[],
    cases: [] as Array<typeof importedCase & { id: string; datasetId: string }>,
    writes: [] as { method: string; path: string; body: unknown }[],
    rejectRun: false,
    rejectVersion: false,
    runReads: 0,
    run: null as Record<string, unknown> | null,
    messages,
    variables,
  };
  await page.route('**/api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname,
      method = req.method();
    const body = method === 'GET' ? undefined : req.postDataJSON();
    const send = (data: unknown) => route.fulfill({ json: { code: 'SUCCESS', data } });
    const reject = () =>
      route.fulfill({
        status: 402,
        json: { code: 'PAID_BUDGET_DENIED', message: '离线预算拒绝：未授权' },
      });
    if (method !== 'GET') state.writes.push({ method, path, body });
    if (method === 'GET' && path === '/api/aihub/agents/a') return send({ definition, versions });
    if (method === 'GET' && path === '/api/aihub/agents') return send([definition]);
    if (method === 'POST' && path === '/api/aihub/agents/a/versions') {
      expect(body).toEqual(draftInput);
      if (state.rejectVersion) return reject();
      const version = { ...versions[0]!, ...body, id: 'draft', status: 'DRAFT', publishedAt: null };
      versions.push(version);
      return send(version);
    }
    if (method === 'POST' && path === '/api/aihub/agents/versions/draft/transition') {
      expect(body).toEqual({ status: 'READY' });
      const version = versions.find((v) => v.id === 'draft')!;
      expect(version.status).toBe('DRAFT');
      version.status = 'READY';
      return send(version);
    }
    if (method === 'GET' && path === '/api/aihub/prompts') return send([prompt]);
    if (method === 'POST' && path === '/api/aihub/prompts/p/versions') {
      expect(body).toEqual({
        semanticVersion: expect.stringMatching(/^draft-/),
        changeSummary: '后台编辑草稿',
      });
      return send(promptVersion);
    }
    if (method === 'GET' && path === '/api/aihub/prompts/versions/pv')
      return send({ definition: prompt, version: promptVersion, messages, variables });
    if (method === 'PUT' && path === '/api/aihub/prompts/versions/pv/content') {
      expect(body).toEqual({
        messages: messages.map(
          ({ ordinal, role, messageKey, contentTemplate, trustedInstruction }) => ({
            ordinal,
            role,
            messageKey,
            contentTemplate: role === 'USER' ? 'USER 已编辑 {{question}}' : contentTemplate,
            trustedInstruction,
          }),
        ),
        variables: [
          {
            messageKey: 'user',
            variableName: 'question',
            valueType: 'STRING',
            valueSource: 'INPUT',
            required: true,
            sensitive: false,
            maxLength: 1000,
            allowUntrustedContent: true,
          },
        ],
      });
      messages.forEach((m) => {
        m.contentTemplate = body.messages.find(
          (v: { role: string }) => v.role === m.role,
        ).contentTemplate;
      });
      return send(promptVersion);
    }
    const base = '/api/aihub/rag-evaluations';
    if (path === `${base}/datasets` && method === 'GET') return send(state.datasets);
    if (path === `${base}/datasets` && method === 'POST') {
      expect(body).toEqual({
        name: '离线事务数据集',
        description: '有状态模拟',
        agentKey: 'customer-service',
        status: 'DRAFT',
      });
      const dataset = { ...body, id: 'dataset', caseCount: 0, createdAt: now, updatedAt: now };
      state.datasets.push(dataset);
      return send(dataset);
    }
    if (path === `${base}/datasets/dataset` && method === 'GET') {
      expect(state.datasets).toHaveLength(1);
      return send({
        dataset: state.datasets[0],
        cases: state.cases,
        runs: state.run ? [state.run] : [],
      });
    }
    if (path === `${base}/datasets/dataset/cases/import` && method === 'POST') {
      expect(body).toEqual([importedCase]);
      state.cases.push({ ...body[0], id: 'case', datasetId: 'dataset' });
      state.datasets[0]!.caseCount = 1;
      return send({ createdCount: 1, updatedCount: 0, totalCount: 1 });
    }
    if (path === `${base}/datasets/dataset/cases/case` && method === 'PUT') {
      expect(body).toEqual({
        ...importedCase,
        expectedFacts: ['保留事实', '新增事实'],
        expectedFactAlternatives: { 保留事实: ['保留同义'] },
      });
      Object.assign(state.cases[0]!, body);
      return send(state.cases[0]);
    }
    if (path === '/api/aihub/agents/customer-service/releases' && method === 'GET') {
      expect(url.search).toBe('?environment=dev');
      const release = {
        id: 'release',
        agentDefinitionId: 'a',
        agentVersionId: 'av',
        environment: 'dev',
        releaseStatus: 'ACTIVE',
        releaseSnapshotId: 'snap',
        releasedBy: 'offline',
        releasedAt: now,
        rolledBackFromReleaseId: null,
        createdAt: now,
      };
      return send([
        release,
        { ...release, id: 'retired', agentVersionId: 'retired', releaseStatus: 'RETIRED' },
      ]);
    }
    if (path === '/api/aihub/policies' && method === 'GET') {
      expect(url.search).toBe('?agentId=a');
      const policy = {
        id: 'rag',
        ownerAgentDefinitionId: 'a',
        policyKey: 'offline-rag',
        semanticVersion: '1',
        rewriteQueryLimit: 1,
        vectorTopK: 10,
        ftsTopK: 10,
        fusionTopK: 10,
        rerankTopK: 5,
        contextTokenLimit: 1000,
        citationLimit: 3,
        status: 'PUBLISHED',
        checksum: null,
        createdBy: 'offline',
        createdAt: now,
        publishedAt: now,
      };
      return send({
        modelPolicies: [],
        ragPolicies: [policy, { ...policy, id: 'draft-rag', status: 'DRAFT' }],
      });
    }
    if (path === '/api/knowledge/bases' && method === 'GET')
      return send({
        items: [
          {
            id: 'kb',
            code: 'policy',
            name: '离线制度库',
            description: null,
            knowledgeType: 'TECHNICAL_DOCUMENTATION',
            visibilityScope: 'COMPANY_WIDE',
            status: 'ACTIVE',
            currentIndexReleaseId: 'index',
            createdAt: now,
            updatedAt: now,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 100,
      });
    if (path === '/api/knowledge/bases/kb/index-releases' && method === 'GET')
      return send([
        {
          id: 'index',
          knowledgeBaseId: 'kb',
          releaseNo: 1,
          status: 'PUBLISHED',
          documentCount: 1,
          chunkCount: 1,
          embeddingModel: 'offline',
          embeddingDimension: 3,
          checksum: null,
          previousReleaseId: null,
          createdAt: now,
          publishedAt: now,
        },
      ]);
    if (path === `${base}/runs` && method === 'POST') {
      expect(body).toEqual(frozenInput);
      if (state.rejectRun) return reject();
      state.run = {
        ...body,
        id: 'run',
        status: 'PENDING',
        totalCount: 1,
        passedCount: 0,
        failedCount: 0,
        metrics: null,
        failureCode: null,
        failureMessage: null,
        createdAt: now,
        startedAt: null,
        finishedAt: null,
      };
      return send(state.run);
    }
    if (path === `${base}/runs/run` && method === 'GET') {
      expect(state.run).not.toBeNull();
      state.runReads++;
      const done = state.runReads > 1;
      Object.assign(state.run!, {
        status: done ? 'SUCCEEDED' : 'RUNNING',
        passedCount: done ? 1 : 0,
        startedAt: now,
        finishedAt: done ? now : null,
      });
      return send({
        run: state.run,
        cases: state.cases,
        results: done
          ? [
              {
                id: 'result',
                runId: 'run',
                caseId: 'case',
                debugRunId: 'offline-debug',
                executionStatus: 'SUCCEEDED',
                passed: true,
                latencyMs: 12,
                answerMode: 'COMPANY_KNOWLEDGE',
                answerMarkdown: '**离线模拟回答**',
                citations: [
                  {
                    citation_no: 1,
                    knowledge_base_id: 'kb',
                    document_id: 'doc',
                    document_version_id: 'doc-v2',
                    index_release_id: 'index',
                    chunk_id: 'chunk',
                    document_title: '报销制度',
                    version_no: 2,
                    section_path: null,
                    page_no: null,
                    quoted_text: '离线冻结引文',
                    content_hash: 'offline',
                    parent_id: null,
                    citation_type: null,
                    original_spans: null,
                  },
                ],
                metrics: null,
                errorCode: null,
                errorMessage: null,
                createdAt: now,
              },
            ]
          : [],
      });
    }
    await route.fallback();
  });
  return state;
}
