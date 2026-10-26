const knowledgeTypes: Record<string, string> = {
  COMPANY_POLICY: '公司制度',
  BUSINESS_PROCESS: '业务流程',
  PRODUCT_DOCUMENTATION: '产品文档',
  TECHNICAL_DOCUMENTATION: '技术文档',
};

const statuses: Record<string, string> = {
  DRAFT: '草稿',
  ACTIVE: '已启用',
  DISABLED: '已停用',
  ARCHIVED: '已归档',
  PROCESSING: '处理中',
  READY: '待发布',
  PUBLISHED: '已发布',
  RETIRED: '已退役',
  FAILED: '处理失败',
  QUEUED: '排队中',
  RUNNING: '运行中',
  SUCCEEDED: '已完成',
  PARTIAL_FAILED: '部分失败',
  CANCELLED: '已取消',
};

export const knowledgeTypeLabel = (value: string) => knowledgeTypes[value] ?? value;
export const knowledgeStatusLabel = (value: string) => statuses[value] ?? value;
export const visibilityScopeLabel = (value: string) =>
  value === 'COMPANY_WIDE' ? '全员可见' : value;
export const documentSourceLabel = (value: string) =>
  ({ UPLOAD: '单文件上传', BATCH_UPLOAD: '批量导入' })[value] ?? value;
