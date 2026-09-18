import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type {
  ActionPlanViewModel,
  DiagnosisViewModel,
  PlatformContentViewModel,
  RetrospectiveViewModel,
} from '../../entities/operation-deliverable';
import { PlatformContentView } from './PlatformContentView';
import { ActionPlanView, DiagnosisView, RetrospectiveView } from './StructuredOperationViews';

function platformContent(): PlatformContentViewModel {
  return {
    kind: 'platform_content',
    id: 'platform-1',
    platform: '小红书',
    title: '小红书发布稿',
    lead: '面向运营团队的正式文案。',
    copyText: '只允许复制这一段 Agent 原文。',
    warnings: [],
    citations: [],
    content: {
      kind: 'platform_content',
      body_markdown: '<script>alert(1)</script>\n## 正文\n[安全链接](https://example.test)',
      hashtags: ['AI运营', '内容策略'],
      format_notes: ['建议配一张封面图'],
    },
  };
}

function actionPlan(): ActionPlanViewModel {
  return {
    kind: 'action_plan',
    id: 'plan-1',
    platform: '通用',
    title: '七日行动计划',
    lead: '优先验证核心选题。',
    copyText: '行动计划原文',
    warnings: [],
    citations: [],
    content: {
      kind: 'action_plan',
      goal: '提升本周互动率',
      audience: '新关注的内容创作者',
      phases: [
        {
          phase_id: 'phase-1',
          title: '执行阶段一',
          actions: ['完成选题'],
          metrics: ['发布 3 篇'],
        },
      ],
      metrics: ['互动率'],
      assumptions: ['具备日常发布资源'],
    },
  };
}

function diagnosis(): DiagnosisViewModel {
  return {
    kind: 'diagnosis',
    id: 'diagnosis-1',
    platform: '通用',
    title: '运营诊断',
    lead: '先处理高优先级问题。',
    copyText: '诊断原文',
    warnings: [],
    citations: [],
    content: {
      kind: 'diagnosis',
      findings: [
        {
          finding_id: 'low',
          title: '低优先级问题',
          evidence: ['低优先级证据'],
          priority: 'low',
          recommendation: '低优先级建议',
        },
        {
          finding_id: 'high',
          title: '高优先级问题',
          evidence: ['高优先级证据'],
          priority: 'high',
          recommendation: '高优先级建议',
        },
      ],
      data_gaps: ['缺少转化漏斗数据'],
    },
  };
}

function retrospective(): RetrospectiveViewModel {
  return {
    kind: 'retrospective',
    id: 'retro-1',
    platform: '通用',
    title: '活动复盘',
    lead: '聚焦下一轮改进。',
    copyText: '复盘原文',
    warnings: [],
    citations: [],
    content: {
      kind: 'retrospective',
      objectives: ['扩大有效触达'],
      outcomes: ['新增 120 位关注者'],
      gaps: ['转化不足'],
      causes: ['首屏信息不够明确'],
      next_steps: ['重写首屏'],
    },
  };
}

describe('operation delivery structured views', () => {
  it('平台正文渲染 Markdown 但跳过原始 HTML，并只复制 Agent copyText', async () => {
    const onCopyItem = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <PlatformContentView
        deliverable={platformContent()}
        onCopyItem={onCopyItem}
        provenance={null}
      />,
    );

    expect(screen.getByRole('heading', { name: '正文' })).toBeVisible();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByRole('link', { name: '安全链接' })).toHaveAttribute('target', '_blank');

    await user.click(screen.getByRole('button', { name: '复制全文' }));
    expect(onCopyItem).toHaveBeenCalledWith('只允许复制这一段 Agent 原文。');
  });

  it('按 action_plan 的语义结构渲染执行阶段与指标', () => {
    render(<ActionPlanView deliverable={actionPlan()} />);

    expect(screen.getByRole('heading', { name: '执行阶段' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '执行阶段一' })).toBeVisible();
    expect(screen.getByText('发布 3 篇')).toBeVisible();
  });

  it('按 diagnosis 的优先级顺序渲染证据、判断、建议和数据缺口', () => {
    render(<DiagnosisView deliverable={diagnosis()} />);

    const findingHeadings = screen.getAllByRole('heading', { level: 3 });
    expect(findingHeadings.map((heading) => heading.textContent)).toEqual([
      '高优先级问题',
      '低优先级问题',
    ]);
    expect(screen.getByText('高优先级证据')).toBeVisible();
    expect(screen.getByText('高优先级建议')).toBeVisible();
    expect(screen.getByRole('heading', { name: '数据缺口' })).toBeVisible();
  });

  it('按 retrospective 的五个连续区块渲染复盘内容', () => {
    render(<RetrospectiveView deliverable={retrospective()} />);

    expect(screen.getByRole('heading', { name: '目标' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '结果' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '差距' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '原因' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '下一步' })).toBeVisible();
  });
});
