import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type {
  DeliveryProvenanceViewModel,
  RankedDigestViewModel,
} from '../../entities/operation-deliverable';
import { RankedDigestView } from './RankedDigestView';

function rankedDigestViewModel(): RankedDigestViewModel {
  return {
    kind: 'ranked_digest',
    id: 'digest-1',
    platform: '通用',
    title: '今日 AI 热点',
    lead: '已核验的行业动态。',
    copyText: '1. Meta 发布新模型\n发布了新模型。',
    warnings: [],
    citations: [
      {
        citation_id: 'citation-1',
        url: 'https://news.example.test/announcement',
        title: '官方公告',
        source: '示例来源',
        published_at: '2026-09-17T00:00:00Z',
        source_type: 'official',
        source_tier: 'primary',
        verification_status: 'verified',
        supports_item_ids: ['item-1'],
        independent_source_group: 'example',
      },
    ],
    content: {
      kind: 'ranked_digest',
      selection_summary: '按重要性与新近性排序。',
      ranking_basis: 'mixed',
      items: [
        {
          item_id: 'item-1',
          rank: 1,
          title: 'Meta 发布新模型',
          occurred_at: '2026-09-17T00:00:00Z',
          summary: '发布了可用于内容生产的新模型。',
          why_it_matters: '会影响团队对内容生产效率的评估。',
          content_angles: ['从生产效率角度解读'],
          metrics: ['推理速度提升'],
          source_refs: ['citation-1'],
          confidence: 'high',
          verification_status: 'verified',
        },
      ],
    },
  };
}

function provenance(): DeliveryProvenanceViewModel {
  return {
    source_count: 1,
    verified_source_count: 1,
    candidate_count: 3,
    merged_event_count: 2,
    retained_count: 1,
    eliminated_count: 1,
    collection_window_start: '2026-09-16T00:00:00Z',
    collection_window_end: '2026-09-17T00:00:00Z',
    ranking_basis: 'mixed',
  };
}

describe('RankedDigestView', () => {
  it('先显示连续编号热点与运营价值，来源默认折叠', async () => {
    const user = userEvent.setup();
    const viewModel = rankedDigestViewModel();
    viewModel.content.items.push({
      ...viewModel.content.items[0],
      item_id: 'item-2',
      rank: 9,
      title: '第二条热点',
    });
    render(<RankedDigestView deliverable={viewModel} provenance={provenance()} />);

    expect(screen.getByRole('list', { name: '热点榜' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '1. Meta 发布新模型' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '2. 第二条热点' })).toBeVisible();
    expect(screen.getAllByText('为什么值得关注')).toHaveLength(2);
    expect(screen.getAllByText('高可信度')).toHaveLength(2);
    expect(screen.queryByRole('link', { name: '官方公告' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /来源与采集依据（1 条）/ }));
    expect(screen.getByRole('link', { name: '官方公告' })).toHaveAttribute(
      'href',
      'https://news.example.test/announcement',
    );
    expect(screen.getByText('候选 3 条')).toBeVisible();
    expect(screen.getByText('保留 1 条')).toBeVisible();
  });

  it('视觉上只保留标题中的连续编号，不再额外显示有序列表标记', () => {
    const viewModel = rankedDigestViewModel();
    viewModel.content.items.push({
      ...viewModel.content.items[0],
      item_id: 'item-2',
      title: '第二条热点',
    });
    render(<RankedDigestView deliverable={viewModel} provenance={provenance()} />);

    const rankedList = screen.getByRole('list', { name: '热点榜' });
    expect(window.getComputedStyle(rankedList).listStyleType).toBe('none');
    expect(screen.getByRole('heading', { name: '1. Meta 发布新模型' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '2. 第二条热点' })).toBeVisible();
  });

  it('只将 Agent 提供的 copyText 交给复制回调', async () => {
    const onCopyItem = vi.fn();
    const user = userEvent.setup();
    render(
      <RankedDigestView
        deliverable={rankedDigestViewModel()}
        provenance={provenance()}
        onCopyItem={onCopyItem}
      />,
    );

    await user.click(screen.getByRole('button', { name: '复制热点榜' }));
    expect(onCopyItem).toHaveBeenCalledWith('1. Meta 发布新模型\n发布了新模型。');
  });

  it('仅为无凭据 HTTPS 来源提供外链，仍保留其可读来源名称', async () => {
    const user = userEvent.setup();
    const viewModel = rankedDigestViewModel();
    viewModel.citations[0] = {
      ...viewModel.citations[0],
      url: 'https://editor:secret@example.test/announcement',
      title: '受限来源',
    };
    render(<RankedDigestView deliverable={viewModel} provenance={provenance()} />);

    await user.click(screen.getByRole('button', { name: /来源与采集依据（1 条）/ }));
    expect(screen.getByText('受限来源')).toBeVisible();
    expect(screen.queryByRole('link', { name: '受限来源' })).not.toBeInTheDocument();
  });
});
