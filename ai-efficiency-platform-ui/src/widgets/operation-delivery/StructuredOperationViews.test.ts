import { expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import Antd from 'ant-design-vue';
import Structured from './StructuredOperationView.vue';
import Delivery from './OperationDelivery.vue';
import type {
  ActionPlanViewModel,
  DiagnosisViewModel,
  RetrospectiveViewModel,
  DeliverableSetDto,
  NextActionV2,
} from '../../entities/operation-deliverable';
const common = {
  id: 'd1',
  platform: '通用',
  title: '交付标题',
  lead: '导语',
  copyText: '原文',
  warnings: [],
  citations: [],
};
it('行动计划完整保留目标受众、阶段、指标与前提', () => {
  const value: ActionPlanViewModel = {
    ...common,
    kind: 'action_plan',
    content: {
      kind: 'action_plan',
      goal: '目标',
      audience: '受众',
      phases: [{ phase_id: 'p1', title: '阶段一', actions: ['行动'], metrics: ['阶段指标值'] }],
      metrics: ['整体指标值'],
      assumptions: ['前提'],
    },
  };
  const wrapper = mount(Structured, { props: { deliverable: value }, global: { plugins: [Antd] } });
  for (const text of ['目标', '受众', '阶段一', '行动', '阶段指标值', '整体指标值', '前提'])
    expect(wrapper.text()).toContain(text);
  wrapper.unmount();
});
it('诊断按优先级展示证据建议和数据缺口', () => {
  const value: DiagnosisViewModel = {
    ...common,
    kind: 'diagnosis',
    content: {
      kind: 'diagnosis',
      findings: [
        {
          finding_id: 'low',
          title: '低问题',
          evidence: [],
          priority: 'low',
          recommendation: '低建议',
        },
        {
          finding_id: 'high',
          title: '高问题',
          evidence: ['证据值'],
          priority: 'high',
          recommendation: '高建议',
        },
      ],
      data_gaps: ['缺少数据'],
    },
  };
  const wrapper = mount(Structured, { props: { deliverable: value }, global: { plugins: [Antd] } });
  expect(wrapper.findAll('h3').map((node) => node.text())).toEqual(['高问题', '低问题']);
  expect(wrapper.text()).toContain('证据值');
  expect(wrapper.text()).toContain('高建议');
  expect(wrapper.text()).toContain('缺少数据');
  expect(wrapper.text()).toContain('未提供');
  wrapper.unmount();
});
it('复盘保留目标结果差距原因下一步五区块', () => {
  const value: RetrospectiveViewModel = {
    ...common,
    kind: 'retrospective',
    content: {
      kind: 'retrospective',
      objectives: ['目标值'],
      outcomes: ['结果值'],
      gaps: ['差距值'],
      causes: ['原因值'],
      next_steps: ['下一步值'],
    },
  };
  const wrapper = mount(Structured, { props: { deliverable: value }, global: { plugins: [Antd] } });
  expect(wrapper.findAll('h3').map((node) => node.text())).toEqual([
    '目标',
    '结果',
    '差距',
    '原因',
    '下一步',
  ]);
  wrapper.unmount();
});
it('V1保留正文来源标签格式说明警告', async () => {
  const value: DeliverableSetDto = {
    contract_version: 'deliverable-set/1',
    summary: '旧版摘要',
    degraded: true,
    deliverables: [
      {
        contract_version: 'deliverable/1',
        platform: '小红书',
        title: '旧版标题',
        body: '## 正文',
        hashtags: ['AI'],
        format_notes: ['格式值'],
        citations: [{ url: 'https://example.test', title: '来源值', source: null }],
        warnings: ['警告值'],
      },
    ],
  };
  const wrapper = mount(Delivery, { props: { value }, global: { plugins: [Antd] } });
  expect(wrapper.text()).toContain('旧版摘要');
  expect(wrapper.text()).toContain('警告值');
  expect(wrapper.text()).toContain('格式值');
  await wrapper.get('.ant-collapse-header').trigger('click');
  await flushPromises();
  expect(wrapper.get('a').attributes('href')).toBe('https://example.test');
  wrapper.unmount();
});
it('V3仅复制交付copy_text，按最高版本匹配成稿并保留警告', async () => {
  const value: DeliverableSetDto = {
    contract_version: 'deliverable-set/3',
    run_id: 'r1',
    intent_revision: 1,
    summary: { message: '新交付', result_count: 1, complete: true },
    degraded: false,
    warnings: [{ code: 'w1', message: '全局警告' }],
    deliverables: [
      {
        contract_version: 'deliverable/3',
        deliverable_id: 'd1',
        scenario: 'multi_platform_content',
        platform: 'wechat_official_account',
        title: '新版标题',
        copy_text: '精确原文',
        content: {
          kind: 'platform_content',
          platform: 'wechat_official_account',
          title: '新版标题',
          introduction: '导语',
          sections: [],
          closing: '结尾',
          hashtags: [],
        },
        warnings: [{ code: 'w2', message: '交付警告' }],
      },
    ],
  };
  const writeText = vi.fn();
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  const artifact = {
    artifactId: 'old',
    artifactType: 'platform_content',
    platform: 'wechat_official_account',
    version: 1,
    title: '标题',
    createdAt: '',
  };
  const wrapper = mount(Delivery, {
    props: { value, artifacts: [artifact, { ...artifact, artifactId: 'latest', version: 2 }] },
    global: { plugins: [Antd] },
  });
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '复制结果')!
    .trigger('click');
  await flushPromises();
  expect(writeText).toHaveBeenCalledWith('精确原文');
  expect(wrapper.text()).toContain('已复制');
  expect(wrapper.text()).toContain('全局警告');
  expect(wrapper.text()).toContain('交付警告');
  expect(wrapper.get('a[download]').attributes('href')).toContain('/latest/download');
  wrapper.unmount();
});
it('后续动作白名单与来源缺回调时禁用', async () => {
  const { default: Actions } =
    await import('../../features/operation-next-action/OperationNextActions.vue');
  const types = [
    'rewrite_for_platform',
    'expand_item',
    'generate_script',
    'replace_candidates',
    'show_sources',
    'refine_constraints',
    'server_command',
  ];
  const actions = types.map((type, i) => ({
    action_id: String(i),
    action_type: type,
    label: type,
    target_deliverable_id: 'd1',
    target_item_ids: [],
    intent_patch: {},
    requires_user_input: false,
  })) as NextActionV2[];
  const wrapper = mount(Actions, { props: { actions }, global: { plugins: [Antd] } });
  expect(wrapper.findAll('button')).toHaveLength(6);
  expect(wrapper.findAll('button')[4]!.attributes('disabled')).toBeDefined();
  await wrapper.findAll('button')[0]!.trigger('click');
  expect(wrapper.emitted('submit')?.[0]).toEqual(['rewrite_for_platform']);
  wrapper.unmount();
});

it('V2聚合保留来源动作与下一轮可见消息，并展示复制失败', async () => {
  const value: DeliverableSetDto = {
    contract_version: 'deliverable-set/2',
    run_id: 'r1',
    intent_revision: 0,
    summary: { message: 'V2摘要', result_count: 1, complete: true },
    degraded: false,
    warnings: [],
    provenance: null,
    deliverables: [
      {
        contract_version: 'deliverable/2',
        deliverable_id: 'd1',
        deliverable_kind: 'platform_content',
        platform: '小红书',
        title: '平台稿',
        lead: '导语',
        citations: [
          {
            citation_id: 'c1',
            url: 'https://example.test',
            title: '来源名称',
            source: null,
            published_at: null,
            source_type: 'official',
            source_tier: 'primary',
            verification_status: 'verified',
            supports_item_ids: [],
            independent_source_group: null,
          },
        ],
        copy_text: '稿件原文',
        warnings: [],
        content: {
          kind: 'platform_content',
          body_markdown: '平台正文',
          hashtags: [],
          format_notes: [],
        },
      },
    ],
    next_actions: [
      {
        action_id: 'a1',
        action_type: 'show_sources',
        label: '查看来源',
        target_deliverable_id: null,
        target_item_ids: [],
        intent_patch: {},
        requires_user_input: false,
      },
      {
        action_id: 'a2',
        action_type: 'rewrite_for_platform',
        label: '改写为公众号',
        target_deliverable_id: 'd1',
        target_item_ids: [],
        intent_patch: { internal: '不可见' },
        requires_user_input: false,
      },
    ],
  };
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
  const wrapper = mount(Delivery, { props: { value }, global: { plugins: [Antd] } });
  expect(wrapper.text()).not.toContain('来源名称');
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '查看来源')!
    .trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('来源名称');
  expect(wrapper.emitted('submitNextAction')).toBeUndefined();
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '改写为公众号')!
    .trigger('click');
  expect(wrapper.emitted('submitNextAction')?.[0]).toEqual(['改写为公众号']);
  expect(wrapper.text()).not.toContain('不可见');
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '复制全文')!
    .trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('复制失败，请手动复制');
  wrapper.unmount();
});
