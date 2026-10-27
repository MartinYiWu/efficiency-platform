import { expect, it } from 'vitest';

import { agentTypeLabel, aiStatusLabel, answerModeLabel } from './presentation';

it('renders common AI management statuses in Chinese', () => {
  expect(aiStatusLabel('ACTIVE')).toBe('已启用');
  expect(aiStatusLabel('VALIDATED')).toBe('已验证');
  expect(aiStatusLabel('SUCCEEDED')).toBe('已完成');
});

it('renders agent and answer mode names in Chinese', () => {
  expect(agentTypeLabel('CUSTOMER_SERVICE')).toBe('智能客服');
  expect(answerModeLabel('COMPANY_KNOWLEDGE')).toBe('公司知识');
  expect(answerModeLabel('INSUFFICIENT_EVIDENCE')).toBe('证据不足');
});

it('labels the formal CLARIFY answer mode in AI management', () => {
  expect(answerModeLabel('CLARIFY')).toBe('需要补充信息');
});
