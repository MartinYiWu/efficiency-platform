import type { RouteRecordRaw } from 'vue-router';

export const routes: RouteRecordRaw[] = [
  {
    path: '/ai-center/memories',
    component: () => import('../../pages/agent-memory/MemoryCenterPage.vue'),
    meta: { title: '记忆中心' },
  },
  {
    path: '/ai-center/memories/:id',
    component: () => import('../../pages/agent-memory/MemoryDetailPage.vue'),
    meta: { title: '偏好详情' },
  },
  { path: '/', redirect: '/ai-assistants/hr/workbench' },
  {
    path: '/ai-assistants/operations/chat',
    component: () => import('../../pages/operations-assistant/chat/OperationsChatPage.vue'),
    meta: { title: 'OperationsChatPage' },
  },
  {
    path: '/ai-assistants/customer-service/chat',
    component: () => import('../../pages/customer-service/CustomerServiceChatPage.vue'),
    meta: { title: 'CustomerServiceChatPage' },
  },
  {
    path: '/knowledge-center/knowledge-bases',
    component: () => import('../../pages/knowledge-center/KnowledgeBaseListPage.vue'),
    meta: { title: 'KnowledgeBaseListPage' },
  },
  {
    path: '/knowledge-center/knowledge-bases/:baseId',
    component: () => import('../../pages/knowledge-center/KnowledgeBaseDetailPage.vue'),
    meta: { title: 'KnowledgeBaseDetailPage' },
  },
  {
    path: '/knowledge-center/knowledge-bases/:baseId/imports',
    component: () => import('../../pages/knowledge-center/KnowledgeImportPage.vue'),
    meta: { title: 'KnowledgeImportPage' },
  },
  {
    path: '/knowledge-center/documents/:documentId',
    component: () => import('../../pages/knowledge-center/KnowledgeDocumentPage.vue'),
    meta: { title: 'KnowledgeDocumentPage' },
  },
  {
    path: '/ai-center/agents',
    component: () => import('../../pages/ai-center/AgentListPage.vue'),
    meta: { title: 'AgentListPage' },
  },
  {
    path: '/ai-center/agents/:agentId',
    component: () => import('../../pages/ai-center/AgentDetailPage.vue'),
    meta: { title: 'AgentDetailPage' },
  },
  {
    path: '/ai-center/prompts',
    component: () => import('../../pages/ai-center/PromptManagementPage.vue'),
    meta: { title: 'PromptManagementPage' },
  },
  {
    path: '/ai-center/model-policies',
    component: () => import('../../pages/ai-center/ModelPolicyPage.vue'),
    meta: { title: 'ModelPolicyPage' },
  },
  {
    path: '/ai-center/rag-policies',
    component: () => import('../../pages/ai-center/RagPolicyPage.vue'),
    meta: { title: 'RagPolicyPage' },
  },
  {
    path: '/ai-center/rag-debug',
    component: () => import('../../pages/ai-center/RagDebugPage.vue'),
    meta: { title: 'RagDebugPage' },
  },
  {
    path: '/ai-center/rag-evaluations',
    component: () => import('../../pages/ai-center/RagEvaluationListPage.vue'),
    meta: { title: 'RagEvaluationListPage' },
  },
  {
    path: '/ai-center/rag-evaluations/:datasetId',
    component: () => import('../../pages/ai-center/RagEvaluationDatasetPage.vue'),
    meta: { title: 'RagEvaluationDatasetPage' },
  },
  {
    path: '/ai-center/rag-evaluations/runs/:runId',
    component: () => import('../../pages/ai-center/RagEvaluationRunPage.vue'),
    meta: { title: 'RagEvaluationRunPage' },
  },
  {
    path: '/ai-center/runs',
    component: () => import('../../pages/ai-center/RunListPage.vue'),
    meta: { title: 'RunListPage' },
  },
  {
    path: '/ai-center/runs/:runId',
    component: () => import('../../pages/ai-center/RunReplayPage.vue'),
    meta: { title: 'RunReplayPage' },
  },
  {
    path: '/ai-center/feedback',
    component: () => import('../../pages/ai-center/FeedbackPage.vue'),
    meta: { title: 'FeedbackPage' },
  },
  {
    path: '/ai-assistants/hr/chat',
    component: () => import('../../pages/hr-assistant/chat/HrChatPage.vue'),
    meta: { title: 'HrChatPage' },
  },
  { path: '/ai-assistants/hr/resumes', redirect: '/ai-assistants/hr/resumes/upload' },
  {
    path: '/ai-assistants/hr/resumes/upload',
    component: () => import('../../pages/hr-assistant/resumes/ResumeUploadPage.vue'),
    meta: { title: 'ResumeUploadPage' },
  },
  {
    path: '/ai-assistants/hr/resumes/batches/:batchId',
    component: () => import('../../pages/hr-assistant/resumes/ResumeProgressPage.vue'),
    meta: { title: 'ResumeProgressPage' },
  },
  {
    path: '/ai-assistants/hr/resumes/candidates/:candidateId/confirm',
    component: () => import('../../pages/hr-assistant/resumes/ResumeCorrectionPage.vue'),
    meta: { title: 'ResumeCorrectionPage' },
  },
  {
    path: '/ai-assistants/hr/settings/audit',
    component: () => import('../../pages/hr-assistant/settings/AuditPage.vue'),
    meta: { title: 'AuditPage' },
  },
  {
    path: '/ai-assistants/hr/settings/synonyms',
    alias: '/ai-assistants/hr/settings/global',
    component: () => import('../../pages/hr-assistant/settings/SkillSynonymPage.vue'),
    meta: { title: 'SkillSynonymPage' },
  },
  {
    path: '/ai-assistants/hr/talent',
    component: () => import('../../pages/hr-assistant/talent/TalentSearchPage.vue'),
    meta: { title: 'TalentSearchPage' },
  },
  {
    path: '/ai-assistants/hr/talent/:candidateId',
    component: () => import('../../pages/hr-assistant/talent/CandidateProfilePage.vue'),
    meta: { title: 'CandidateProfilePage' },
  },
  {
    path: '/ai-assistants/hr/matching',
    component: () => import('../../pages/hr-assistant/matching/MatchResultsPage.vue'),
    meta: { title: 'MatchResultsPage' },
  },
  {
    path: '/ai-assistants/hr/matching/:candidateId',
    component: () => import('../../pages/hr-assistant/matching/MatchDetailPage.vue'),
    meta: { title: 'MatchDetailPage' },
  },
  {
    path: '/ai-assistants/hr/matching/filtered',
    component: () => import('../../pages/hr-assistant/matching/FilteredResumesPage.vue'),
    meta: { title: 'FilteredResumesPage' },
  },
  {
    path: '/ai-assistants/hr/interviews/assigned/:assignmentId',
    component: () => import('../../pages/hr-assistant/interviews/InterviewAssignedPage.vue'),
    meta: { title: '面试官提纲' },
  },
  {
    path: '/ai-assistants/hr/interviews/guide',
    component: () => import('../../pages/hr-assistant/interviews/InterviewGuidePreviewPage.vue'),
    meta: { title: 'InterviewGuidePreviewPage' },
  },
  {
    path: '/ai-assistants/hr/interviews/questions',
    component: () => import('../../pages/hr-assistant/interviews/InterviewQuestionSetPage.vue'),
    meta: { title: 'InterviewQuestionSetPage' },
  },
  {
    path: '/ai-assistants/hr/interviews/generate',
    component: () => import('../../pages/hr-assistant/interviews/InterviewGeneratePage.vue'),
    meta: { title: 'InterviewGeneratePage' },
  },
  {
    path: '/ai-assistants/hr/interviews',
    component: () => import('../../pages/hr-assistant/module-entry/HrModuleEntryPage.vue'),
    meta: { title: 'HrModuleEntryPage' },
    props: {
      title: '面试准备',
      description: '配置、编辑与导出结构化面试指南。',
      nextPage: 'PAGE-16 面试题生成配置',
    },
  },
  {
    path: '/ai-assistants/hr/settings',
    component: () => import('../../pages/hr-assistant/settings/SkillSynonymPage.vue'),
    meta: { title: 'SkillSynonymPage' },
  },
  {
    path: '/ai-assistants/hr/workbench',
    component: () => import('../../pages/hr-assistant/workbench/HrWorkbenchPage.vue'),
    meta: { title: 'HrWorkbenchPage' },
  },
  {
    path: '/ai-assistants/hr/component-states',
    component: () => import('../../pages/hr-assistant/component-states/HrComponentStatesPage.vue'),
    meta: { title: 'HrComponentStatesPage' },
  },
  {
    path: '/ai-assistants/hr/positions',
    component: () => import('../../pages/hr-assistant/positions/PositionListPage.vue'),
    meta: { title: 'PositionListPage' },
  },
  {
    path: '/ai-assistants/hr/positions/templates',
    component: () => import('../../pages/hr-assistant/positions/PositionTemplateLibraryPage.vue'),
    meta: { title: 'PositionTemplateLibraryPage' },
  },
  {
    path: '/ai-assistants/hr/positions/:positionId',
    component: () => import('../../pages/hr-assistant/positions/PositionDetailPage.vue'),
    meta: { title: 'PositionDetailPage' },
  },
  {
    path: '/ai-assistants/hr/positions/new',
    component: () => import('../../pages/hr-assistant/positions/PositionBasicPage.vue'),
    meta: { title: 'PositionBasicPage' },
  },
  {
    path: '/ai-assistants/hr/positions/new/soft-requirements',
    component: () => import('../../pages/hr-assistant/positions/PositionWizardPage.vue'),
    meta: { title: 'PositionWizardPage' },
  },
  {
    path: '/ai-assistants/hr/positions/new/hard-conditions',
    component: () => import('../../pages/hr-assistant/positions/PositionHardConditionsPage.vue'),
    meta: { title: 'PositionHardConditionsPage' },
  },
  {
    path: '/ai-assistants/hr/positions/new/preview',
    component: () => import('../../pages/hr-assistant/positions/PositionPreviewPage.vue'),
    meta: { title: 'PositionPreviewPage' },
  },
  {
    path: '/ai-assistants/hr/positions/new/weights',
    component: () => import('../../pages/hr-assistant/positions/PositionWeightsPage.vue'),
    meta: { title: 'PositionWeightsPage' },
  },
  {
    path: '/:pathMatch(.*)*',
    component: () => import('../../pages/not-found/NotFoundPage.vue'),
    meta: { title: 'NotFoundPage' },
  },
];
