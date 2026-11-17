import type { InjectionKey } from 'vue';

export type TopAgent = 'operations' | 'customer-service' | 'hr';
export type MemoryField = 'response.language' | 'response.detail_level' | 'response.format';
export interface MemoryScope {
  topAgent: TopAgent;
  sessionId?: string;
}
export interface MemoryVersion {
  versionId: string;
  value: string;
  status: string;
  sourceType: 'USER_PREFERENCE_DECISION';
  sourceRef: string;
  expiresAt: string | null;
}
export interface MemoryPreference extends MemoryVersion {
  id: string;
  topAgent: TopAgent;
  fieldKey: MemoryField;
  revision: number;
}
export interface MemoryCommand {
  fieldKey: MemoryField;
  value: string;
  expectedRevision: number;
  idempotencyKey: string;
}
export interface MemoryPage {
  items: MemoryPreference[];
  total: number;
  page: number;
  pageSize: number;
}
export interface MemoryDetail {
  preference: MemoryPreference;
  history: MemoryVersion[];
}
export interface MemoryApi {
  list(scope: MemoryScope, page?: number, signal?: AbortSignal): Promise<MemoryPage>;
  detail(id: string, scope: MemoryScope, signal?: AbortSignal): Promise<MemoryDetail>;
  save(scope: MemoryScope, command: MemoryCommand, signal?: AbortSignal): Promise<MemoryPreference>;
  correct(
    id: string,
    scope: MemoryScope,
    command: MemoryCommand,
    signal?: AbortSignal,
  ): Promise<MemoryPreference>;
}
export interface MemoryDeletionTask {
  jobId: string;
  itemId: string;
  status: string;
  jobStatus: string;
  revision: number;
  deletionEpoch: number;
  suppressionId: string;
  suppressionRevision: number;
  requiredTargets: number;
  completedTargets: number;
}
export interface ForgetMemoryCommand {
  itemId: string;
  expectedRevision: number;
  idempotencyKey: string;
  mode: 'FORGET_AND_SUPPRESS';
}
export interface MemoryReauthorizationCommand extends MemoryCommand {
  itemId: string;
  expected_suppression_revision: number;
  confirmation: 'ALLOW_REMEMBER';
}
export interface MemoryDeletionApi {
  forget(
    scope: MemoryScope,
    command: ForgetMemoryCommand,
    signal?: AbortSignal,
  ): Promise<MemoryDeletionTask>;
  deletion(jobId: string, scope: MemoryScope, signal?: AbortSignal): Promise<MemoryDeletionTask>;
  reauthorize(
    suppressionId: string,
    scope: MemoryScope,
    command: MemoryReauthorizationCommand,
    signal?: AbortSignal,
  ): Promise<MemoryPreference>;
}
export const memoryAccessTokenKey: InjectionKey<() => string | undefined> =
  Symbol('memoryAccessToken');
export const agentOptions = [
  { value: 'operations', label: '内容运营助手' },
  { value: 'customer-service', label: '智能客服' },
  { value: 'hr', label: '人事助手' },
];
export const fieldLabels: Record<MemoryField, string> = {
  'response.language': '回复语言',
  'response.detail_level': '详细程度',
  'response.format': '回复格式',
};
export const valueLabels: Record<string, string> = {
  'zh-CN': '简体中文',
  'en-US': '英语',
  concise: '简洁',
  standard: '标准',
  detailed: '详细',
  prose: '段落',
  bullets: '要点',
  table: '表格',
};
