import { describe, expect, it } from 'vitest';
import { mapDeliverableSet } from './mappers';
import { parseDeliverableSet } from './schemas';

const deliverableSetV1 = () => ({
  contract_version: 'deliverable-set/1',
  summary: '已生成 1 份平台内容。',
  degraded: false,
  deliverables: [
    {
      contract_version: 'deliverable/1',
      platform: '小红书',
      title: 'AI 热点标题',
      body: '正文内容',
      hashtags: ['#AI'],
      format_notes: ['短段落'],
      citations: [{ url: 'https://example.test/source', title: '官方公告', source: '示例来源' }],
      warnings: [],
    },
  ],
});

const deliverableSetV2 = () => ({
  contract_version: 'deliverable-set/2',
  run_id: 'run-1',
  intent_revision: 0,
  summary: { message: '已核验 1 条行业动态。', result_count: 1, complete: true },
  deliverables: [
    {
      contract_version: 'deliverable/2',
      deliverable_id: 'digest-1',
      deliverable_kind: 'ranked_digest',
      platform: '通用',
      title: '今日 AI 热点',
      lead: '以下为已核验的行业动态。',
      citations: [
        {
          citation_id: 'citation-1',
          url: 'https://example.test/announcement',
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
      copy_text: '可复制正文',
      warnings: [],
      content: {
        kind: 'ranked_digest',
        selection_summary: '按重要性排序。',
        ranking_basis: 'importance',
        items: [
          {
            item_id: 'item-1',
            rank: 1,
            title: '示例模型发布',
            occurred_at: '2026-09-17T00:00:00Z',
            summary: '发布了新模型。',
            why_it_matters: '影响内容生产效率。',
            content_angles: ['行业解读'],
            metrics: ['性能提升'],
            source_refs: ['citation-1'],
            confidence: 'high',
            verification_status: 'verified',
          },
        ],
      },
    },
  ],
  next_actions: [],
  provenance: {
    source_count: 1,
    verified_source_count: 1,
    candidate_count: 1,
    merged_event_count: 1,
    retained_count: 1,
    eliminated_count: 0,
    collection_window_start: '2026-09-16T00:00:00Z',
    collection_window_end: '2026-09-17T00:00:00Z',
    ranking_basis: 'importance',
  },
  degraded: false,
  warnings: [],
});

describe('parseDeliverableSet', () => {
  it('按 contract_version 解析 V1 与 V2，不根据字段猜版本', () => {
    expect(parseDeliverableSet(deliverableSetV1())?.contract_version).toBe('deliverable-set/1');
    expect(parseDeliverableSet(deliverableSetV2())?.contract_version).toBe('deliverable-set/2');

    const withoutVersion = deliverableSetV2();
    delete (withoutVersion as { contract_version?: string }).contract_version;
    expect(parseDeliverableSet(withoutVersion)).toBeNull();
  });

  it('拒绝 V2 未知字段、未知 content.kind 和非 HTTPS 来源', () => {
    expect(parseDeliverableSet({ ...deliverableSetV2(), unexpected: true })).toBeNull();

    const unknownKind = deliverableSetV2();
    unknownKind.deliverables[0].content.kind = 'raw_html';
    expect(parseDeliverableSet(unknownKind)).toBeNull();

    const unsafeCitation = deliverableSetV2();
    unsafeCitation.deliverables[0].citations[0].url = 'javascript:alert(1)';
    expect(parseDeliverableSet(unsafeCitation)).toBeNull();
  });

  it('只接受无凭据且带 hostname 的 HTTPS V2 来源', () => {
    const credentialCitation = deliverableSetV2();
    credentialCitation.deliverables[0].citations[0].url =
      'https://editor:secret@example.test/announcement';
    expect(parseDeliverableSet(credentialCitation)).toBeNull();

    const safeBusinessCitation = deliverableSetV2();
    safeBusinessCitation.deliverables[0].citations[0].url =
      'https://news.example.test/announcement?category=ai';
    expect(parseDeliverableSet(safeBusinessCitation)?.contract_version).toBe('deliverable-set/2');
  });

  it('拒绝含 51 个顶层 intent_patch 键的 V2 后续动作', () => {
    const tooManyIntentKeys = {
      ...deliverableSetV2(),
      next_actions: [
        {
          action_id: 'action-1',
          action_type: 'rewrite_for_platform',
          label: '改写为小红书文案',
          target_deliverable_id: 'digest-1',
          target_item_ids: [],
          intent_patch: Object.fromEntries(
            Array.from({ length: 51 }, (_, index) => [`constraint_${index}`, index]),
          ),
          requires_user_input: false,
        },
      ],
    };

    expect(parseDeliverableSet(tooManyIntentKeys)).toBeNull();
  });

  it('只映射 Agent 交付的结构化事实，不从正文猜测热点或来源', () => {
    const dto = parseDeliverableSet(deliverableSetV2());
    if (!dto) throw new Error('fixture must satisfy the V2 contract');

    const viewModel = mapDeliverableSet(dto);
    expect(viewModel.kind).toBe('v2');
    if (viewModel.kind !== 'v2') throw new Error('fixture must map to V2');
    expect(viewModel.deliverables[0]?.kind).toBe('ranked_digest');
    expect(viewModel.citationsById['citation-1']?.title).toBe('官方公告');
    expect(viewModel.deliverables[0]?.copyText).toBe('可复制正文');
  });

  it('保留 V1 DTO 原始 URL，但仅为安全 URL 提供可点击 href', () => {
    const unsafeV1 = deliverableSetV1();
    unsafeV1.deliverables[0].citations[0].url = 'javascript:alert(1)';
    const unsafeDto = parseDeliverableSet(unsafeV1);
    if (!unsafeDto) throw new Error('V1 DTO must retain backwards-compatible source text');
    const unsafeViewModel = mapDeliverableSet(unsafeDto);
    if (unsafeViewModel.kind !== 'legacy') throw new Error('fixture must map to legacy view');
    expect(unsafeViewModel.deliverables[0]?.citations[0]).toMatchObject({
      url: 'javascript:alert(1)',
      href: null,
    });

    const safeDto = parseDeliverableSet(deliverableSetV1());
    if (!safeDto) throw new Error('fixture must satisfy the V1 contract');
    const safeViewModel = mapDeliverableSet(safeDto);
    if (safeViewModel.kind !== 'legacy') throw new Error('fixture must map to legacy view');
    expect(safeViewModel.deliverables[0]?.citations[0]?.href).toBe('https://example.test/source');
  });
});
