const statusLabels: Record<string, string> = {
  ACTIVE: '已启用',
  DRAFT: '草稿',
  VALIDATED: '已验证',
  RELEASED: '已发布',
  RETIRED: '已退役',
  PENDING: '待发布',
  RUNNING: '运行中',
  QUEUED: '排队中',
  SUCCEEDED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  ARCHIVED: '已归档',
};

export const aiStatusLabel = (value: string) => statusLabels[value] ?? value;
export const promptScopeLabel = (value: string) =>
  ({ SHARED: '共享', PRIVATE: 'Agent 专属' })[value] ?? value;

export const agentTypeLabel = (value: string) =>
  ({ CUSTOMER_SERVICE: '智能客服', OPERATIONS: '运营助手', HR: '招聘助手' })[value] ?? value;

export const answerModeLabel = (value: string) =>
  ({
    COMPANY_KNOWLEDGE: '公司知识',
    MIXED: '公司知识与通用建议',
    GENERAL_ADVICE: '通用建议',
    INSUFFICIENT_EVIDENCE: '证据不足',
  })[value] ?? value;
