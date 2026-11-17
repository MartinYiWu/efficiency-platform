import { afterEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import Antd from 'ant-design-vue';
import type {
  PlatformContentViewModel,
  RankedDigestViewModel,
} from '../../entities/operation-deliverable';
afterEach(() => vi.restoreAllMocks());
const common = {
  id: 'd1',
  platform: '小红书',
  title: '运营交付',
  lead: '导语',
  copyText: '只复制原文',
  warnings: [],
  citations: [],
};
it('平台正文保留安全Markdown、标签、格式说明并只复制原文', async () => {
  const { default: Page } = await import('./PlatformContentView.vue');
  const value: PlatformContentViewModel = {
    ...common,
    kind: 'platform_content',
    content: {
      kind: 'platform_content',
      body_markdown:
        '## 正文\n[安全](https://example.test) [危险](http://example.test)\n<script>bad()</script>',
      hashtags: ['AI'],
      format_notes: ['封面建议'],
    },
  };
  const wrapper = mount(Page, {
    props: { deliverable: value, provenance: null },
    global: { plugins: [Antd] },
  });
  expect(wrapper.find('script').exists()).toBe(false);
  expect(wrapper.find('a[href="https://example.test"]').attributes('rel')).toBe(
    'noopener noreferrer',
  );
  expect(wrapper.find('a[href="http://example.test"]').exists()).toBe(false);
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '复制全文')!
    .trigger('click');
  expect(wrapper.emitted('copyItem')?.[0]).toEqual(['只复制原文']);
  expect(wrapper.text()).toContain('封面建议');
  wrapper.unmount();
});
it('热点连续编号并折叠证据，过滤不安全来源外链', async () => {
  const { default: Page } = await import('./RankedDigestView.vue');
  const item = {
    item_id: 'i1',
    rank: 9,
    title: '热点',
    occurred_at: null,
    summary: '摘要',
    why_it_matters: '运营价值',
    content_angles: ['角度'],
    metrics: ['指标'],
    source_refs: ['c1'],
    confidence: 'high' as const,
    verification_status: 'verified' as const,
  };
  const value: RankedDigestViewModel = {
    ...common,
    kind: 'ranked_digest',
    citations: [
      {
        citation_id: 'c1',
        url: 'http://example.test',
        title: '受限来源',
        source: null,
        published_at: null,
        source_type: 'official',
        source_tier: 'primary',
        verification_status: 'verified',
        supports_item_ids: ['i1'],
        independent_source_group: 'g',
      },
    ],
    content: {
      kind: 'ranked_digest',
      selection_summary: '排序',
      ranking_basis: 'mixed',
      items: [item, { ...item, item_id: 'i2', title: '另一热点' }],
    },
  };
  const wrapper = mount(Page, {
    props: { deliverable: value, provenance: null },
    global: { plugins: [Antd] },
  });
  expect(wrapper.text()).toContain('1. 热点');
  expect(wrapper.text()).toContain('2. 另一热点');
  expect(wrapper.text()).not.toContain('受限来源');
  await wrapper.get('.ant-collapse-header').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('受限来源');
  expect(wrapper.find('a[href="http://example.test"]').exists()).toBe(false);
  wrapper.unmount();
});
it('后续动作仅六种允许类型，查看来源不提交隐藏补丁', async () => {
  const { default: Page } =
    await import('../../features/operation-next-action/OperationNextActions.vue');
  const action = {
    action_id: 'a1',
    action_type: 'show_sources' as const,
    label: '查看来源',
    target_deliverable_id: null,
    target_item_ids: [],
    intent_patch: { secret: '隐藏内容' },
    requires_user_input: false,
  };
  const wrapper = mount(Page, {
    props: { actions: [action], onShowSources: vi.fn() },
    global: { plugins: [Antd] },
  });
  await wrapper.get('button').trigger('click');
  expect(wrapper.emitted('submit')).toBeUndefined();
  expect(wrapper.text()).not.toContain('隐藏内容');
  wrapper.unmount();
});
it('成稿操作保留编码ID、复制、微信预览和下载', async () => {
  const { default: Page } =
    await import('../../features/operation-artifact/OperationArtifactActions.vue');
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('原文'));
  const writeText = vi.fn();
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  const wrapper = mount(Page, {
    props: {
      artifact: {
        artifactId: 'a/b',
        artifactType: 'platform_content',
        platform: 'wechat_official_account',
        version: 1,
        title: '标题',
        createdAt: '',
      },
      baseUrl: '',
    },
    global: { plugins: [Antd] },
  });
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '复制成稿')!
    .trigger('click');
  await flushPromises();
  expect(writeText).toHaveBeenCalledWith('原文');
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '微信预览')!
    .trigger('click');
  expect(open).toHaveBeenCalledWith(
    '/api/operations/artifacts/a%2Fb/wechat-html',
    '_blank',
    'noopener,noreferrer',
  );
  expect(wrapper.get('a').attributes('href')).toBe('/api/operations/artifacts/a%2Fb/download');
  wrapper.unmount();
});
