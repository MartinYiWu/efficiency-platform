import type {
  CitationV1,
  CitationV2,
  DeliverableSetDto,
  DeliverySetV2ViewModel,
  OperationDeliverableV2,
  OperationDeliverableViewModel,
  OperationDeliveryViewModel,
} from './model';

function toSafeHttpsHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' &&
      parsed.hostname.length > 0 &&
      parsed.username.length === 0 &&
      parsed.password.length === 0
      ? url
      : null;
  } catch {
    return null;
  }
}

function mapLegacyCitation(citation: CitationV1) {
  return { ...citation, href: toSafeHttpsHref(citation.url) };
}

function mapDeliverable(deliverable: OperationDeliverableV2): OperationDeliverableViewModel {
  const base = {
    id: deliverable.deliverable_id,
    platform: deliverable.platform,
    title: deliverable.title,
    lead: deliverable.lead,
    citations: deliverable.citations,
    copyText: deliverable.copy_text,
    warnings: deliverable.warnings,
  };
  switch (deliverable.deliverable_kind) {
    case 'ranked_digest':
      return { ...base, kind: 'ranked_digest', content: deliverable.content };
    case 'platform_content':
      return { ...base, kind: 'platform_content', content: deliverable.content };
    case 'action_plan':
      return { ...base, kind: 'action_plan', content: deliverable.content };
    case 'diagnosis':
      return { ...base, kind: 'diagnosis', content: deliverable.content };
    case 'retrospective':
      return { ...base, kind: 'retrospective', content: deliverable.content };
  }
}

function collectCitations(deliverables: OperationDeliverableV2[]): Record<string, CitationV2> {
  return deliverables.reduce<Record<string, CitationV2>>((citationsById, deliverable) => {
    deliverable.citations.forEach((citation) => {
      citationsById[citation.citation_id] = citation;
    });
    return citationsById;
  }, {});
}

function mapV2(
  dto: Extract<DeliverableSetDto, { contract_version: 'deliverable-set/2' }>,
): DeliverySetV2ViewModel {
  const deliverableIds = new Set(dto.deliverables.map((deliverable) => deliverable.deliverable_id));
  return {
    kind: 'v2',
    runId: dto.run_id,
    intentRevision: dto.intent_revision,
    summary: dto.summary,
    deliverables: dto.deliverables.map(mapDeliverable),
    nextActions: dto.next_actions.filter(
      (action) =>
        action.action_type === 'show_sources' ||
        (action.target_deliverable_id !== null && deliverableIds.has(action.target_deliverable_id)),
    ),
    provenance: dto.provenance,
    degraded: dto.degraded,
    warnings: dto.warnings,
    citationsById: collectCitations(dto.deliverables),
  };
}

export function mapDeliverableSet(dto: DeliverableSetDto): OperationDeliveryViewModel {
  if (dto.contract_version === 'deliverable-set/1') {
    return {
      kind: 'legacy',
      summary: dto.summary,
      degraded: dto.degraded,
      deliverables: dto.deliverables.map((deliverable) => ({
        ...deliverable,
        citations: deliverable.citations.map(mapLegacyCitation),
      })),
    };
  }
  return mapV2(dto);
}
