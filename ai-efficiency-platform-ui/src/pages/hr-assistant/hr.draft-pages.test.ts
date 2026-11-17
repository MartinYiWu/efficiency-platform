import { render, screen, fireEvent, cleanup } from '@testing-library/vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, it, expect, vi } from 'vitest';
import type { Component } from 'vue';
import PositionWeightsPage from './positions/PositionWeightsPage.vue';
import PositionHardConditionsPage from './positions/PositionHardConditionsPage.vue';
import PositionWizardPage from './positions/PositionWizardPage.vue';
const draft = {
  positionId: 'p1',
  name: 'Java岗位',
  family: 'TECHNOLOGY',
  departmentId: 'd1',
  level: 'P6',
  jdText: '',
  lastStep: 'BASIC',
  scoring: null,
  draftScoring: null,
  hardConditions: [],
  criteria: [],
  version: 2,
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
async function show(component: Component) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: draft }))),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component }],
  });
  await router.push('/?positionId=p1');
  render(component, { global: { plugins: [router] } });
  await screen.findByText(/草稿已保存/);
}
it('恢复真实权重草稿，合计不为100时禁止下一步', async () => {
  await show(PositionWeightsPage);
  expect(screen.getByRole('button', { name: /下一步/ })).toBeEnabled();
  await fireEvent.update(screen.getByLabelText('技能匹配权重'), '30');
  await fireEvent.blur(screen.getByLabelText('技能匹配权重'));
  expect(screen.getByRole('button', { name: /下一步/ })).toBeDisabled();
});
it('真实草稿硬性条件可新增删除，不预置示例规则', async () => {
  await show(PositionHardConditionsPage);
  expect(screen.queryByRole('button', { name: '删除条件-1' })).not.toBeInTheDocument();
  await fireEvent.click(screen.getByRole('button', { name: '＋ 添加硬性条件' }));
  expect(screen.getByRole('button', { name: '删除条件-1' })).toBeInTheDocument();
  await fireEvent.click(screen.getByRole('button', { name: '删除条件-1' }));
  expect(screen.queryByRole('button', { name: '删除条件-1' })).not.toBeInTheDocument();
});
it('真实草稿软性要求新增完整锚点，不混入固定技能', async () => {
  await show(PositionWizardPage);
  await fireEvent.click(screen.getByRole('button', { name: '＋ 添加评分要求' }));
  expect(screen.getByText('显著满足锚点')).toBeInTheDocument();
  await fireEvent.click(screen.getByRole('button', { name: '删除要求-1' }));
  expect(screen.queryByText('显著满足锚点')).not.toBeInTheDocument();
});

it('语言硬条件显式配置等级序号与整数容差并保留四档锚点', async () => {
  const input = {
    ...draft,
    hardConditions: [
      {
        id: 'language',
        type: 'LANGUAGE',
        label: '英语',
        expected: 'CEFR B2',
        unit: 'CEFR',
        threshold: 4,
        tolerance: 1,
        overridable: true,
        values: ['B2'],
        matchMode: 'ALL',
      },
    ],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: input }))),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: PositionHardConditionsPage }],
  });
  await router.push('/?positionId=p1');
  render(PositionHardConditionsPage, { global: { plugins: [router] } });
  await screen.findByText('考试体系（如CEFR / JLPT）');
  expect(screen.getByText('标准值')).toBeInTheDocument();
  const threshold = screen.getByLabelText('目标等级序号（按已发布等级体系配置）');
  expect(threshold).toHaveValue('4');
  const tolerance = screen.getByLabelText('允许容差等级');
  expect(tolerance).toHaveAttribute('aria-valuemax', '1');
  await fireEvent.update(threshold, '3');
  await fireEvent.blur(threshold);
  expect(tolerance).toHaveAttribute('aria-valuemax', '0');
  await fireEvent.update(threshold, '4');
  await fireEvent.blur(threshold);
  expect(tolerance).toHaveAttribute('aria-valuemax', '1');
  expect(screen.getByText(/不得由界面或模型猜测体系换算/)).toBeInTheDocument();
  await fireEvent.click(screen.getByRole('button', { name: '配置语言四档锚点' }));
  expect(screen.getByText('部分满足 / 容差档')).toBeInTheDocument();
});
